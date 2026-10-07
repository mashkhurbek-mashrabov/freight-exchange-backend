"""Tests for loads app models and factories."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.accounts.tests.factories import ShipperUserFactory
from apps.geo.tests.factories import CountryFactory, CurrencyFactory
from apps.loads.models import Favorite, Load, PaymentTerms, RoutePoint
from apps.loads.tests.factories import (
    FavoriteFactory,
    LoadDocumentFactory,
    LoadFactory,
    PaymentTermsFactory,
    RoutePointFactory,
    make_load_with_route,
)


@pytest.mark.django_db
def test_load_defaults_and_str() -> None:
    """Verify Load default fields, str representation, and relations."""
    shipper = ShipperUserFactory()
    load = Load.objects.create(
        shipper=shipper,
        cargo_description="Cotton fabric",
        weight_t=Decimal("12.500"),
    )

    assert load.status == Load.Status.DRAFT
    assert load.transport_mode == Load.TransportMode.FTL
    assert load.trucks_needed == 1
    assert load.trucks_found == 0
    assert load.price_negotiable is True
    assert load.is_adr is False
    assert load.temp_controlled is False
    assert str(load) == f"Load #{load.pk}: Cotton fabric (draft)"


@pytest.mark.django_db
def test_load_clean_validations() -> None:
    """Verify Load model clean validations for ADR, temperature control, and currency."""
    shipper = ShipperUserFactory()
    currency = CurrencyFactory(code="USD")

    # ADR without adr_class
    adr_load = Load(
        shipper=shipper,
        cargo_description="Hazardous chemicals",
        weight_t=Decimal("5.000"),
        is_adr=True,
        adr_class=None,
    )
    with pytest.raises(ValidationError) as exc_info:
        adr_load.full_clean()
    assert "adr_class" in exc_info.value.message_dict

    # Temperature control without limits
    temp_load = Load(
        shipper=shipper,
        cargo_description="Fresh produce",
        weight_t=Decimal("10.000"),
        temp_controlled=True,
    )
    with pytest.raises(ValidationError) as exc_info:
        temp_load.full_clean()
    assert "temp_min_c" in exc_info.value.message_dict

    # Inverted temperature range
    inverted_temp_load = Load(
        shipper=shipper,
        cargo_description="Frozen fish",
        weight_t=Decimal("10.000"),
        temp_controlled=True,
        temp_min_c=Decimal("15.00"),
        temp_max_c=Decimal("5.00"),
    )
    with pytest.raises(ValidationError) as exc_info:
        inverted_temp_load.full_clean()
    assert "temp_max_c" in exc_info.value.message_dict

    # Price without currency
    price_load = Load(
        shipper=shipper,
        cargo_description="Consumer goods",
        weight_t=Decimal("8.000"),
        price_amount=Decimal("1200.00"),
        currency=None,
    )
    with pytest.raises(ValidationError) as exc_info:
        price_load.full_clean()
    assert "currency" in exc_info.value.message_dict

    # Valid load passes clean
    valid_load = Load(
        shipper=shipper,
        cargo_description="Consumer goods",
        weight_t=Decimal("8.000"),
        is_adr=True,
        adr_class=3,
        temp_controlled=True,
        temp_min_c=Decimal("-18.00"),
        temp_max_c=Decimal("-15.00"),
        price_amount=Decimal("1200.00"),
        currency=currency,
    )
    valid_load.full_clean()


@pytest.mark.django_db
def test_route_point_ordering_and_unique_constraint() -> None:
    """Verify RoutePoint ordering by seq and unique (load, seq) constraint."""
    load = LoadFactory()
    country = CountryFactory(code="UZ")

    point_2 = RoutePoint.objects.create(
        load=load,
        seq=2,
        kind=RoutePoint.Kind.UNLOADING,
        country=country,
        lat=Decimal("41.300000"),
        lng=Decimal("69.240000"),
    )
    point_1 = RoutePoint.objects.create(
        load=load,
        seq=1,
        kind=RoutePoint.Kind.LOADING,
        country=country,
        lat=Decimal("41.200000"),
        lng=Decimal("69.100000"),
    )

    # Ordering by seq
    points = list(load.route_points.all())
    assert points == [point_1, point_2]
    assert str(point_1) == f"RoutePoint #1 (loading) - Load #{load.pk}"

    # Unique constraint violation
    with pytest.raises(IntegrityError):
        RoutePoint.objects.create(
            load=load,
            seq=1,
            kind=RoutePoint.Kind.STOP,
            country=country,
            lat=Decimal("41.250000"),
            lng=Decimal("69.150000"),
        )


@pytest.mark.django_db
def test_payment_terms_onetoone_and_str() -> None:
    """Verify PaymentTerms OneToOne primary key to Load and factory."""
    terms = PaymentTermsFactory(
        prepay_amount=Decimal("300.00"),
        prepay_method=PaymentTerms.PrepayMethod.CASH,
        paid_amount=Decimal("700.00"),
        paid_method=PaymentTerms.PrepayMethod.TRANSFER,
    )

    load = terms.load
    assert terms.pk == load.pk
    assert load.payment_terms == terms
    assert str(terms) == f"PaymentTerms for Load #{load.pk}"


@pytest.mark.django_db
def test_load_document_and_str() -> None:
    """Verify LoadDocument creation and str representation."""
    doc = LoadDocumentFactory(name="CMR_waybill.pdf")
    assert str(doc) == f"CMR_waybill.pdf (Load #{doc.load_id})"
    assert doc in doc.load.documents.all()


@pytest.mark.django_db
def test_favorite_unique_constraint_and_str() -> None:
    """Verify Favorite unique (user, load) constraint and factory."""
    fav = FavoriteFactory()
    user = fav.user
    load = fav.load

    assert str(fav) == f"User #{user.pk} -> Load #{load.pk}"
    assert fav in load.favorites.all()

    with pytest.raises(IntegrityError):
        Favorite.objects.create(user=user, load=load)


@pytest.mark.django_db
def test_route_point_factory() -> None:
    """Verify RoutePointFactory generates valid route point."""
    point = RoutePointFactory(seq=3, kind=RoutePoint.Kind.CUSTOMS)
    assert point.seq == 3
    assert point.kind == RoutePoint.Kind.CUSTOMS


@pytest.mark.django_db
def test_make_load_with_route_helper() -> None:
    """Verify make_load_with_route helper creates route points properly."""
    load = make_load_with_route()
    route_points = list(load.route_points.all())

    assert len(route_points) == 2
    assert route_points[0].seq == 1
    assert route_points[0].kind == RoutePoint.Kind.LOADING
    assert route_points[0].country.code == "UZ"
    assert route_points[1].seq == 2
    assert route_points[1].kind == RoutePoint.Kind.UNLOADING
    assert route_points[1].country.code == "RU"
