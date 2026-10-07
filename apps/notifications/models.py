"""Notifications model definitions."""

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class Notification(BaseModel):
    """Notification model for user alerts."""

    class NotificationType(models.TextChoices):
        OFFER_RECEIVED = "offer_received", "Offer Received"
        OFFER_ACCEPTED = "offer_accepted", "Offer Accepted"
        OFFER_REJECTED = "offer_rejected", "Offer Rejected"
        OFFER_COUNTERED = "offer_countered", "Offer Countered"
        ORDER_STATUS = "order_status", "Order Status"
        ACCOUNT_VERIFIED = "account_verified", "Account Verified"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    type = models.CharField(
        max_length=30,
        choices=NotificationType.choices,
    )
    payload = models.JSONField(
        default=dict,
        blank=True,
    )
    read_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["user", "read_at", "-created_at"],
                name="notif_user_read_created_idx",
            ),
        ]

    def __str__(self) -> str:
        """Return human-readable notification description."""
        status_str = "read" if self.read_at else "unread"
        return f"Notification {self.pk}: {self.type} for user {self.user_id} ({status_str})"
