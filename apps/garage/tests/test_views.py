"""Tests for garage API views."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.garage.models import Vehicle, VehicleKind
from apps.garage.tests.factories import VehicleFactory


@pytest.mark.django_db
def test_auth_required_for_all_endpoints() -> None:
    client = APIClient()

    # GET vehicle-types
    res = client.get("/api/v1/vehicle-types")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert res.json()["code"] == "not_authenticated"

    # GET vehicles
    res = client.get("/api/v1/vehicles")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert res.json()["code"] == "not_authenticated"

    # POST vehicles
    res = client.post("/api/v1/vehicles", data={"kind": "tractor", "plate_number": "01A123AA"})
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert res.json()["code"] == "not_authenticated"

    # GET / PATCH / DELETE vehicle detail
    res = client.get("/api/v1/vehicles/1")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert res.json()["code"] == "not_authenticated"

    res = client.patch("/api/v1/vehicles/1", data={"brand": "MAN"})
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert res.json()["code"] == "not_authenticated"

    res = client.delete("/api/v1/vehicles/1")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert res.json()["code"] == "not_authenticated"


@pytest.mark.django_db
def test_vehicle_types_fixture_loads_and_filter_by_kind() -> None:
    call_command("loaddata", "apps/garage/fixtures/vehicle_types.json")

    user = User.objects.create_user(phone="+998902222221")
    client = APIClient()
    client.force_authenticate(user=user)

    # All vehicle types
    res = client.get("/api/v1/vehicle-types")
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert len(data) >= 24
    # Unpaginated list response
    assert isinstance(data, list)

    # Filter tractors
    res_tractors = client.get("/api/v1/vehicle-types?kind=tractor")
    assert res_tractors.status_code == status.HTTP_200_OK
    tractors = res_tractors.json()
    assert len(tractors) >= 4
    assert all(item["kind"] == "tractor" for item in tractors)

    # Filter trailers
    res_trailers = client.get("/api/v1/vehicle-types?kind=trailer")
    assert res_trailers.status_code == status.HTTP_200_OK
    trailers = res_trailers.json()
    assert len(trailers) >= 20
    assert all(item["kind"] == "trailer" for item in trailers)


@pytest.mark.django_db
def test_user_sees_only_own_vehicles() -> None:
    user1 = User.objects.create_user(phone="+998902222222")
    user2 = User.objects.create_user(phone="+998902222223")

    v1 = VehicleFactory(owner=user1, plate_number="01A111AA")
    v2 = VehicleFactory(owner=user1, plate_number="01A222AA")
    VehicleFactory(owner=user2, plate_number="01A333AA")

    client = APIClient()
    client.force_authenticate(user=user1)

    res = client.get("/api/v1/vehicles")
    assert res.status_code == status.HTTP_200_OK
    results = res.json()["results"]
    assert len(results) == 2
    plate_numbers = {item["plate_number"] for item in results}
    assert plate_numbers == {v1.plate_number, v2.plate_number}


@pytest.mark.django_db
def test_plate_normalized_and_duplicate_plate_returns_400() -> None:
    user = User.objects.create_user(phone="+998902222224")
    client = APIClient()
    client.force_authenticate(user=user)

    # Create vehicle with spaces and lowercase
    res = client.post(
        "/api/v1/vehicles",
        data={
            "kind": "tractor",
            "plate_number": " 01 a 123 aa ",
            "brand": "Mercedes",
        },
    )
    assert res.status_code == status.HTTP_201_CREATED
    data = res.json()
    assert data["plate_number"] == "01A123AA"

    # Verify directly in DB that it is stored normalized
    vehicle_in_db = Vehicle.objects.get(pk=data["id"])
    assert vehicle_in_db.plate_number == "01A123AA"

    # Attempt to create duplicate with identical plate
    res_dup1 = client.post(
        "/api/v1/vehicles",
        data={
            "kind": "tractor",
            "plate_number": "01A123AA",
        },
    )
    assert res_dup1.status_code == status.HTTP_400_BAD_REQUEST
    assert res_dup1.json()["code"] == "validation_error"

    # Attempt to create duplicate with differently formatted plate
    res_dup2 = client.post(
        "/api/v1/vehicles",
        data={
            "kind": "tractor",
            "plate_number": "01 A 123 AA",
        },
    )
    assert res_dup2.status_code == status.HTTP_400_BAD_REQUEST
    assert res_dup2.json()["code"] == "validation_error"

    # Attempt to create duplicate with leading/trailing spaces and lower case
    res_dup3 = client.post(
        "/api/v1/vehicles",
        data={
            "kind": "trailer",
            "plate_number": "  01a123aa  ",
        },
    )
    assert res_dup3.status_code == status.HTTP_400_BAD_REQUEST
    assert res_dup3.json()["code"] == "validation_error"


@pytest.mark.django_db
def test_pairing_wrong_kind_returns_400() -> None:
    user = User.objects.create_user(phone="+998902222225")
    tractor1 = VehicleFactory(owner=user, kind=VehicleKind.TRACTOR, plate_number="01A555AA")

    client = APIClient()
    client.force_authenticate(user=user)

    # Attempt to pair tractor with another tractor
    res = client.post(
        "/api/v1/vehicles",
        data={
            "kind": "tractor",
            "plate_number": "01A666AA",
            "paired_vehicle_id": tractor1.id,
        },
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.json()["code"] == "validation_error"


@pytest.mark.django_db
def test_pairing_other_owner_returns_400() -> None:
    user1 = User.objects.create_user(phone="+998902222226")
    user2 = User.objects.create_user(phone="+998902222227")
    user2_trailer = VehicleFactory(owner=user2, kind=VehicleKind.TRAILER, plate_number="01A777AA")

    client = APIClient()
    client.force_authenticate(user=user1)

    # User 1 tries to pair with User 2's trailer
    res = client.post(
        "/api/v1/vehicles",
        data={
            "kind": "tractor",
            "plate_number": "01A888AA",
            "paired_vehicle_id": user2_trailer.id,
        },
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.json()["code"] == "validation_error"


@pytest.mark.django_db
def test_soft_delete_hides_from_list_and_detail() -> None:
    user = User.objects.create_user(phone="+998902222228")
    vehicle = VehicleFactory(owner=user, plate_number="01A999AA")

    client = APIClient()
    client.force_authenticate(user=user)

    # Ensure it appears initially in list
    res = client.get("/api/v1/vehicles")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["count"] == 1

    # Delete vehicle
    res_delete = client.delete(f"/api/v1/vehicles/{vehicle.id}")
    assert res_delete.status_code == status.HTTP_204_NO_CONTENT

    # Ensure it no longer appears in list
    res_list_after = client.get("/api/v1/vehicles")
    assert res_list_after.status_code == status.HTTP_200_OK
    assert res_list_after.json()["count"] == 0

    # Detail now returns 404
    res_detail = client.get(f"/api/v1/vehicles/{vehicle.id}")
    assert res_detail.status_code == status.HTTP_404_NOT_FOUND
    assert res_detail.json()["code"] == "not_found"


@pytest.mark.django_db
def test_others_vehicle_returns_404() -> None:
    user1 = User.objects.create_user(phone="+998902222229")
    user2 = User.objects.create_user(phone="+998902222230")
    vehicle = VehicleFactory(owner=user2, plate_number="01B111BB")

    client = APIClient()
    client.force_authenticate(user=user1)

    # Detail
    res = client.get(f"/api/v1/vehicles/{vehicle.id}")
    assert res.status_code == status.HTTP_404_NOT_FOUND
    assert res.json()["code"] == "not_found"

    # Patch
    res = client.patch(f"/api/v1/vehicles/{vehicle.id}", data={"brand": "DAF"})
    assert res.status_code == status.HTTP_404_NOT_FOUND
    assert res.json()["code"] == "not_found"

    # Delete
    res = client.delete(f"/api/v1/vehicles/{vehicle.id}")
    assert res.status_code == status.HTTP_404_NOT_FOUND
    assert res.json()["code"] == "not_found"


@pytest.mark.django_db
def test_kind_filter_on_vehicles() -> None:
    user = User.objects.create_user(phone="+998902222231")
    VehicleFactory(owner=user, kind=VehicleKind.TRACTOR, plate_number="01C111CC")
    VehicleFactory(owner=user, kind=VehicleKind.TRAILER, plate_number="01C222CC")

    client = APIClient()
    client.force_authenticate(user=user)

    res_all = client.get("/api/v1/vehicles")
    assert res_all.status_code == status.HTTP_200_OK
    assert res_all.json()["count"] == 2

    res_tractors = client.get("/api/v1/vehicles?kind=tractor")
    assert res_tractors.status_code == status.HTTP_200_OK
    assert res_tractors.json()["count"] == 1
    assert res_tractors.json()["results"][0]["kind"] == "tractor"

    res_trailers = client.get("/api/v1/vehicles?kind=trailer")
    assert res_trailers.status_code == status.HTTP_200_OK
    assert res_trailers.json()["count"] == 1
    assert res_trailers.json()["results"][0]["kind"] == "trailer"


@pytest.mark.django_db
def test_multipart_image_upload_and_patch_vehicle() -> None:
    user = User.objects.create_user(phone="+998902222232")
    trailer = VehicleFactory(owner=user, kind=VehicleKind.TRAILER, plate_number="01D222DD")

    client = APIClient()
    client.force_authenticate(user=user)

    image_content = (
        b"\x47\x49\x46\x38\x39\x61\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff"
        b"\x00\x00\x00\x21\xf9\x04\x01\x00\x00\x00\x00\x2c\x00\x00\x00\x00"
        b"\x01\x00\x01\x00\x00\x02\x02\x44\x01\x00\x3b"
    )
    image_file = SimpleUploadedFile("passport.gif", image_content, content_type="image/gif")

    # POST multipart
    res = client.post(
        "/api/v1/vehicles",
        data={
            "kind": "tractor",
            "plate_number": "01D111DD",
            "brand": "Mercedes",
            "tech_passport_image": image_file,
            "paired_vehicle_id": trailer.id,
        },
        format="multipart",
    )
    assert res.status_code == status.HTTP_201_CREATED
    data = res.json()
    assert data["plate_number"] == "01D111DD"
    assert data["paired_vehicle_id"] == trailer.id
    assert data["tech_passport_image"] is not None

    vehicle_id = data["id"]

    # PATCH vehicle
    res_patch = client.patch(
        f"/api/v1/vehicles/{vehicle_id}",
        data={
            "brand": "Mercedes-Benz Actros",
            "owner_full_name": "Updated Name",
        },
    )
    assert res_patch.status_code == status.HTTP_200_OK
    patch_data = res_patch.json()
    assert patch_data["brand"] == "Mercedes-Benz Actros"
    assert patch_data["owner_full_name"] == "Updated Name"
