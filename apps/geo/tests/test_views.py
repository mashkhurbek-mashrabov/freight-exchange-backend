"""Tests for geo reference data API views."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.geo.models import ExchangeRate
from apps.geo.tests.factories import (
    CountryFactory,
    CurrencyFactory,
)


@pytest.mark.django_db
def test_endpoints_require_authentication(api_client: APIClient) -> None:
    """Verify that all geo endpoints return 401 when called without credentials."""
    for path in ["/api/v1/countries", "/api/v1/currencies", "/api/v1/exchange-rates"]:
        response = api_client.get(path)
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.data.get("code") == "not_authenticated"


@pytest.mark.django_db
def test_endpoints_return_seeded_data(auth_client: APIClient) -> None:
    """Verify that seeded data from fixtures is returned unpaginated via API endpoints."""
    call_command("loaddata", "countries", "currencies", "exchange_rates")

    # Countries endpoint
    res_countries = auth_client.get("/api/v1/countries")
    assert res_countries.status_code == status.HTTP_200_OK
    assert isinstance(res_countries.data, list)
    assert len(res_countries.data) >= 40
    country_codes = {c["code"] for c in res_countries.data}
    assert "UZ" in country_codes
    assert "RU" in country_codes

    # Currencies endpoint
    res_currencies = auth_client.get("/api/v1/currencies")
    assert res_currencies.status_code == status.HTTP_200_OK
    assert isinstance(res_currencies.data, list)
    curr_codes = {c["code"] for c in res_currencies.data}
    assert {"UZS", "USD", "EUR", "RUB", "KZT", "AED"}.issubset(curr_codes)

    # Exchange rates endpoint
    res_rates = auth_client.get("/api/v1/exchange-rates")
    assert res_rates.status_code == status.HTTP_200_OK
    assert isinstance(res_rates.data, list)
    assert len(res_rates.data) >= 10


@pytest.mark.django_db
def test_countries_search(auth_client: APIClient) -> None:
    """Verify countries endpoint search filtering across code and name_i18n."""
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
    res = auth_client.get("/api/v1/countries?search=uz")
    assert res.status_code == status.HTTP_200_OK
    assert len(res.data) == 1
    assert res.data[0]["code"] == "UZ"

    # Search by Russian name
    res = auth_client.get("/api/v1/countries?search=Россия")
    assert res.status_code == status.HTTP_200_OK
    assert len(res.data) == 1
    assert res.data[0]["code"] == "RU"

    # Search by English name
    res = auth_client.get("/api/v1/countries?search=Kazakhstan")
    assert res.status_code == status.HTTP_200_OK
    assert len(res.data) == 1
    assert res.data[0]["code"] == "KZ"


@pytest.mark.django_db
def test_exchange_rates_filtering_and_latest(auth_client: APIClient) -> None:
    """Verify exchange rates filtering by base/quote and returning only latest per pair."""
    usd = CurrencyFactory.create(code="USD")
    uzs = CurrencyFactory.create(code="UZS")
    eur = CurrencyFactory.create(code="EUR")

    t_old = timezone.now() - timedelta(days=2)
    t_new = timezone.now()

    # Two rates for USD/UZS
    ExchangeRate.objects.create(
        base=usd, quote=uzs, rate=Decimal("12600.000000"), fetched_at=t_old
    )
    ExchangeRate.objects.create(
        base=usd, quote=uzs, rate=Decimal("12750.000000"), fetched_at=t_new
    )
    # One rate for USD/EUR
    ExchangeRate.objects.create(
        base=usd, quote=eur, rate=Decimal("0.920000"), fetched_at=t_new
    )

    # Unfiltered list: returns 2 latest rates
    res = auth_client.get("/api/v1/exchange-rates")
    assert res.status_code == status.HTTP_200_OK
    assert len(res.data) == 2
    rate_map = {f"{r['base']}/{r['quote']}": r["rate"] for r in res.data}
    assert Decimal(rate_map["USD/UZS"]) == Decimal("12750.000000")
    assert Decimal(rate_map["USD/EUR"]) == Decimal("0.920000")

    # Filter by base
    res_base = auth_client.get("/api/v1/exchange-rates?base=USD")
    assert res_base.status_code == status.HTTP_200_OK
    assert len(res_base.data) == 2

    # Filter by quote
    res_quote = auth_client.get("/api/v1/exchange-rates?quote=UZS")
    assert res_quote.status_code == status.HTTP_200_OK
    assert len(res_quote.data) == 1
    assert res_quote.data[0]["quote"] == "UZS"

    # Filter by base and quote
    res_pair = auth_client.get("/api/v1/exchange-rates?base=USD&quote=UZS")
    assert res_pair.status_code == status.HTTP_200_OK
    assert len(res_pair.data) == 1
    assert Decimal(res_pair.data[0]["rate"]) == Decimal("12750.000000")


@pytest.mark.django_db
def test_caching_and_django_assert_num_queries(
    auth_client: APIClient, django_assert_num_queries: pytest.FixtureRequest
) -> None:
    """Verify second call is served from cache with 0 database queries."""
    call_command("loaddata", "countries", "currencies", "exchange_rates")

    # 1. Countries caching
    auth_client.get("/api/v1/countries")
    with django_assert_num_queries(0):
        res_cached = auth_client.get("/api/v1/countries")
    assert res_cached.status_code == status.HTTP_200_OK

    # 2. Currencies caching
    auth_client.get("/api/v1/currencies")
    with django_assert_num_queries(0):
        res_cached = auth_client.get("/api/v1/currencies")
    assert res_cached.status_code == status.HTTP_200_OK

    # 3. Exchange rates caching
    auth_client.get("/api/v1/exchange-rates")
    with django_assert_num_queries(0):
        res_cached = auth_client.get("/api/v1/exchange-rates")
    assert res_cached.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_cache_invalidation_on_save(
    auth_client: APIClient, django_assert_num_queries: pytest.FixtureRequest
) -> None:
    """Verify that saving or creating a record purges cache so next call queries DB."""
    CountryFactory.create(code="UZ", name_i18n={"en": "Uzbekistan"})

    # Prime cache
    res1 = auth_client.get("/api/v1/countries")
    assert len(res1.data) == 1

    # Confirmed served from cache
    with django_assert_num_queries(0):
        auth_client.get("/api/v1/countries")

    # Create new country (triggers post_save signal)
    CountryFactory.create(code="TR", name_i18n={"en": "Turkey"})

    # Subsequent request queries DB and sees new record
    res2 = auth_client.get("/api/v1/countries")
    assert len(res2.data) == 2
    assert any(c["code"] == "TR" for c in res2.data)

    # Prime currencies cache
    CurrencyFactory.create(code="USD")
    res_c1 = auth_client.get("/api/v1/currencies")
    assert len(res_c1.data) == 1

    with django_assert_num_queries(0):
        auth_client.get("/api/v1/currencies")

    # Create new currency
    CurrencyFactory.create(code="EUR")
    res_c2 = auth_client.get("/api/v1/currencies")
    assert len(res_c2.data) == 2
