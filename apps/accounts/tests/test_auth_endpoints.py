"""Tests for authentication API endpoints."""

from unittest.mock import patch

import pytest
from django.conf import settings
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import OtpCode, User
from apps.accounts.tests.factories import UserFactory


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_otp_request_endpoint_success(api_client: APIClient) -> None:
    """POST /auth/otp/request sends SMS and returns 204."""
    with patch("apps.accounts.services.send_sms"):
        response = api_client.post(
            "/api/v1/auth/otp/request",
            {"phone": "+998900000001"},
            format="json",
        )
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert OtpCode.objects.filter(phone="+998900000001").exists()


@pytest.mark.django_db
def test_otp_request_endpoint_rate_limited(api_client: APIClient) -> None:
    """POST /auth/otp/request returns 429 when rate limit exceeded."""
    phone = "+998900000002"
    with patch("apps.accounts.services.send_sms"):
        for _ in range(3):
            res = api_client.post("/api/v1/auth/otp/request", {"phone": phone}, format="json")
            assert res.status_code == status.HTTP_204_NO_CONTENT

        res_blocked = api_client.post("/api/v1/auth/otp/request", {"phone": phone}, format="json")
        assert res_blocked.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert res_blocked.data["code"] == "otp_rate_limited"


@pytest.mark.django_db
def test_otp_request_endpoint_invalid_phone(api_client: APIClient) -> None:
    """POST /auth/otp/request returns 400 validation_error for malformed phone."""
    response = api_client.post(
        "/api/v1/auth/otp/request",
        {"phone": "invalid"},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "validation_error"


@pytest.mark.django_db
def test_otp_verify_endpoint_success(api_client: APIClient) -> None:
    """POST /auth/otp/verify with dev code returns 200 and tokens."""
    with patch.object(settings, "OTP_DEV_CODE", "000000"):
        response = api_client.post(
            "/api/v1/auth/otp/verify",
            {"phone": "+998900000001", "code": "000000"},
            format="json",
        )
    assert response.status_code == status.HTTP_200_OK
    assert "access" in response.data
    assert "refresh" in response.data
    assert response.data["is_new"] is True
    assert response.data["user"]["phone"] == "+998900000001"


@pytest.mark.django_db
def test_otp_verify_endpoint_blocked_user(api_client: APIClient) -> None:
    """POST /auth/otp/verify for blocked user returns 403 account_blocked."""
    UserFactory(phone="+998900000003", status=User.Status.BLOCKED)
    with patch.object(settings, "OTP_DEV_CODE", "000000"):
        response = api_client.post(
            "/api/v1/auth/otp/verify",
            {"phone": "+998900000003", "code": "000000"},
            format="json",
        )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "account_blocked"


@pytest.mark.django_db
def test_token_refresh_endpoint_success(api_client: APIClient) -> None:
    """POST /auth/token/refresh returns new access token."""
    user = UserFactory(phone="+998900000004")
    refresh = RefreshToken.for_user(user)

    response = api_client.post(
        "/api/v1/auth/token/refresh",
        {"refresh": str(refresh)},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    assert "access" in response.data


@pytest.mark.django_db
def test_otp_verify_endpoint_inactive_user(api_client: APIClient) -> None:
    """POST /auth/otp/verify for inactive user returns 403 account_blocked."""
    UserFactory(phone="+998900000099", is_active=False)
    with patch.object(settings, "OTP_DEV_CODE", "000000"):
        response = api_client.post(
            "/api/v1/auth/otp/verify",
            {"phone": "+998900000099", "code": "000000"},
            format="json",
        )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "account_blocked"


@pytest.mark.django_db
def test_token_refresh_endpoint_blocked_user(api_client: APIClient) -> None:
    """POST /auth/token/refresh for blocked user returns 401 account_blocked."""
    user = UserFactory(phone="+998900000006")
    refresh = RefreshToken.for_user(user)

    user.status = User.Status.BLOCKED
    user.save(update_fields=["status"])

    response = api_client.post(
        "/api/v1/auth/token/refresh",
        {"refresh": str(refresh)},
        format="json",
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["code"] == "account_blocked"


@pytest.mark.django_db
def test_token_refresh_endpoint_inactive_user(api_client: APIClient) -> None:
    """POST /auth/token/refresh for inactive user returns 401 account_blocked."""
    user = UserFactory(phone="+998900000007")
    refresh = RefreshToken.for_user(user)

    user.is_active = False
    user.save(update_fields=["is_active"])

    response = api_client.post(
        "/api/v1/auth/token/refresh",
        {"refresh": str(refresh)},
        format="json",
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["code"] == "account_blocked"


@pytest.mark.django_db
def test_logout_endpoint_blacklists_refresh_token(api_client: APIClient) -> None:
    """POST /auth/logout blacklists the token so subsequent refresh fails."""
    user = UserFactory(phone="+998900000005")
    refresh = RefreshToken.for_user(user)

    # Logout
    logout_res = api_client.post(
        "/api/v1/auth/logout",
        {"refresh": str(refresh)},
        format="json",
    )
    assert logout_res.status_code == status.HTTP_204_NO_CONTENT

    # Trying to use blacklisted refresh token to refresh access token must fail
    refresh_res = api_client.post(
        "/api/v1/auth/token/refresh",
        {"refresh": str(refresh)},
        format="json",
    )
    assert refresh_res.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_authenticated_request_with_token_blocked_user_rejected(api_client: APIClient) -> None:
    """Requests with access token of a blocked user are rejected with 401."""
    user = UserFactory(phone="+998900000008")
    refresh = RefreshToken.for_user(user)
    access_token = str(refresh.access_token)

    # Block user
    user.status = User.Status.BLOCKED
    user.save(update_fields=["status"])

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
    response = api_client.get("/api/v1/me")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["code"] == "account_blocked"

