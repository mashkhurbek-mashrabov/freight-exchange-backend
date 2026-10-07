"""Admin configuration for notifications app."""

from django.contrib import admin

from apps.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Admin configuration for Notification model."""

    list_display = ("user", "type", "read_at", "created_at")
    list_filter = ("type",)
    search_fields = ("user__phone",)
    readonly_fields = ("created_at", "updated_at")
