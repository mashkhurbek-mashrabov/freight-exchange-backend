"""Factory definitions for loads app."""

from decimal import Decimal
from typing import Any

import factory
from factory.django import DjangoModelFactory

from apps.accounts.tests.factories import ShipperUserFactory, UserFactory
from apps.geo.models import Currency
from apps.geo.tests.factories import CountryFactory
from apps.loads.models import Favorite, Load, LoadDocument, PaymentTerms, RoutePoint


class LoadFactory(DjangoModelFactory):
    """Factory for Load model."""

    class Meta:
        model = Load
        skip_postgeneration_save = True

    shipper = factory.SubFactory(ShipperUserFactory)
    company = None
    cargo_description = "Standard pallet freight"
    cargo_type = "consumer_goods"
    weight_t = Decimal("18.500")
    volume_m3 = Decimal("82.000")
    length_m = Decimal("13.60")
    packaging = "pallet"
    transport_mode = Load.TransportMode.FTL
    vehicle_category = "curtainsider"
    trucks_needed = 1
    trucks_found = 0
    is_adr = False
    adr_class = None
    temp_controlled = False
    temp_min_c = None
    temp_max_c = None
    price_amount = Decimal("2500.00")
    currency = factory.LazyFunction(
        lambda: Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar"})[0]
    )
    vat_included = False
    price_negotiable = True
    distance_km = 950
    status = Load.Status.DRAFT
    published_at = None
    expires_at = None

    @factory.post_generation
    def body_types(self, create: bool, extracted: Any, **kwargs: Any) -> None:
        if not create or not extracted:
            return
        self.body_types.set(extracted)


class RoutePointFactory(DjangoModelFactory):
    """Factory for RoutePoint model."""

    class Meta:
        model = RoutePoint

    load = factory.SubFactory(LoadFactory)
    seq = 1
    kind = RoutePoint.Kind.LOADING
    country = factory.SubFactory(CountryFactory)
    address = factory.Sequence(lambda n: f"Address {n}")
    lat = Decimal("41.299496")
    lng = Decimal("69.240073")
    planned_from = None
    planned_to = None
    asap = False
    ready_to_load = False
    comment = ""


class PaymentTermsFactory(DjangoModelFactory):
    """Factory for PaymentTerms model."""

    class Meta:
        model = PaymentTerms

    load = factory.SubFactory(LoadFactory)
    prepay_amount = Decimal("500.00")
    prepay_method = PaymentTerms.PrepayMethod.TRANSFER
    paid_amount = Decimal("2000.00")
    paid_method = PaymentTerms.PrepayMethod.TRANSFER
    remaining_amount = Decimal("0.00")
    payment_due_days = 5
    conditions = "Net 5 days upon delivery"


class LoadDocumentFactory(DjangoModelFactory):
    """Factory for LoadDocument model."""

    class Meta:
        model = LoadDocument

    load = factory.SubFactory(LoadFactory)
    name = factory.Sequence(lambda n: f"Document_{n}.pdf")
    file = None


class FavoriteFactory(DjangoModelFactory):
    """Factory for Favorite model."""

    class Meta:
        model = Favorite

    user = factory.SubFactory(UserFactory)
    load = factory.SubFactory(LoadFactory)


def make_load_with_route(load: Load | None = None, **kwargs: Any) -> Load:
    """Helper creating loading (seq 1) and unloading (seq 2) route points for a load."""
    if load is None:
        load = LoadFactory(**kwargs)

    uz = CountryFactory(
        code="UZ",
        name_i18n={"en": "Uzbekistan", "ru": "Узбекистан", "uz": "O'zbekiston"},
    )
    ru = CountryFactory(
        code="RU",
        name_i18n={"en": "Russia", "ru": "Россия", "uz": "Rossiya"},
    )

    RoutePointFactory(
        load=load,
        seq=1,
        kind=RoutePoint.Kind.LOADING,
        country=uz,
        address="Tashkent, Uzbekistan",
        lat=Decimal("41.299496"),
        lng=Decimal("69.240073"),
    )
    RoutePointFactory(
        load=load,
        seq=2,
        kind=RoutePoint.Kind.UNLOADING,
        country=ru,
        address="Moscow, Russia",
        lat=Decimal("55.755826"),
        lng=Decimal("37.617300"),
    )
    return load
