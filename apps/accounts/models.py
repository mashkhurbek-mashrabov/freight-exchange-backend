"""Accounts model definitions."""

from decimal import Decimal
from typing import Any

from django.conf import settings
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel


class UserManager(BaseUserManager):
    """Custom user manager where phone is the unique identifier."""

    def create_user(
        self, phone: str, password: str | None = None, **extra_fields: Any
    ) -> "User":
        """Create and return a regular user with an unusable password by default."""
        if not phone:
            raise ValueError("The phone number must be set.")
        extra_fields.setdefault("is_active", True)
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)

        user = self.model(phone=phone, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(
        self, phone: str, password: str | None = None, **extra_fields: Any
    ) -> "User":
        """Create and return a superuser."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(phone=phone, password=password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin, BaseModel):
    """Custom user model for Freight Exchange."""

    class Role(models.TextChoices):
        CARRIER = "carrier", "Carrier"
        SHIPPER = "shipper", "Shipper"
        BOTH = "both", "Both"

    class Language(models.TextChoices):
        UZ = "uz", "Uzbek"
        RU = "ru", "Russian"
        EN = "en", "English"

    class Status(models.TextChoices):
        NEW = "new", "New"
        PENDING_REVIEW = "pending_review", "Pending Review"
        VERIFIED = "verified", "Verified"
        BLOCKED = "blocked", "Blocked"

    phone = models.CharField(max_length=20, unique=True)
    full_name = models.CharField(max_length=255, blank=True, default="")
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.CARRIER,
    )
    language = models.CharField(
        max_length=10,
        choices=Language.choices,
        default=Language.RU,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
    )
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"
        ordering = ["-id"]

    def __str__(self) -> str:
        """Return phone and display name or role."""
        return f"{self.phone} ({self.full_name or self.role})"


class Company(BaseModel):
    """Company associated with a user."""

    owner = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="company",
    )
    name = models.CharField(max_length=255)
    tin = models.CharField(max_length=50, unique=True, null=True, blank=True)
    address = models.TextField(blank=True, default="")
    rating_avg = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    rating_count = models.PositiveIntegerField(default=0)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Company"
        verbose_name_plural = "Companies"
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"{self.name} ({self.tin or 'no TIN'})"


class Device(BaseModel):
    """Mobile device registered for push notifications."""

    class Platform(models.TextChoices):
        IOS = "ios", "iOS"
        ANDROID = "android", "Android"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="devices",
    )
    fcm_token = models.CharField(max_length=255, unique=True)
    platform = models.CharField(max_length=20, choices=Platform.choices)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = "Device"
        verbose_name_plural = "Devices"
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"{self.user_id} - {self.platform} ({self.fcm_token[:12]}...)"


class OtpCode(BaseModel):
    """One-time password hash record for phone authentication."""

    phone = models.CharField(max_length=20)
    code_hash = models.CharField(max_length=64)
    attempts = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "OTP Code"
        verbose_name_plural = "OTP Codes"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["phone", "created_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.phone} (expires: {self.expires_at})"
