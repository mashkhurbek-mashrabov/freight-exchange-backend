"""Integration and API view tests for load write and detail endpoints."""

from decimal import Decimal

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Company, User
from apps.accounts.tests.factories import CarrierUserFactory, ShipperUserFactory, UserFactory
from apps.garage.models import VehicleType
from apps.geo.models import Country, Currency
from apps.loads.models import Favorite, Load, RoutePoint
from apps.loads.services import create_load, publish_load
from apps.offers.tests.factories import OfferFactory


@pytest.fixture
def countries(db: None) -> tuple[Country, Country, Country]:
    uz, _ = Country.objects.get_or_create(
        code="UZ",
        defaults={"name_i18n": {"en": "Uzbekistan", "ru": "Узбекистан"}},
    )
    kz, _ = Country.objects.get_or_create(
        code="KZ",
        defaults={"name_i18n": {"en": "Kazakhstan", "ru": "Казахстан"}},
    )
    ru, _ = Country.objects.get_or_create(
        code="RU",
        defaults={"name_i18n": {"en": "Russia", "ru": "Россия"}},
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
def test_create_load_api_success(
    countries: tuple[Country, Country, Country],
    currency_usd: Currency,
    vehicle_type_tent: VehicleType,
) -> None:
    shipper = ShipperUserFactory()
    company = Company.objects.create(owner=shipper, name="Global Freight LLC")

    client = APIClient()
    client.force_authenticate(user=shipper)

    payload = {
        "cargo_description": "Electronics pallet cargo",
        "cargo_type": "electronics",
        "weight_t": "18.500",
        "volume_m3": "85.000",
        "length_m": "13.60",
        "packaging": "pallet",
        "transport_mode": "FTL",
        "vehicle_category": "curtainsider",
        "trucks_needed": 1,
        "is_adr": False,
        "temp_controlled": False,
        "price_amount": "3200.00",
        "currency": "USD",
        "vat_included": False,
        "price_negotiable": True,
        "body_types": [vehicle_type_tent.pk],
        "route_points": [
            {
                "seq": 1,
                "kind": "loading",
                "country": "UZ",
                "address": "Tashkent",
                "lat": "41.299496",
                "lng": "69.240073",
                "asap": True,
                "ready_to_load": True,
                "comment": "Gate 1",
            },
            {
                "seq": 2,
                "kind": "customs",
                "country": "KZ",
                "address": "Zhibek Zholy",
                "lat": "43.344990",
                "lng": "68.257320",
                "comment": "Customs clearance",
            },
            {
                "seq": 3,
                "kind": "unloading",
                "country": "RU",
                "address": "Moscow",
                "lat": "55.755826",
                "lng": "37.617300",
                "comment": "Terminal",
            },
        ],
        "payment_terms": {
            "prepay_amount": "1000.00",
            "prepay_method": "transfer",
            "paid_amount": "2200.00",
            "paid_method": "transfer",
            "remaining_amount": "0.00",
            "payment_due_days": 7,
            "conditions": "Net 7 days",
        },
    }

    res = client.post("/api/v1/loads", data=payload, format="json")
    assert res.status_code == status.HTTP_201_CREATED
    data = res.json()

    assert data["status"] == "draft"
    assert data["shipper"] == shipper.pk
    assert data["shipper_company_name"] == company.name
    assert len(data["route_points"]) == 3
    assert data["route_points"][0]["country"]["code"] == "UZ"
    assert data["payment_terms"]["payment_due_days"] == 7
    assert data["is_favorite"] is False
    assert data["my_offer"] is None
    assert isinstance(data["weight_t"], str)
    assert isinstance(data["price_amount"], str)
    assert data["distance_km"] is not None
    assert data["distance_km"] > 0


@pytest.mark.django_db
def test_create_load_unverified_403(countries: tuple[Country, Country, Country]) -> None:
    user = UserFactory(role=User.Role.SHIPPER, status=User.Status.NEW)
    client = APIClient()
    client.force_authenticate(user=user)

    res = client.post(
        "/api/v1/loads",
        data={"cargo_description": "Load", "weight_t": "10.0"},
        format="json",
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN
    assert res.json()["code"] == "account_not_verified"


@pytest.mark.django_db
def test_create_load_carrier_role_403(countries: tuple[Country, Country, Country]) -> None:
    carrier = CarrierUserFactory()
    client = APIClient()
    client.force_authenticate(user=carrier)

    res = client.post(
        "/api/v1/loads",
        data={"cargo_description": "Load", "weight_t": "10.0"},
        format="json",
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN
    assert res.json()["code"] == "role_not_allowed"


@pytest.mark.django_db
def test_create_load_unauthenticated_401() -> None:
    client = APIClient()
    res = client.post(
        "/api/v1/loads",
        data={"cargo_description": "Load", "weight_t": "10.0"},
        format="json",
    )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert res.json()["code"] == "not_authenticated"


@pytest.mark.django_db
def test_create_load_validation_errors(countries: tuple[Country, Country, Country]) -> None:
    shipper = ShipperUserFactory()
    client = APIClient()
    client.force_authenticate(user=shipper)

    # Empty route points
    res = client.post(
        "/api/v1/loads",
        data={"cargo_description": "Load", "weight_t": "10.0", "route_points": []},
        format="json",
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.json()["code"] == "validation_error"


@pytest.mark.django_db
def test_get_load_detail_draft_hidden_from_non_owner(
    countries: tuple[Country, Country, Country],
) -> None:
    shipper = ShipperUserFactory()
    other_user = CarrierUserFactory()

    data = {
        "cargo_description": "Secret draft",
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

    # Owner gets 200
    client = APIClient()
    client.force_authenticate(user=shipper)
    res = client.get(f"/api/v1/loads/{load.pk}")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["id"] == load.pk

    # Non-owner gets 404
    client.force_authenticate(user=other_user)
    res = client.get(f"/api/v1/loads/{load.pk}")
    assert res.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_get_load_detail_active_load_visible_with_offer_and_favorite(
    countries: tuple[Country, Country, Country],
    currency_usd: Currency,
) -> None:
    shipper = ShipperUserFactory()
    carrier = CarrierUserFactory()

    data = {
        "cargo_description": "Public active load",
        "weight_t": Decimal("10.000"),
        "price_amount": Decimal("2500.00"),
        "currency": currency_usd,
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

    # Add favorite for carrier
    Favorite.objects.create(user=carrier, load=load)

    # Carrier makes an offer
    offer = OfferFactory(
        load=load,
        carrier=carrier,
        proposer=carrier,
        recipient=shipper,
        amount=Decimal("2400.00"),
        currency=currency_usd,
    )

    client = APIClient()
    client.force_authenticate(user=carrier)
    res = client.get(f"/api/v1/loads/{load.pk}")
    assert res.status_code == status.HTTP_200_OK
    resp_data = res.json()

    assert resp_data["is_favorite"] is True
    assert resp_data["my_offer"] is not None
    assert resp_data["my_offer"]["id"] == offer.pk
    assert resp_data["my_offer"]["amount"] == "2400.00"
    assert resp_data["my_offer"]["currency"] == "USD"


@pytest.mark.django_db
def test_patch_load_detail_success(countries: tuple[Country, Country, Country]) -> None:
    shipper = ShipperUserFactory()
    data = {
        "cargo_description": "Original",
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

    client = APIClient()
    client.force_authenticate(user=shipper)
    res = client.patch(
        f"/api/v1/loads/{load.pk}",
        data={"cargo_description": "Patched description"},
        format="json",
    )
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["cargo_description"] == "Patched description"


@pytest.mark.django_db
def test_patch_load_detail_forbidden_for_non_owner(
    countries: tuple[Country, Country, Country],
) -> None:
    shipper = ShipperUserFactory()
    other_shipper = ShipperUserFactory()
    data = {
        "cargo_description": "Original",
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

    client = APIClient()
    client.force_authenticate(user=other_shipper)
    res = client.patch(
        f"/api/v1/loads/{load.pk}",
        data={"cargo_description": "Hacked"},
        format="json",
    )
    assert res.status_code == status.HTTP_403_FORBIDDEN
    assert res.json()["code"] == "permission_denied"


@pytest.mark.django_db
def test_patch_load_detail_invalid_transition(
    countries: tuple[Country, Country, Country],
) -> None:
    shipper = ShipperUserFactory()
    data = {
        "cargo_description": "Original",
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

    client = APIClient()
    client.force_authenticate(user=shipper)
    res = client.patch(
        f"/api/v1/loads/{load.pk}",
        data={"cargo_description": "New"},
        format="json",
    )
    assert res.status_code == status.HTTP_409_CONFLICT
    assert res.json()["code"] == "invalid_transition"


@pytest.mark.django_db
def test_publish_load_endpoint(countries: tuple[Country, Country, Country]) -> None:
    shipper = ShipperUserFactory()
    other_shipper = ShipperUserFactory()

    data = {
        "cargo_description": "Original",
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

    # Non-owner fails
    client = APIClient()
    client.force_authenticate(user=other_shipper)
    res = client.post(f"/api/v1/loads/{load.pk}/publish")
    assert res.status_code == status.HTTP_403_FORBIDDEN

    # Owner succeeds
    client.force_authenticate(user=shipper)
    res = client.post(f"/api/v1/loads/{load.pk}/publish")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["status"] == "active"

    # Publish twice returns 409
    res = client.post(f"/api/v1/loads/{load.pk}/publish")
    assert res.status_code == status.HTTP_409_CONFLICT
    assert res.json()["code"] == "invalid_transition"


@pytest.mark.django_db
def test_cancel_load_endpoint(countries: tuple[Country, Country, Country]) -> None:
    shipper = ShipperUserFactory()
    other_shipper = ShipperUserFactory()

    data = {
        "cargo_description": "Original",
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

    # Non-owner fails
    client = APIClient()
    client.force_authenticate(user=other_shipper)
    res = client.post(f"/api/v1/loads/{load.pk}/cancel")
    assert res.status_code == status.HTTP_403_FORBIDDEN

    # Owner succeeds
    client.force_authenticate(user=shipper)
    res = client.post(f"/api/v1/loads/{load.pk}/cancel")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["status"] == "cancelled"


@pytest.mark.django_db
def test_favorite_endpoints(countries: tuple[Country, Country, Country]) -> None:
    shipper = ShipperUserFactory()
    carrier = CarrierUserFactory()

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
    publish_load(load, user=shipper)

    client = APIClient()
    client.force_authenticate(user=carrier)

    # POST favorite -> 204
    res = client.post(f"/api/v1/loads/{load.pk}/favorite")
    assert res.status_code == status.HTTP_204_NO_CONTENT
    assert Favorite.objects.filter(user=carrier, load=load).exists()

    # POST again (idempotent) -> 204
    res = client.post(f"/api/v1/loads/{load.pk}/favorite")
    assert res.status_code == status.HTTP_204_NO_CONTENT

    # Check GET shows is_favorite=True
    res = client.get(f"/api/v1/loads/{load.pk}")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["is_favorite"] is True

    # DELETE favorite -> 204
    res = client.delete(f"/api/v1/loads/{load.pk}/favorite")
    assert res.status_code == status.HTTP_204_NO_CONTENT
    assert not Favorite.objects.filter(user=carrier, load=load).exists()

    # DELETE again (idempotent) -> 204
    res = client.delete(f"/api/v1/loads/{load.pk}/favorite")
    assert res.status_code == status.HTTP_204_NO_CONTENT

    # Check GET shows is_favorite=False
    res = client.get(f"/api/v1/loads/{load.pk}")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["is_favorite"] is False


@pytest.mark.django_db
def test_create_load_rejects_zero_or_negative_price_amount(
    countries: tuple[Country, Country, Country],
    currency_usd: Currency,
) -> None:
    shipper = ShipperUserFactory()
    client = APIClient()
    client.force_authenticate(user=shipper)

    base_payload = {
        "cargo_description": "Timber",
        "weight_t": "10.000",
        "currency": "USD",
        "route_points": [
            {
                "seq": 1,
                "kind": RoutePoint.Kind.LOADING,
                "country": "UZ",
                "lat": "41.0",
                "lng": "69.0",
            },
            {
                "seq": 2,
                "kind": RoutePoint.Kind.UNLOADING,
                "country": "KZ",
                "lat": "43.0",
                "lng": "76.0",
            },
        ],
    }

    # Zero price amount
    payload_zero = {**base_payload, "price_amount": "0.00"}
    res = client.post("/api/v1/loads", data=payload_zero, format="json")
    assert res.status_code == status.HTTP_400_BAD_REQUEST

    # Negative price amount
    payload_neg = {**base_payload, "price_amount": "-500.00"}
    res = client.post("/api/v1/loads", data=payload_neg, format="json")
    assert res.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.django_db
def test_create_load_rejects_negative_payment_terms_amounts(
    countries: tuple[Country, Country, Country],
    currency_usd: Currency,
) -> None:
    shipper = ShipperUserFactory()
    client = APIClient()
    client.force_authenticate(user=shipper)

    payload = {
        "cargo_description": "Machinery",
        "weight_t": "15.000",
        "price_amount": "1200.00",
        "currency": "USD",
        "route_points": [
            {
                "seq": 1,
                "kind": RoutePoint.Kind.LOADING,
                "country": "UZ",
                "lat": "41.0",
                "lng": "69.0",
            },
            {
                "seq": 2,
                "kind": RoutePoint.Kind.UNLOADING,
                "country": "KZ",
                "lat": "43.0",
                "lng": "76.0",
            },
        ],
        "payment_terms": {
            "prepay_amount": "-100.00",
        },
    }
    res = client.post("/api/v1/loads", data=payload, format="json")
    assert res.status_code == status.HTTP_400_BAD_REQUEST

