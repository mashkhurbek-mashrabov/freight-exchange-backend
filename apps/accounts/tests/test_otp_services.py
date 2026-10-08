"""Tests for OTP authentication service logic."""

import datetime
from unittest.mock import patch

import pytest
from django.conf import settings
from django.utils import timezone

from apps.accounts.models import OtpCode, User
from apps.accounts.services import (
    hash_otp_code,
    request_otp,
    verify_otp,
)
from apps.accounts.tests.factories import OtpCodeFactory, UserFactory
from apps.core.exceptions import ServiceError


@pytest.mark.django_db
def test_request_otp_happy_path() -> None:
    """Verify request_otp creates an OtpCode record and sends SMS."""
    phone = "+998901234567"
    with patch("apps.accounts.services.send_sms") as mock_send_sms:
        request_otp(phone)
        assert mock_send_sms.called
        assert mock_send_sms.call_args[0][0] == phone
        assert "Your verification code is" in mock_send_sms.call_args[0][1]

    otp = OtpCode.objects.filter(phone=phone).first()
    assert otp is not None
    assert otp.attempts == 0
    assert otp.used_at is None
    assert otp.expires_at > timezone.now()


@pytest.mark.django_db
def test_request_otp_rate_limit() -> None:
    """Verify rate limit allows 3 requests and blocks the 4th with 429."""
    phone = "+998901112233"
    with patch("apps.accounts.services.send_sms"):
        request_otp(phone)
        request_otp(phone)
        request_otp(phone)

        with pytest.raises(ServiceError) as exc_info:
            request_otp(phone)

        assert exc_info.value.status_code == 429
        assert exc_info.value.code == "otp_rate_limited"


@pytest.mark.django_db
def test_request_otp_invalid_phone() -> None:
    """Verify invalid phone formats raise validation_error with 400."""
    with pytest.raises(ServiceError) as exc_info:
        request_otp("invalid-phone")
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "validation_error"


@pytest.mark.django_db
def test_verify_otp_happy_path_new_user() -> None:
    """Verify verifying OTP creates new user with unusable password and status=new."""
    phone = "+998909876543"
    code = "123456"
    OtpCodeFactory(
        phone=phone,
        code_hash=hash_otp_code(code),
        expires_at=timezone.now() + datetime.timedelta(minutes=5),
    )

    with patch.object(settings, "OTP_DEV_CODE", ""):
        result = verify_otp(phone=phone, code=code)

    assert result["is_new"] is True
    assert "access" in result
    assert "refresh" in result
    user = result["user"]
    assert user.phone == phone
    assert user.status == User.Status.NEW
    assert not user.has_usable_password()

    otp = OtpCode.objects.get(phone=phone)
    assert otp.used_at is not None


@pytest.mark.django_db
def test_verify_otp_happy_path_existing_user() -> None:
    """Verify verifying OTP for existing user returns is_new=False."""
    user = UserFactory(phone="+998901122334", status=User.Status.VERIFIED)
    code = "654321"
    OtpCodeFactory(
        phone=user.phone,
        code_hash=hash_otp_code(code),
        expires_at=timezone.now() + datetime.timedelta(minutes=5),
    )

    with patch.object(settings, "OTP_DEV_CODE", ""):
        result = verify_otp(phone=user.phone, code=code)

    assert result["is_new"] is False
    assert result["user"].id == user.id
    assert result["user"].status == User.Status.VERIFIED


@pytest.mark.django_db
def test_verify_otp_wrong_code() -> None:
    """Verify wrong OTP code increments attempts and raises otp_invalid."""
    phone = "+998903334455"
    OtpCodeFactory(
        phone=phone,
        code_hash=hash_otp_code("111111"),
        attempts=0,
    )

    with patch.object(settings, "OTP_DEV_CODE", ""):
        with pytest.raises(ServiceError) as exc_info:
            verify_otp(phone=phone, code="222222")

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "otp_invalid"

    otp = OtpCode.objects.get(phone=phone)
    assert otp.attempts == 1


@pytest.mark.django_db
def test_verify_otp_expired_code() -> None:
    """Verify expired OTP code raises otp_expired with 400."""
    phone = "+998904445566"
    OtpCodeFactory(
        phone=phone,
        code_hash=hash_otp_code("111111"),
        expires_at=timezone.now() - datetime.timedelta(minutes=1),
    )

    with patch.object(settings, "OTP_DEV_CODE", ""):
        with pytest.raises(ServiceError) as exc_info:
            verify_otp(phone=phone, code="111111")

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "otp_expired"


@pytest.mark.django_db
def test_verify_otp_attempts_limit() -> None:
    """Verify reaching 5 attempts raises otp_attempts_exceeded."""
    phone = "+998905556677"
    OtpCodeFactory(
        phone=phone,
        code_hash=hash_otp_code("111111"),
        attempts=4,
    )

    with patch.object(settings, "OTP_DEV_CODE", ""):
        with pytest.raises(ServiceError) as exc_info:
            verify_otp(phone=phone, code="000000")

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "otp_attempts_exceeded"

    otp = OtpCode.objects.get(phone=phone)
    assert otp.attempts == 5

    with patch.object(settings, "OTP_DEV_CODE", ""):
        with pytest.raises(ServiceError) as exc_info2:
            verify_otp(phone=phone, code="111111")

    assert exc_info2.value.status_code == 400
    assert exc_info2.value.code == "otp_attempts_exceeded"


@pytest.mark.django_db
def test_verify_otp_dev_code_accepted() -> None:
    """Verify dev code is accepted without requiring a stored OtpCode."""
    phone = "+998906667788"
    with patch.object(settings, "OTP_DEV_CODE", "000000"):
        result = verify_otp(phone=phone, code="000000")

    assert result["is_new"] is True
    assert result["user"].phone == phone
    assert OtpCode.objects.filter(phone=phone).count() == 0


@pytest.mark.django_db
def test_verify_otp_blocked_user() -> None:
    """Verify blocked user attempting OTP verification raises account_blocked with 403."""
    phone = "+998907778899"
    UserFactory(phone=phone, status=User.Status.BLOCKED)

    with patch.object(settings, "OTP_DEV_CODE", "000000"):
        with pytest.raises(ServiceError) as exc_info:
            verify_otp(phone=phone, code="000000")

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "account_blocked"


@pytest.mark.django_db
def test_verify_otp_used_code_cannot_be_reused() -> None:
    """Verify code with used_at set cannot be verified again."""
    phone = "+998908889900"
    code = "777888"
    OtpCodeFactory(
        phone=phone,
        code_hash=hash_otp_code(code),
        used_at=timezone.now(),
    )

    with patch.object(settings, "OTP_DEV_CODE", ""):
        with pytest.raises(ServiceError) as exc_info:
            verify_otp(phone=phone, code=code)

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "otp_invalid"

