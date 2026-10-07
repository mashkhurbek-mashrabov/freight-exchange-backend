"""API view tests for offers endpoints."""

from decimal import Decimal
from typing import Any

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.tests.factories import CarrierUserFactory, ShipperUserFactory, UserFactory
from apps.garage.models import VehicleKind
from apps.garage.tests.factories import VehicleFactory
from apps.geo.tests.factories import CountryFactory
from apps.loads.models import Load, RoutePoint
from apps.loads.tests.factories import LoadFactory, RoutePointFactory
from apps.offers.models import Offer
from apps.offers.tests.factories import OfferFactory
from apps.orders.models import Order


def _auth_client(user: User) -> APIClient:
    """Return APIClient authenticated with given user."""
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_endpoints_require_authentication() -> None:
    """Verify all offer endpoints return 401 when unauthenticated."""
    client = APIClient()

    resp = client.post("/api/v1/loads/1/offers", {})
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    resp = client.get("/api/v1/offers")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    resp = client.get("/api/v1/offers/1")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    resp = client.post("/api/v1/offers/1/accept")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    resp = client.post("/api/v1/offers/1/reject")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    resp = client.post("/api/v1/offers/1/cancel")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    resp = client.post("/api/v1/offers/1/counter", {})
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.django_db
def test_post_load_offers_success() -> None:
    """Verify verified carrier can submit offer with price_bid; phone is hidden before accept."""
    carrier = CarrierUserFactory(phone="+998901112233", full_name="Carrier One")
    shipper = ShipperUserFactory(phone="+998904445566", full_name="Shipper One")
    load = LoadFactory(shipper=shipper, status=Load.Status.ACTIVE)
    tractor = VehicleFactory(owner=carrier, kind=VehicleKind.TRACTOR)

    client = _auth_client(carrier)
    resp = client.post(
        f"/api/v1/loads/{load.pk}/offers",
        {
            "mode": "price_bid",
            "amount": "2300.00",
            "currency": load.currency.code,
            "vehicle_id": tractor.pk,
            "comment": "Can pick up immediately",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    data = resp.json()

    assert data["id"] is not None
    assert data["load_id"] == load.pk
    assert data["status"] == "pending"
    assert data["amount"] == "2300.00"
    assert data["vehicle_id"] == tractor.pk

    # Phone numbers hidden before acceptance
    assert data["carrier"]["id"] == carrier.pk
    assert data["carrier"]["full_name"] == "Carrier One"
    assert data["carrier"]["phone"] is None

    assert data["recipient"]["id"] == shipper.pk
    assert data["recipient"]["full_name"] == "Shipper One"
    assert data["recipient"]["phone"] is None


@pytest.mark.django_db
def test_post_load_offers_unverified_carrier_rejected() -> None:
    """Verify unverified carrier receives 403 account_not_verified."""
    unverified = UserFactory(role=User.Role.CARRIER, status=User.Status.NEW)
    load = LoadFactory(status=Load.Status.ACTIVE)

    client = _auth_client(unverified)
    resp = client.post(
        f"/api/v1/loads/{load.pk}/offers",
        {"mode": "price_bid", "amount": "2000.00", "currency": load.currency.code},
        format="json",
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert resp.json()["code"] == "account_not_verified"


@pytest.mark.django_db
def test_post_load_offers_shipper_role_rejected() -> None:
    """Verify shipper role cannot create offers (403 role_not_allowed)."""
    shipper = ShipperUserFactory()
    load = LoadFactory(status=Load.Status.ACTIVE)

    client = _auth_client(shipper)
    resp = client.post(
        f"/api/v1/loads/{load.pk}/offers",
        {"mode": "price_bid", "amount": "2000.00", "currency": load.currency.code},
        format="json",
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert resp.json()["code"] == "role_not_allowed"


@pytest.mark.django_db
def test_post_load_offers_own_load_rejected() -> None:
    """Verify carrier offering on own load gets 403 own_load."""
    user_both = UserFactory(role=User.Role.BOTH, status=User.Status.VERIFIED)
    own_load = LoadFactory(shipper=user_both, status=Load.Status.ACTIVE)

    client = _auth_client(user_both)
    resp = client.post(
        f"/api/v1/loads/{own_load.pk}/offers",
        {"mode": "price_bid", "amount": "2000.00", "currency": own_load.currency.code},
        format="json",
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert resp.json()["code"] == "own_load"


@pytest.mark.django_db
def test_post_load_offers_duplicate_pending_rejected() -> None:
    """Verify duplicate pending offer returns 409 duplicate_offer."""
    carrier = CarrierUserFactory()
    load = LoadFactory(status=Load.Status.ACTIVE)
    client = _auth_client(carrier)

    first_resp = client.post(
        f"/api/v1/loads/{load.pk}/offers",
        {"mode": "price_bid", "amount": "2000.00", "currency": load.currency.code},
        format="json",
    )
    assert first_resp.status_code == status.HTTP_201_CREATED

    second_resp = client.post(
        f"/api/v1/loads/{load.pk}/offers",
        {"mode": "price_bid", "amount": "2100.00", "currency": load.currency.code},
        format="json",
    )
    assert second_resp.status_code == status.HTTP_409_CONFLICT
    assert second_resp.json()["code"] == "duplicate_offer"


@pytest.mark.django_db
def test_post_load_offers_non_existent_load_404() -> None:
    """Verify non-existent load ID returns 404."""
    carrier = CarrierUserFactory()
    client = _auth_client(carrier)

    resp = client.post(
        "/api/v1/loads/999999/offers",
        {"mode": "price_bid", "amount": "2000.00", "currency": "USD"},
        format="json",
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_get_offers_list_direction_and_status_filters() -> None:
    """Verify ?direction=outgoing|incoming and ?status= filters on deals list."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    load = LoadFactory(shipper=shipper, status=Load.Status.ACTIVE)

    offer1 = OfferFactory(
        load=load,
        carrier=carrier,
        proposer=carrier,
        recipient=shipper,
        status=Offer.Status.PENDING,
    )
    offer2 = OfferFactory(
        load=load,
        carrier=carrier,
        proposer=shipper,
        recipient=carrier,
        status=Offer.Status.ACCEPTED,
    )

    client_carrier = _auth_client(carrier)

    # Carrier outgoing -> offer1
    resp = client_carrier.get("/api/v1/offers?direction=outgoing")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["count"] == 1
    assert resp.json()["results"][0]["id"] == offer1.pk

    # Carrier incoming -> offer2
    resp = client_carrier.get("/api/v1/offers?direction=incoming")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["count"] == 1
    assert resp.json()["results"][0]["id"] == offer2.pk

    # Carrier status=pending -> offer1
    resp = client_carrier.get("/api/v1/offers?status=pending")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["count"] == 1
    assert resp.json()["results"][0]["id"] == offer1.pk

    # Shipper outgoing -> offer2
    client_shipper = _auth_client(shipper)
    resp = client_shipper.get("/api/v1/offers?direction=outgoing")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["count"] == 1
    assert resp.json()["results"][0]["id"] == offer2.pk


@pytest.mark.django_db
def test_get_offers_list_constant_query_count(
    django_assert_num_queries: Any,
) -> None:
    """Verify list endpoint executes constant number of queries regardless of items count."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    c_uz = CountryFactory(code="UZ")
    c_kz = CountryFactory(code="KZ")

    # Seed 1 load with route points and 1 offer
    load1 = LoadFactory(shipper=shipper, status=Load.Status.ACTIVE)
    RoutePointFactory(
        load=load1,
        seq=1,
        kind=RoutePoint.Kind.LOADING,
        country=c_uz,
        address="Tashkent",
    )
    RoutePointFactory(
        load=load1,
        seq=2,
        kind=RoutePoint.Kind.UNLOADING,
        country=c_kz,
        address="Almaty",
    )
    OfferFactory(load=load1, carrier=carrier, proposer=carrier, recipient=shipper)

    client = _auth_client(carrier)

    # Count queries for 1 item
    with django_assert_num_queries(3):
        resp1 = client.get("/api/v1/offers")
    assert resp1.status_code == status.HTTP_200_OK
    assert resp1.json()["count"] == 1

    # Add 5 more loads with route points and offers
    for _ in range(5):
        load_i = LoadFactory(shipper=shipper, status=Load.Status.ACTIVE)
        RoutePointFactory(
            load=load_i,
            seq=1,
            kind=RoutePoint.Kind.LOADING,
            country=c_uz,
            address="Tashkent",
        )
        RoutePointFactory(
            load=load_i,
            seq=2,
            kind=RoutePoint.Kind.UNLOADING,
            country=c_kz,
            address="Almaty",
        )
        OfferFactory(load=load_i, carrier=carrier, proposer=carrier, recipient=shipper)

    # Query count must remain exactly 3 (count + select_related offers + prefetched route_points)
    with django_assert_num_queries(3):
        resp2 = client.get("/api/v1/offers")
    assert resp2.status_code == status.HTTP_200_OK
    assert resp2.json()["count"] == 6


@pytest.mark.django_db
def test_get_offer_detail_party_access_and_404_for_others() -> None:
    """Verify GET /offers/<id> is accessible by parties, but returns 404 for uninvolved users."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    unrelated_user = UserFactory(status=User.Status.VERIFIED)
    load = LoadFactory(shipper=shipper, status=Load.Status.ACTIVE)
    offer = OfferFactory(load=load, carrier=carrier, proposer=carrier, recipient=shipper)

    # Proposer can view
    client_carrier = _auth_client(carrier)
    resp = client_carrier.get(f"/api/v1/offers/{offer.pk}")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["id"] == offer.pk

    # Recipient can view
    client_shipper = _auth_client(shipper)
    resp = client_shipper.get(f"/api/v1/offers/{offer.pk}")
    assert resp.status_code == status.HTTP_200_OK

    # Uninvolved party gets 404 Not Found
    client_unrelated = _auth_client(unrelated_user)
    resp = client_unrelated.get(f"/api/v1/offers/{offer.pk}")
    assert resp.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.django_db
def test_post_offer_accept_success_and_phone_revealed() -> None:
    """Verify accepting an offer reveals phones and creates Order."""
    carrier = CarrierUserFactory(phone="+998901234567")
    shipper = ShipperUserFactory(phone="+998909876543")
    load = LoadFactory(shipper=shipper, status=Load.Status.ACTIVE)
    offer = OfferFactory(
        load=load,
        carrier=carrier,
        proposer=carrier,
        recipient=shipper,
        amount=Decimal("2200.00"),
        status=Offer.Status.PENDING,
    )

    client = _auth_client(shipper)
    resp = client.post(f"/api/v1/offers/{offer.pk}/accept")
    assert resp.status_code == status.HTTP_200_OK

    data = resp.json()
    assert data["status"] == "accepted"
    assert data["responded_at"] is not None

    # Phones are revealed once accepted
    assert data["carrier"]["phone"] == "+998901234567"
    assert data["recipient"]["phone"] == "+998909876543"

    # Order exists in DB
    order = Order.objects.filter(offer_id=offer.pk).first()
    assert order is not None
    assert order.agreed_amount == Decimal("2200.00")


@pytest.mark.django_db
def test_post_offer_accept_non_recipient_rejected() -> None:
    """Verify non-recipient cannot accept offer (403)."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    load = LoadFactory(shipper=shipper, status=Load.Status.ACTIVE)
    offer = OfferFactory(load=load, carrier=carrier, proposer=carrier, recipient=shipper)

    client = _auth_client(carrier)
    resp = client.post(f"/api/v1/offers/{offer.pk}/accept")
    assert resp.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.django_db
def test_post_offer_reject_success() -> None:
    """Verify recipient can reject pending offer."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    load = LoadFactory(shipper=shipper, status=Load.Status.ACTIVE)
    offer = OfferFactory(load=load, carrier=carrier, proposer=carrier, recipient=shipper)

    client = _auth_client(shipper)
    resp = client.post(f"/api/v1/offers/{offer.pk}/reject")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["status"] == "rejected"


@pytest.mark.django_db
def test_post_offer_cancel_success_and_recipient_forbidden() -> None:
    """Verify proposer can cancel offer and recipient cannot."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    load = LoadFactory(shipper=shipper, status=Load.Status.ACTIVE)
    offer = OfferFactory(load=load, carrier=carrier, proposer=carrier, recipient=shipper)

    # Shipper tries to cancel -> 403
    client_shipper = _auth_client(shipper)
    resp = client_shipper.post(f"/api/v1/offers/{offer.pk}/cancel")
    assert resp.status_code == status.HTTP_403_FORBIDDEN

    # Carrier cancels -> 200
    client_carrier = _auth_client(carrier)
    resp = client_carrier.post(f"/api/v1/offers/{offer.pk}/cancel")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["status"] == "cancelled"


@pytest.mark.django_db
def test_post_offer_counter_success() -> None:
    """Verify recipient can counter an offer, returning the new pending offer."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    load = LoadFactory(shipper=shipper, status=Load.Status.ACTIVE)
    offer = OfferFactory(
        load=load,
        carrier=carrier,
        proposer=carrier,
        recipient=shipper,
        amount=Decimal("2000.00"),
    )

    client = _auth_client(shipper)
    resp = client.post(
        f"/api/v1/offers/{offer.pk}/counter",
        {
            "amount": "2300.00",
            "currency": load.currency.code,
            "comment": "Price adjustment for urgency",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    data = resp.json()

    assert data["id"] is not None
    assert data["parent_id"] == offer.pk
    assert data["amount"] == "2300.00"
    assert data["status"] == "pending"
    assert data["proposer"]["id"] == shipper.pk
    assert data["recipient"]["id"] == carrier.pk


@pytest.mark.django_db
def test_load_summary_serialization_with_route_points() -> None:
    """Verify LoadSummarySerializer computes origin/destination from RoutePoints."""
    shipper = ShipperUserFactory()
    c_uz = CountryFactory(code="UZ")
    c_ru = CountryFactory(code="RU")

    load = LoadFactory(
        shipper=shipper,
        status=Load.Status.ACTIVE,
        price_amount=Decimal("4500.00"),
    )
    RoutePointFactory(
        load=load,
        seq=1,
        kind=RoutePoint.Kind.LOADING,
        country=c_uz,
        address="Tashkent Ring Road 10",
    )
    RoutePointFactory(
        load=load,
        seq=2,
        kind=RoutePoint.Kind.UNLOADING,
        country=c_ru,
        address="Moscow Warehouse 4",
    )

    offer = OfferFactory(load=load)
    client = _auth_client(offer.carrier)

    resp = client.get(f"/api/v1/offers/{offer.pk}")
    assert resp.status_code == status.HTTP_200_OK

    load_data = resp.json()["load"]
    assert load_data["id"] == load.pk
    assert load_data["price"] == "4500.00"
    assert load_data["origin"]["address"] == "Tashkent Ring Road 10"
    assert load_data["origin"]["country"] == "UZ"
    assert load_data["destination"]["address"] == "Moscow Warehouse 4"
    assert load_data["destination"]["country"] == "RU"
    assert load_data["origin_address"] == "Tashkent Ring Road 10"
    assert load_data["origin_country"] == "UZ"
    assert load_data["destination_address"] == "Moscow Warehouse 4"
    assert load_data["destination_country"] == "RU"
