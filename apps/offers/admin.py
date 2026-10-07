"""Admin configuration for offers app."""

from django.contrib import admin

from apps.offers.models import Offer


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    """Admin interface for Offer model."""

    list_display = (
        "id",
        "load",
        "carrier",
        "proposer",
        "recipient",
        "mode",
        "amount",
        "currency",
        "status",
        "created_at",
        "responded_at",
    )
    list_filter = (
        "status",
        "mode",
        "currency",
        "created_at",
    )
    search_fields = (
        "load__cargo_description",
        "carrier__phone",
        "proposer__phone",
        "recipient__phone",
        "comment",
    )
