"""Admin configuration for notifications app."""

from django.contrib import admin

from apps.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Admin configuration for Notification model."""

    list_display = ("id", "user", "type", "read_at", "created_at")
    list_filter = ("type", "read_at", "created_at")
    search_fields = ("user__phone",)
    raw_id_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")
