"""Tests for Notification model."""

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.notifications.models import Notification
from apps.notifications.tests.factories import NotificationFactory, UserFactory


@pytest.mark.django_db
def test_notification_creation_and_defaults() -> None:
    """Verify Notification model creation and default values."""
    user = User.objects.create_user(phone="+998901234501")
    notification = Notification.objects.create(
        user=user,
        type=Notification.NotificationType.OFFER_RECEIVED,
    )

    assert notification.pk is not None
    assert notification.user == user
    assert notification.type == "offer_received"
    assert notification.payload == {}
    assert notification.read_at is None
    assert notification.created_at is not None
    assert notification.updated_at is not None
    assert "unread" in str(notification)


@pytest.mark.django_db
def test_notification_str_read_state() -> None:
    """Verify Notification __str__ changes when read_at is set."""
    notification = NotificationFactory(read_at=timezone.now())
    assert "read" in str(notification)


@pytest.mark.django_db
def test_notification_ordering_newest_first() -> None:
    """Verify default ordering is newest first (-created_at)."""
    user = UserFactory()
    n1 = NotificationFactory(user=user)
    n2 = NotificationFactory(user=user)

    notifications = list(Notification.objects.filter(user=user))
    assert notifications == [n2, n1]
