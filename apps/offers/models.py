"""Offers model definitions."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import BaseModel


class Offer(BaseModel):
    """Offer or bid submitted on a load."""

    class Mode(models.TextChoices):
        COMMENT_ONLY = "comment_only", "Comment Only"
        PRICE_BID = "price_bid", "Price Bid"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"
        COUNTERED = "countered", "Countered"

    load = models.ForeignKey(
        "loads.Load",
        on_delete=models.CASCADE,
        related_name="offers",
    )
    carrier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="offers_as_carrier",
    )
    proposer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="offers_proposed",
    )
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="offers_received",
    )
    vehicle = models.ForeignKey(
        "garage.Vehicle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    trailer = models.ForeignKey(
        "garage.Vehicle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="counters",
    )
    mode = models.CharField(
        max_length=20,
        choices=Mode.choices,
        default=Mode.PRICE_BID,
    )
    amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
    )
    currency = models.ForeignKey(
        "geo.Currency",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    comment = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    responded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Offer"
        verbose_name_plural = "Offers"
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["load", "carrier"],
                condition=models.Q(status="pending"),
                name="unique_pending_offer_per_carrier_load",
            ),
            models.CheckConstraint(
                condition=~models.Q(proposer=models.F("recipient")),
                name="check_offer_proposer_not_recipient",
            ),
            models.CheckConstraint(
                condition=~models.Q(mode="price_bid") | models.Q(amount__isnull=False),
                name="check_offer_price_bid_requires_amount",
            ),
        ]

    def __str__(self) -> str:
        return f"Offer #{self.pk}: Load #{self.load_id} ({self.status})"

    def clean(self) -> None:
        """Validate proposer vs recipient and price_bid amount requirement."""
        super().clean()
        if self.proposer_id and self.recipient_id and self.proposer_id == self.recipient_id:
            raise ValidationError({"recipient": "Proposer and recipient cannot be the same user."})
        if self.mode == self.Mode.PRICE_BID and self.amount is None:
            raise ValidationError({"amount": "Amount is required when mode is price_bid."})
