"""Tests for notification background tasks."""

import logging

import pytest

from apps.notifications.models import Notification
from apps.notifications.tasks import send_push
from apps.notifications.tests.factories import NotificationFactory


@pytest.mark.django_db
def test_send_push_eager_execution_logs_correctly(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify send_push task executes eagerly and logs expected push message."""
    notification = NotificationFactory(
        type=Notification.NotificationType.OFFER_RECEIVED,
    )

    with caplog.at_level(logging.INFO, logger="apps.notifications"):
        result = send_push.delay(notification.pk)

    assert result.successful()
    expected_message = f"push to user {notification.user_id} type {notification.type}"
    assert any(
        record.name == "apps.notifications"
        and record.levelno == logging.INFO
        and expected_message in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.django_db
def test_send_push_missing_notification_handled_gracefully(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify send_push logs warning and returns cleanly if notification does not exist."""
    with caplog.at_level(logging.WARNING, logger="apps.notifications"):
        result = send_push.delay(999999)

    assert result.successful()
    assert any(
        record.name == "apps.notifications"
        and record.levelno == logging.WARNING
        and "999999 not found" in record.getMessage()
        for record in caplog.records
    )
