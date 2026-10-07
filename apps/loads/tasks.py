"""Celery background tasks for loads app."""

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.loads.models import Load
from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.offers.models import Offer


@shared_task
def expire_loads() -> int:
    """Expire active loads past their expiration timestamp and reject pending offers.

    Returns the total number of loads transitioned to expired status.
    """
    now = timezone.now()
    expired_ids = list(
        Load.objects.filter(
            status=Load.Status.ACTIVE,
            expires_at__lt=now,
        ).values_list("id", flat=True)
    )

    if not expired_ids:
        return 0

    count = 0
    for load_id in expired_ids:
        with transaction.atomic():
            locked_load = (
                Load.objects.select_for_update()
                .filter(pk=load_id, status=Load.Status.ACTIVE, expires_at__lt=now)
                .first()
            )
            if not locked_load:
                continue

            locked_load.status = Load.Status.EXPIRED
            locked_load.save(update_fields=["status", "updated_at"])
            count += 1

            pending_offers = locked_load.offers.select_for_update().filter(
                status=Offer.Status.PENDING
            )
            for offer in pending_offers:
                offer.status = Offer.Status.REJECTED
                offer.responded_at = now
                offer.save(update_fields=["status", "responded_at", "updated_at"])
                notify(
                    offer.carrier,
                    Notification.NotificationType.OFFER_REJECTED,
                    {
                        "load_id": locked_load.id,
                        "offer_id": offer.id,
                        "reason": "load_expired",
                    },
                )

    return count
