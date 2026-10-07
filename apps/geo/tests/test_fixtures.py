"""Tests verifying reference fixture loading and contents."""

import pytest
from django.core.management import call_command

from apps.geo.models import Country, Currency, ExchangeRate


@pytest.mark.django_db
def test_fixtures_load_and_contain_required_data() -> None:
    """Verify fixtures load correctly with >= 40 countries, required currencies and rates."""
    call_command("loaddata", "countries", "currencies", "exchange_rates")

    # Countries verification
    countries_count = Country.objects.count()
    assert countries_count >= 40, f"Expected >= 40 countries, found {countries_count}"

    uz = Country.objects.get(code="UZ")
    assert uz.name_i18n.get("uz") == "Oʻzbekiston"
    assert uz.name_i18n.get("ru") == "Узбекистан"
    assert uz.name_i18n.get("en") == "Uzbekistan"
    assert "uz.png" in uz.flag_url

    ru = Country.objects.get(code="RU")
    assert ru.name_i18n.get("ru") == "Россия"
    assert "ru.png" in ru.flag_url

    kz = Country.objects.get(code="KZ")
    assert kz.name_i18n.get("ru") == "Казахстан"

    # Currencies verification
    currencies = set(Currency.objects.values_list("code", flat=True))
    required_currencies = {"UZS", "USD", "EUR", "RUB", "KZT", "AED"}
    assert required_currencies.issubset(currencies)

    # Exchange rates verification
    rates_count = ExchangeRate.objects.count()
    assert rates_count >= 10

    usd_uzs = ExchangeRate.objects.filter(base_id="USD", quote_id="UZS").first()
    assert usd_uzs is not None
    assert usd_uzs.rate > 0
