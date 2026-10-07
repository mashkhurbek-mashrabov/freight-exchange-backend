"""Unit tests for loads domain services."""

from decimal import Decimal

import pytest

from apps.accounts.models import User
from apps.accounts.tests.factories import CarrierUserFactory, ShipperUserFactory, UserFactory
from apps.core.exceptions import ServiceError
from apps.garage.models import VehicleType
from apps.geo.models import Country, Currency
from apps.loads.models import Favorite, Load, RoutePoint
from apps.loads.services import (
    add_favorite,
    cancel_load,
    compute_distance_km,
    create_load,
    publish_load,
    remove_favorite,
    update_load,
)
from apps.notifications.models import Notification
from apps.offers.models import Offer
from apps.offers.tests.factories import OfferFactory


@pytest.fixture
def countries(db: None) -> tuple[Country, Country, Country]:
    uz, _ = Country.objects.get_or_create(
        code="UZ",
        defaults={"name_i18n": {"en": "Uzbekistan", "ru": "Узбекистан", "uz": "O'zbekiston"}},
    )
    kz, _ = Country.objects.get_or_create(
        code="KZ",
        defaults={"name_i18n": {"en": "Kazakhstan", "ru": "Казахстан", "uz": "Qozog'iston"}},
    )
    ru, _ = Country.objects.get_or_create(
        code="RU",
        defaults={"name_i18n": {"en": "Russia", "ru": "Россия", "uz": "Rossiya"}},
    )
    return uz, kz, ru


@pytest.fixture
def currency_usd(db: None) -> Currency:
    curr, _ = Currency.objects.get_or_create(code="USD", defaults={"name": "US Dollar"})
    return curr


@pytest.fixture
def vehicle_type_tent(db: None) -> VehicleType:
    vt, _ = VehicleType.objects.get_or_create(
        code="tent",
        defaults={"name_i18n": {"en": "Tilt", "ru": "Тент"}, "kind": VehicleType.Kind.TRAILER},
    )
    return vt


@pytest.mark.django_db
def test_compute_distance_km(countries: tuple[Country, Country, Country]) -> None:
    points = [
        {"lat": Decimal("41.299496"), "lng": Decimal("69.240073")},  # Tashkent
        {"lat": Decimal("55.755826"), "lng": Decimal("37.617300")},  # Moscow
    ]
    dist = compute_distance_km(points)
    assert dist > 2500


@pytest.mark.django_db
def test_create_load_with_three_route_points(
    countries: tuple[Country, Country, Country],
    currency_usd: Currency,
    vehicle_type_tent: VehicleType,
) -> None:
    shipper = ShipperUserFactory()
    data = {
        "cargo_description": "Appliance shipment",
        "weight_t": Decimal("20.000"),
        "trucks_needed": 1,
        "price_amount": Decimal("3000.00"),
        "currency": currency_usd,
        "body_types": [vehicle_type_tent.pk],
        "route_points": [
            {
                "seq": 1,
                "kind": RoutePoint.Kind.LOADING,
                "country": "UZ",
                "address": "Tashkent",
                "lat": Decimal("41.299496"),
                "lng": Decimal("69.240073"),
            },
            {
                "seq": 2,
                "kind": RoutePoint.Kind.CUSTOMS,
                "country": "KZ",
                "address": "Zhibek Zholy",
                "lat": Decimal("43.344990"),
                "lng": Decimal("68.257320"),
            },
            {
                "seq": 3,
                "kind": RoutePoint.Kind.UNLOADING,
                "country": "RU",
                "address": "Moscow",
                "lat": Decimal("55.755826"),
                "lng": Decimal("37.617300"),
            },
        ],
        "payment_terms": {
            "prepay_amount": Decimal("1000.00"),
            "prepay_method": "transfer",
            "paid_amount": Decimal("2000.00"),
            "paid_method": "transfer",
            "remaining_amount": Decimal("0.00"),
            "payment_due_days": 5,
        },
    }

    load = create_load(shipper, data)
    assert load.status == Load.Status.DRAFT
    assert load.shipper == shipper
    assert load.route_points.count() == 3
    assert load.body_types.filter(pk=vehicle_type_tent.pk).exists()
    assert load.payment_terms is not None
    assert load.payment_terms.payment_due_days == 5
    assert load.distance_km is not None
    assert load.distance_km > 0


@pytest.mark.django_db
def test_create_load_client_provided_distance_kept(
    countries: tuple[Country, Country, Country],
) -> None:
    shipper = ShipperUserFactory()
    data = {
        "cargo_description": "Goods",
        "weight_t": Decimal("10.000"),
        "distance_km": 1500,
        "route_points": [
            {
                "seq": 1,
                "kind": RoutePoint.Kind.LOADING,
                "country": "UZ",
                "lat": Decimal("41.299496"),
                "lng": Decimal("69.240073"),
            },
            {
                "seq": 2,
                "kind": RoutePoint.Kind.UNLOADING,
                "country": "RU",
                "lat": Decimal("55.755826"),
                "lng": Decimal("37.617300"),
            },
        ],
    }
    load = create_load(shipper, data)
    assert load.distance_km == 1500


@pytest.mark.django_db
def test_create_load_validation_empty_route_points() -> None:
    shipper = ShipperUserFactory()
    data = {
        "cargo_description": "Goods",
        "weight_t": Decimal("10.000"),
        "route_points": [],
    }
    with pytest.raises(ServiceError) as exc:
        create_load(shipper, data)
    assert exc.value.code == "validation_error"
    assert exc.value.status_code == 400


@pytest.mark.django_db
def test_create_load_validation_first_not_loading(
    countries: tuple[Country, Country, Country],
) -> None:
    shipper = ShipperUserFactory()
    data = {
        "cargo_description": "Goods",
        "weight_t": Decimal("10.000"),
        "route_points": [
            {
                "seq": 1,
                "kind": RoutePoint.Kind.STOP,
                "country": "UZ",
                "lat": Decimal("41.0"),
                "lng": Decimal("69.0"),
            },
            {
                "seq": 2,
                "kind": RoutePoint.Kind.UNLOADING,
                "country": "RU",
                "lat": Decimal("55.0"),
                "lng": Decimal("37.0"),
            },
        ],
    }
    with pytest.raises(ServiceError) as exc:
        create_load(shipper, data)
    assert exc.value.code == "validation_error"
    assert "First route point must be loading" in exc.value.detail


@pytest.mark.django_db
def test_create_load_validation_last_not_unloading(
    countries: tuple[Country, Country, Country],
) -> None:
    shipper = ShipperUserFactory()
    data = {
        "cargo_description": "Goods",
        "weight_t": Decimal("10.000"),
        "route_points": [
            {
                "seq": 1,
                "kind": RoutePoint.Kind.LOADING,
                "country": "UZ",
                "lat": Decimal("41.0"),
                "lng": Decimal("69.0"),
            },
            {
                "seq": 2,
                "kind": RoutePoint.Kind.BORDER,
                "country": "KZ",
                "lat": Decimal("43.0"),
                "lng": Decimal("68.0"),
            },
        ],
    }
    with pytest.raises(ServiceError) as exc:
        create_load(shipper, data)
    assert exc.value.code == "validation_error"
    assert "Last route point must be unloading" in exc.value.detail


@pytest.mark.django_db
def test_create_load_validation_seq_not_unique(
    countries: tuple[Country, Country, Country],
) -> None:
    shipper = ShipperUserFactory()
    data = {
        "cargo_description": "Goods",
        "weight_t": Decimal("10.000"),
        "route_points": [
            {
                "seq": 1,
                "kind": RoutePoint.Kind.LOADING,
                "country": "UZ",
                "lat": Decimal("41.0"),
                "lng": Decimal("69.0"),
            },
            {
                "seq": 1,
                "kind": RoutePoint.Kind.UNLOADING,
                "country": "RU",
                "lat": Decimal("55.0"),
                "lng": Decimal("37.0"),
            },
        ],
    }
    with pytest.raises(ServiceError) as exc:
        create_load(shipper, data)
    assert exc.value.code == "validation_error"
    assert "sequence numbers must be unique" in exc.value.detail


@pytest.mark.django_db
def test_create_load_validation_adr_class_required(
    countries: tuple[Country, Country, Country],
) -> None:
    shipper = ShipperUserFactory()
    data = {
        "cargo_description": "Hazardous chemicals",
        "weight_t": Decimal("10.000"),
        "is_adr": True,
        "adr_class": None,
        "route_points": [
            {
                "seq": 1,
                "kind": RoutePoint.Kind.LOADING,
                "country": "UZ",
                "lat": Decimal("41.0"),
                "lng": Decimal("69.0"),
            },
            {
                "seq": 2,
                "kind": RoutePoint.Kind.UNLOADING,
                "country": "RU",
                "lat": Decimal("55.0"),
                "lng": Decimal("37.0"),
            },
        ],
    }
    with pytest.raises(ServiceError) as exc:
        create_load(shipper, data)
    assert exc.value.code == "validation_error"
    assert "ADR class is required" in exc.value.detail


@pytest.mark.django_db
def test_create_load_validation_temp_controlled_requires_temps(
    countries: tuple[Country, Country, Country],
) -> None:
    shipper = ShipperUserFactory()
    data = {
        "cargo_description": "Frozen meat",
        "weight_t": Decimal("10.000"),
        "temp_controlled": True,
        "temp_min_c": None,
        "temp_max_c": Decimal("4.0"),
        "route_points": [
            {
                "seq": 1,
                "kind": RoutePoint.Kind.LOADING,
                "country": "UZ",
                "lat": Decimal("41.0"),
                "lng": Decimal("69.0"),
            },
            {
                "seq": 2,
                "kind": RoutePoint.Kind.UNLOADING,
                "country": "RU",
                "lat": Decimal("55.0"),
                "lng": Decimal("37.0"),
            },
        ],
    }
    with pytest.raises(ServiceError) as exc:
        create_load(shipper, data)
    assert exc.value.code == "validation_error"


@pytest.mark.django_db
def test_create_load_validation_temp_min_greater_than_max(
    countries: tuple[Country, Country, Country],
) -> None:
    shipper = ShipperUserFactory()
    data = {
        "cargo_description": "Produce",
        "weight_t": Decimal("10.000"),
        "temp_controlled": True,
        "temp_min_c": Decimal("10.0"),
        "temp_max_c": Decimal("2.0"),
        "route_points": [
            {
                "seq": 1,
                "kind": RoutePoint.Kind.LOADING,
                "country": "UZ",
                "lat": Decimal("41.0"),
                "lng": Decimal("69.0"),
            },
            {
                "seq": 2,
                "kind": RoutePoint.Kind.UNLOADING,
                "country": "RU",
                "lat": Decimal("55.0"),
                "lng": Decimal("37.0"),
            },
        ],
    }
    with pytest.raises(ServiceError) as exc:
        create_load(shipper, data)
    assert exc.value.code == "validation_error"
    assert "cannot be greater than" in exc.value.detail


@pytest.mark.django_db
def test_create_load_validation_price_requires_currency(
    countries: tuple[Country, Country, Country],
) -> None:
    shipper = ShipperUserFactory()
    data = {
        "cargo_description": "Goods",
        "weight_t": Decimal("10.000"),
        "price_amount": Decimal("1000.00"),
        "currency": None,
        "route_points": [
            {
                "seq": 1,
                "kind": RoutePoint.Kind.LOADING,
                "country": "UZ",
                "lat": Decimal("41.0"),
                "lng": Decimal("69.0"),
            },
            {
                "seq": 2,
                "kind": RoutePoint.Kind.UNLOADING,
                "country": "RU",
                "lat": Decimal("55.0"),
                "lng": Decimal("37.0"),
            },
        ],
    }
    with pytest.raises(ServiceError) as exc:
        create_load(shipper, data)
    assert exc.value.code == "validation_error"
    assert "Currency is required" in exc.value.detail


@pytest.mark.django_db
def test_create_load_validation_trucks_needed_less_than_one(
    countries: tuple[Country, Country, Country],
) -> None:
    shipper = ShipperUserFactory()
    data = {
        "cargo_description": "Goods",
        "weight_t": Decimal("10.000"),
        "trucks_needed": 0,
        "route_points": [
            {
                "seq": 1,
                "kind": RoutePoint.Kind.LOADING,
                "country": "UZ",
                "lat": Decimal("41.0"),
                "lng": Decimal("69.0"),
            },
            {
                "seq": 2,
                "kind": RoutePoint.Kind.UNLOADING,
                "country": "RU",
                "lat": Decimal("55.0"),
                "lng": Decimal("37.0"),
            },
        ],
    }
    with pytest.raises(ServiceError) as exc:
        create_load(shipper, data)
    assert exc.value.code == "validation_error"
    assert "trucks_needed must be at least 1" in exc.value.detail


@pytest.mark.django_db
def test_create_load_validation_weight_must_be_positive(
    countries: tuple[Country, Country, Country],
) -> None:
    shipper = ShipperUserFactory()
    data = {
        "cargo_description": "Goods",
        "weight_t": Decimal("0.0"),
        "route_points": [
            {
                "seq": 1,
                "kind": RoutePoint.Kind.LOADING,
                "country": "UZ",
                "lat": Decimal("41.0"),
                "lng": Decimal("69.0"),
            },
            {
                "seq": 2,
                "kind": RoutePoint.Kind.UNLOADING,
                "country": "RU",
                "lat": Decimal("55.0"),
                "lng": Decimal("37.0"),
            },
        ],
    }
    with pytest.raises(ServiceError) as exc:
        create_load(shipper, data)
    assert exc.value.code == "validation_error"
    assert "weight_t must be greater than 0" in exc.value.detail


@pytest.mark.django_db
def test_create_load_unverified_user_raises_403(
    countries: tuple[Country, Country, Country],
) -> None:
    user = UserFactory(role=User.Role.SHIPPER, status=User.Status.NEW)
    data = {
        "cargo_description": "Goods",
        "weight_t": Decimal("10.000"),
        "route_points": [
            {
                "seq": 1,
                "kind": RoutePoint.Kind.LOADING,
                "country": "UZ",
                "lat": Decimal("41.0"),
                "lng": Decimal("69.0"),
            },
            {
                "seq": 2,
                "kind": RoutePoint.Kind.UNLOADING,
                "country": "RU",
                "lat": Decimal("55.0"),
                "lng": Decimal("37.0"),
            },
        ],
    }
    with pytest.raises(ServiceError) as exc:
        create_load(user, data)
    assert exc.value.code == "account_not_verified"
    assert exc.value.status_code == 403


@pytest.mark.django_db
def test_create_load_carrier_only_role_raises_403(
    countries: tuple[Country, Country, Country],
) -> None:
    carrier = CarrierUserFactory()
    data = {
        "cargo_description": "Goods",
        "weight_t": Decimal("10.000"),
        "route_points": [
            {
                "seq": 1,
                "kind": RoutePoint.Kind.LOADING,
                "country": "UZ",
                "lat": Decimal("41.0"),
                "lng": Decimal("69.0"),
            },
            {
                "seq": 2,
                "kind": RoutePoint.Kind.UNLOADING,
                "country": "RU",
                "lat": Decimal("55.0"),
                "lng": Decimal("37.0"),
            },
        ],
    }
    with pytest.raises(ServiceError) as exc:
        create_load(carrier, data)
    assert exc.value.code == "role_not_allowed"
    assert exc.value.status_code == 403


@pytest.mark.django_db
def test_update_load_replaces_route_points(countries: tuple[Country, Country, Country]) -> None:
    shipper = ShipperUserFactory()
    data = {
        "cargo_description": "Initial goods",
        "weight_t": Decimal("10.000"),
        "route_points": [
            {
                "seq": 1,
                "kind": RoutePoint.Kind.LOADING,
                "country": "UZ",
                "lat": Decimal("41.0"),
                "lng": Decimal("69.0"),
            },
            {
                "seq": 2,
                "kind": RoutePoint.Kind.UNLOADING,
                "country": "RU",
                "lat": Decimal("55.0"),
                "lng": Decimal("37.0"),
            },
        ],
    }
    load = create_load(shipper, data)
    assert load.route_points.count() == 2

    # Update with 3 route points
    update_data = {
        "cargo_description": "Updated goods",
        "route_points": [
            {
                "seq": 1,
                "kind": RoutePoint.Kind.LOADING,
                "country": "UZ",
                "lat": Decimal("41.299496"),
                "lng": Decimal("69.240073"),
            },
            {
                "seq": 2,
                "kind": RoutePoint.Kind.CUSTOMS,
                "country": "KZ",
                "lat": Decimal("43.344990"),
                "lng": Decimal("68.257320"),
            },
            {
                "seq": 3,
                "kind": RoutePoint.Kind.UNLOADING,
                "country": "RU",
                "lat": Decimal("55.755826"),
                "lng": Decimal("37.617300"),
            },
        ],
    }
    updated = update_load(load, update_data, user=shipper)
    assert updated.cargo_description == "Updated goods"
    assert updated.route_points.count() == 3


@pytest.mark.django_db
def test_update_load_only_owner_allowed(countries: tuple[Country, Country, Country]) -> None:
    shipper = ShipperUserFactory()
    other_shipper = ShipperUserFactory()
    data = {
        "cargo_description": "Initial",
        "weight_t": Decimal("10.000"),
        "route_points": [
            {
                "seq": 1,
                "kind": RoutePoint.Kind.LOADING,
                "country": "UZ",
                "lat": Decimal("41.0"),
                "lng": Decimal("69.0"),
            },
            {
                "seq": 2,
                "kind": RoutePoint.Kind.UNLOADING,
                "country": "RU",
                "lat": Decimal("55.0"),
                "lng": Decimal("37.0"),
            },
        ],
    }
    load = create_load(shipper, data)

    with pytest.raises(ServiceError) as exc:
        update_load(load, {"cargo_description": "Hacked"}, user=other_shipper)
    assert exc.value.code == "permission_denied"
    assert exc.value.status_code == 403


@pytest.mark.django_db
def test_update_load_cannot_update_completed_or_cancelled(
    countries: tuple[Country, Country, Country],
) -> None:
    shipper = ShipperUserFactory()
    data = {
        "cargo_description": "Initial",
        "weight_t": Decimal("10.000"),
        "route_points": [
            {
                "seq": 1,
                "kind": RoutePoint.Kind.LOADING,
                "country": "UZ",
                "lat": Decimal("41.0"),
                "lng": Decimal("69.0"),
            },
            {
                "seq": 2,
                "kind": RoutePoint.Kind.UNLOADING,
                "country": "RU",
                "lat": Decimal("55.0"),
                "lng": Decimal("37.0"),
            },
        ],
    }
    load = create_load(shipper, data)
    load.status = Load.Status.COMPLETED
    load.save(update_fields=["status"])

    with pytest.raises(ServiceError) as exc:
        update_load(load, {"cargo_description": "New"}, user=shipper)
    assert exc.value.code == "invalid_transition"
    assert exc.value.status_code == 409

    load.status = Load.Status.CANCELLED
    load.save(update_fields=["status"])

    with pytest.raises(ServiceError) as exc:
        update_load(load, {"cargo_description": "New"}, user=shipper)
    assert exc.value.code == "invalid_transition"
    assert exc.value.status_code == 409


@pytest.mark.django_db
def test_publish_load_success(countries: tuple[Country, Country, Country]) -> None:
    shipper = ShipperUserFactory()
    data = {
        "cargo_description": "To be published",
        "weight_t": Decimal("12.000"),
        "route_points": [
            {
                "seq": 1,
                "kind": RoutePoint.Kind.LOADING,
                "country": "UZ",
                "lat": Decimal("41.0"),
                "lng": Decimal("69.0"),
            },
            {
                "seq": 2,
                "kind": RoutePoint.Kind.UNLOADING,
                "country": "RU",
                "lat": Decimal("55.0"),
                "lng": Decimal("37.0"),
            },
        ],
    }
    load = create_load(shipper, data)
    assert load.status == Load.Status.DRAFT

    published = publish_load(load, user=shipper)
    assert published.status == Load.Status.ACTIVE
    assert published.published_at is not None
    assert published.expires_at is not None
    # Default expiry is approximately +7 days
    diff = published.expires_at - published.published_at
    assert diff.days == 7


@pytest.mark.django_db
def test_publish_load_twice_raises_409(countries: tuple[Country, Country, Country]) -> None:
    shipper = ShipperUserFactory()
    data = {
        "cargo_description": "Goods",
        "weight_t": Decimal("10.000"),
        "route_points": [
            {
                "seq": 1,
                "kind": RoutePoint.Kind.LOADING,
                "country": "UZ",
                "lat": Decimal("41.0"),
                "lng": Decimal("69.0"),
            },
            {
                "seq": 2,
                "kind": RoutePoint.Kind.UNLOADING,
                "country": "RU",
                "lat": Decimal("55.0"),
                "lng": Decimal("37.0"),
            },
        ],
    }
    load = create_load(shipper, data)
    publish_load(load, user=shipper)

    with pytest.raises(ServiceError) as exc:
        publish_load(load, user=shipper)
    assert exc.value.code == "invalid_transition"
    assert exc.value.status_code == 409


@pytest.mark.django_db
def test_cancel_load_rejects_pending_offers(countries: tuple[Country, Country, Country]) -> None:
    shipper = ShipperUserFactory()
    carrier = CarrierUserFactory()
    data = {
        "cargo_description": "Goods",
        "weight_t": Decimal("10.000"),
        "route_points": [
            {
                "seq": 1,
                "kind": RoutePoint.Kind.LOADING,
                "country": "UZ",
                "lat": Decimal("41.0"),
                "lng": Decimal("69.0"),
            },
            {
                "seq": 2,
                "kind": RoutePoint.Kind.UNLOADING,
                "country": "RU",
                "lat": Decimal("55.0"),
                "lng": Decimal("37.0"),
            },
        ],
    }
    load = create_load(shipper, data)
    publish_load(load, user=shipper)

    offer = OfferFactory(
        load=load,
        carrier=carrier,
        proposer=carrier,
        recipient=shipper,
        status=Offer.Status.PENDING,
    )

    cancelled = cancel_load(load, user=shipper)
    assert cancelled.status == Load.Status.CANCELLED

    offer.refresh_from_db()
    assert offer.status == Offer.Status.REJECTED
    assert offer.responded_at is not None

    notif = Notification.objects.filter(
        user=carrier, type=Notification.NotificationType.OFFER_REJECTED
    ).first()
    assert notif is not None
    assert notif.payload.get("reason") == "load_cancelled"


@pytest.mark.django_db
def test_favorite_add_and_remove_idempotent(countries: tuple[Country, Country, Country]) -> None:
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    data = {
        "cargo_description": "Fav load",
        "weight_t": Decimal("10.000"),
        "route_points": [
            {
                "seq": 1,
                "kind": RoutePoint.Kind.LOADING,
                "country": "UZ",
                "lat": Decimal("41.0"),
                "lng": Decimal("69.0"),
            },
            {
                "seq": 2,
                "kind": RoutePoint.Kind.UNLOADING,
                "country": "RU",
                "lat": Decimal("55.0"),
                "lng": Decimal("37.0"),
            },
        ],
    }
    load = create_load(shipper, data)

    # Add twice
    add_favorite(carrier, load)
    add_favorite(carrier, load)
    assert Favorite.objects.filter(user=carrier, load=load).count() == 1

    # Remove twice
    assert remove_favorite(carrier, load) is True
    assert remove_favorite(carrier, load) is False
    assert Favorite.objects.filter(user=carrier, load=load).count() == 0
