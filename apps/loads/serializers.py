"""Serializers for loads app."""

from typing import Any

from drf_spectacular.settings import spectacular_settings
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.garage.models import VehicleType
from apps.garage.serializers import VehicleTypeSerializer
from apps.geo.models import Country, Currency
from apps.geo.serializers import CountrySerializer
from apps.loads.models import Favorite, Load, LoadDocument, PaymentTerms, RoutePoint
from apps.offers.models import Offer

spectacular_settings.ENUM_NAME_OVERRIDES.setdefault(
    "VehicleKindEnum", "apps.garage.models.VehicleKind"
)
spectacular_settings.ENUM_NAME_OVERRIDES.setdefault(
    "RoutePointKindEnum", "apps.loads.models.RoutePoint.Kind"
)
spectacular_settings.ENUM_NAME_OVERRIDES.setdefault(
    "PaymentMethodEnum", "apps.loads.models.PaymentTerms.PrepayMethod"
)


class RoutePointWriteSerializer(serializers.Serializer):
    """Write serializer for creating or updating a route point."""

    seq = serializers.IntegerField(min_value=1, help_text="Sequence position in route (1-indexed).")
    kind = serializers.ChoiceField(
        choices=RoutePoint.Kind.choices,
        help_text="Point kind (loading, stop, transit, border, customs, unloading).",
    )
    country = serializers.PrimaryKeyRelatedField(
        queryset=Country.objects.all(),
        help_text="Country ISO 2-letter code.",
    )
    address = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        default="",
        help_text="Address or location name.",
    )
    lat = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        coerce_to_string=True,
        help_text="Latitude.",
    )
    lng = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        coerce_to_string=True,
        help_text="Longitude.",
    )
    planned_from = serializers.DateTimeField(
        required=False,
        allow_null=True,
        default=None,
        help_text="Planned start time.",
    )
    planned_to = serializers.DateTimeField(
        required=False,
        allow_null=True,
        default=None,
        help_text="Planned finish time.",
    )
    asap = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Indicates if arrival/loading is needed as soon as possible.",
    )
    ready_to_load = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Indicates if cargo is ready for immediate loading.",
    )
    comment = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Route point notes or comments.",
    )

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        """Support country_id alias if country is not explicitly provided."""
        if isinstance(data, dict):
            data = data.copy()
            if "country_id" in data and "country" not in data:
                data["country"] = data["country_id"]
        return super().to_internal_value(data)


class PaymentTermsWriteSerializer(serializers.Serializer):
    """Write serializer for load payment conditions."""

    prepay_amount = serializers.DecimalField(
        max_digits=18,
        decimal_places=2,
        required=False,
        allow_null=True,
        coerce_to_string=True,
        help_text="Prepayment amount.",
    )
    prepay_method = serializers.ChoiceField(
        choices=PaymentTerms.PrepayMethod.choices,
        required=False,
        allow_blank=True,
        default="",
        help_text="Prepayment payment method (cash or transfer).",
    )
    paid_amount = serializers.DecimalField(
        max_digits=18,
        decimal_places=2,
        required=False,
        allow_null=True,
        coerce_to_string=True,
        help_text="Already paid or on-delivery amount.",
    )
    paid_method = serializers.ChoiceField(
        choices=PaymentTerms.PrepayMethod.choices,
        required=False,
        allow_blank=True,
        default="",
        help_text="Payment method for paid amount.",
    )
    remaining_amount = serializers.DecimalField(
        max_digits=18,
        decimal_places=2,
        required=False,
        allow_null=True,
        coerce_to_string=True,
        help_text="Remaining balance to be paid.",
    )
    payment_due_days = serializers.IntegerField(
        min_value=0,
        required=False,
        allow_null=True,
        help_text="Payment grace period in days upon delivery.",
    )
    conditions = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Additional payment terms and conditions.",
    )


class LoadWriteSerializer(serializers.Serializer):
    """Write serializer for creating and updating freight loads."""

    cargo_description = serializers.CharField(
        max_length=255,
        required=False,
        help_text="Description of the cargo.",
    )
    cargo_type = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        default="",
        help_text="Type or category of cargo.",
    )
    weight_t = serializers.DecimalField(
        max_digits=10,
        decimal_places=3,
        required=False,
        coerce_to_string=True,
        help_text="Cargo weight in metric tons.",
    )
    volume_m3 = serializers.DecimalField(
        max_digits=10,
        decimal_places=3,
        required=False,
        allow_null=True,
        coerce_to_string=True,
        help_text="Cargo volume in cubic meters.",
    )
    length_m = serializers.DecimalField(
        max_digits=8,
        decimal_places=2,
        required=False,
        allow_null=True,
        coerce_to_string=True,
        help_text="Required vehicle/cargo length in meters.",
    )
    packaging = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        default="",
        help_text="Packaging format (pallets, boxes, etc.).",
    )
    transport_mode = serializers.ChoiceField(
        choices=Load.TransportMode.choices,
        required=False,
        default=Load.TransportMode.FTL,
        help_text="Transport mode: FTL or LTL.",
    )
    vehicle_category = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        default="",
        help_text="Recommended vehicle category.",
    )
    body_types = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=VehicleType.objects.all(),
        required=False,
        default=list,
        help_text="List of accepted vehicle body type IDs.",
    )
    trucks_needed = serializers.IntegerField(
        min_value=1,
        required=False,
        default=1,
        help_text="Number of trucks required for this load.",
    )
    is_adr = serializers.BooleanField(
        required=False,
        default=False,
        help_text="True if dangerous/hazardous goods.",
    )
    adr_class = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="ADR hazard class (1-9).",
    )
    temp_controlled = serializers.BooleanField(
        required=False,
        default=False,
        help_text="True if temperature-controlled cargo.",
    )
    temp_min_c = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        allow_null=True,
        coerce_to_string=True,
        help_text="Minimum allowed temperature in Celsius.",
    )
    temp_max_c = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        allow_null=True,
        coerce_to_string=True,
        help_text="Maximum allowed temperature in Celsius.",
    )
    price_amount = serializers.DecimalField(
        max_digits=18,
        decimal_places=2,
        required=False,
        allow_null=True,
        coerce_to_string=True,
        help_text="Offered price amount.",
    )
    currency = serializers.PrimaryKeyRelatedField(
        queryset=Currency.objects.all(),
        required=False,
        allow_null=True,
        help_text="Currency ISO code (e.g. USD).",
    )
    vat_included = serializers.BooleanField(
        required=False,
        default=False,
        help_text="True if VAT is included in price.",
    )
    price_negotiable = serializers.BooleanField(
        required=False,
        default=True,
        help_text="True if the shipper accepts price bids.",
    )
    distance_km = serializers.IntegerField(
        min_value=0,
        required=False,
        allow_null=True,
        help_text="Total route distance in km. Computed if omitted.",
    )
    expires_at = serializers.DateTimeField(
        required=False,
        allow_null=True,
        help_text="Load expiration timestamp.",
    )
    route_points = RoutePointWriteSerializer(
        many=True,
        required=False,
        help_text="Ordered list of route stops.",
    )
    payment_terms = PaymentTermsWriteSerializer(
        required=False,
        allow_null=True,
        help_text="Payment conditions and terms.",
    )

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        """Support currency_id alias if currency is not explicitly provided."""
        if isinstance(data, dict):
            data = data.copy()
            if "currency_id" in data and "currency" not in data:
                data["currency"] = data["currency_id"]
        return super().to_internal_value(data)


class RoutePointDetailSerializer(serializers.ModelSerializer):
    """Detailed read representation of a route point including nested country."""

    country = CountrySerializer(read_only=True)
    lat = serializers.DecimalField(max_digits=9, decimal_places=6, coerce_to_string=True)
    lng = serializers.DecimalField(max_digits=9, decimal_places=6, coerce_to_string=True)

    class Meta:
        model = RoutePoint
        fields = [
            "id",
            "seq",
            "kind",
            "country",
            "address",
            "lat",
            "lng",
            "planned_from",
            "planned_to",
            "asap",
            "ready_to_load",
            "comment",
        ]
        read_only_fields = fields


class PaymentTermsDetailSerializer(serializers.ModelSerializer):
    """Detailed read representation of payment conditions."""

    prepay_amount = serializers.DecimalField(
        max_digits=18,
        decimal_places=2,
        coerce_to_string=True,
        allow_null=True,
    )
    paid_amount = serializers.DecimalField(
        max_digits=18,
        decimal_places=2,
        coerce_to_string=True,
        allow_null=True,
    )
    remaining_amount = serializers.DecimalField(
        max_digits=18,
        decimal_places=2,
        coerce_to_string=True,
        allow_null=True,
    )

    class Meta:
        model = PaymentTerms
        fields = [
            "prepay_amount",
            "prepay_method",
            "paid_amount",
            "paid_method",
            "remaining_amount",
            "payment_due_days",
            "conditions",
        ]
        read_only_fields = fields


class LoadDocumentSerializer(serializers.ModelSerializer):
    """Read representation of attached load documents."""

    class Meta:
        model = LoadDocument
        fields = ["id", "name", "file"]
        read_only_fields = fields


class CompactOfferSerializer(serializers.Serializer):
    """Compact summary of requester's offer for this load."""

    id = serializers.IntegerField(help_text="Offer ID.")
    status = serializers.CharField(help_text="Offer status.")
    mode = serializers.CharField(help_text="Offer mode (comment_only or price_bid).")
    amount = serializers.CharField(
        allow_null=True,
        help_text="Offered price amount as string.",
    )
    currency = serializers.CharField(
        allow_null=True,
        help_text="Offer currency code.",
    )


class LoadDetailSerializer(serializers.ModelSerializer):
    """Full detail serializer for loads including nested relations and user context."""

    shipper_company_name = serializers.SerializerMethodField(
        help_text="Company name of the posting shipper.",
    )
    route_points = RoutePointDetailSerializer(many=True, read_only=True)
    payment_terms = serializers.SerializerMethodField(
        help_text="Payment conditions for the load.",
    )
    documents = LoadDocumentSerializer(many=True, read_only=True)
    body_types = VehicleTypeSerializer(many=True, read_only=True)
    currency = serializers.SlugRelatedField(
        slug_field="code",
        read_only=True,
        allow_null=True,
    )
    weight_t = serializers.DecimalField(max_digits=10, decimal_places=3, coerce_to_string=True)
    volume_m3 = serializers.DecimalField(
        max_digits=10,
        decimal_places=3,
        coerce_to_string=True,
        allow_null=True,
    )
    length_m = serializers.DecimalField(
        max_digits=8,
        decimal_places=2,
        coerce_to_string=True,
        allow_null=True,
    )
    temp_min_c = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        coerce_to_string=True,
        allow_null=True,
    )
    temp_max_c = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        coerce_to_string=True,
        allow_null=True,
    )
    price_amount = serializers.DecimalField(
        max_digits=18,
        decimal_places=2,
        coerce_to_string=True,
        allow_null=True,
    )
    is_favorite = serializers.SerializerMethodField(
        help_text="Whether this load is bookmarked by the current user.",
    )
    my_offer = serializers.SerializerMethodField(
        help_text="Compact summary of current user's latest offer for this load.",
    )

    class Meta:
        model = Load
        fields = [
            "id",
            "shipper",
            "company",
            "shipper_company_name",
            "cargo_description",
            "cargo_type",
            "weight_t",
            "volume_m3",
            "length_m",
            "packaging",
            "transport_mode",
            "vehicle_category",
            "body_types",
            "trucks_needed",
            "trucks_found",
            "is_adr",
            "adr_class",
            "temp_controlled",
            "temp_min_c",
            "temp_max_c",
            "price_amount",
            "currency",
            "vat_included",
            "price_negotiable",
            "distance_km",
            "status",
            "published_at",
            "expires_at",
            "created_at",
            "updated_at",
            "route_points",
            "payment_terms",
            "documents",
            "is_favorite",
            "my_offer",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_shipper_company_name(self, obj: Load) -> str | None:
        if obj.company:
            return obj.company.name
        if hasattr(obj.shipper, "company") and obj.shipper.company:
            return obj.shipper.company.name
        return None

    @extend_schema_field(PaymentTermsDetailSerializer)
    def get_payment_terms(self, obj: Load) -> dict[str, Any] | None:
        try:
            pt = obj.payment_terms
        except PaymentTerms.DoesNotExist:
            return None
        if pt is None:
            return None
        return PaymentTermsDetailSerializer(pt).data

    @extend_schema_field(serializers.BooleanField())
    def get_is_favorite(self, obj: Load) -> bool:
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            return False
        return Favorite.objects.filter(user=request.user, load=obj).exists()

    @extend_schema_field(CompactOfferSerializer)
    def get_my_offer(self, obj: Load) -> dict[str, Any] | None:
        request = self.context.get("request")
        if not request or not request.user or not request.user.is_authenticated:
            return None
        latest_offer = (
            Offer.objects.filter(load=obj, carrier=request.user)
            .order_by("-created_at", "-id")
            .first()
        )
        if not latest_offer:
            latest_offer = (
                Offer.objects.filter(load=obj, proposer=request.user)
                .order_by("-created_at", "-id")
                .first()
            )
        if not latest_offer:
            return None
        return {
            "id": latest_offer.id,
            "status": latest_offer.status,
            "mode": latest_offer.mode,
            "amount": str(latest_offer.amount) if latest_offer.amount is not None else None,
            "currency": latest_offer.currency_id,
        }
