"""Admin configuration for accounts app."""

from django.contrib import admin

from .models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    """Admin configuration for custom User."""

    list_display = (
        "id",
        "phone",
        "full_name",
        "role",
        "status",
        "is_active",
        "is_staff",
    )
    list_filter = ("role", "status", "is_active", "is_staff")
    search_fields = ("phone", "full_name")
    ordering = ("-id",)
