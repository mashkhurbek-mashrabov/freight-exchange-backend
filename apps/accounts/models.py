"""Accounts model definitions."""

from typing import Any

from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)
from django.db import models

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
