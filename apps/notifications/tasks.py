"""Celery background tasks for notifications."""

import logging

from celery import shared_task

from apps.notifications.models import Notification

logger = logging.getLogger("apps.notifications")


@shared_task
def send_push(notification_id: int) -> None:
    """Send push notification stub.

    FCM delivery wiring will be implemented later and will query device tokens
    from `accounts.Device` (e.g., Device.objects.filter(user=notification.user)).
    Do NOT import accounts.Device here as it may not exist yet or be developed
    concurrently in another lane.
    """
    try:
        notification = Notification.objects.select_related("user").get(pk=notification_id)
    except Notification.DoesNotExist:
        logger.warning("Notification %s not found for push dispatch", notification_id)
        return

    logger.info("push to user %s type %s", notification.user_id, notification.type)
