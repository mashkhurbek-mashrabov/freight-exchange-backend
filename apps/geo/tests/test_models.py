"""Tests for geo models and signals."""

from decimal import Decimal
from unittest.mock import patch

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.geo.models import Country, Currency, ExchangeRate
from apps.geo.tests.factories import (
    CountryFactory,
    CurrencyFactory,
    ExchangeRateFactory,
)


@pytest.mark.django_db
def test_country_model_str_and_fields() -> None:
    """Test Country string representation and fields."""
    country = CountryFactory.create(
        code="UZ",
        name_i18n={"en": "Uzbekistan", "ru": "Узбекистан", "uz": "Oʻzbekiston"},
        flag_url="https://flagcdn.com/w80/uz.png",
    )
    assert str(country) == "UZ - Uzbekistan"
    assert country.pk == "UZ"


@pytest.mark.django_db
def test_country_unique_code_primary_key() -> None:
    """Test Country duplicate primary key raises IntegrityError."""
    CountryFactory.create(code="TR")
    with pytest.raises(IntegrityError):
        Country.objects.create(code="TR", name_i18n={"en": "Turkey"})


@pytest.mark.django_db
def test_currency_model_str_and_fields() -> None:
    """Test Currency string representation and fields."""
    curr1 = CurrencyFactory.create(code="USD", name="US Dollar")
    assert str(curr1) == "USD (US Dollar)"

    curr2 = CurrencyFactory.create(code="EUR", name="EUR")
    assert str(curr2) == "EUR"


@pytest.mark.django_db
def test_currency_unique_code_primary_key() -> None:
    """Test Currency duplicate primary key raises IntegrityError."""
    CurrencyFactory.create(code="KZT")
    with pytest.raises(IntegrityError):
        Currency.objects.create(code="KZT", name="Kazakhstani Tenge")


@pytest.mark.django_db
def test_exchange_rate_unique_constraint() -> None:
    """Test ExchangeRate unique constraint on (base, quote, fetched_at)."""
    now = timezone.now()
    c1 = CurrencyFactory.create()
    c2 = CurrencyFactory.create()

    ExchangeRate.objects.create(
        base=c1, quote=c2, rate=Decimal("12000.000000"), fetched_at=now
    )
    with pytest.raises(IntegrityError):
        ExchangeRate.objects.create(
            base=c1, quote=c2, rate=Decimal("13000.000000"), fetched_at=now
        )


@pytest.mark.django_db
def test_exchange_rate_model_str() -> None:
    """Test ExchangeRate string representation."""
    rate = ExchangeRateFactory.create()
    assert rate.base_id in str(rate)
    assert rate.quote_id in str(rate)


@pytest.mark.django_db
def test_signals_invalidate_cache_on_save_and_delete() -> None:
    """Test signals fire cache invalidation on save and delete."""
    with patch(
        "apps.geo.signals.invalidate_countries_cache"
    ) as mock_country_inv:
        country = CountryFactory.create()
        assert mock_country_inv.call_count >= 1

        mock_country_inv.reset_mock()
        country.delete()
        assert mock_country_inv.call_count >= 1

    with patch(
        "apps.geo.signals.invalidate_currencies_cache"
    ) as mock_curr_inv:
        curr = CurrencyFactory.create()
        assert mock_curr_inv.call_count >= 1

        mock_curr_inv.reset_mock()
        curr.delete()
        assert mock_curr_inv.call_count >= 1

    with patch(
        "apps.geo.signals.invalidate_exchange_rates_cache"
    ) as mock_rate_inv:
        rate = ExchangeRateFactory.create()
        assert mock_rate_inv.call_count >= 1

        mock_rate_inv.reset_mock()
        rate.delete()
        assert mock_rate_inv.call_count >= 1
