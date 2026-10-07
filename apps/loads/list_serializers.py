"""List and read serializers for loads app."""

from decimal import Decimal
from typing import Any

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.loads.models import Load, RoutePoint


class LocationSummarySerializer(serializers.Serializer):
    """Origin or destination route point summary."""

    country = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="Country ISO 2-letter code.",
    )
    address = serializers.CharField(
        allow_blank=True,
        default="",
        required=False,
        help_text="Full street/city address string.",
    )


class VehicleTypeCompactSerializer(serializers.Serializer):
    """Compact representation of vehicle body type."""

    id = serializers.IntegerField(read_only=True)
    code = serializers.CharField(read_only=True)
    name_i18n = serializers.JSONField(read_only=True)


class LoadCompactSerializer(serializers.Serializer):
    """Compact serializer for public load board listings and favorites."""

    id = serializers.IntegerField(read_only=True)
    origin = serializers.SerializerMethodField()
    destination = serializers.SerializerMethodField()
    distance_km = serializers.IntegerField(allow_null=True, read_only=True)
    weight_t = serializers.DecimalField(max_digits=10, decimal_places=3, read_only=True)
    volume_m3 = serializers.DecimalField(
        max_digits=10, decimal_places=3, allow_null=True, read_only=True
    )
    body_types = VehicleTypeCompactSerializer(many=True, read_only=True)
    price_amount = serializers.DecimalField(
        max_digits=18, decimal_places=2, allow_null=True, read_only=True
    )
    currency = serializers.CharField(source="currency_id", allow_null=True, read_only=True)
    shipper_company = serializers.SerializerMethodField()
    published_at = serializers.DateTimeField(allow_null=True, read_only=True)
    negotiable = serializers.BooleanField(source="price_negotiable", read_only=True)
    trucks_needed = serializers.IntegerField(read_only=True)
    trucks_found = serializers.IntegerField(read_only=True)

    @extend_schema_field(LocationSummarySerializer)
    def get_origin(self, obj: Load) -> dict[str, Any]:
        """Return loading location with lowest sequence number."""
        country = getattr(obj, "origin_country_code", None)
        address = getattr(obj, "origin_address", None)
        if country is None and address is None:
            first_loading = (
                obj.route_points.filter(kind=RoutePoint.Kind.LOADING).order_by("seq").first()
            )
            if first_loading:
                country = first_loading.country_id
                address = first_loading.address
        return {"country": country, "address": address or ""}

    @extend_schema_field(LocationSummarySerializer)
    def get_destination(self, obj: Load) -> dict[str, Any]:
        """Return unloading location with highest sequence number."""
        country = getattr(obj, "destination_country_code", None)
        address = getattr(obj, "destination_address", None)
        if country is None and address is None:
            last_unloading = (
                obj.route_points.filter(kind=RoutePoint.Kind.UNLOADING).order_by("-seq").first()
            )
            if last_unloading:
                country = last_unloading.country_id
                address = last_unloading.address
        return {"country": country, "address": address or ""}

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_shipper_company(self, obj: Load) -> str | None:
        """Return company name associated with the load or shipper."""
        if hasattr(obj, "shipper_company"):
            return obj.shipper_company
        if obj.company_id and obj.company:
            return obj.company.name
        shipper = getattr(obj, "shipper", None)
        if shipper and hasattr(shipper, "company") and shipper.company:
            return shipper.company.name
        return None


class LoadMineSerializer(LoadCompactSerializer):
    """Extended serializer for shipper's own loads in LoadMineView."""

    status = serializers.CharField(read_only=True)
    expires_at = serializers.DateTimeField(allow_null=True, read_only=True)
    offers_count = serializers.SerializerMethodField()

    @extend_schema_field(serializers.IntegerField())
    def get_offers_count(self, obj: Load) -> int:
        """Return total offer count on this load."""
        if hasattr(obj, "offers_count"):
            return obj.offers_count
        return obj.offers.count()


class LoadMapItemSerializer(serializers.Serializer):
    """Marker serializer for map view."""

    id = serializers.IntegerField(read_only=True)
    lat = serializers.SerializerMethodField()
    lng = serializers.SerializerMethodField()
    price_amount = serializers.DecimalField(
        max_digits=18, decimal_places=2, allow_null=True, read_only=True
    )
    currency = serializers.CharField(source="currency_id", allow_null=True, read_only=True)

    @extend_schema_field(serializers.DecimalField(max_digits=9, decimal_places=6))
    def get_lat(self, obj: Any) -> Decimal | None:
        """Return latitude of the first loading point."""
        val = getattr(obj, "first_loading_lat", None)
        if val is not None:
            return val
        if hasattr(obj, "route_points"):
            fl = obj.route_points.filter(kind=RoutePoint.Kind.LOADING).order_by("seq").first()
            if fl:
                return fl.lat
        return getattr(obj, "lat", None)

    @extend_schema_field(serializers.DecimalField(max_digits=9, decimal_places=6))
    def get_lng(self, obj: Any) -> Decimal | None:
        """Return longitude of the first loading point."""
        val = getattr(obj, "first_loading_lng", None)
        if val is not None:
            return val
        if hasattr(obj, "route_points"):
            fl = obj.route_points.filter(kind=RoutePoint.Kind.LOADING).order_by("seq").first()
            if fl:
                return fl.lng
        return getattr(obj, "lng", None)
