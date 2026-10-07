"""Business logic services for accounts and authentication."""

import datetime
import hashlib
import hmac
import re
import secrets
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Company, Device, OtpCode, User
from apps.accounts.sms import send_sms
from apps.core.exceptions import ServiceError


def normalize_phone(phone: str) -> str:
    """Normalize and validate E.164 phone format (+ followed by 9-15 digits)."""
    cleaned = re.sub(r"[\s\-\(\)]", "", str(phone).strip())
    if not re.match(r"^\+[1-9]\d{8,14}$", cleaned):
        raise ServiceError(
            detail="Invalid phone number format. Must be E.164 (e.g. +998901234567).",
            code="validation_error",
            status_code=400,
        )
    return cleaned


def hash_otp_code(code: str) -> str:
    """Compute HMAC-SHA256 hex digest for an OTP code using SECRET_KEY."""
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        code.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def check_and_increment_otp_rate_limit(phone: str) -> None:
    """Rate limit OTP requests to max 3 per phone per 10 minutes."""
    cache_key = f"otp_rate_limit:{phone}"
    count = cache.get(cache_key, 0)
    if count >= 3:
        raise ServiceError(
            detail="Too many OTP requests. Please try again later.",
            code="otp_rate_limited",
            status_code=429,
        )

    if count == 0:
        cache.set(cache_key, 1, timeout=600)
    else:
        try:
            cache.incr(cache_key)
        except Exception:
            cache.set(cache_key, count + 1, timeout=600)


def request_otp(phone: str) -> None:
    """Request a 6-digit OTP code sent via SMS with rate limiting."""
    normalized_phone = normalize_phone(phone)
    check_and_increment_otp_rate_limit(normalized_phone)

    code = f"{secrets.randbelow(1_000_000):06d}"
    code_hash = hash_otp_code(code)
    expires_at = timezone.now() + datetime.timedelta(minutes=5)

    OtpCode.objects.create(
        phone=normalized_phone,
        code_hash=code_hash,
        expires_at=expires_at,
        attempts=0,
    )

    send_sms(normalized_phone, f"Your verification code is {code}")


def verify_otp(phone: str, code: str) -> dict[str, Any]:
    """Verify OTP code, create/load user, and issue JWT tokens."""
    normalized_phone = normalize_phone(phone)
    dev_code = getattr(settings, "OTP_DEV_CODE", "")
    is_dev_code = bool(dev_code and code == dev_code)

    otp = None
    if not is_dev_code:
        otp = (
            OtpCode.objects.filter(phone=normalized_phone, used_at__isnull=True)
            .order_by("-created_at")
            .first()
        )
        if not otp:
            raise ServiceError(
                detail="Invalid OTP code.",
                code="otp_invalid",
                status_code=400,
            )

        if otp.attempts >= 5:
            raise ServiceError(
                detail="Maximum OTP verification attempts exceeded.",
                code="otp_attempts_exceeded",
                status_code=400,
            )

        if otp.expires_at <= timezone.now():
            raise ServiceError(
                detail="OTP code has expired.",
                code="otp_expired",
                status_code=400,
            )

        expected_hash = hash_otp_code(code)
        if not hmac.compare_digest(otp.code_hash, expected_hash):
            otp.attempts += 1
            otp.save(update_fields=["attempts", "updated_at"])
            if otp.attempts >= 5:
                raise ServiceError(
                    detail="Maximum OTP verification attempts exceeded.",
                    code="otp_attempts_exceeded",
                    status_code=400,
                )
            raise ServiceError(
                detail="Invalid OTP code.",
                code="otp_invalid",
                status_code=400,
            )

    with transaction.atomic():
        if otp is not None:
            otp = (
                OtpCode.objects.select_for_update()
                .filter(id=otp.id)
                .first()
            )
            if otp:
                otp.used_at = timezone.now()
                otp.save(update_fields=["used_at", "updated_at"])

        user, is_new = User.objects.get_or_create(
            phone=normalized_phone,
            defaults={"status": User.Status.NEW},
        )
        if is_new:
            user.set_unusable_password()
            user.save(update_fields=["password", "updated_at"])

        if user.status == User.Status.BLOCKED:
            raise ServiceError(
                detail="User account is blocked.",
                code="account_blocked",
                status_code=403,
            )

        refresh = RefreshToken.for_user(user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "is_new": is_new,
            "user": user,
        }


def logout(refresh_token: str) -> None:
    """Blacklist the given refresh token."""
    try:
        token = RefreshToken(refresh_token)
        token.blacklist()
    except Exception as exc:
        raise ServiceError(
            detail="Invalid or expired refresh token.",
            code="validation_error",
            status_code=400,
        ) from exc


def update_profile(user: User, **data: Any) -> User:
    """Update user profile fields, ignoring phone and status modifications."""
    writable_fields = {"full_name", "role", "language", "avatar"}
    update_fields = []
    for field, value in data.items():
        if field in writable_fields:
            setattr(user, field, value)
            update_fields.append(field)
    if update_fields:
        update_fields.append("updated_at")
        user.save(update_fields=update_fields)
    return user


def upsert_company(user: User, data: dict[str, Any]) -> tuple[Company, bool]:
    """Create or update company associated with the user, ensuring unique TIN."""
    tin = data.get("tin")
    if tin:
        conflict = Company.objects.filter(tin=tin).exclude(owner=user).exists()
        if conflict:
            raise ServiceError(
                detail="Company with this TIN already exists.",
                code="conflict",
                status_code=409,
            )

    company, created = Company.objects.get_or_create(
        owner=user,
        defaults={
            "name": data.get("name", ""),
            "tin": tin,
            "address": data.get("address", ""),
        },
    )
    if not created:
        company.name = data.get("name", company.name)
        company.tin = tin
        company.address = data.get("address", company.address)
        company.save(update_fields=["name", "tin", "address", "updated_at"])

    return company, created


def register_device(user: User, fcm_token: str, platform: str) -> tuple[Device, bool]:
    """Register or update an FCM device token, moving it to current user."""
    with transaction.atomic():
        device, created = Device.objects.select_for_update().get_or_create(
            fcm_token=fcm_token,
            defaults={
                "user": user,
                "platform": platform,
                "last_seen_at": timezone.now(),
            },
        )
        if not created:
            device.user = user
            device.platform = platform
            device.last_seen_at = timezone.now()
            device.save(update_fields=["user", "platform", "last_seen_at", "updated_at"])
        return device, created


def delete_device(user: User, fcm_token: str) -> None:
    """Delete a registered device by its FCM token for the user."""
    Device.objects.filter(user=user, fcm_token=fcm_token).delete()


@transaction.atomic
def mark_verified(users) -> int:
    """Set status=verified for non-verified users and send account_verified notifications."""
    from apps.notifications.models import Notification
    from apps.notifications.services import notify

    targets = list(users.exclude(status=User.Status.VERIFIED))
    for user in targets:
        user.status = User.Status.VERIFIED
        user.save(update_fields=["status", "updated_at"])
        notify(user, Notification.Type.ACCOUNT_VERIFIED, {})
    return len(targets)
