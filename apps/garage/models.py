"""Garage model definitions."""

import re
from typing import Any

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.models import BaseModel


def normalize_plate_number(plate: str) -> str:
    """Normalize plate number by removing all whitespace and uppercasing."""
    if not plate:
        return ""
    return re.sub(r"\s+", "", plate).upper()


class VehicleKind(models.TextChoices):
    """Supported vehicle categories."""

    TRACTOR = "tractor", "Tractor"
    TRAILER = "trailer", "Trailer"


class VehicleType(models.Model):
    """Vehicle type or body type classification."""

    Kind = VehicleKind

    code = models.CharField(max_length=50, unique=True)
    name_i18n = models.JSONField(default=dict)
    image_url = models.CharField(max_length=500, blank=True, default="")
    kind = models.CharField(max_length=20, choices=VehicleKind.choices)

    class Meta:
        verbose_name = "Vehicle Type"
        verbose_name_plural = "Vehicle Types"
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.code} ({self.kind})"


class Vehicle(BaseModel):
    """Vehicle owned by a carrier."""

    Kind = VehicleKind

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="vehicles",
    )
    kind = models.CharField(max_length=20, choices=VehicleKind.choices)
    vehicle_type = models.ForeignKey(
        VehicleType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="vehicles",
    )
    plate_number = models.CharField(max_length=50, unique=True)
    tech_passport_no = models.CharField(max_length=50, blank=True, default="")
    owner_full_name = models.CharField(max_length=255, blank=True, default="")
    brand = models.CharField(max_length=100, blank=True, default="")
    tech_passport_image = models.ImageField(
        upload_to="vehicles/tech_passports/",
        null=True,
        blank=True,
    )
    paired_vehicle = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="paired_vehicles",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Vehicle"
        verbose_name_plural = "Vehicles"
        ordering = ["-id"]

    def __str__(self) -> str:
        return f"{self.plate_number} ({self.kind})"

    def clean(self) -> None:
        super().clean()
        if self.plate_number:
            self.plate_number = normalize_plate_number(self.plate_number)

        if self.vehicle_type and self.vehicle_type.kind != self.kind:
            raise ValidationError(
                {"vehicle_type": "Vehicle type kind must match vehicle kind."}
            )

        if self.paired_vehicle:
            if self.pk and self.paired_vehicle_id == self.pk:
                raise ValidationError(
                    {"paired_vehicle": "A vehicle cannot be paired with itself."}
                )
            if self.paired_vehicle.owner_id != self.owner_id:
                raise ValidationError(
                    {"paired_vehicle": "Paired vehicle must belong to the same owner."}
                )
            if self.paired_vehicle.kind == self.kind:
                raise ValidationError(
                    {"paired_vehicle": "Paired vehicle must have the opposite kind."}
                )

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.plate_number:
            self.plate_number = normalize_plate_number(self.plate_number)
        super().save(*args, **kwargs)
