"""Tests for load_references management command."""

import io

import pytest
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.garage.models import VehicleType
from apps.geo.models import Country, Currency, ExchangeRate


@pytest.fixture
def auth_client() -> APIClient:
    """Return APIClient authenticated with verified user."""
    user = User.objects.create_user(
        phone="+998901234567",
        full_name="Reference Test User",
        status=User.Status.VERIFIED,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_first_run_creates_rows_and_second_run_is_idempotent() -> None:
    """Verify first run populates reference data and second run creates 0 rows."""
    out = io.StringIO()
    call_command("load_references", stdout=out)
    output = out.getvalue()

    # Check lower bounds for first run
    assert Country.objects.count() >= 45
    assert Currency.objects.count() >= 6
    assert Currency.objects.filter(code="UZS").exists()
    assert Currency.objects.filter(code="USD").exists()
    assert Currency.objects.filter(code="RUB").exists()
    assert VehicleType.objects.count() >= 24
    assert ExchangeRate.objects.count() >= 10

    # Verify summary printed
    assert "Country:" in output
    assert "Currency:" in output
    assert "VehicleType:" in output
    assert "ExchangeRate:" in output
    assert "0 existing" in output

    country_count = Country.objects.count()
    currency_count = Currency.objects.count()
    vt_count = VehicleType.objects.count()
    er_count = ExchangeRate.objects.count()

    # Second run
    out2 = io.StringIO()
    call_command("load_references", stdout=out2)
    output2 = out2.getvalue()

    assert Country.objects.count() == country_count
    assert Currency.objects.count() == currency_count
    assert VehicleType.objects.count() == vt_count
    assert ExchangeRate.objects.count() == er_count

    assert f"Country: 0 created, {country_count} existing" in output2
    assert f"Currency: 0 created, {currency_count} existing" in output2
    assert f"VehicleType: 0 created, {vt_count} existing" in output2
    assert f"ExchangeRate: 0 created, {er_count} existing" in output2


@pytest.mark.django_db
def test_admin_edited_field_survives_second_run_and_resets_with_force() -> None:
    """Verify admin changes are preserved normally and reset when --force is used."""
    call_command("load_references")

    uz = Country.objects.get(code="UZ")
    custom_name_i18n = {
        "uz": "Oʻzbekiston Respublikasi (Admin)",
        "ru": "Узбекистан (Админ)",
        "en": "Uzbekistan (Admin Edited)",
    }
    uz.name_i18n = custom_name_i18n
    uz.save()

    # Second run without --force: admin change must survive
    out_no_force = io.StringIO()
    call_command("load_references", stdout=out_no_force)
    uz.refresh_from_db()
    assert uz.name_i18n == custom_name_i18n
    assert "Country: 0 created," in out_no_force.getvalue()

    # Run with --force: admin change must be reset from fixture
    out_force = io.StringIO()
    call_command("load_references", force=True, stdout=out_force)
    uz.refresh_from_db()
    assert uz.name_i18n != custom_name_i18n
    assert uz.name_i18n.get("en") == "Uzbekistan"
    assert "Country: 0 created," in out_force.getvalue()


@pytest.mark.django_db
def test_partially_prepopulated_db_works() -> None:
    """Verify loading succeeds and preserves pre-existing rows when DB is partially filled."""
    Country.objects.create(
        code="UZ",
        name_i18n={"en": "Custom UZ", "ru": "Пользовательский УЗ", "uz": "Maxsus UZ"},
        flag_url="https://example.com/custom_uz.png",
    )
    Currency.objects.create(code="USD", name="Custom US Dollar")
    VehicleType.objects.create(
        code="truck_tractor",
        name_i18n={"en": "Custom Tractor"},
        image_url="",
        kind="tractor",
    )

    out = io.StringIO()
    call_command("load_references", stdout=out)
    output = out.getvalue()

    # Missing rows are created
    assert Country.objects.count() >= 45
    assert Currency.objects.count() >= 6
    assert VehicleType.objects.count() >= 24
    assert ExchangeRate.objects.count() >= 10

    # Pre-existing rows retain their original values
    uz = Country.objects.get(code="UZ")
    assert uz.name_i18n["en"] == "Custom UZ"
    assert uz.flag_url == "https://example.com/custom_uz.png"

    usd = Currency.objects.get(code="USD")
    assert usd.name == "Custom US Dollar"

    tractor = VehicleType.objects.get(code="truck_tractor")
    assert tractor.name_i18n["en"] == "Custom Tractor"

    assert "Country: " in output and " 1 existing" in output
    assert "Currency: " in output and " 1 existing" in output
    assert "VehicleType: " in output and " 1 existing" in output


@pytest.mark.django_db
def test_cache_invalidated_and_endpoints_return_data(auth_client: APIClient) -> None:
    """Verify cache is purged by command and endpoints return full loaded reference data."""
    # Seed minimal data first and warm up cache
    Country.objects.create(
        code="UZ",
        name_i18n={"en": "Uzbekistan", "ru": "Узбекистан", "uz": "Oʻzbekiston"},
    )
    Currency.objects.create(code="UZS", name="UZS")

    res_countries_before = auth_client.get("/api/v1/countries")
    assert res_countries_before.status_code == status.HTTP_200_OK
    assert len(res_countries_before.data) == 1

    res_currencies_before = auth_client.get("/api/v1/currencies")
    assert res_currencies_before.status_code == status.HTTP_200_OK
    assert len(res_currencies_before.data) == 1

    # Load all references (which invalidates reference caches)
    call_command("load_references")

    # Countries endpoint returns newly loaded data after cache invalidation
    res_countries_after = auth_client.get("/api/v1/countries")
    assert res_countries_after.status_code == status.HTTP_200_OK
    assert len(res_countries_after.data) >= 45

    # Currencies endpoint returns loaded data
    res_currencies_after = auth_client.get("/api/v1/currencies")
    assert res_currencies_after.status_code == status.HTTP_200_OK
    assert len(res_currencies_after.data) >= 6
    curr_codes = {c["code"] for c in res_currencies_after.data}
    assert {"UZS", "USD", "RUB"}.issubset(curr_codes)
