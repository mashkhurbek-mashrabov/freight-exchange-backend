from drf_spectacular.settings import spectacular_settings
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import User
from apps.core.validators import validate_document_file
from apps.loads.models import Load, RoutePoint
from apps.orders.models import Order, OrderDocument, OrderStatusEvent, Rating

spectacular_settings.ENUM_NAME_OVERRIDES.setdefault(
    "OrderStatusEnum",
    "apps.orders.models.Order.Status",
)
spectacular_settings.ENUM_NAME_OVERRIDES.setdefault(
    "UserStatusEnum",
    "apps.accounts.models.User.Status",
)


class UserSummarySerializer(serializers.ModelSerializer):
    """Compact summary of a user."""

    class Meta:
        model = User
        fields = ["id", "full_name"]


class OrderPartySerializer(serializers.ModelSerializer):
    """Party (carrier/shipper) representation with visible phone and company."""

    company = serializers.SerializerMethodField(help_text="Company name or null.")
    company_name = serializers.SerializerMethodField(help_text="Company name or null.")

    class Meta:
        model = User
        fields = [
            "id",
            "full_name",
            "phone",
            "company",
            "company_name",
        ]

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_company(self, obj: User) -> str | None:
        """Return the company name if available."""
        company = getattr(obj, "company", None)
        return company.name if company else None

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_company_name(self, obj: User) -> str | None:
        """Alias for company name."""
        return self.get_company(obj)


class OrderLoadSummarySerializer(serializers.ModelSerializer):
    """Summary of the associated load."""

    class Meta:
        model = Load
        fields = [
            "id",
            "cargo_description",
            "weight_t",
            "distance_km",
        ]


class OrderRoutePointSerializer(serializers.ModelSerializer):
    """Route point representation for orders."""

    kind = serializers.CharField(read_only=True)
    country_code = serializers.CharField(source="country.code", read_only=True)

    class Meta:
        model = RoutePoint
        fields = [
            "id",
            "seq",
            "kind",
            "country",
            "country_code",
            "address",
            "lat",
            "lng",
            "planned_from",
            "planned_to",
            "asap",
            "ready_to_load",
            "comment",
        ]


class OrderStatusEventSerializer(serializers.ModelSerializer):
    """Audit log event on order status transition."""

    actor = UserSummarySerializer(read_only=True)

    class Meta:
        model = OrderStatusEvent
        fields = [
            "id",
            "status",
            "actor",
            "note",
            "at",
        ]


class OrderDocumentSerializer(serializers.ModelSerializer):
    """Document attached to an order."""

    uploaded_by = UserSummarySerializer(read_only=True)

    class Meta:
        model = OrderDocument
        fields = [
            "id",
            "name",
            "file",
            "size_kb",
            "uploaded_by",
            "created_at",
        ]


class RatingSerializer(serializers.ModelSerializer):
    """Rating submitted on a completed order."""

    rater = UserSummarySerializer(read_only=True)
    ratee = UserSummarySerializer(read_only=True)

    class Meta:
        model = Rating
        fields = [
            "id",
            "order",
            "rater",
            "ratee",
            "stars",
            "reasons",
            "comment",
            "created_at",
        ]


class OrderListSerializer(serializers.ModelSerializer):
    """Order representation for list endpoints."""

    load = OrderLoadSummarySerializer(read_only=True)
    carrier = OrderPartySerializer(read_only=True)
    shipper = OrderPartySerializer(read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "offer",
            "load",
            "shipper",
            "carrier",
            "vehicle",
            "trailer",
            "agreed_amount",
            "currency",
            "status",
            "cancel_reason",
            "completed_at",
            "created_at",
            "updated_at",
        ]


class OrderDetailSerializer(serializers.ModelSerializer):
    """Detailed order representation for parties."""

    load = OrderLoadSummarySerializer(read_only=True)
    route_points = OrderRoutePointSerializer(
        source="load.route_points.all",
        many=True,
        read_only=True,
    )
    status_events = OrderStatusEventSerializer(many=True, read_only=True)
    documents = OrderDocumentSerializer(many=True, read_only=True)
    ratings = RatingSerializer(many=True, read_only=True)
    carrier = OrderPartySerializer(read_only=True)
    shipper = OrderPartySerializer(read_only=True)

    class Meta:
        model = Order
        fields = [
            "id",
            "offer",
            "load",
            "shipper",
            "carrier",
            "vehicle",
            "trailer",
            "agreed_amount",
            "currency",
            "status",
            "cancel_reason",
            "completed_at",
            "route_points",
            "status_events",
            "documents",
            "ratings",
            "created_at",
            "updated_at",
        ]


class OrderStatusUpdateSerializer(serializers.Serializer):
    """Request serializer for changing order status."""

    status = serializers.ChoiceField(
        choices=Order.Status.choices,
        help_text="Target order status.",
    )
    note = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Optional note or cancellation reason.",
    )
    cancel_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Alternative cancellation reason field.",
    )


class OrderDocumentUploadSerializer(serializers.Serializer):
    """Request serializer for uploading an order document."""

    file = serializers.FileField(
        help_text="Document file to upload.",
        validators=[validate_document_file],
    )
    name = serializers.CharField(
        max_length=255,
        help_text="Display name for document (e.g. CMR, Bill of Lading, Invoice).",
    )


class OrderRatingCreateSerializer(serializers.Serializer):
    """Request serializer for submitting an order rating."""

    stars = serializers.IntegerField(
        min_value=1,
        max_value=5,
        help_text="Rating score between 1 and 5 stars.",
    )
    reasons = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        default=list,
        help_text="Optional list of predefined reason tags.",
    )
    comment = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Optional written feedback comment.",
    )
