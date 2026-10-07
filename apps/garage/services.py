"""Business logic and services for garage app."""

from typing import Any

from django.db import IntegrityError, transaction

from apps.core.exceptions import ServiceError
from apps.garage.models import Vehicle, VehicleType, normalize_plate_number


def create_vehicle(
    *,
    owner: Any,
    kind: str,
    plate_number: str,
    vehicle_type: VehicleType | int | None = None,
    tech_passport_no: str = "",
    owner_full_name: str = "",
    brand: str = "",
    tech_passport_image: Any = None,
    paired_vehicle: Vehicle | int | None = None,
    is_active: bool = True,
) -> Vehicle:
    """Create and return a new vehicle with pairing and plate validations."""
    normalized_plate = normalize_plate_number(plate_number)
    if not normalized_plate:
        raise ServiceError(
            detail="Plate number is required.",
            code="validation_error",
            status_code=400,
        )

    if Vehicle.objects.filter(plate_number=normalized_plate).exists():
        raise ServiceError(
            detail="Vehicle with this plate number already exists.",
            code="validation_error",
            status_code=400,
        )

    # Resolve and validate vehicle_type
    resolved_type: VehicleType | None = None
    if isinstance(vehicle_type, int):
        resolved_type = VehicleType.objects.filter(pk=vehicle_type).first()
        if resolved_type is None:
            raise ServiceError(
                detail="Vehicle type not found.",
                code="validation_error",
                status_code=400,
            )
    elif isinstance(vehicle_type, VehicleType):
        resolved_type = vehicle_type

    if resolved_type is not None and resolved_type.kind != kind:
        raise ServiceError(
            detail="Vehicle type kind must match vehicle kind.",
            code="validation_error",
            status_code=400,
        )

    # Resolve and validate paired_vehicle
    resolved_paired: Vehicle | None = None
    if isinstance(paired_vehicle, int):
        resolved_paired = Vehicle.objects.filter(pk=paired_vehicle).first()
        if resolved_paired is None:
            raise ServiceError(
                detail="Paired vehicle not found.",
                code="validation_error",
                status_code=400,
            )
    elif isinstance(paired_vehicle, Vehicle):
        resolved_paired = paired_vehicle

    if resolved_paired is not None:
        if resolved_paired.owner_id != owner.id:
            raise ServiceError(
                detail="Paired vehicle must belong to the same owner.",
                code="validation_error",
                status_code=400,
            )
        if resolved_paired.kind == kind:
            raise ServiceError(
                detail="Paired vehicle must have the opposite kind.",
                code="validation_error",
                status_code=400,
            )
        if not resolved_paired.is_active:
            raise ServiceError(
                detail="Cannot pair with an inactive vehicle.",
                code="validation_error",
                status_code=400,
            )

    try:
        with transaction.atomic():
            vehicle = Vehicle.objects.create(
                owner=owner,
                kind=kind,
                vehicle_type=resolved_type,
                plate_number=normalized_plate,
                tech_passport_no=tech_passport_no,
                owner_full_name=owner_full_name,
                brand=brand,
                tech_passport_image=tech_passport_image,
                paired_vehicle=resolved_paired,
                is_active=is_active,
            )
            return vehicle
    except IntegrityError as exc:
        raise ServiceError(
            detail="Vehicle with this plate number already exists.",
            code="validation_error",
            status_code=400,
        ) from exc


def update_vehicle(vehicle: Vehicle, **data: Any) -> Vehicle:
    """Update an existing vehicle with validations."""
    with transaction.atomic():
        if "plate_number" in data:
            normalized_plate = normalize_plate_number(data["plate_number"])
            if not normalized_plate:
                raise ServiceError(
                    detail="Plate number is required.",
                    code="validation_error",
                    status_code=400,
                )
            if (
                Vehicle.objects.filter(plate_number=normalized_plate)
                .exclude(pk=vehicle.pk)
                .exists()
            ):
                raise ServiceError(
                    detail="Vehicle with this plate number already exists.",
                    code="validation_error",
                    status_code=400,
                )
            vehicle.plate_number = normalized_plate

        effective_kind = data.get("kind", vehicle.kind)

        if "vehicle_type" in data:
            v_type = data["vehicle_type"]
            if isinstance(v_type, int):
                v_type = VehicleType.objects.filter(pk=v_type).first()
                if data["vehicle_type"] is not None and v_type is None:
                    raise ServiceError(
                        detail="Vehicle type not found.",
                        code="validation_error",
                        status_code=400,
                    )
            vehicle.vehicle_type = v_type

        if vehicle.vehicle_type is not None and vehicle.vehicle_type.kind != effective_kind:
            raise ServiceError(
                detail="Vehicle type kind must match vehicle kind.",
                code="validation_error",
                status_code=400,
            )

        if "paired_vehicle" in data:
            p_vehicle = data["paired_vehicle"]
            if isinstance(p_vehicle, int):
                p_vehicle = Vehicle.objects.filter(pk=p_vehicle).first()
                if data["paired_vehicle"] is not None and p_vehicle is None:
                    raise ServiceError(
                        detail="Paired vehicle not found.",
                        code="validation_error",
                        status_code=400,
                    )
            if p_vehicle is not None:
                if p_vehicle.pk == vehicle.pk:
                    raise ServiceError(
                        detail="A vehicle cannot be paired with itself.",
                        code="validation_error",
                        status_code=400,
                    )
                if p_vehicle.owner_id != vehicle.owner_id:
                    raise ServiceError(
                        detail="Paired vehicle must belong to the same owner.",
                        code="validation_error",
                        status_code=400,
                    )
                if p_vehicle.kind == effective_kind:
                    raise ServiceError(
                        detail="Paired vehicle must have the opposite kind.",
                        code="validation_error",
                        status_code=400,
                    )
                if not p_vehicle.is_active:
                    raise ServiceError(
                        detail="Cannot pair with an inactive vehicle.",
                        code="validation_error",
                        status_code=400,
                    )
            vehicle.paired_vehicle = p_vehicle
        elif "kind" in data and vehicle.paired_vehicle is not None:
            if vehicle.paired_vehicle.kind == effective_kind:
                raise ServiceError(
                    detail="Paired vehicle must have the opposite kind.",
                    code="validation_error",
                    status_code=400,
                )

        if "kind" in data:
            vehicle.kind = effective_kind

        for field in ("tech_passport_no", "owner_full_name", "brand", "is_active"):
            if field in data:
                setattr(vehicle, field, data[field])

        if "tech_passport_image" in data:
            vehicle.tech_passport_image = data["tech_passport_image"]

        try:
            vehicle.save()
        except IntegrityError as exc:
            raise ServiceError(
                detail="Vehicle with this plate number already exists.",
                code="validation_error",
                status_code=400,
            ) from exc

        return vehicle


def deactivate_vehicle(vehicle: Vehicle) -> None:
    """Soft delete vehicle (set is_active=False) and unpair relations."""
    with transaction.atomic():
        # Unpair vehicles paired with this one
        Vehicle.objects.filter(paired_vehicle=vehicle).update(paired_vehicle=None)
        vehicle.paired_vehicle = None
        vehicle.is_active = False
        vehicle.save(update_fields=["is_active", "paired_vehicle", "updated_at"])
