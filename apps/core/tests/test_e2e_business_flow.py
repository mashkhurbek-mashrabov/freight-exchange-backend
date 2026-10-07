"""Full business-flow end-to-end tests exercising the HTTP REST API with JWT authentication.

Covers:
1. Complete happy path:
   - Shipper and carrier OTP authentication + profile/company setup
   - Verification via admin mark_verified service
   - Carrier registers tractor + trailer (paired)
   - Shipper posts draft load with 3 route points + publishes
   - Carrier finds load via ?suitable=true and filters
   - Carrier submits price_bid offer
   - Shipper counters with new price
   - Recipient rules checked: proposer cannot accept own counter
   - Carrier accepts counter -> Order created with agreed counter amount, load in_progress
   - Carrier status transitions: received -> picked_up -> delivered -> awaiting_confirm
   - Shipper completes order -> load marked completed
   - Both parties rate order -> company rating_avg & rating_count updated
   - Notifications visible via GET /notifications with unread_count and read-all
2. Competing offers on multi-truck load:
   - 2-truck load with 3 competing carriers
   - Accepting 2 offers auto-rejects the 3rd pending offer and notifies
3. Cancellation path:
   - Order cancelled by carrier -> trucks_found decremented, load returns to active
4. Unverified gate:
   - Unverified user blocked with 403 account_not_verified on create load/offer/order status
"""

from decimal import Decimal

import pytest
from django.core.management import call_command
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Company, User
from apps.accounts.services import mark_verified
from apps.garage.models import VehicleType
from apps.loads.models import Load
from apps.offers.models import Offer
from apps.orders.models import Order


@pytest.fixture(autouse=True)
def load_reference_fixtures(db: None) -> None:
    """Load reference data for countries, currencies, and vehicle types."""
    call_command("loaddata", "countries", "currencies", "exchange_rates", "vehicle_types")


def _auth_user_via_otp(
    phone: str,
    *,
    role: str = "carrier",
    full_name: str = "Test User",
    company_name: str = "",
    company_tin: str = "",
    verified: bool = True,
) -> tuple[APIClient, User]:
    """Helper to register and authenticate a user via the OTP HTTP flow."""
    client = APIClient()

    # 1. Request OTP
    req_resp = client.post("/api/v1/auth/otp/request", {"phone": phone})
    assert req_resp.status_code == status.HTTP_204_NO_CONTENT

    # 2. Verify OTP with dev code
    verify_resp = client.post("/api/v1/auth/otp/verify", {"phone": phone, "code": "000000"})
    assert verify_resp.status_code == status.HTTP_200_OK
    token = verify_resp.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    # 3. Update profile role and full_name
    patch_resp = client.patch(
        "/api/v1/me",
        {"role": role, "full_name": full_name, "language": "ru"},
    )
    assert patch_resp.status_code == status.HTTP_200_OK

    # 4. Upsert company if provided
    if company_name and company_tin:
        comp_resp = client.put(
            "/api/v1/me/company",
            {"name": company_name, "tin": company_tin, "address": "Test City"},
        )
        assert comp_resp.status_code == status.HTTP_200_OK

    user = User.objects.get(phone=phone)

    # 5. Admin verification gate
    if verified:
        mark_verified(User.objects.filter(pk=user.pk))
        user.refresh_from_db()

    return client, user


@pytest.mark.django_db
@override_settings(OTP_DEV_CODE="000000")
def test_full_business_flow_e2e_happy_path() -> None:
    """Exercise complete freight marketplace flow from OTP auth to order rating."""
    # 1. Authenticate verified Shipper and Carrier
    shipper_client, shipper_user = _auth_user_via_otp(
        phone="+998901000001",
        role="shipper",
        full_name="Shipper Express",
        company_name="Logistics Direct",
        company_tin="123456789",
        verified=True,
    )
    carrier_client, carrier_user = _auth_user_via_otp(
        phone="+998902000002",
        role="carrier",
        full_name="Carrier Transport",
        company_name="Fast Freight LLC",
        company_tin="987654321",
        verified=True,
    )

    assert shipper_user.status == User.Status.VERIFIED
    assert carrier_user.status == User.Status.VERIFIED

    # 2. Carrier registers vehicles: tractor + trailer (paired)
    tractor_type = VehicleType.objects.filter(kind=VehicleType.Kind.TRACTOR).first()
    trailer_type = VehicleType.objects.filter(kind=VehicleType.Kind.TRAILER).first()
    assert tractor_type is not None
    assert trailer_type is not None

    tractor_resp = carrier_client.post(
        "/api/v1/vehicles",
        {
            "kind": "tractor",
            "plate_number": "01A777AA",
            "vehicle_type_id": tractor_type.id,
            "brand": "Volvo FH",
            "owner_full_name": "Carrier Transport",
            "tech_passport_no": "TP-TR-001",
        },
    )
    assert tractor_resp.status_code == status.HTTP_201_CREATED
    tractor_id = tractor_resp.data["id"]

    trailer_resp = carrier_client.post(
        "/api/v1/vehicles",
        {
            "kind": "trailer",
            "plate_number": "01B888BB",
            "vehicle_type_id": trailer_type.id,
            "brand": "Krone Profiliner",
            "owner_full_name": "Carrier Transport",
            "tech_passport_no": "TP-TL-002",
            "paired_vehicle_id": tractor_id,
        },
    )
    assert trailer_resp.status_code == status.HTTP_201_CREATED
    trailer_id = trailer_resp.data["id"]

    # 3. Shipper creates draft load with 3 route points and payment terms
    create_load_payload = {
        "cargo_description": "Agricultural equipment and spare parts",
        "cargo_type": "machinery",
        "weight_t": "18.500",
        "volume_m3": "86.000",
        "length_m": "13.60",
        "packaging": "wooden crates",
        "transport_mode": "FTL",
        "body_types": [trailer_type.id],
        "trucks_needed": 1,
        "price_amount": "3000.00",
        "currency": "USD",
        "price_negotiable": True,
        "route_points": [
            {
                "seq": 1,
                "kind": "loading",
                "country": "UZ",
                "address": "Tashkent Logistics Hub",
                "lat": "41.299496",
                "lng": "69.240073",
                "asap": True,
                "ready_to_load": True,
                "comment": "Warehouse bay 3",
            },
            {
                "seq": 2,
                "kind": "customs",
                "country": "KZ",
                "address": "Zhibek Zholy customs terminal",
                "lat": "43.344990",
                "lng": "68.257320",
                "comment": "Customs clearance declaration",
            },
            {
                "seq": 3,
                "kind": "unloading",
                "country": "RU",
                "address": "Moscow distribution centre",
                "lat": "55.755826",
                "lng": "37.617300",
                "comment": "Dock 12 receiver",
            },
        ],
        "payment_terms": {
            "prepay_amount": "1000.00",
            "prepay_method": "transfer",
            "paid_amount": "2000.00",
            "paid_method": "transfer",
            "payment_due_days": 5,
            "conditions": "Net 5 days upon completed delivery receipt",
        },
    }

    create_load_resp = shipper_client.post("/api/v1/loads", create_load_payload, format="json")
    assert create_load_resp.status_code == status.HTTP_201_CREATED
    load_id = create_load_resp.data["id"]
    assert create_load_resp.data["status"] == Load.Status.DRAFT

    # 4. Shipper publishes the load
    pub_resp = shipper_client.post(f"/api/v1/loads/{load_id}/publish")
    assert pub_resp.status_code == status.HTTP_200_OK
    assert pub_resp.data["status"] == Load.Status.ACTIVE

    # 5. Carrier lists loads with ?suitable=true and filters
    list_resp = carrier_client.get(
        "/api/v1/loads?suitable=true&origin_country=UZ&destination_country=RU&transport_mode=FTL"
    )
    assert list_resp.status_code == status.HTTP_200_OK
    matched_ids = [item["id"] for item in list_resp.data["results"]]
    assert load_id in matched_ids

    # 6. Carrier creates price_bid offer
    offer_payload = {
        "mode": "price_bid",
        "amount": "2800.00",
        "currency": "USD",
        "vehicle_id": tractor_id,
        "trailer_id": trailer_id,
        "comment": "Ready to load tomorrow 8am",
    }
    offer_resp = carrier_client.post(
        f"/api/v1/loads/{load_id}/offers", offer_payload, format="json"
    )
    assert offer_resp.status_code == status.HTTP_201_CREATED
    offer_id = offer_resp.data["id"]
    assert offer_resp.data["status"] == Offer.Status.PENDING
    assert offer_resp.data["amount"] == "2800.00"

    # 7. Shipper counters the offer
    counter_payload = {
        "amount": "2900.00",
        "currency": "USD",
        "comment": "Counter offer: 2900 USD",
    }
    counter_resp = shipper_client.post(
        f"/api/v1/offers/{offer_id}/counter", counter_payload, format="json"
    )
    assert counter_resp.status_code == status.HTTP_201_CREATED
    counter_id = counter_resp.data["id"]
    assert counter_resp.data["status"] == Offer.Status.PENDING
    assert counter_resp.data["amount"] == "2900.00"

    # Old offer must now be marked countered
    old_offer = Offer.objects.get(pk=offer_id)
    assert old_offer.status == Offer.Status.COUNTERED

    # 8. Recipient rules check: Shipper (proposer of counter) cannot accept own counter
    shipper_accept_attempt = shipper_client.post(f"/api/v1/offers/{counter_id}/accept")
    assert shipper_accept_attempt.status_code in (
        status.HTTP_403_FORBIDDEN,
        status.HTTP_409_CONFLICT,
    )

    # Carrier (recipient of counter) accepts the counter offer
    carrier_accept_resp = carrier_client.post(f"/api/v1/offers/{counter_id}/accept")
    assert carrier_accept_resp.status_code == status.HTTP_200_OK
    assert carrier_accept_resp.data["status"] == Offer.Status.ACCEPTED

    # 9. Verify Order created with agreed counter amount and Load in_progress
    order = Order.objects.get(offer_id=counter_id)
    assert order.agreed_amount == Decimal("2900.00")
    assert order.status == Order.Status.CREATED

    load = Load.objects.get(pk=load_id)
    assert load.status == Load.Status.IN_PROGRESS
    assert load.trucks_found == 1

    # 10. Carrier advances order status: received -> picked_up -> delivered -> awaiting_confirm
    s1 = carrier_client.post(
        f"/api/v1/orders/{order.id}/status",
        {"status": "received", "note": "Arrived at origin depot"},
    )
    assert s1.status_code == status.HTTP_200_OK
    assert s1.data["status"] == Order.Status.RECEIVED

    s2 = carrier_client.post(
        f"/api/v1/orders/{order.id}/status",
        {"status": "picked_up", "note": "Cargo loaded and secured"},
    )
    assert s2.status_code == status.HTTP_200_OK
    assert s2.data["status"] == Order.Status.PICKED_UP

    s3 = carrier_client.post(
        f"/api/v1/orders/{order.id}/status",
        {"status": "delivered", "note": "Arrived at destination dock"},
    )
    assert s3.status_code == status.HTTP_200_OK
    assert s3.data["status"] == Order.Status.DELIVERED

    s4 = carrier_client.post(
        f"/api/v1/orders/{order.id}/status",
        {"status": "awaiting_confirm", "note": "Unloading done, awaiting confirmation"},
    )
    assert s4.status_code == status.HTTP_200_OK
    assert s4.data["status"] == Order.Status.AWAITING_CONFIRM

    # Carrier cannot complete (shipper only)
    carrier_complete_attempt = carrier_client.post(
        f"/api/v1/orders/{order.id}/status",
        {"status": "completed", "note": "Carrier trying to complete"},
    )
    assert carrier_complete_attempt.status_code in (
        status.HTTP_403_FORBIDDEN,
        status.HTTP_409_CONFLICT,
    )

    # 11. Shipper completes the order
    s5 = shipper_client.post(
        f"/api/v1/orders/{order.id}/status",
        {"status": "completed", "note": "Received cargo in perfect condition"},
    )
    assert s5.status_code == status.HTTP_200_OK
    assert s5.data["status"] == Order.Status.COMPLETED

    order.refresh_from_db()
    assert order.status == Order.Status.COMPLETED

    # Load must now be completed since trucks_found == trucks_needed == 1
    load.refresh_from_db()
    assert load.status == Load.Status.COMPLETED

    # 12. Both parties submit ratings
    carrier_rate_resp = carrier_client.post(
        f"/api/v1/orders/{order.id}/rating",
        {
            "stars": 5,
            "reasons": ["punctual", "fast_payment"],
            "comment": "Excellent shipper, prompt payment confirmation.",
        },
    )
    assert carrier_rate_resp.status_code == status.HTTP_201_CREATED

    shipper_rate_resp = shipper_client.post(
        f"/api/v1/orders/{order.id}/rating",
        {
            "stars": 4,
            "reasons": ["on_time"],
            "comment": "Reliable carrier, delivered safely.",
        },
    )
    assert shipper_rate_resp.status_code == status.HTTP_201_CREATED

    # 13. Verify company rating_avg and rating_count for both parties
    shipper_comp = Company.objects.get(owner=shipper_user)
    assert shipper_comp.rating_count == 1
    assert shipper_comp.rating_avg == Decimal("5.00")

    carrier_comp = Company.objects.get(owner=carrier_user)
    assert carrier_comp.rating_count == 1
    assert carrier_comp.rating_avg == Decimal("4.00")

    # 14. Verify notifications for both parties with unread_count and read-all
    carrier_notif_resp = carrier_client.get("/api/v1/notifications")
    assert carrier_notif_resp.status_code == status.HTTP_200_OK
    assert carrier_notif_resp.data["count"] > 0
    assert carrier_notif_resp.data["unread_count"] > 0

    carrier_readall_resp = carrier_client.post("/api/v1/notifications/read-all")
    assert carrier_readall_resp.status_code == status.HTTP_200_OK
    assert carrier_readall_resp.data["updated"] > 0

    carrier_notif_after = carrier_client.get("/api/v1/notifications")
    assert carrier_notif_after.data["unread_count"] == 0

    shipper_notif_resp = shipper_client.get("/api/v1/notifications")
    assert shipper_notif_resp.status_code == status.HTTP_200_OK
    assert shipper_notif_resp.data["count"] > 0
    assert shipper_notif_resp.data["unread_count"] > 0

    shipper_readall_resp = shipper_client.post("/api/v1/notifications/read-all")
    assert shipper_readall_resp.status_code == status.HTTP_200_OK
    assert shipper_readall_resp.data["updated"] > 0

    shipper_notif_after = shipper_client.get("/api/v1/notifications")
    assert shipper_notif_after.data["unread_count"] == 0


@pytest.mark.django_db
@override_settings(OTP_DEV_CODE="000000")
def test_two_truck_load_three_competing_carriers_auto_reject() -> None:
    """A 2-truck load with 3 competing carriers: accepting 2 auto-rejects the 3rd pending offer."""
    shipper_client, shipper_user = _auth_user_via_otp(
        phone="+998903000001",
        role="shipper",
        full_name="Shipper Multi",
        company_name="Multi-Truck Corp",
        company_tin="300000001",
        verified=True,
    )
    c1_client, _ = _auth_user_via_otp(
        phone="+998903000002",
        role="carrier",
        full_name="Carrier Alpha",
        company_name="Alpha Trans",
        company_tin="300000002",
        verified=True,
    )
    c2_client, _ = _auth_user_via_otp(
        phone="+998903000003",
        role="carrier",
        full_name="Carrier Beta",
        company_name="Beta Trans",
        company_tin="300000003",
        verified=True,
    )
    c3_client, c3_user = _auth_user_via_otp(
        phone="+998903000004",
        role="carrier",
        full_name="Carrier Gamma",
        company_name="Gamma Trans",
        company_tin="300000004",
        verified=True,
    )

    # Shipper creates 2-truck load
    load_payload = {
        "cargo_description": "Bulk construction materials",
        "cargo_type": "building_materials",
        "weight_t": "40.000",
        "transport_mode": "FTL",
        "trucks_needed": 2,
        "price_amount": "5000.00",
        "currency": "USD",
        "route_points": [
            {
                "seq": 1,
                "kind": "loading",
                "country": "UZ",
                "address": "Navoi quarry",
                "lat": "40.084444",
                "lng": "65.379167",
            },
            {
                "seq": 2,
                "kind": "unloading",
                "country": "UZ",
                "address": "Tashkent construction site",
                "lat": "41.299496",
                "lng": "69.240073",
            },
        ],
    }
    create_resp = shipper_client.post("/api/v1/loads", load_payload, format="json")
    assert create_resp.status_code == status.HTTP_201_CREATED
    load_id = create_resp.data["id"]

    pub_resp = shipper_client.post(f"/api/v1/loads/{load_id}/publish")
    assert pub_resp.status_code == status.HTTP_200_OK

    # 3 competing carriers submit price bids
    o1_resp = c1_client.post(
        f"/api/v1/loads/{load_id}/offers",
        {"mode": "price_bid", "amount": "4900.00", "currency": "USD"},
    )
    assert o1_resp.status_code == status.HTTP_201_CREATED
    offer_1_id = o1_resp.data["id"]

    o2_resp = c2_client.post(
        f"/api/v1/loads/{load_id}/offers",
        {"mode": "price_bid", "amount": "4800.00", "currency": "USD"},
    )
    assert o2_resp.status_code == status.HTTP_201_CREATED
    offer_2_id = o2_resp.data["id"]

    o3_resp = c3_client.post(
        f"/api/v1/loads/{load_id}/offers",
        {"mode": "price_bid", "amount": "4700.00", "currency": "USD"},
    )
    assert o3_resp.status_code == status.HTTP_201_CREATED
    offer_3_id = o3_resp.data["id"]

    # Shipper accepts offer 1 -> trucks_found becomes 1 (load still active, offer 2 & 3 pending)
    acc1 = shipper_client.post(f"/api/v1/offers/{offer_1_id}/accept")
    assert acc1.status_code == status.HTTP_200_OK
    load = Load.objects.get(pk=load_id)
    assert load.trucks_found == 1
    assert load.status == Load.Status.ACTIVE
    assert Offer.objects.get(pk=offer_2_id).status == Offer.Status.PENDING
    assert Offer.objects.get(pk=offer_3_id).status == Offer.Status.PENDING

    # Shipper accepts offer 2 -> trucks_found reaches 2 (trucks_needed),
    # load in_progress, offer 3 auto-rejected
    acc2 = shipper_client.post(f"/api/v1/offers/{offer_2_id}/accept")
    assert acc2.status_code == status.HTTP_200_OK

    load.refresh_from_db()
    assert load.trucks_found == 2
    assert load.status == Load.Status.IN_PROGRESS

    # 3rd offer must be auto-rejected
    offer_3 = Offer.objects.get(pk=offer_3_id)
    assert offer_3.status == Offer.Status.REJECTED

    # Carrier 3 receives notification about offer rejection
    c3_notif_resp = c3_client.get("/api/v1/notifications")
    assert c3_notif_resp.status_code == status.HTTP_200_OK
    rejected_types = [n["type"] for n in c3_notif_resp.data["results"]]
    assert "offer_rejected" in rejected_types


@pytest.mark.django_db
@override_settings(OTP_DEV_CODE="000000")
def test_order_cancellation_decrements_trucks_and_restores_load_active() -> None:
    """Cancelling an order decrements trucks_found and restores in_progress load back to active."""
    shipper_client, _ = _auth_user_via_otp(
        phone="+998904000001",
        role="shipper",
        full_name="Shipper Cancel",
        company_name="Cancel Test Corp",
        company_tin="400000001",
        verified=True,
    )
    carrier_client, _ = _auth_user_via_otp(
        phone="+998904000002",
        role="carrier",
        full_name="Carrier Cancel",
        company_name="Cancel Carrier LLC",
        company_tin="400000002",
        verified=True,
    )

    # Create & publish load (1 truck needed)
    load_resp = shipper_client.post(
        "/api/v1/loads",
        {
            "cargo_description": "Beverages",
            "weight_t": "10.000",
            "trucks_needed": 1,
            "price_amount": "1200.00",
            "currency": "USD",
            "route_points": [
                {
                    "seq": 1,
                    "kind": "loading",
                    "country": "UZ",
                    "address": "Tashkent",
                    "lat": "41.299496",
                    "lng": "69.240073",
                },
                {
                    "seq": 2,
                    "kind": "unloading",
                    "country": "UZ",
                    "address": "Samarkand",
                    "lat": "39.654167",
                    "lng": "66.959722",
                },
            ],
        },
        format="json",
    )
    load_id = load_resp.data["id"]
    shipper_client.post(f"/api/v1/loads/{load_id}/publish")

    # Carrier offers, shipper accepts
    offer_resp = carrier_client.post(
        f"/api/v1/loads/{load_id}/offers",
        {"mode": "price_bid", "amount": "1200.00", "currency": "USD"},
    )
    offer_id = offer_resp.data["id"]
    shipper_client.post(f"/api/v1/offers/{offer_id}/accept")

    load = Load.objects.get(pk=load_id)
    assert load.trucks_found == 1
    assert load.status == Load.Status.IN_PROGRESS

    order = Order.objects.get(offer_id=offer_id)

    # Carrier cancels order from created status
    cancel_resp = carrier_client.post(
        f"/api/v1/orders/{order.id}/status",
        {
            "status": "cancelled",
            "note": "Vehicle engine failure before departure",
        },
    )
    assert cancel_resp.status_code == status.HTTP_200_OK
    assert cancel_resp.data["status"] == Order.Status.CANCELLED
    assert cancel_resp.data["cancel_reason"] == "Vehicle engine failure before departure"

    # Load trucks_found decremented to 0 and status restored to active
    load.refresh_from_db()
    assert load.trucks_found == 0
    assert load.status == Load.Status.ACTIVE


@pytest.mark.django_db
@override_settings(OTP_DEV_CODE="000000")
def test_unverified_user_blocked_with_account_not_verified() -> None:
    """Unverified users receive 403 account_not_verified on create load, create offer,
    order status.
    """
    # Authenticate unverified user
    unverified_client, unverified_user = _auth_user_via_otp(
        phone="+998905000001",
        role="both",
        full_name="Unverified User",
        verified=False,
    )
    assert unverified_user.status == User.Status.NEW

    # 1. Blocked on create load
    create_load_resp = unverified_client.post(
        "/api/v1/loads",
        {
            "cargo_description": "Test Cargo",
            "weight_t": "5.000",
            "trucks_needed": 1,
            "route_points": [
                {
                    "seq": 1,
                    "kind": "loading",
                    "country": "UZ",
                    "lat": "41.0",
                    "lng": "69.0",
                },
                {
                    "seq": 2,
                    "kind": "unloading",
                    "country": "UZ",
                    "lat": "42.0",
                    "lng": "70.0",
                },
            ],
        },
        format="json",
    )
    assert create_load_resp.status_code == status.HTTP_403_FORBIDDEN
    assert create_load_resp.data["code"] == "account_not_verified"

    # Create active load and order using verified users to test offer and order status gates
    verified_shipper, _ = _auth_user_via_otp(
        phone="+998905000002",
        role="shipper",
        verified=True,
    )
    verified_carrier, _ = _auth_user_via_otp(
        phone="+998905000003",
        role="carrier",
        verified=True,
    )

    load_resp = verified_shipper.post(
        "/api/v1/loads",
        {
            "cargo_description": "Verified Cargo",
            "weight_t": "5.000",
            "trucks_needed": 1,
            "price_amount": "500.00",
            "currency": "USD",
            "route_points": [
                {
                    "seq": 1,
                    "kind": "loading",
                    "country": "UZ",
                    "lat": "41.0",
                    "lng": "69.0",
                },
                {
                    "seq": 2,
                    "kind": "unloading",
                    "country": "UZ",
                    "lat": "42.0",
                    "lng": "70.0",
                },
            ],
        },
        format="json",
    )
    load_id = load_resp.data["id"]
    verified_shipper.post(f"/api/v1/loads/{load_id}/publish")

    # 2. Blocked on create offer
    offer_resp = unverified_client.post(
        f"/api/v1/loads/{load_id}/offers",
        {"mode": "price_bid", "amount": "450.00", "currency": "USD"},
    )
    assert offer_resp.status_code == status.HTTP_403_FORBIDDEN
    assert offer_resp.data["code"] == "account_not_verified"

    # Create order via verified carrier
    carrier_offer_resp = verified_carrier.post(
        f"/api/v1/loads/{load_id}/offers",
        {"mode": "price_bid", "amount": "500.00", "currency": "USD"},
    )
    carrier_offer_id = carrier_offer_resp.data["id"]
    verified_shipper.post(f"/api/v1/offers/{carrier_offer_id}/accept")
    order = Order.objects.get(offer_id=carrier_offer_id)

    # 3. Blocked on order status change
    order_status_resp = unverified_client.post(
        f"/api/v1/orders/{order.id}/status",
        {"status": "received", "note": "Unverified attempting status change"},
    )
    assert order_status_resp.status_code == status.HTTP_403_FORBIDDEN
    assert order_status_resp.data["code"] == "account_not_verified"
