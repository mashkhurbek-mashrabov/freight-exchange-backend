"""Domain services for geo reference data."""

from typing import Any
from urllib.parse import parse_qsl, urlencode

from django.core.cache import cache
from django.db import connection, models
from django.db.models import Q, QuerySet

from apps.geo.models import Country, Currency, ExchangeRate
from apps.geo.serializers import (
    CountrySerializer,
    CurrencySerializer,
    ExchangeRateSerializer,
)

CACHE_TIMEOUT = 3600  # 1 hour in seconds


def normalize_query_string(query_string: str = "") -> str:
    """Normalize query string for consistent cache key generation."""
    if not query_string:
        return ""
    params = parse_qsl(query_string, keep_blank_values=True)
    sorted_params = sorted(params)
    return urlencode(sorted_params)


def build_cache_key(namespace: str, query_string: str = "") -> str:
    """Construct a namespaced cache key incorporating normalized query string."""
    norm_qs = normalize_query_string(query_string)
    return f"geo:{namespace}:{norm_qs}"


def track_cache_key(namespace: str, key: str) -> None:
    """Track generated cache keys for comprehensive invalidation."""
    registry_key = f"geo:keys:{namespace}"
    keys: set[str] = cache.get(registry_key, set())
    if key not in keys:
        keys.add(key)
        cache.set(registry_key, keys, timeout=CACHE_TIMEOUT * 24)


def invalidate_cache(namespace: str) -> None:
    """Invalidate all tracked cache keys for a given namespace."""
    registry_key = f"geo:keys:{namespace}"
    keys: set[str] = cache.get(registry_key, set())
    keys_to_delete = list(keys)
    # Ensure default patterns are always purged
    keys_to_delete.extend([
        f"geo:{namespace}:",
        f"geo:{namespace}",
    ])
    cache.delete_many(keys_to_delete)
    cache.delete(registry_key)


def invalidate_countries_cache() -> None:
    """Invalidate countries reference cache."""
    invalidate_cache("countries")


def invalidate_currencies_cache() -> None:
    """Invalidate currencies and exchange rates reference cache."""
    invalidate_cache("currencies")
    invalidate_cache("exchange_rates")


def invalidate_exchange_rates_cache() -> None:
    """Invalidate exchange rates reference cache."""
    invalidate_cache("exchange_rates")


def invalidate_all_geo_caches() -> None:
    """Invalidate all geo reference caches."""
    invalidate_countries_cache()
    invalidate_currencies_cache()
    invalidate_exchange_rates_cache()


def filter_countries(search: str | None = None) -> QuerySet[Country]:
    """Return countries queryset optionally filtered by search over code or name_i18n."""
    qs = Country.objects.all().order_by("code")
    if search:
        term = search.strip()
        if term:
            qs = qs.filter(
                Q(code__icontains=term)
                | Q(name_i18n__en__icontains=term)
                | Q(name_i18n__ru__icontains=term)
                | Q(name_i18n__uz__icontains=term)
            )
    return qs


def filter_currencies() -> QuerySet[Currency]:
    """Return all currencies ordered by code."""
    return Currency.objects.all().order_by("code")


def latest_rates(
    base: str | None = None,
    quote: str | None = None,
) -> QuerySet[ExchangeRate]:
    """Return the latest exchange rate per base/quote currency pair."""
    qs = ExchangeRate.objects.select_related("base", "quote")
    if base:
        qs = qs.filter(base__code__iexact=base.strip())
    if quote:
        qs = qs.filter(quote__code__iexact=quote.strip())

    if connection.vendor == "postgresql":
        return qs.order_by("base_id", "quote_id", "-fetched_at").distinct(
            "base_id", "quote_id"
        )

    latest_subquery = (
        ExchangeRate.objects.filter(
            base_id=models.OuterRef("base_id"),
            quote_id=models.OuterRef("quote_id"),
        )
        .order_by("-fetched_at")
        .values("pk")[:1]
    )
    return qs.filter(pk=models.Subquery(latest_subquery)).order_by(
        "base_id", "quote_id"
    )


def get_cached_countries(
    query_string: str = "",
    search: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve countries serialized payload, served from 1-hour cache."""
    cache_key = build_cache_key("countries", query_string)
    track_cache_key("countries", cache_key)

    def fetch() -> list[dict[str, Any]]:
        qs = filter_countries(search=search)
        return list(CountrySerializer(qs, many=True).data)

    return cache.get_or_set(cache_key, fetch, timeout=CACHE_TIMEOUT)


def get_cached_currencies(query_string: str = "") -> list[dict[str, Any]]:
    """Retrieve currencies serialized payload, served from 1-hour cache."""
    cache_key = build_cache_key("currencies", query_string)
    track_cache_key("currencies", cache_key)

    def fetch() -> list[dict[str, Any]]:
        qs = filter_currencies()
        return list(CurrencySerializer(qs, many=True).data)

    return cache.get_or_set(cache_key, fetch, timeout=CACHE_TIMEOUT)


def get_cached_exchange_rates(
    query_string: str = "",
    base: str | None = None,
    quote: str | None = None,
) -> list[dict[str, Any]]:
    """Retrieve latest exchange rates serialized payload, served from 1-hour cache."""
    cache_key = build_cache_key("exchange_rates", query_string)
    track_cache_key("exchange_rates", cache_key)

    def fetch() -> list[dict[str, Any]]:
        qs = latest_rates(base=base, quote=quote)
        return list(ExchangeRateSerializer(qs, many=True).data)

    return cache.get_or_set(cache_key, fetch, timeout=CACHE_TIMEOUT)
