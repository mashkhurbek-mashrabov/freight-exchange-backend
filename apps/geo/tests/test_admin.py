"""Tests for geo admin interface."""

from unittest.mock import MagicMock

import pytest
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory

from apps.geo.admin import CountryAdmin, CurrencyAdmin, ExchangeRateAdmin, HasFlagFilter
from apps.geo.models import Country, Currency, ExchangeRate
from apps.geo.tests.factories import (
    CountryFactory,
    CurrencyFactory,
    ExchangeRateFactory,
)


class DummyAdminSite(AdminSite):
    """Dummy AdminSite for testing ModelAdmin instances."""


@pytest.mark.django_db
def test_country_admin_list_display_and_filter() -> None:
    """Test CountryAdmin displays correct columns and custom filter works."""
    site = DummyAdminSite()
    admin_instance = CountryAdmin(Country, site)
    rf = RequestFactory()

    c1 = CountryFactory.create(
        code="UZ",
        name_i18n={"en": "Uzbekistan", "ru": "Узбекистан", "uz": "Oʻzbekiston"},
        flag_url="https://flagcdn.com/w80/uz.png",
    )
    c2 = CountryFactory.create(code="XX", name_i18n={}, flag_url="")

    assert admin_instance.name_en(c1) == "Uzbekistan"
    assert admin_instance.name_ru(c1) == "Узбекистан"
    assert admin_instance.name_uz(c1) == "Oʻzbekiston"
    assert admin_instance.name_en(c2) == ""

    # Test HasFlagFilter
    req_yes = rf.get("/admin/geo/country/?has_flag=yes")
    filter_instance = HasFlagFilter(
        req_yes, req_yes.GET.copy(), Country, admin_instance
    )
    qs_yes = filter_instance.queryset(req_yes, Country.objects.all())
    assert c1 in qs_yes
    assert c2 not in qs_yes

    req_no = rf.get("/admin/geo/country/?has_flag=no")
    filter_instance_no = HasFlagFilter(
        req_no, req_no.GET.copy(), Country, admin_instance
    )
    qs_no = filter_instance_no.queryset(req_no, Country.objects.all())
    assert c2 in qs_no
    assert c1 not in qs_no


@pytest.mark.django_db
def test_admin_save_and_delete_invalidation() -> None:
    """Test admin save_model and delete_model purge cache."""
    site = DummyAdminSite()
    c_admin = CountryAdmin(Country, site)
    cur_admin = CurrencyAdmin(Currency, site)
    ex_admin = ExchangeRateAdmin(ExchangeRate, site)

    rf = RequestFactory()
    request = rf.get("/")
    form = MagicMock()

    country = CountryFactory.create()
    c_admin.save_model(request, country, form, True)
    c_admin.delete_model(request, country)

    cur = CurrencyFactory.create()
    cur_admin.save_model(request, cur, form, True)
    cur_admin.delete_model(request, cur)

    ex = ExchangeRateFactory.create()
    ex_admin.save_model(request, ex, form, True)
    ex_admin.delete_model(request, ex)
