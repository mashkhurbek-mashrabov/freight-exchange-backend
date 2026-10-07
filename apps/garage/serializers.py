"""Serializers for garage app."""

from typing import Any

from rest_framework import serializers

from apps.garage.models import Vehicle, VehicleKind, VehicleType, normalize_plate_number


class VehicleTypeSerializer(serializers.ModelSerializer):
    """Vehicle type read serializer."""

    class Meta:
        model = VehicleType
        fields = ["id", "code", "name_i18n", "kind", "image_url"]
        read_only_fields = fields


class VehicleSerializer(serializers.ModelSerializer):
    """Vehicle representation serializer."""

    vehicle_type = VehicleTypeSerializer(read_only=True)
    paired_vehicle_id = serializers.IntegerField(
        read_only=True,
        allow_null=True,
    )
    paired_vehicle = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Vehicle
        fields = [
            "id",
            "kind",
            "vehicle_type",
            "plate_number",
            "tech_passport_no",
            "owner_full_name",
            "brand",
            "tech_passport_image",
            "paired_vehicle_id",
            "paired_vehicle",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class VehicleCreateUpdateSerializer(serializers.ModelSerializer):
    """Vehicle create and update write serializer."""

    kind = serializers.ChoiceField(choices=VehicleKind.choices, required=False)
    vehicle_type_id = serializers.PrimaryKeyRelatedField(
        queryset=VehicleType.objects.all(),
        source="vehicle_type",
        required=False,
        allow_null=True,
    )
    paired_vehicle_id = serializers.PrimaryKeyRelatedField(
        queryset=Vehicle.objects.all(),
        source="paired_vehicle",
        required=False,
        allow_null=True,
    )
    plate_number = serializers.CharField(max_length=50, required=False)

    class Meta:
        model = Vehicle
        fields = [
            "kind",
            "vehicle_type_id",
            "plate_number",
            "tech_passport_no",
            "owner_full_name",
            "brand",
            "tech_passport_image",
            "paired_vehicle_id",
        ]

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        """Support fallback alias fields vehicle_type and paired_vehicle."""
        if hasattr(data, "copy"):
            data = data.copy()
        elif isinstance(data, dict):
            data = dict(data)

        if isinstance(data, dict):
            if "vehicle_type" in data and "vehicle_type_id" not in data:
                data["vehicle_type_id"] = data["vehicle_type"]
            if "paired_vehicle" in data and "paired_vehicle_id" not in data:
                data["paired_vehicle_id"] = data["paired_vehicle"]

        return super().to_internal_value(data)

    def validate_plate_number(self, value: str) -> str:
        """Validate and normalize plate number, preventing duplicates with 400."""
        normalized = normalize_plate_number(value)
        if not normalized:
            raise serializers.ValidationError("Plate number is required.")

        qs = Vehicle.objects.filter(plate_number=normalized)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
                "Vehicle with this plate number already exists."
            )
        return normalized

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Validate required fields on creation and vehicle pairing rules."""
        if self.instance is None:
            if "kind" not in attrs:
                raise serializers.ValidationError({"kind": "This field is required."})
            if "plate_number" not in attrs:
                raise serializers.ValidationError(
                    {"plate_number": "This field is required."}
                )

        target_kind = attrs.get("kind")
        if not target_kind and self.instance:
            target_kind = self.instance.kind

        vehicle_type = attrs.get("vehicle_type")
        if vehicle_type is None and self.instance and "vehicle_type" not in attrs:
            vehicle_type = self.instance.vehicle_type

        if vehicle_type and target_kind and vehicle_type.kind != target_kind:
            raise serializers.ValidationError(
                {"vehicle_type_id": "Vehicle type kind must match vehicle kind."}
            )

        paired_vehicle = attrs.get("paired_vehicle")
        if paired_vehicle is None and self.instance and "paired_vehicle" not in attrs:
            paired_vehicle = self.instance.paired_vehicle

        if paired_vehicle:
            request = self.context.get("request")
            owner = getattr(request, "user", None) if request else None

            if self.instance and paired_vehicle.pk == self.instance.pk:
                raise serializers.ValidationError(
                    {"paired_vehicle_id": "A vehicle cannot be paired with itself."}
                )

            if owner and paired_vehicle.owner_id != owner.id:
                raise serializers.ValidationError(
                    {
                        "paired_vehicle_id": (
                            "Paired vehicle must belong to the same owner."
                        )
                    }
                )
            elif (
                self.instance
                and paired_vehicle.owner_id != self.instance.owner_id
            ):
                raise serializers.ValidationError(
                    {
                        "paired_vehicle_id": (
                            "Paired vehicle must belong to the same owner."
                        )
                    }
                )

            if target_kind and paired_vehicle.kind == target_kind:
                raise serializers.ValidationError(
                    {
                        "paired_vehicle_id": (
                            "Paired vehicle must have the opposite kind."
                        )
                    }
                )

            if not paired_vehicle.is_active:
                raise serializers.ValidationError(
                    {"paired_vehicle_id": "Cannot pair with an inactive vehicle."}
                )

        return attrs
