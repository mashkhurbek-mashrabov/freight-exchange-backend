"""Orders model definitions."""

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import BaseModel


class Order(BaseModel):
    """Execution contract between shipper and carrier created upon offer acceptance."""

    class Status(models.TextChoices):
        CREATED = "created", "Created"
        RECEIVED = "received", "Received"
        PICKED_UP = "picked_up", "Picked Up"
        DELIVERED = "delivered", "Delivered"
        AWAITING_CONFIRM = "awaiting_confirm", "Awaiting Confirm"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    offer = models.OneToOneField(
        "offers.Offer",
        on_delete=models.CASCADE,
        related_name="order",
    )
    load = models.ForeignKey(
        "loads.Load",
        on_delete=models.CASCADE,
        related_name="orders",
    )
    shipper = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders_as_shipper",
    )
    carrier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="orders_as_carrier",
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
    agreed_amount = models.DecimalField(
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
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.CREATED,
    )
    cancel_reason = models.TextField(blank=True, default="")
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Order"
        verbose_name_plural = "Orders"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["status", "-created_at"], name="order_status_created_idx"),
        ]

    def __str__(self) -> str:
        return f"Order #{self.pk}: Load #{self.load_id} ({self.status})"


class OrderStatusEvent(models.Model):
    """Audit log entry recorded on each order status transition."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="status_events",
    )
    status = models.CharField(
        max_length=20,
        choices=Order.Status.choices,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_status_events",
    )
    note = models.TextField(blank=True, default="")
    at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Order Status Event"
        verbose_name_plural = "Order Status Events"
        ordering = ["at", "id"]

    def __str__(self) -> str:
        return f"Order #{self.order_id} -> {self.status} at {self.at}"


class OrderDocument(BaseModel):
    """Document attached to an order (CMR, invoice, photo, etc.)."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to="orders/documents/")
    size_kb = models.PositiveIntegerField(default=0)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_documents",
    )

    class Meta:
        verbose_name = "Order Document"
        verbose_name_plural = "Order Documents"
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"{self.name} (Order #{self.order_id})"


class Rating(BaseModel):
    """Post-fulfillment rating submitted by a party of an order."""

    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name="ratings",
    )
    rater = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ratings_given",
    )
    ratee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ratings_received",
    )
    stars = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    reasons = ArrayField(
        models.CharField(max_length=100),
        default=list,
        blank=True,
    )
    comment = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Rating"
        verbose_name_plural = "Ratings"
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["order", "rater"],
                name="unique_order_rater_rating",
            ),
        ]

    def __str__(self) -> str:
        return f"Rating {self.stars}* by User #{self.rater_id} on Order #{self.order_id}"
