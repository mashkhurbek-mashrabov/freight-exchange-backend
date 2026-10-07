"""Tests for notification domain services."""

from unittest.mock import patch

import pytest
from django.db import transaction
from django.http import Http404
from django.utils import timezone

from apps.notifications.models import Notification
from apps.notifications.services import mark_all_read, mark_read, notify, unread_count
from apps.notifications.tests.factories import NotificationFactory, UserFactory


@pytest.mark.django_db
def test_notify_creates_row() -> None:
    """Verify notify service creates a Notification row with correct fields."""
    user = UserFactory()
    payload = {"load_id": 42, "amount": "1500.00"}

    with patch("apps.notifications.services.send_push.delay"):
        notification = notify(
            user=user,
            type=Notification.NotificationType.OFFER_RECEIVED,
            payload=payload,
        )

    assert notification.pk is not None
    assert notification.user == user
    assert notification.type == Notification.NotificationType.OFFER_RECEIVED
    assert notification.payload == payload
    assert notification.read_at is None

    # Check persistence
    fetched = Notification.objects.get(pk=notification.pk)
    assert fetched.payload == payload


@pytest.mark.django_db
def test_notify_on_commit_dispatches_task_exactly_once(
    django_capture_on_commit_callbacks: pytest.FixtureRequest,
) -> None:
    """Verify on_commit dispatches send_push.delay exactly once with notification.pk."""
    user = UserFactory()

    with patch("apps.notifications.services.send_push.delay") as mock_delay:
        with django_capture_on_commit_callbacks(execute=True) as callbacks:
            notification = notify(
                user=user,
                type=Notification.NotificationType.OFFER_ACCEPTED,
                payload={"order_id": 99},
            )

        assert len(callbacks) == 1
        mock_delay.assert_called_once_with(notification.pk)


@pytest.mark.django_db
def test_notify_rolled_back_transaction_creates_no_task_call(
    django_capture_on_commit_callbacks: pytest.FixtureRequest,
) -> None:
    """Verify rolled-back transaction creates no task call and commits no row."""
    user = UserFactory()

    with patch("apps.notifications.services.send_push.delay") as mock_delay:
        with django_capture_on_commit_callbacks(execute=True) as callbacks:
            try:
                with transaction.atomic():
                    notify(
                        user=user,
                        type=Notification.NotificationType.OFFER_REJECTED,
                        payload={"reason": "price too low"},
                    )
                    raise RuntimeError("Simulated transaction rollback")
            except RuntimeError:
                pass

        assert len(callbacks) == 0
        mock_delay.assert_not_called()
        assert Notification.objects.count() == 0


@pytest.mark.django_db
def test_mark_read_sets_read_at() -> None:
    """Verify mark_read sets read_at timestamp."""
    user = UserFactory()
    notification = NotificationFactory(user=user, read_at=None)

    updated = mark_read(user=user, pk=notification.pk)
    assert updated.read_at is not None
    assert updated.pk == notification.pk

    notification.refresh_from_db()
    assert notification.read_at is not None


@pytest.mark.django_db
def test_mark_read_idempotent() -> None:
    """Verify mark_read is idempotent and preserves the initial read_at timestamp."""
    user = UserFactory()
    notification = NotificationFactory(user=user, read_at=None)

    first_result = mark_read(user=user, pk=notification.pk)
    initial_read_at = first_result.read_at

    # Subsequent call
    second_result = mark_read(user=user, pk=notification.pk)
    assert second_result.read_at == initial_read_at

    notification.refresh_from_db()
    assert notification.read_at == initial_read_at


@pytest.mark.django_db
def test_mark_read_other_user_raises_404() -> None:
    """Verify mark_read raises Http404 for other user's notification."""
    user1 = UserFactory()
    user2 = UserFactory()
    notification = NotificationFactory(user=user1)

    with pytest.raises(Http404, match="Notification not found."):
        mark_read(user=user2, pk=notification.pk)


@pytest.mark.django_db
def test_mark_read_nonexistent_raises_404() -> None:
    """Verify mark_read raises Http404 for non-existent pk."""
    user = UserFactory()

    with pytest.raises(Http404, match="Notification not found."):
        mark_read(user=user, pk=999999)


@pytest.mark.django_db
def test_mark_all_read() -> None:
    """Verify mark_all_read marks only the user's unread notifications."""
    user1 = UserFactory()
    user2 = UserFactory()

    # User 1: 3 unread, 1 already read
    NotificationFactory.create_batch(3, user=user1, read_at=None)
    already_read = NotificationFactory(user=user1, read_at=timezone.now())

    # User 2: 2 unread
    user2_notif = NotificationFactory(user=user2, read_at=None)

    count_updated = mark_all_read(user=user1)
    assert count_updated == 3

    # All user1 notifications should now be read
    assert Notification.objects.filter(user=user1, read_at__isnull=True).count() == 0
    # Already read was not changed
    already_read.refresh_from_db()
    assert already_read.read_at is not None
    # User 2 notifications untouched
    user2_notif.refresh_from_db()
    assert user2_notif.read_at is None

    # Running again updates 0
    assert mark_all_read(user=user1) == 0


@pytest.mark.django_db
def test_unread_count() -> None:
    """Verify unread_count returns correct count for user."""
    user = UserFactory()
    other_user = UserFactory()

    assert unread_count(user) == 0

    NotificationFactory.create_batch(4, user=user, read_at=None)
    NotificationFactory(user=user, read_at=timezone.now())
    NotificationFactory(user=other_user, read_at=None)

    assert unread_count(user) == 4
