"""Admin configuration for garage app."""

from django.contrib import admin

from apps.garage.models import Vehicle, VehicleType


@admin.register(VehicleType)
class VehicleTypeAdmin(admin.ModelAdmin):
    """Admin representation for VehicleType."""

    list_display = ["id", "code", "kind", "image_url"]
    list_filter = ["kind"]
    search_fields = ["code", "name_i18n"]


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    """Admin representation for Vehicle."""

    list_display = [
        "id",
        "plate_number",
        "kind",
        "owner",
        "vehicle_type",
        "paired_vehicle",
        "is_active",
        "created_at",
    ]
    list_filter = ["kind", "is_active", "vehicle_type"]
    search_fields = [
        "plate_number",
        "brand",
        "owner_full_name",
        "owner__phone",
        "tech_passport_no",
    ]
    raw_id_fields = ["owner", "paired_vehicle", "vehicle_type"]
