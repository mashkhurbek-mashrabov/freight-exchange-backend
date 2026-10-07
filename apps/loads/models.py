"""Loads model definitions."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import BaseModel


class Load(BaseModel):
    """Freight load posted by a shipper."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ACTIVE = "active", "Active"
        IN_PROGRESS = "in_progress", "In Progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    class TransportMode(models.TextChoices):
        FTL = "FTL", "FTL"
        LTL = "LTL", "LTL"

    shipper = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="loads",
    )
    company = models.ForeignKey(
        "accounts.Company",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="loads",
    )
    cargo_description = models.CharField(max_length=255)
    cargo_type = models.CharField(max_length=100, blank=True, default="")
    weight_t = models.DecimalField(max_digits=10, decimal_places=3)
    volume_m3 = models.DecimalField(
        max_digits=10,
        decimal_places=3,
        null=True,
        blank=True,
    )
    length_m = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
    )
    packaging = models.CharField(max_length=100, blank=True, default="")
    transport_mode = models.CharField(
        max_length=10,
        choices=TransportMode.choices,
        default=TransportMode.FTL,
    )
    vehicle_category = models.CharField(max_length=100, blank=True, default="")
    body_types = models.ManyToManyField(
        "garage.VehicleType",
        related_name="loads",
        blank=True,
    )
    trucks_needed = models.PositiveIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
    )
    trucks_found = models.PositiveIntegerField(default=0)
    is_adr = models.BooleanField(default=False)
    adr_class = models.PositiveSmallIntegerField(null=True, blank=True)
    temp_controlled = models.BooleanField(default=False)
    temp_min_c = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    temp_max_c = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )
    price_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
    )
    currency = models.ForeignKey(
        "geo.Currency",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="loads",
    )
    vat_included = models.BooleanField(default=False)
    price_negotiable = models.BooleanField(default=True)
    distance_km = models.PositiveIntegerField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    published_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Load"
        verbose_name_plural = "Loads"
        ordering = ["-id"]
        indexes = [
            models.Index(fields=["status", "-published_at"], name="load_status_pub_idx"),
            models.Index(fields=["shipper"], name="load_shipper_idx"),
            models.Index(fields=["currency"], name="load_currency_idx"),
        ]

    def __str__(self) -> str:
        return f"Load #{self.pk}: {self.cargo_description} ({self.status})"

    def clean(self) -> None:
        """Validate ADR, temperature control, and currency constraints."""
        super().clean()
        if self.is_adr and self.adr_class is None:
            raise ValidationError({"adr_class": "ADR class is required when is_adr is True."})
        if self.temp_controlled:
            if self.temp_min_c is None:
                raise ValidationError(
                    {"temp_min_c": "Minimum temperature is required when temp_controlled is True."}
                )
            if self.temp_max_c is None:
                raise ValidationError(
                    {"temp_max_c": "Maximum temperature is required when temp_controlled is True."}
                )
            if (
                self.temp_min_c is not None
                and self.temp_max_c is not None
                and self.temp_min_c > self.temp_max_c
            ):
                raise ValidationError(
                    {"temp_max_c": "Maximum temperature cannot be less than minimum temperature."}
                )
        if self.price_amount is not None and not self.currency_id:
            raise ValidationError(
                {"currency": "Currency is required when price_amount is provided."}
            )


class RoutePoint(BaseModel):
    """Sequential stop along the route of a load."""

    class Kind(models.TextChoices):
        LOADING = "loading", "Loading"
        STOP = "stop", "Stop"
        TRANSIT = "transit", "Transit"
        BORDER = "border", "Border"
        CUSTOMS = "customs", "Customs"
        UNLOADING = "unloading", "Unloading"

    load = models.ForeignKey(
        Load,
        on_delete=models.CASCADE,
        related_name="route_points",
    )
    seq = models.PositiveSmallIntegerField()
    kind = models.CharField(
        max_length=20,
        choices=Kind.choices,
    )
    country = models.ForeignKey(
        "geo.Country",
        on_delete=models.PROTECT,
        related_name="route_points",
    )
    address = models.CharField(max_length=255, blank=True, default="")
    lat = models.DecimalField(max_digits=9, decimal_places=6)
    lng = models.DecimalField(max_digits=9, decimal_places=6)
    planned_from = models.DateTimeField(null=True, blank=True)
    planned_to = models.DateTimeField(null=True, blank=True)
    asap = models.BooleanField(default=False)
    ready_to_load = models.BooleanField(default=False)
    comment = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Route Point"
        verbose_name_plural = "Route Points"
        ordering = ["seq"]
        constraints = [
            models.UniqueConstraint(
                fields=["load", "seq"],
                name="unique_route_point_load_seq",
            ),
        ]

    def __str__(self) -> str:
        return f"RoutePoint #{self.seq} ({self.kind}) - Load #{self.load_id}"


class PaymentTerms(BaseModel):
    """Payment conditions associated with a load."""

    class PrepayMethod(models.TextChoices):
        CASH = "cash", "Cash"
        TRANSFER = "transfer", "Transfer"

    load = models.OneToOneField(
        Load,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="payment_terms",
    )
    prepay_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
    )
    prepay_method = models.CharField(
        max_length=20,
        choices=PrepayMethod.choices,
        blank=True,
        default="",
    )
    paid_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
    )
    paid_method = models.CharField(
        max_length=20,
        choices=PrepayMethod.choices,
        blank=True,
        default="",
    )
    remaining_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        null=True,
        blank=True,
    )
    payment_due_days = models.PositiveIntegerField(
        null=True,
        blank=True,
    )
    conditions = models.TextField(blank=True, default="")

    class Meta:
        verbose_name = "Payment Terms"
        verbose_name_plural = "Payment Terms"

    def __str__(self) -> str:
        return f"PaymentTerms for Load #{self.load_id}"


class LoadDocument(BaseModel):
    """Document attached to a load."""

    load = models.ForeignKey(
        Load,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    name = models.CharField(max_length=255)
    file = models.FileField(
        upload_to="loads/documents/",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "Load Document"
        verbose_name_plural = "Load Documents"
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"{self.name} (Load #{self.load_id})"


class Favorite(BaseModel):
    """User favorite bookmarked load."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="favorite_loads",
    )
    load = models.ForeignKey(
        Load,
        on_delete=models.CASCADE,
        related_name="favorites",
    )

    class Meta:
        verbose_name = "Favorite"
        verbose_name_plural = "Favorites"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "load"],
                name="unique_user_favorite_load",
            ),
        ]

    def __str__(self) -> str:
        return f"User #{self.user_id} -> Load #{self.load_id}"
