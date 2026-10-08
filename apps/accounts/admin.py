"""Admin configuration for accounts app."""

from typing import Any

from django.contrib import admin

from apps.accounts import services
from apps.accounts.models import Company, Device, OtpCode, User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """Admin configuration for custom User."""

    list_display = (
        "phone",
        "full_name",
        "role",
        "status",
        "is_active",
    )
    list_filter = ("status", "role", "language")
    search_fields = ("phone", "full_name")
    ordering = ("-id",)
    actions = ["mark_verified"]

    @admin.action(description="Mark selected users as verified")
    def mark_verified(self, request: Any, queryset: Any) -> None:
        """Mark selected users as verified."""
        services.mark_verified(queryset)

    def save_model(self, request: Any, obj: Any, form: Any, change: bool) -> None:
        """Save model and dispatch account_verified notification when transitioning to verified."""
        old_status = None
        if change and obj.pk:
            old_status = User.objects.filter(pk=obj.pk).values_list("status", flat=True).first()
        super().save_model(request, obj, form, change)
        if change and old_status != User.Status.VERIFIED and obj.status == User.Status.VERIFIED:
            from apps.notifications.models import Notification
            from apps.notifications.services import notify

            notify(obj, Notification.NotificationType.ACCOUNT_VERIFIED, {})


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    """Admin configuration for Company."""

    list_display = (
        "name",
        "owner",
        "tin",
        "rating_avg",
        "rating_count",
        "verified_at",
    )
    list_filter = ("rating_avg",)
    search_fields = ("name", "tin", "owner__phone")
    ordering = ("-id",)


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    """Admin configuration for Device."""

    list_display = ("user", "platform", "fcm_token", "last_seen_at")
    list_filter = ("platform",)
    search_fields = ("fcm_token", "user__phone")
    ordering = ("-id",)


@admin.register(OtpCode)
class OtpCodeAdmin(admin.ModelAdmin):
    """Admin configuration for OtpCode."""

    list_display = ("phone", "attempts", "expires_at", "used_at", "created_at")
    list_filter = ("attempts", "used_at")
    search_fields = ("phone",)
    ordering = ("-created_at",)
