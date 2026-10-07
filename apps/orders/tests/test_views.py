"""Integration tests for orders API endpoints."""

from decimal import Decimal
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.accounts.tests.factories import (
    CarrierUserFactory,
    CompanyFactory,
    ShipperUserFactory,
    UserFactory,
)
from apps.loads.models import Load
from apps.loads.tests.factories import LoadFactory, RoutePointFactory
from apps.notifications.models import Notification
from apps.orders.models import Order
from apps.orders.tests.factories import (
    OrderDocumentFactory,
    OrderFactory,
    OrderStatusEventFactory,
    RatingFactory,
)


@pytest.mark.django_db
def test_endpoints_require_authentication() -> None:
    """Verify all order endpoints reject unauthenticated requests with 401."""
    client = APIClient()

    assert client.get("/api/v1/orders").status_code == status.HTTP_401_UNAUTHORIZED
    assert client.get("/api/v1/orders/1").status_code == status.HTTP_401_UNAUTHORIZED
    assert (
        client.post("/api/v1/orders/1/status", data={"status": "received"}).status_code
        == status.HTTP_401_UNAUTHORIZED
    )
    assert (
        client.post("/api/v1/orders/1/documents", data={"name": "CMR"}).status_code
        == status.HTTP_401_UNAUTHORIZED
    )
    assert (
        client.post("/api/v1/orders/1/rating", data={"stars": 5}).status_code
        == status.HTTP_401_UNAUTHORIZED
    )


@pytest.mark.django_db
def test_order_list_scoping_and_pagination() -> None:
    """Verify GET /orders returns only own orders (as carrier or shipper) and is paginated."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    other_carrier = CarrierUserFactory()

    # Create 3 orders where carrier is party, 2 where shipper is party, 2 unrelated
    order_c1 = OrderFactory(carrier=carrier)
    order_c2 = OrderFactory(carrier=carrier)
    order_cs = OrderFactory(carrier=carrier, shipper=shipper)
    order_s1 = OrderFactory(shipper=shipper, carrier=other_carrier)
    OrderFactory.create_batch(2, carrier=other_carrier)

    client = APIClient()
    client.force_authenticate(user=carrier)

    response = client.get("/api/v1/orders")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "count" in data
    assert "next" in data
    assert "previous" in data
    assert "results" in data
    assert data["count"] == 3
    returned_ids = {item["id"] for item in data["results"]}
    assert returned_ids == {order_c1.pk, order_c2.pk, order_cs.pk}

    # Authenticate as shipper
    client.force_authenticate(user=shipper)
    res_shipper = client.get("/api/v1/orders")
    data_shipper = res_shipper.json()
    assert data_shipper["count"] == 2
    assert {item["id"] for item in data_shipper["results"]} == {order_cs.pk, order_s1.pk}


@pytest.mark.django_db
def test_order_list_tab_filters() -> None:
    """Verify ?tab=active and ?tab=history filter orders correctly, and missing tab returns all."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()

    # Active orders
    order_created = OrderFactory(carrier=carrier, shipper=shipper, status=Order.Status.CREATED)
    order_received = OrderFactory(carrier=carrier, shipper=shipper, status=Order.Status.RECEIVED)
    order_picked_up = OrderFactory(carrier=carrier, shipper=shipper, status=Order.Status.PICKED_UP)

    # History orders
    order_completed = OrderFactory(carrier=carrier, shipper=shipper, status=Order.Status.COMPLETED)
    order_cancelled = OrderFactory(carrier=carrier, shipper=shipper, status=Order.Status.CANCELLED)

    client = APIClient()
    client.force_authenticate(user=carrier)

    # 1. tab=active: returns only non-completed and non-cancelled orders
    res_active = client.get("/api/v1/orders?tab=active")
    assert res_active.status_code == status.HTTP_200_OK
    active_ids = {item["id"] for item in res_active.json()["results"]}
    assert active_ids == {order_created.pk, order_received.pk, order_picked_up.pk}

    # 2. tab=history: returns only completed and cancelled orders
    res_history = client.get("/api/v1/orders?tab=history")
    assert res_history.status_code == status.HTTP_200_OK
    history_ids = {item["id"] for item in res_history.json()["results"]}
    assert history_ids == {order_completed.pk, order_cancelled.pk}

    # 3. No tab: returns all 5 orders
    res_all = client.get("/api/v1/orders")
    assert res_all.status_code == status.HTTP_200_OK
    all_ids = {item["id"] for item in res_all.json()["results"]}
    assert all_ids == {
        order_created.pk,
        order_received.pk,
        order_picked_up.pk,
        order_completed.pk,
        order_cancelled.pk,
    }


@pytest.mark.django_db
def test_order_list_constant_queries(django_assert_num_queries: Any) -> None:
    """Verify GET /orders executes a constant number of database queries (no N+1)."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    CompanyFactory(owner=carrier)
    CompanyFactory(owner=shipper)

    # Create 10 orders
    OrderFactory.create_batch(10, carrier=carrier, shipper=shipper)

    client = APIClient()
    client.force_authenticate(user=carrier)

    # 1 count query + 1 select query with joins
    with django_assert_num_queries(2):
        response = client.get("/api/v1/orders")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.json()["results"]) == 10


@pytest.mark.django_db
def test_order_detail_view_parties_and_payload() -> None:
    """Verify GET /orders/<id> includes load summary, route_points, events, docs, contacts."""
    carrier = CarrierUserFactory(full_name="Carrier Man", phone="+998901111111")
    shipper = ShipperUserFactory(full_name="Shipper Pro", phone="+998902222222")
    CompanyFactory(owner=carrier, name="Carrier Express")
    CompanyFactory(owner=shipper, name="Shipper Corp")

    load = LoadFactory(
        shipper=shipper,
        cargo_description="Heavy machinery parts",
        weight_t=Decimal("22.500"),
        distance_km=1200,
    )
    # Add route points to load
    rp1 = RoutePointFactory(load=load, seq=1, address="Tashkent Depot", kind="loading")
    rp2 = RoutePointFactory(load=load, seq=2, address="Samarkand Site", kind="unloading")

    order = OrderFactory(load=load, carrier=carrier, shipper=shipper, status=Order.Status.CREATED)
    event = OrderStatusEventFactory(
        order=order,
        status=Order.Status.CREATED,
        actor=carrier,
        note="Initial creation",
    )
    doc = OrderDocumentFactory(order=order, name="CMR.pdf", size_kb=150, uploaded_by=carrier)
    rating = RatingFactory(
        order=order,
        rater=carrier,
        ratee=shipper,
        stars=5,
        reasons=["punctual"],
    )

    client = APIClient()

    # 1. Non-party receives 404
    intruder = CarrierUserFactory()
    client.force_authenticate(user=intruder)
    res_intruder = client.get(f"/api/v1/orders/{order.pk}")
    assert res_intruder.status_code == status.HTTP_404_NOT_FOUND
    assert res_intruder.json()["code"] == "not_found"

    # 2. Carrier party receives 200 with full details
    client.force_authenticate(user=carrier)
    response = client.get(f"/api/v1/orders/{order.pk}")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    # Verify load summary
    assert data["load"]["id"] == load.pk
    assert data["load"]["cargo_description"] == "Heavy machinery parts"
    assert Decimal(data["load"]["weight_t"]) == Decimal("22.500")
    assert data["load"]["distance_km"] == 1200

    # Verify route points from load
    assert len(data["route_points"]) == 2
    assert data["route_points"][0]["id"] == rp1.pk
    assert data["route_points"][0]["kind"] == "loading"
    assert data["route_points"][1]["id"] == rp2.pk
    assert data["route_points"][1]["kind"] == "unloading"

    # Verify timeline status events
    assert len(data["status_events"]) == 1
    assert data["status_events"][0]["id"] == event.pk
    assert data["status_events"][0]["status"] == "created"
    assert data["status_events"][0]["actor"]["id"] == carrier.pk

    # Verify attached documents
    assert len(data["documents"]) == 1
    assert data["documents"][0]["id"] == doc.pk
    assert data["documents"][0]["name"] == "CMR.pdf"
    assert data["documents"][0]["size_kb"] == 150

    # Verify ratings
    assert len(data["ratings"]) == 1
    assert data["ratings"][0]["id"] == rating.pk
    assert data["ratings"][0]["stars"] == 5

    # Verify carrier & shipper contact details (phones and company visible to parties)
    assert data["carrier"]["id"] == carrier.pk
    assert data["carrier"]["full_name"] == "Carrier Man"
    assert data["carrier"]["phone"] == "+998901111111"
    assert data["carrier"]["company"] == "Carrier Express"

    assert data["shipper"]["id"] == shipper.pk
    assert data["shipper"]["full_name"] == "Shipper Pro"
    assert data["shipper"]["phone"] == "+998902222222"
    assert data["shipper"]["company"] == "Shipper Corp"


@pytest.mark.django_db
def test_order_status_transitions_happy_path() -> None:
    """Full happy path POST /orders/<id>/status transitions."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    load = LoadFactory(
        shipper=shipper,
        status=Load.Status.IN_PROGRESS,
        trucks_needed=1,
        trucks_found=1,
    )
    order = OrderFactory(load=load, carrier=carrier, shipper=shipper, status=Order.Status.CREATED)

    client = APIClient()

    # 1. Carrier transitions created -> received
    client.force_authenticate(user=carrier)
    res_1 = client.post(
        f"/api/v1/orders/{order.pk}/status",
        data={"status": "received", "note": "Received by driver"},
    )
    assert res_1.status_code == status.HTTP_200_OK
    assert res_1.json()["status"] == "received"

    # Notification to shipper
    notif = Notification.objects.filter(user=shipper).first()
    assert notif is not None
    assert notif.type == "order_status"
    assert notif.payload == {"order_id": order.pk, "status": "received"}

    # 2. Carrier transitions received -> picked_up
    res_2 = client.post(
        f"/api/v1/orders/{order.pk}/status",
        data={"status": "picked_up", "note": "Loaded onto trailer"},
    )
    assert res_2.status_code == status.HTTP_200_OK
    assert res_2.json()["status"] == "picked_up"

    # 3. Carrier transitions picked_up -> delivered
    res_3 = client.post(
        f"/api/v1/orders/{order.pk}/status",
        data={"status": "delivered", "note": "Arrived at destination"},
    )
    assert res_3.status_code == status.HTTP_200_OK
    assert res_3.json()["status"] == "delivered"

    # 4. Carrier transitions delivered -> awaiting_confirm
    res_4 = client.post(
        f"/api/v1/orders/{order.pk}/status",
        data={"status": "awaiting_confirm", "note": "Please confirm delivery"},
    )
    assert res_4.status_code == status.HTTP_200_OK
    assert res_4.json()["status"] == "awaiting_confirm"

    # 5. Shipper transitions awaiting_confirm -> completed
    client.force_authenticate(user=shipper)
    res_5 = client.post(
        f"/api/v1/orders/{order.pk}/status",
        data={"status": "completed", "note": "All goods received intact"},
    )
    assert res_5.status_code == status.HTTP_200_OK
    data_completed = res_5.json()
    assert data_completed["status"] == "completed"
    assert data_completed["completed_at"] is not None

    load.refresh_from_db()
    assert load.status == Load.Status.COMPLETED


@pytest.mark.django_db
def test_order_status_unverified_user_403() -> None:
    """Unverified user attempting status transition receives 403 account_not_verified."""
    unverified_carrier = UserFactory(role=User.Role.CARRIER, status=User.Status.NEW)
    shipper = ShipperUserFactory()
    order = OrderFactory(carrier=unverified_carrier, shipper=shipper, status=Order.Status.CREATED)

    client = APIClient()
    client.force_authenticate(user=unverified_carrier)

    response = client.post(
        f"/api/v1/orders/{order.pk}/status",
        data={"status": "received"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json()["code"] == "account_not_verified"


@pytest.mark.django_db
def test_order_status_wrong_role_403_for_each_status() -> None:
    """Wrong role returns 403 for each status."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    order = OrderFactory(carrier=carrier, shipper=shipper, status=Order.Status.CREATED)

    client = APIClient()
    client.force_authenticate(user=shipper)

    # Shipper attempting carrier-only statuses
    for carrier_status in ["received", "picked_up", "delivered", "awaiting_confirm"]:
        res = client.post(
            f"/api/v1/orders/{order.pk}/status",
            data={"status": carrier_status},
        )
        assert res.status_code == status.HTTP_403_FORBIDDEN
        assert res.json()["code"] in ("permission_denied", "role_not_allowed")

    # Carrier attempting shipper-only completed status
    order.status = Order.Status.AWAITING_CONFIRM
    order.save(update_fields=["status"])

    client.force_authenticate(user=carrier)
    res_completed = client.post(
        f"/api/v1/orders/{order.pk}/status",
        data={"status": "completed"},
    )
    assert res_completed.status_code == status.HTTP_403_FORBIDDEN
    assert res_completed.json()["code"] in ("permission_denied", "role_not_allowed")


@pytest.mark.django_db
def test_order_status_invalid_transition_409() -> None:
    """Invalid transitions return 409 invalid_transition."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    order = OrderFactory(carrier=carrier, shipper=shipper, status=Order.Status.CREATED)

    client = APIClient()
    client.force_authenticate(user=carrier)

    # Skipping created -> picked_up
    res = client.post(
        f"/api/v1/orders/{order.pk}/status",
        data={"status": "picked_up"},
    )
    assert res.status_code == status.HTTP_409_CONFLICT
    assert res.json()["code"] == "invalid_transition"

    # Terminal state completed -> anything
    order.status = Order.Status.COMPLETED
    order.save(update_fields=["status"])

    res_terminal = client.post(
        f"/api/v1/orders/{order.pk}/status",
        data={"status": "cancelled", "note": "Too late"},
    )
    assert res_terminal.status_code == status.HTTP_409_CONFLICT
    assert res_terminal.json()["code"] == "invalid_transition"


@pytest.mark.django_db
def test_order_status_cancel_from_picked_up_409() -> None:
    """Cancellation from picked_up returns 409 invalid_transition."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    order = OrderFactory(carrier=carrier, shipper=shipper, status=Order.Status.PICKED_UP)

    client = APIClient()
    client.force_authenticate(user=carrier)

    res = client.post(
        f"/api/v1/orders/{order.pk}/status",
        data={"status": "cancelled", "note": "Breakdown"},
    )
    assert res.status_code == status.HTTP_409_CONFLICT
    assert res.json()["code"] == "invalid_transition"


@pytest.mark.django_db
def test_order_status_cancel_without_reason_400() -> None:
    """Cancellation without reason note returns 400 validation_error."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    order = OrderFactory(carrier=carrier, shipper=shipper, status=Order.Status.CREATED)

    client = APIClient()
    client.force_authenticate(user=carrier)

    res = client.post(
        f"/api/v1/orders/{order.pk}/status",
        data={"status": "cancelled", "note": ""},
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.json()["code"] == "validation_error"


@pytest.mark.django_db
def test_order_status_non_party_404() -> None:
    """Non-party user attempting to update status gets 404."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    intruder = CarrierUserFactory()
    order = OrderFactory(carrier=carrier, shipper=shipper, status=Order.Status.CREATED)

    client = APIClient()
    client.force_authenticate(user=intruder)

    res = client.post(
        f"/api/v1/orders/{order.pk}/status",
        data={"status": "received"},
    )
    assert res.status_code == status.HTTP_404_NOT_FOUND
    assert res.json()["code"] == "not_found"


@pytest.mark.django_db
def test_load_completes_only_after_all_trucks_orders_complete() -> None:
    """Load completes only when count(completed orders) == trucks_needed (trucks_needed=2)."""
    shipper = ShipperUserFactory()
    carrier1 = CarrierUserFactory()
    carrier2 = CarrierUserFactory()

    load = LoadFactory(
        shipper=shipper,
        status=Load.Status.IN_PROGRESS,
        trucks_needed=2,
        trucks_found=2,
    )
    order1 = OrderFactory(
        load=load,
        carrier=carrier1,
        shipper=shipper,
        status=Order.Status.AWAITING_CONFIRM,
    )
    order2 = OrderFactory(
        load=load,
        carrier=carrier2,
        shipper=shipper,
        status=Order.Status.AWAITING_CONFIRM,
    )

    client = APIClient()
    client.force_authenticate(user=shipper)

    # Shipper completes order 1
    res1 = client.post(
        f"/api/v1/orders/{order1.pk}/status",
        data={"status": "completed", "note": "Order 1 complete"},
    )
    assert res1.status_code == status.HTTP_200_OK
    load.refresh_from_db()
    assert load.status == Load.Status.IN_PROGRESS

    # Shipper completes order 2
    res2 = client.post(
        f"/api/v1/orders/{order2.pk}/status",
        data={"status": "completed", "note": "Order 2 complete"},
    )
    assert res2.status_code == status.HTTP_200_OK
    load.refresh_from_db()
    assert load.status == Load.Status.COMPLETED


@pytest.mark.django_db
def test_order_documents_upload_multipart() -> None:
    """Upload documents via multipart request, checking size_kb and permissions."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    intruder = CarrierUserFactory()
    order = OrderFactory(carrier=carrier, shipper=shipper)

    client = APIClient()

    # 1. Non-party receives 404
    client.force_authenticate(user=intruder)
    file_bytes = b"x" * 2048  # 2 KB
    upload_file = SimpleUploadedFile("bill_of_lading.pdf", file_bytes, "application/pdf")
    res_intruder = client.post(
        f"/api/v1/orders/{order.pk}/documents",
        data={"name": "Bill of Lading", "file": upload_file},
        format="multipart",
    )
    assert res_intruder.status_code == status.HTTP_404_NOT_FOUND

    # 2. Carrier party uploads document successfully
    client.force_authenticate(user=carrier)
    upload_file2 = SimpleUploadedFile("cmr_doc.pdf", file_bytes, "application/pdf")
    response = client.post(
        f"/api/v1/orders/{order.pk}/documents",
        data={"name": "Signed CMR", "file": upload_file2},
        format="multipart",
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["name"] == "Signed CMR"
    assert data["size_kb"] == 2
    assert data["uploaded_by"]["id"] == carrier.pk


@pytest.mark.django_db
def test_order_rating_view_and_company_recompute() -> None:
    """Submit rating for completed order, test duplicate rating 409 and company rating math."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    intruder = CarrierUserFactory()
    carrier_company = CompanyFactory(owner=carrier, name="Carrier Ltd")
    shipper_company = CompanyFactory(owner=shipper, name="Shipper Ltd")

    order = OrderFactory(carrier=carrier, shipper=shipper, status=Order.Status.CREATED)

    client = APIClient()
    client.force_authenticate(user=carrier)

    # 1. Cannot rate non-completed order (409)
    res_early = client.post(
        f"/api/v1/orders/{order.pk}/rating",
        data={"stars": 5, "comment": "Too early"},
    )
    assert res_early.status_code == status.HTTP_409_CONFLICT
    assert res_early.json()["code"] == "invalid_status"

    # Mark completed
    order.status = Order.Status.COMPLETED
    order.save(update_fields=["status"])

    # 2. Non-party receives 404
    client.force_authenticate(user=intruder)
    res_intruder = client.post(
        f"/api/v1/orders/{order.pk}/rating",
        data={"stars": 5},
    )
    assert res_intruder.status_code == status.HTTP_404_NOT_FOUND

    # 3. Invalid stars returns 400
    client.force_authenticate(user=carrier)
    res_invalid_stars = client.post(
        f"/api/v1/orders/{order.pk}/rating",
        data={"stars": 0},
    )
    assert res_invalid_stars.status_code == status.HTTP_400_BAD_REQUEST

    # 4. Carrier rates shipper with 5 stars
    res_c = client.post(
        f"/api/v1/orders/{order.pk}/rating",
        data={
            "stars": 5,
            "reasons": ["fast_loading", "polite"],
            "comment": "Quick turnaround",
        },
    )
    assert res_c.status_code == status.HTTP_201_CREATED
    assert res_c.json()["stars"] == 5
    shipper_company.refresh_from_db()
    assert shipper_company.rating_avg == Decimal("5.00")
    assert shipper_company.rating_count == 1

    # 5. Duplicate rating returns 409
    res_dup = client.post(
        f"/api/v1/orders/{order.pk}/rating",
        data={"stars": 4},
    )
    assert res_dup.status_code == status.HTTP_409_CONFLICT
    assert res_dup.json()["code"] == "already_rated"

    # 6. Shipper rates carrier with 4 stars
    client.force_authenticate(user=shipper)
    res_s = client.post(
        f"/api/v1/orders/{order.pk}/rating",
        data={"stars": 4, "reasons": ["careful"], "comment": "Good driver"},
    )
    assert res_s.status_code == status.HTTP_201_CREATED
    carrier_company.refresh_from_db()
    assert carrier_company.rating_avg == Decimal("4.00")
    assert carrier_company.rating_count == 1

    # 7. Additional rating for shipper on another completed order to verify avg 4.50
    order2 = OrderFactory(
        carrier=CarrierUserFactory(),
        shipper=shipper,
        status=Order.Status.COMPLETED,
    )
    client.force_authenticate(user=order2.carrier)
    res_second = client.post(
        f"/api/v1/orders/{order2.pk}/rating",
        data={"stars": 4, "reasons": ["punctual"]},
    )
    assert res_second.status_code == status.HTTP_201_CREATED
    shipper_company.refresh_from_db()
    # (5 + 4) / 2 = 4.50
    assert shipper_company.rating_avg == Decimal("4.50")
    assert shipper_company.rating_count == 2
