"""Serializers for accounts and authentication endpoints."""

import re
from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers, status
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.settings import api_settings as jwt_settings

from apps.accounts.models import Company, Device, User
from apps.core.validators import validate_image_file


class OtpRequestSerializer(serializers.Serializer):
    """Serializer for requesting an OTP code."""

    phone = serializers.CharField(
        max_length=20,
        help_text="Phone number in E.164 format (e.g. +998900000001).",
    )

    def validate_phone(self, value: str) -> str:
        cleaned = re.sub(r"[\s\-\(\)]", "", str(value).strip())
        if not re.match(r"^\+[1-9]\d{8,14}$", cleaned):
            raise serializers.ValidationError(
                "Invalid phone number format. Must be E.164 (e.g. +998901234567)."
            )
        return cleaned


class OtpVerifySerializer(serializers.Serializer):
    """Serializer for verifying an OTP code."""

    phone = serializers.CharField(
        max_length=20,
        help_text="Phone number in E.164 format (e.g. +998900000001).",
    )
    code = serializers.CharField(
        max_length=6,
        min_length=6,
        help_text="6-digit verification code.",
    )

    def validate_phone(self, value: str) -> str:
        cleaned = re.sub(r"[\s\-\(\)]", "", str(value).strip())
        if not re.match(r"^\+[1-9]\d{8,14}$", cleaned):
            raise serializers.ValidationError(
                "Invalid phone number format. Must be E.164 (e.g. +998901234567)."
            )
        return cleaned

    def validate_code(self, value: str) -> str:
        code = str(value).strip()
        if not code.isdigit() or len(code) != 6:
            raise serializers.ValidationError("Code must be exactly 6 digits.")
        return code


class CompanySerializer(serializers.ModelSerializer):
    """Serializer for company profile."""

    class Meta:
        model = Company
        fields = [
            "id",
            "name",
            "tin",
            "address",
            "rating_avg",
            "rating_count",
            "verified_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "rating_avg",
            "rating_count",
            "verified_at",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "name": {"required": True},
            "tin": {
                "required": False,
                "allow_null": True,
                "allow_blank": True,
                "validators": [],
            },
            "address": {"required": False, "allow_blank": True},
        }


class UserSerializer(serializers.ModelSerializer):
    """Serializer for user details."""

    company = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "phone",
            "full_name",
            "role",
            "language",
            "status",
            "avatar",
            "is_active",
            "company",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "phone",
            "status",
            "is_active",
            "company",
            "created_at",
            "updated_at",
        ]

    @extend_schema_field(CompanySerializer)
    def get_company(self, obj: User) -> dict[str, Any] | None:
        try:
            if hasattr(obj, "company") and obj.company is not None:
                return CompanySerializer(obj.company).data
        except (Company.DoesNotExist, AttributeError):
            return None
        return None


class UserUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating user profile."""

    avatar = serializers.ImageField(
        required=False,
        allow_null=True,
        validators=[validate_image_file],
    )

    class Meta:
        model = User
        fields = ["full_name", "role", "language", "avatar"]
        extra_kwargs = {
            "full_name": {"required": False},
            "role": {"required": False},
            "language": {"required": False},
        }


class OtpVerifyResponseSerializer(serializers.Serializer):
    """Response payload for successful OTP verification."""

    access = serializers.CharField(help_text="JWT access token.")
    refresh = serializers.CharField(help_text="JWT refresh token.")
    is_new = serializers.BooleanField(help_text="True if newly registered user.")
    user = UserSerializer(help_text="User profile information.")


class TokenRefreshResponseSerializer(serializers.Serializer):
    """Response payload for token refresh."""

    access = serializers.CharField(help_text="New JWT access token.")
    refresh = serializers.CharField(
        required=False,
        help_text="New JWT refresh token if rotation is enabled.",
    )


class CustomTokenRefreshSerializer(TokenRefreshSerializer):
    """Token refresh serializer validating user active and non-blocked status."""

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        refresh = self.token_class(attrs["refresh"])
        user_id = refresh.get(jwt_settings.USER_ID_CLAIM)
        if user_id is not None:
            user = User.objects.filter(pk=user_id).first()
            if not user or not user.is_active or user.status == User.Status.BLOCKED:
                from apps.core.exceptions import ServiceError

                raise ServiceError(
                    detail="User account is blocked or inactive.",
                    code="account_blocked",
                    status_code=status.HTTP_401_UNAUTHORIZED,
                )
        return super().validate(attrs)


class LogoutSerializer(serializers.Serializer):
    """Serializer for logging out and blacklisting refresh token."""

    refresh = serializers.CharField(help_text="JWT refresh token to blacklist.")


class DeviceSerializer(serializers.ModelSerializer):
    """Serializer for mobile device registration."""

    class Meta:
        model = Device
        fields = [
            "id",
            "fcm_token",
            "platform",
            "last_seen_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "last_seen_at",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "fcm_token": {"validators": []},
        }
