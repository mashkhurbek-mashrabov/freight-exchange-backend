"""Tests for profile, company, and device endpoints."""

import io

import pytest
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Company, Device, User
from apps.accounts.tests.factories import CompanyFactory, DeviceFactory, UserFactory


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


def generate_test_image() -> io.BytesIO:
    """Generate a dummy image for testing file uploads."""
    file = io.BytesIO()
    image = Image.new("RGBA", size=(100, 100), color=(155, 0, 0))
    image.save(file, "png")
    file.name = "test_avatar.png"
    file.seek(0)
    return file


@pytest.mark.django_db
def test_me_get_unauthenticated(api_client: APIClient) -> None:
    """GET /me requires authentication and returns 401."""
    response = api_client.get("/api/v1/me")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["code"] == "not_authenticated"


@pytest.mark.django_db
def test_me_get_authenticated(api_client: APIClient) -> None:
    """GET /me returns user profile."""
    user = UserFactory(full_name="Alisher Navoi", role=User.Role.SHIPPER)
    api_client.force_authenticate(user=user)

    response = api_client.get("/api/v1/me")
    assert response.status_code == status.HTTP_200_OK
    assert response.data["phone"] == user.phone
    assert response.data["full_name"] == "Alisher Navoi"
    assert response.data["role"] == "shipper"
    assert response.data["company"] is None


@pytest.mark.django_db
def test_me_patch_profile_and_status_ignored(api_client: APIClient) -> None:
    """PATCH /me updates writable fields, but ignores status changes."""
    user = UserFactory(status=User.Status.NEW)
    api_client.force_authenticate(user=user)

    response = api_client.patch(
        "/api/v1/me",
        {
            "full_name": "Updated Name",
            "role": "both",
            "language": "uz",
            "status": "verified",  # Attempt to self-verify must be ignored
        },
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["full_name"] == "Updated Name"
    assert response.data["role"] == "both"
    assert response.data["language"] == "uz"
    assert response.data["status"] == User.Status.NEW

    user.refresh_from_db()
    assert user.full_name == "Updated Name"
    assert user.status == User.Status.NEW


@pytest.mark.django_db
def test_me_patch_avatar_upload(api_client: APIClient) -> None:
    """PATCH /me supports multipart avatar upload."""
    user = UserFactory()
    api_client.force_authenticate(user=user)

    avatar = generate_test_image()
    response = api_client.patch(
        "/api/v1/me",
        {"avatar": avatar},
        format="multipart",
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["avatar"] is not None

    user.refresh_from_db()
    assert bool(user.avatar) is True


@pytest.mark.django_db
def test_me_company_create_and_update(api_client: APIClient) -> None:
    """PUT /me/company creates and updates company profile."""
    user = UserFactory()
    api_client.force_authenticate(user=user)

    # 1. Create company
    res_create = api_client.put(
        "/api/v1/me/company",
        {"name": "TransLogistics LLC", "tin": "123456789", "address": "Tashkent"},
        format="json",
    )
    assert res_create.status_code == status.HTTP_200_OK
    assert res_create.data["name"] == "TransLogistics LLC"
    assert res_create.data["tin"] == "123456789"
    assert Company.objects.filter(owner=user).count() == 1

    # 2. Update company
    res_update = api_client.put(
        "/api/v1/me/company",
        {"name": "TransLogistics Global", "tin": "123456789", "address": "Samarkand"},
        format="json",
    )
    assert res_update.status_code == status.HTTP_200_OK
    assert res_update.data["name"] == "TransLogistics Global"
    assert res_update.data["address"] == "Samarkand"
    assert Company.objects.filter(owner=user).count() == 1


@pytest.mark.django_db
def test_me_company_duplicate_tin_conflict(api_client: APIClient) -> None:
    """PUT /me/company with duplicate TIN of another company returns 409."""
    other_user = UserFactory()
    CompanyFactory(owner=other_user, tin="987654321")

    current_user = UserFactory()
    api_client.force_authenticate(user=current_user)

    response = api_client.put(
        "/api/v1/me/company",
        {"name": "Another Company", "tin": "987654321"},
        format="json",
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data["code"] == "conflict"


@pytest.mark.django_db
def test_me_devices_register_and_reassign(api_client: APIClient) -> None:
    """POST /me/devices registers token or moves it from previous user."""
    user1 = UserFactory()
    user2 = UserFactory()

    # 1. user1 registers token
    api_client.force_authenticate(user=user1)
    res1 = api_client.post(
        "/api/v1/me/devices",
        {"fcm_token": "token_abc_123", "platform": "android"},
        format="json",
    )
    assert res1.status_code == status.HTTP_201_CREATED
    assert res1.data["fcm_token"] == "token_abc_123"

    device = Device.objects.get(fcm_token="token_abc_123")
    assert device.user == user1

    # 2. user2 registers the same token -> moves to user2, returns 200
    api_client.force_authenticate(user=user2)
    res2 = api_client.post(
        "/api/v1/me/devices",
        {"fcm_token": "token_abc_123", "platform": "ios"},
        format="json",
    )
    assert res2.status_code == status.HTTP_200_OK
    device.refresh_from_db()
    assert device.user == user2
    assert device.platform == "ios"


@pytest.mark.django_db
def test_me_devices_delete(api_client: APIClient) -> None:
    """DELETE /me/devices/{token} removes the device."""
    user = UserFactory()
    DeviceFactory(user=user, fcm_token="token_to_delete")
    api_client.force_authenticate(user=user)

    response = api_client.delete("/api/v1/me/devices/token_to_delete")
    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert not Device.objects.filter(fcm_token="token_to_delete").exists()
