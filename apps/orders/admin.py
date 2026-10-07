"""Admin configuration for orders app."""

from django.contrib import admin

from apps.orders.models import Order, OrderDocument, OrderStatusEvent, Rating


class OrderStatusEventInline(admin.TabularInline):
    """Inline for status transition history on an order."""

    model = OrderStatusEvent
    extra = 0
    ordering = ("at", "id")
    readonly_fields = ("at",)


class OrderDocumentInline(admin.TabularInline):
    """Inline for documents attached to an order."""

    model = OrderDocument
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    """Admin interface for Order model."""

    inlines = [OrderStatusEventInline, OrderDocumentInline]
    list_display = (
        "id",
        "load",
        "shipper",
        "carrier",
        "status",
        "agreed_amount",
        "currency",
        "created_at",
        "completed_at",
    )
    list_filter = (
        "status",
        "currency",
        "created_at",
    )
    search_fields = (
        "id",
        "load__cargo_description",
        "shipper__phone",
        "shipper__full_name",
        "carrier__phone",
        "carrier__full_name",
    )


@admin.register(OrderStatusEvent)
class OrderStatusEventAdmin(admin.ModelAdmin):
    """Admin interface for OrderStatusEvent model."""

    list_display = ("id", "order", "status", "actor", "at")
    list_filter = ("status", "at")
    search_fields = ("order__id", "actor__phone", "note")
    raw_id_fields = ("order", "actor")
    readonly_fields = ("at",)


@admin.register(OrderDocument)
class OrderDocumentAdmin(admin.ModelAdmin):
    """Admin interface for OrderDocument model."""

    list_display = ("id", "order", "name", "size_kb", "uploaded_by", "created_at")
    list_filter = ("created_at",)
    search_fields = ("name", "order__id", "uploaded_by__phone")
    raw_id_fields = ("order", "uploaded_by")


@admin.register(Rating)
class RatingAdmin(admin.ModelAdmin):
    """Admin interface for Rating model."""

    list_display = (
        "id",
        "order",
        "rater",
        "ratee",
        "stars",
        "created_at",
    )
    list_filter = (
        "stars",
        "created_at",
    )
    search_fields = (
        "order__id",
        "rater__phone",
        "ratee__phone",
        "comment",
    )
    raw_id_fields = ("order", "rater", "ratee")
