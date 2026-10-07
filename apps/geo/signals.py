"""Signals for geo reference data cache invalidation."""

from typing import Any

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.geo.models import Country, Currency, ExchangeRate
from apps.geo.services import (
    invalidate_countries_cache,
    invalidate_currencies_cache,
    invalidate_exchange_rates_cache,
)


@receiver([post_save, post_delete], sender=Country)
def country_cache_invalidation_handler(
    sender: type[Country], instance: Country, **kwargs: Any
) -> None:
    """Invalidate country cache upon creation, update, or deletion."""
    invalidate_countries_cache()


@receiver([post_save, post_delete], sender=Currency)
def currency_cache_invalidation_handler(
    sender: type[Currency], instance: Currency, **kwargs: Any
) -> None:
    """Invalidate currency and exchange rate caches upon creation, update, or deletion."""
    invalidate_currencies_cache()


@receiver([post_save, post_delete], sender=ExchangeRate)
def exchange_rate_cache_invalidation_handler(
    sender: type[ExchangeRate], instance: ExchangeRate, **kwargs: Any
) -> None:
    """Invalidate exchange rate cache upon creation, update, or deletion."""
    invalidate_exchange_rates_cache()
