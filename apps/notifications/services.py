"""Notification domain services."""

from typing import Any

from django.db import transaction
from django.http import Http404
from django.utils import timezone

from apps.notifications.models import Notification
from apps.notifications.tasks import send_push


def notify(
    user: Any,
    type: str,
    payload: dict[str, Any] | None = None,
) -> Notification:
    """Create a notification row and dispatch a push notification task on commit.

    Creates the row inside the caller's transaction and schedules send_push
    via transaction.on_commit to ensure notifications are only pushed if the
    enclosing transaction successfully commits.
    """
    if payload is None:
        payload = {}

    notification = Notification.objects.create(
        user=user,
        type=type,
        payload=payload,
    )
    transaction.on_commit(lambda: send_push.delay(notification.pk))
    return notification


def mark_read(user: Any, pk: int) -> Notification:
    """Mark a notification as read idempotently.

    Raises Http404 if the notification does not exist or belongs to another user.
    """
    try:
        notification = Notification.objects.get(pk=pk, user=user)
    except Notification.DoesNotExist:
        raise Http404("Notification not found.") from None

    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at", "updated_at"])

    return notification


def mark_all_read(user: Any) -> int:
    """Mark all unread notifications for a user as read.

    Returns the count of updated notifications.
    """
    now = timezone.now()
    return Notification.objects.filter(user=user, read_at__isnull=True).update(
        read_at=now,
        updated_at=now,
    )


def unread_count(user: Any) -> int:
    """Return the total number of unread notifications for a user."""
    return Notification.objects.filter(user=user, read_at__isnull=True).count()
