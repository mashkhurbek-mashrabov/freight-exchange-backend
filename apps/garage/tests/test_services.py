"""Tests for garage services."""

import pytest

from apps.accounts.models import User
from apps.core.exceptions import ServiceError
from apps.garage import services
from apps.garage.models import VehicleKind
from apps.garage.tests.factories import VehicleFactory, VehicleTypeFactory


@pytest.mark.django_db
def test_create_vehicle_success() -> None:
    owner = User.objects.create_user(phone="+998901111111")
    v_type = VehicleTypeFactory(kind=VehicleKind.TRACTOR)

    vehicle = services.create_vehicle(
        owner=owner,
        kind=VehicleKind.TRACTOR,
        plate_number=" 01 a 123 aa ",
        vehicle_type=v_type,
        brand="Mercedes",
        tech_passport_no="AAF123",
        owner_full_name="Driver One",
    )

    assert vehicle.pk is not None
    assert vehicle.plate_number == "01A123AA"
    assert vehicle.kind == VehicleKind.TRACTOR
    assert vehicle.vehicle_type == v_type
    assert vehicle.is_active is True


@pytest.mark.django_db
def test_create_vehicle_duplicate_plate_raises_error() -> None:
    owner = User.objects.create_user(phone="+998901111112")
    VehicleFactory(owner=owner, plate_number="01A999AA")

    with pytest.raises(ServiceError) as exc_info:
        services.create_vehicle(
            owner=owner,
            kind=VehicleKind.TRACTOR,
            plate_number=" 01 a 999 aa ",
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "validation_error"


@pytest.mark.django_db
def test_create_vehicle_pairing_wrong_kind_raises_error() -> None:
    owner = User.objects.create_user(phone="+998901111113")
    tractor1 = VehicleFactory(owner=owner, kind=VehicleKind.TRACTOR)

    with pytest.raises(ServiceError) as exc_info:
        services.create_vehicle(
            owner=owner,
            kind=VehicleKind.TRACTOR,
            plate_number="01B111BB",
            paired_vehicle=tractor1,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "validation_error"
    assert "opposite kind" in exc_info.value.detail


@pytest.mark.django_db
def test_create_vehicle_pairing_other_owner_raises_error() -> None:
    owner1 = User.objects.create_user(phone="+998901111114")
    owner2 = User.objects.create_user(phone="+998901111115")
    trailer = VehicleFactory(owner=owner2, kind=VehicleKind.TRAILER)

    with pytest.raises(ServiceError) as exc_info:
        services.create_vehicle(
            owner=owner1,
            kind=VehicleKind.TRACTOR,
            plate_number="01B222BB",
            paired_vehicle=trailer,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "validation_error"
    assert "same owner" in exc_info.value.detail


@pytest.mark.django_db
def test_create_vehicle_type_kind_mismatch_raises_error() -> None:
    owner = User.objects.create_user(phone="+998901111116")
    trailer_type = VehicleTypeFactory(kind=VehicleKind.TRAILER)

    with pytest.raises(ServiceError) as exc_info:
        services.create_vehicle(
            owner=owner,
            kind=VehicleKind.TRACTOR,
            plate_number="01B333BB",
            vehicle_type=trailer_type,
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "validation_error"
    assert "must match vehicle kind" in exc_info.value.detail


@pytest.mark.django_db
def test_update_vehicle_success() -> None:
    owner = User.objects.create_user(phone="+998901111117")
    vehicle = VehicleFactory(owner=owner, kind=VehicleKind.TRACTOR, brand="Scania")
    trailer = VehicleFactory(owner=owner, kind=VehicleKind.TRAILER)

    updated = services.update_vehicle(
        vehicle,
        brand="Volvo",
        paired_vehicle=trailer,
    )

    assert updated.brand == "Volvo"
    assert updated.paired_vehicle == trailer


@pytest.mark.django_db
def test_deactivate_vehicle_unpairs_and_sets_inactive() -> None:
    owner = User.objects.create_user(phone="+998901111118")
    trailer = VehicleFactory(owner=owner, kind=VehicleKind.TRAILER)
    tractor = VehicleFactory(owner=owner, kind=VehicleKind.TRACTOR, paired_vehicle=trailer)

    # Both are active and tractor points to trailer
    assert tractor.paired_vehicle == trailer

    # Deactivate trailer
    services.deactivate_vehicle(trailer)

    trailer.refresh_from_db()
    tractor.refresh_from_db()

    assert trailer.is_active is False
    assert tractor.paired_vehicle is None
