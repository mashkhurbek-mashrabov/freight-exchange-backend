"""Tests for notification API endpoints."""

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.notifications.models import Notification
from apps.notifications.tests.factories import NotificationFactory, UserFactory


@pytest.fixture
def auth_client() -> tuple[APIClient, User]:
    """Return an APIClient authenticated with a test user."""
    user = UserFactory()
    client = APIClient()
    client.force_authenticate(user=user)
    return client, user


@pytest.mark.django_db
def test_endpoints_unauthenticated() -> None:
    """Verify all notification endpoints require authentication (401)."""
    client = APIClient()

    get_resp = client.get("/api/v1/notifications")
    assert get_resp.status_code == status.HTTP_401_UNAUTHORIZED
    assert get_resp.json()["code"] == "not_authenticated"

    read_resp = client.post("/api/v1/notifications/1/read")
    assert read_resp.status_code == status.HTTP_401_UNAUTHORIZED
    assert read_resp.json()["code"] == "not_authenticated"

    read_all_resp = client.post("/api/v1/notifications/read-all")
    assert read_all_resp.status_code == status.HTTP_401_UNAUTHORIZED
    assert read_all_resp.json()["code"] == "not_authenticated"


@pytest.mark.django_db
def test_list_notifications_only_own(auth_client: tuple[APIClient, User]) -> None:
    """Verify GET /notifications returns only the authenticated user's notifications."""
    client, user = auth_client
    other_user = UserFactory()

    user_notifs = NotificationFactory.create_batch(2, user=user)
    NotificationFactory.create_batch(3, user=other_user)

    response = client.get("/api/v1/notifications")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["count"] == 2
    assert len(data["results"]) == 2
    result_ids = [item["id"] for item in data["results"]]
    # Newest first
    assert result_ids == [user_notifs[1].pk, user_notifs[0].pk]


@pytest.mark.django_db
def test_list_notifications_unread_count_top_level(
    auth_client: tuple[APIClient, User],
) -> None:
    """Verify paginated response contains top-level unread_count."""
    client, user = auth_client

    NotificationFactory.create_batch(3, user=user, read_at=None)
    NotificationFactory(user=user, read_at=timezone.now())

    response = client.get("/api/v1/notifications")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["count"] == 4
    assert data["unread_count"] == 3
    assert "next" in data
    assert "previous" in data
    assert "results" in data


@pytest.mark.django_db
def test_list_notifications_filter_unread_true(
    auth_client: tuple[APIClient, User],
) -> None:
    """Verify ?unread=true filters to only unread notifications."""
    client, user = auth_client

    unreads = NotificationFactory.create_batch(2, user=user, read_at=None)
    NotificationFactory.create_batch(2, user=user, read_at=timezone.now())

    response = client.get("/api/v1/notifications?unread=true")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["count"] == 2
    assert data["unread_count"] == 2
    result_ids = {item["id"] for item in data["results"]}
    assert result_ids == {unreads[0].pk, unreads[1].pk}


@pytest.mark.django_db
def test_list_notifications_filter_unread_false(
    auth_client: tuple[APIClient, User],
) -> None:
    """Verify ?unread=false filters to only read notifications."""
    client, user = auth_client

    NotificationFactory.create_batch(2, user=user, read_at=None)
    reads = NotificationFactory.create_batch(2, user=user, read_at=timezone.now())

    response = client.get("/api/v1/notifications?unread=false")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["count"] == 2
    # unread_count remains the user's total unread notifications
    assert data["unread_count"] == 2
    result_ids = {item["id"] for item in data["results"]}
    assert result_ids == {reads[0].pk, reads[1].pk}


@pytest.mark.django_db
def test_mark_read_success_and_idempotent(
    auth_client: tuple[APIClient, User],
) -> None:
    """Verify POST /notifications/{id}/read marks as read idempotently and returns serializer."""
    client, user = auth_client
    notification = NotificationFactory(
        user=user,
        type=Notification.NotificationType.OFFER_RECEIVED,
        payload={"offer_id": 12},
        read_at=None,
    )

    response = client.post(f"/api/v1/notifications/{notification.pk}/read")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["id"] == notification.pk
    assert data["type"] == "offer_received"
    assert data["payload"] == {"offer_id": 12}
    assert data["read_at"] is not None
    initial_read_at = data["read_at"]

    # Call again to verify idempotency
    second_response = client.post(f"/api/v1/notifications/{notification.pk}/read")
    assert second_response.status_code == status.HTTP_200_OK
    assert second_response.json()["read_at"] == initial_read_at


@pytest.mark.django_db
def test_mark_read_other_users_notification_404(
    auth_client: tuple[APIClient, User],
) -> None:
    """Verify POST /notifications/{id}/read returns 404 for other user's notification."""
    client, _ = auth_client
    other_user = UserFactory()
    other_notification = NotificationFactory(user=other_user)

    response = client.post(f"/api/v1/notifications/{other_notification.pk}/read")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["code"] == "not_found"


@pytest.mark.django_db
def test_mark_read_nonexistent_404(
    auth_client: tuple[APIClient, User],
) -> None:
    """Verify POST /notifications/{id}/read returns 404 for nonexistent id."""
    client, _ = auth_client

    response = client.post("/api/v1/notifications/999999/read")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["code"] == "not_found"


@pytest.mark.django_db
def test_mark_all_read_endpoint(
    auth_client: tuple[APIClient, User],
) -> None:
    """Verify POST /notifications/read-all marks all unread and returns {"updated": n}."""
    client, user = auth_client
    other_user = UserFactory()

    # User has 3 unread, 1 read
    NotificationFactory.create_batch(3, user=user, read_at=None)
    NotificationFactory(user=user, read_at=timezone.now())

    # Other user has 2 unread
    other_notif = NotificationFactory(user=other_user, read_at=None)

    response = client.post("/api/v1/notifications/read-all")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"updated": 3}

    # Verify all user notifications now read
    assert Notification.objects.filter(user=user, read_at__isnull=True).count() == 0

    # Other user still unread
    other_notif.refresh_from_db()
    assert other_notif.read_at is None

    # Call again returns {"updated": 0}
    second_response = client.post("/api/v1/notifications/read-all")
    assert second_response.status_code == status.HTTP_200_OK
    assert second_response.json() == {"updated": 0}
