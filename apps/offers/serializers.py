"""Serializers for offers app."""

from typing import Any

from rest_framework import serializers

from apps.accounts.models import User
from apps.loads.models import Load, RoutePoint
from apps.offers.models import Offer


class LocationSummarySerializer(serializers.Serializer):
    """Location summary containing address and country code."""

    address = serializers.CharField(allow_blank=True, allow_null=True)
    country = serializers.CharField(allow_blank=True, allow_null=True)


class LoadSummarySerializer(serializers.Serializer):
    """Summary of a load associated with an offer."""

    id = serializers.IntegerField(source="pk")
    origin = LocationSummarySerializer(allow_null=True)
    destination = LocationSummarySerializer(allow_null=True)
    origin_address = serializers.CharField(allow_blank=True, allow_null=True)
    origin_country = serializers.CharField(allow_blank=True, allow_null=True)
    destination_address = serializers.CharField(allow_blank=True, allow_null=True)
    destination_country = serializers.CharField(allow_blank=True, allow_null=True)
    price = serializers.DecimalField(
        source="price_amount",
        max_digits=18,
        decimal_places=2,
        allow_null=True,
    )
    currency = serializers.CharField(source="currency_id", allow_null=True)

    def to_representation(self, instance: Load) -> dict[str, Any]:
        """Custom representation to resolve route origin and destination."""
        points = []
        if hasattr(instance, "route_points"):
            points = list(instance.route_points.all())
            points.sort(key=lambda p: p.seq)

        loading_pt = None
        unloading_pt = None
        if points:
            for p in points:
                if p.kind == RoutePoint.Kind.LOADING:
                    loading_pt = p
                    break
            if loading_pt is None:
                loading_pt = points[0]

            for p in reversed(points):
                if p.kind == RoutePoint.Kind.UNLOADING:
                    unloading_pt = p
                    break
            if unloading_pt is None:
                unloading_pt = points[-1]

        origin_address = loading_pt.address if loading_pt else None
        origin_country = loading_pt.country_id if loading_pt else None
        dest_address = unloading_pt.address if unloading_pt else None
        dest_country = unloading_pt.country_id if unloading_pt else None

        return {
            "id": instance.pk,
            "origin": {
                "address": origin_address,
                "country": origin_country,
            }
            if loading_pt
            else None,
            "destination": {
                "address": dest_address,
                "country": dest_country,
            }
            if unloading_pt
            else None,
            "origin_address": origin_address,
            "origin_country": origin_country,
            "destination_address": dest_address,
            "destination_country": dest_country,
            "price": (
                self.fields["price"].to_representation(instance.price_amount)
                if instance.price_amount is not None
                else None
            ),
            "currency": instance.currency_id,
        }


class OfferPartySerializer(serializers.Serializer):
    """User representation for offer parties; phone is hidden before acceptance."""

    id = serializers.IntegerField()
    full_name = serializers.CharField(allow_blank=True)
    phone = serializers.CharField(allow_null=True, required=False)


class OfferSerializer(serializers.ModelSerializer):
    """Full representation serializer for Offer model."""

    load = LoadSummarySerializer(read_only=True)
    load_id = serializers.IntegerField(read_only=True)
    carrier = serializers.SerializerMethodField()
    proposer = serializers.SerializerMethodField()
    recipient = serializers.SerializerMethodField()
    vehicle = serializers.IntegerField(source="vehicle_id", allow_null=True, read_only=True)
    trailer = serializers.IntegerField(source="trailer_id", allow_null=True, read_only=True)
    vehicle_id = serializers.IntegerField(allow_null=True, read_only=True)
    trailer_id = serializers.IntegerField(allow_null=True, read_only=True)
    parent = serializers.IntegerField(source="parent_id", allow_null=True, read_only=True)
    parent_id = serializers.IntegerField(allow_null=True, read_only=True)
    currency = serializers.CharField(source="currency_id", allow_null=True, read_only=True)

    class Meta:
        model = Offer
        fields = [
            "id",
            "load",
            "load_id",
            "carrier",
            "proposer",
            "recipient",
            "vehicle",
            "trailer",
            "vehicle_id",
            "trailer_id",
            "parent",
            "parent_id",
            "mode",
            "amount",
            "currency",
            "comment",
            "status",
            "responded_at",
            "created_at",
            "updated_at",
        ]

    def _serialize_user(self, user: User | None, offer_status: str) -> dict[str, Any] | None:
        if user is None:
            return None
        return {
            "id": user.pk,
            "full_name": user.full_name,
            "phone": user.phone if offer_status == Offer.Status.ACCEPTED else None,
        }

    def get_carrier(self, obj: Offer) -> dict[str, Any] | None:
        """Return carrier details with phone conditional on acceptance."""
        return self._serialize_user(obj.carrier, obj.status)

    def get_proposer(self, obj: Offer) -> dict[str, Any] | None:
        """Return proposer details with phone conditional on acceptance."""
        return self._serialize_user(obj.proposer, obj.status)

    def get_recipient(self, obj: Offer) -> dict[str, Any] | None:
        """Return recipient details with phone conditional on acceptance."""
        return self._serialize_user(obj.recipient, obj.status)


class OfferCreateSerializer(serializers.Serializer):
    """Write serializer for creating a new offer on a load."""

    mode = serializers.ChoiceField(
        choices=Offer.Mode.choices,
        default=Offer.Mode.PRICE_BID,
        required=False,
        help_text="Offer mode: price_bid or comment_only.",
    )
    amount = serializers.DecimalField(
        max_digits=18,
        decimal_places=2,
        required=False,
        allow_null=True,
        help_text="Proposed price amount (required if mode is price_bid).",
    )
    currency = serializers.CharField(
        max_length=3,
        required=False,
        allow_null=True,
        help_text="Currency code e.g. USD (required if mode is price_bid).",
    )
    vehicle_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="Carrier tractor vehicle ID.",
    )
    trailer_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="Carrier trailer vehicle ID.",
    )
    vehicle = serializers.IntegerField(
        required=False,
        allow_null=True,
        write_only=True,
        help_text="Alternative alias for vehicle_id.",
    )
    trailer = serializers.IntegerField(
        required=False,
        allow_null=True,
        write_only=True,
        help_text="Alternative alias for trailer_id.",
    )
    comment = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Optional comment or notes for the offer.",
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Normalize vehicle/trailer aliases and validate price_bid requirements."""
        if attrs.get("vehicle") and not attrs.get("vehicle_id"):
            attrs["vehicle_id"] = attrs.get("vehicle")
        if attrs.get("trailer") and not attrs.get("trailer_id"):
            attrs["trailer_id"] = attrs.get("trailer")

        mode = attrs.get("mode", Offer.Mode.PRICE_BID)
        if mode == Offer.Mode.PRICE_BID:
            amount = attrs.get("amount")
            currency = attrs.get("currency")
            if amount is None:
                raise serializers.ValidationError({"amount": "Amount is required for price_bid."})
            if not currency:
                raise serializers.ValidationError(
                    {"currency": "Currency is required for price_bid."}
                )
        return attrs


class CounterOfferSerializer(serializers.Serializer):
    """Write serializer for submitting a counter-offer."""

    amount = serializers.DecimalField(
        max_digits=18,
        decimal_places=2,
        required=True,
        help_text="Counter offer price amount.",
    )
    currency = serializers.CharField(
        max_length=3,
        required=True,
        help_text="Currency code for counter offer.",
    )
    comment = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Counter offer comment or explanation.",
    )
