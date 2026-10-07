"""Tests for geo services logic."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.geo import services
from apps.geo.models import ExchangeRate
from apps.geo.tests.factories import (
    CountryFactory,
    CurrencyFactory,
    ExchangeRateFactory,
)


@pytest.mark.django_db
def test_filter_countries_search() -> None:
    """Test filtering countries by code and localized name_i18n values."""
    CountryFactory.create(
        code="UZ",
        name_i18n={"en": "Uzbekistan", "ru": "Узбекистан", "uz": "Oʻzbekiston"},
    )
    CountryFactory.create(
        code="RU",
        name_i18n={"en": "Russia", "ru": "Россия", "uz": "Rossiya"},
    )
    CountryFactory.create(
        code="KZ",
        name_i18n={"en": "Kazakhstan", "ru": "Казахстан", "uz": "Qozogʻiston"},
    )

    # Search by code
    assert [c.code for c in services.filter_countries(search="uz")] == ["UZ"]
    assert [c.code for c in services.filter_countries(search="RU")] == ["RU"]

    # Search by English name
    assert [c.code for c in services.filter_countries(search="Kazakhstan")] == ["KZ"]

    # Search by Russian name
    assert [c.code for c in services.filter_countries(search="Россия")] == ["RU"]

    # Search by Uzbek name
    assert [c.code for c in services.filter_countries(search="Oʻzbekiston")] == ["UZ"]

    # No search returns all
    assert len(services.filter_countries()) == 3


@pytest.mark.django_db
def test_latest_rates_returns_most_recent_per_pair() -> None:
    """Verify that latest_rates returns strictly the most recent rate per pair."""
    usd = CurrencyFactory.create(code="USD", name="US Dollar")
    uzs = CurrencyFactory.create(code="UZS", name="Uzbek Som")
    eur = CurrencyFactory.create(code="EUR", name="Euro")

    t1 = timezone.now() - timedelta(days=2)
    t2 = timezone.now() - timedelta(days=1)
    t3 = timezone.now()

    # Older USD->UZS rate
    ExchangeRate.objects.create(
        base=usd, quote=uzs, rate=Decimal("12600.000000"), fetched_at=t1
    )
    # Middle USD->UZS rate
    ExchangeRate.objects.create(
        base=usd, quote=uzs, rate=Decimal("12700.000000"), fetched_at=t2
    )
    # Latest USD->UZS rate
    ExchangeRate.objects.create(
        base=usd, quote=uzs, rate=Decimal("12800.000000"), fetched_at=t3
    )

    # EUR->USD rates
    ExchangeRate.objects.create(
        base=eur, quote=usd, rate=Decimal("1.070000"), fetched_at=t1
    )
    ExchangeRate.objects.create(
        base=eur, quote=usd, rate=Decimal("1.090000"), fetched_at=t3
    )

    rates = list(services.latest_rates())
    assert len(rates) == 2

    rate_map = {f"{r.base_id}/{r.quote_id}": r.rate for r in rates}
    assert rate_map["USD/UZS"] == Decimal("12800.000000")
    assert rate_map["EUR/USD"] == Decimal("1.090000")


@pytest.mark.django_db
def test_latest_rates_filter_by_base_and_quote() -> None:
    """Test filtering latest_rates by base, quote, or both."""
    usd = CurrencyFactory.create(code="USD")
    uzs = CurrencyFactory.create(code="UZS")
    eur = CurrencyFactory.create(code="EUR")
    now = timezone.now()

    ExchangeRateFactory.create(base=usd, quote=uzs, fetched_at=now)
    ExchangeRateFactory.create(base=usd, quote=eur, fetched_at=now)
    ExchangeRateFactory.create(base=eur, quote=usd, fetched_at=now)

    # Filter by base
    by_base = list(services.latest_rates(base="USD"))
    assert len(by_base) == 2
    assert all(r.base_id == "USD" for r in by_base)

    # Filter by quote
    by_quote = list(services.latest_rates(quote="EUR"))
    assert len(by_quote) == 1
    assert by_quote[0].quote_id == "EUR"

    # Filter by both base and quote
    by_both = list(services.latest_rates(base="USD", quote="UZS"))
    assert len(by_both) == 1
    assert by_both[0].base_id == "USD" and by_both[0].quote_id == "UZS"


@pytest.mark.django_db
def test_cache_and_invalidation_services() -> None:
    """Test caching services and invalidation functions."""
    CountryFactory.create(code="UZ")
    CurrencyFactory.create(code="USD")

    # Countries cache
    data1 = services.get_cached_countries()
    assert len(data1) == 1
    assert data1[0]["code"] == "UZ"

    # Invalidate and check
    services.invalidate_countries_cache()
    CountryFactory.create(code="RU")
    data2 = services.get_cached_countries()
    assert len(data2) == 2

    # Currencies cache
    c_data1 = services.get_cached_currencies()
    assert len(c_data1) == 1

    services.invalidate_currencies_cache()
    CurrencyFactory.create(code="EUR")
    c_data2 = services.get_cached_currencies()
    assert len(c_data2) == 2


def test_normalize_query_string() -> None:
    """Verify that normalize_query_string orders query parameters deterministically."""
    qs1 = "quote=UZS&base=USD"
    qs2 = "base=USD&quote=UZS"
    assert services.normalize_query_string(qs1) == services.normalize_query_string(qs2)
    assert services.normalize_query_string("") == ""
