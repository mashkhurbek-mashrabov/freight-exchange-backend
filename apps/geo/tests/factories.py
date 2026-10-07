"""Factory definitions for geo models."""

from decimal import Decimal

import factory
from django.utils import timezone
from factory.django import DjangoModelFactory

from apps.geo.models import Country, Currency, ExchangeRate


class CountryFactory(DjangoModelFactory):
    """Factory generating unique 2-letter Country instances."""

    class Meta:
        model = Country
        django_get_or_create = ("code",)

    code = factory.Sequence(
        lambda n: f"{chr(65 + ((n // 26) % 26))}{chr(65 + (n % 26))}"
    )
    name_i18n = factory.LazyAttribute(
        lambda o: {
            "en": f"Country {o.code}",
            "ru": f"Страна {o.code}",
            "uz": f"{o.code} mamlakati",
        }
    )
    flag_url = factory.LazyAttribute(
        lambda o: f"https://flagcdn.com/w80/{o.code.lower()}.png"
    )


class CurrencyFactory(DjangoModelFactory):
    """Factory generating unique 3-letter Currency instances."""

    class Meta:
        model = Currency
        django_get_or_create = ("code",)

    code = factory.Sequence(
        lambda n: f"X{n:02d}" if n < 100 else f"Y{n - 100:02d}"
    )
    name = factory.LazyAttribute(lambda o: f"Currency {o.code}")


class ExchangeRateFactory(DjangoModelFactory):
    """Factory generating ExchangeRate instances."""

    class Meta:
        model = ExchangeRate

    base = factory.SubFactory(CurrencyFactory)
    quote = factory.SubFactory(CurrencyFactory)
    rate = factory.Sequence(lambda n: Decimal(f"{1.0 + (n * 0.05):.6f}"))
    fetched_at = factory.LazyFunction(timezone.now)
