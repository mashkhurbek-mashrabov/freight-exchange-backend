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


@admin.register(RoutePoint)
class RoutePointAdmin(admin.ModelAdmin):
    """Admin interface for RoutePoint model."""

    list_display = (
        "id",
        "load",
        "seq",
        "kind",
        "country",
        "address",
        "asap",
        "ready_to_load",
    )
    list_filter = ("kind", "country", "asap", "ready_to_load")
    search_fields = ("address", "comment", "load__cargo_description")
    raw_id_fields = ("load",)


@admin.register(PaymentTerms)
class PaymentTermsAdmin(admin.ModelAdmin):
    """Admin interface for PaymentTerms model."""

    list_display = (
        "load",
        "prepay_amount",
        "prepay_method",
        "paid_amount",
        "paid_method",
        "payment_due_days",
    )
    list_filter = ("prepay_method", "paid_method")
    search_fields = ("load__cargo_description", "conditions")
    raw_id_fields = ("load",)


@admin.register(LoadDocument)
class LoadDocumentAdmin(admin.ModelAdmin):
    """Admin interface for LoadDocument model."""

    list_display = ("id", "load", "name", "file", "created_at")
    list_filter = ("created_at",)
    search_fields = ("name", "load__cargo_description")
    raw_id_fields = ("load",)


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    """Admin interface for Favorite model."""

    list_display = ("id", "user", "load", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__phone", "load__cargo_description")
    raw_id_fields = ("user", "load")
