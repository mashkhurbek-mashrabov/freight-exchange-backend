"""Admin configuration for loads app."""

from django.contrib import admin

from apps.loads.models import Favorite, Load, LoadDocument, PaymentTerms, RoutePoint


class RoutePointInline(admin.TabularInline):
    """Inline for route points on a load."""

    model = RoutePoint
    extra = 0
    ordering = ("seq",)


class PaymentTermsInline(admin.StackedInline):
    """Inline for payment terms on a load."""

    model = PaymentTerms
    can_delete = False


class LoadDocumentInline(admin.TabularInline):
    """Inline for documents attached to a load."""

    model = LoadDocument
    extra = 0


@admin.register(Load)
class LoadAdmin(admin.ModelAdmin):
    """Admin interface for Load model."""

    inlines = [RoutePointInline, PaymentTermsInline, LoadDocumentInline]
    list_display = (
        "id",
        "cargo_description",
        "shipper",
        "status",
        "transport_mode",
        "trucks_needed",
        "trucks_found",
        "price_amount",
        "currency",
        "published_at",
    )
    list_filter = (
        "status",
        "transport_mode",
        "is_adr",
        "temp_controlled",
        "currency",
        "created_at",
    )
    search_fields = (
        "cargo_description",
        "cargo_type",
        "shipper__phone",
        "shipper__full_name",
    )


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    """Admin interface for Favorite model."""

    list_display = ("id", "user", "load", "created_at")
    search_fields = ("user__phone", "load__cargo_description")
