"""Unit tests for orders services."""

from decimal import Decimal
from typing import Any

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.accounts.models import User
from apps.accounts.tests.factories import (
    CarrierUserFactory,
    CompanyFactory,
    ShipperUserFactory,
    UserFactory,
)
from apps.core.exceptions import ServiceError
from apps.loads.models import Load
from apps.loads.tests.factories import LoadFactory
from apps.notifications.models import Notification
from apps.orders.models import Order, Rating
from apps.orders.services import add_document, change_status, rate_order
from apps.orders.tests.factories import OrderFactory


@pytest.mark.django_db
def test_full_happy_path_transitions_and_ratings() -> None:
    """Full happy path transition sequence and ratings with company average update."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    carrier_company = CompanyFactory(owner=carrier, name="Carrier Trans")
    shipper_company = CompanyFactory(owner=shipper, name="Shipper Logistics")

    load = LoadFactory(
        shipper=shipper,
        status=Load.Status.IN_PROGRESS,
        trucks_needed=1,
        trucks_found=1,
    )
    order = OrderFactory(
        load=load,
        shipper=shipper,
        carrier=carrier,
        status=Order.Status.CREATED,
    )

    # 1. Carrier transitions created -> received
    order = change_status(carrier, order.pk, Order.Status.RECEIVED, note="Carrier received load")
    assert order.status == Order.Status.RECEIVED
    event_1 = order.status_events.last()
    assert event_1.status == Order.Status.RECEIVED
    assert event_1.actor == carrier
    assert event_1.note == "Carrier received load"
    notif_1 = Notification.objects.filter(user=shipper).first()
    assert notif_1 is not None
    assert notif_1.type == Notification.NotificationType.ORDER_STATUS
    assert notif_1.payload == {"order_id": order.pk, "status": Order.Status.RECEIVED}

    # 2. Carrier transitions received -> picked_up
    order = change_status(carrier, order.pk, Order.Status.PICKED_UP, note="Cargo loaded")
    assert order.status == Order.Status.PICKED_UP
    assert order.status_events.filter(status=Order.Status.PICKED_UP).exists()

    # 3. Carrier transitions picked_up -> delivered
    order = change_status(
        carrier,
        order.pk,
        Order.Status.DELIVERED,
        note="Delivered to destination",
    )
    assert order.status == Order.Status.DELIVERED
    assert order.status_events.filter(status=Order.Status.DELIVERED).exists()

    # 4. Carrier transitions delivered -> awaiting_confirm
    order = change_status(
        carrier,
        order.pk,
        Order.Status.AWAITING_CONFIRM,
        note="Awaiting shipper confirm",
    )
    assert order.status == Order.Status.AWAITING_CONFIRM
    assert order.status_events.filter(status=Order.Status.AWAITING_CONFIRM).exists()

    # 5. Shipper transitions awaiting_confirm -> completed
    order = change_status(shipper, order.pk, Order.Status.COMPLETED, note="Confirmed and accepted")
    assert order.status == Order.Status.COMPLETED
    assert order.completed_at is not None
    assert order.status_events.filter(status=Order.Status.COMPLETED).exists()
    load.refresh_from_db()
    assert load.status == Load.Status.COMPLETED

    # 6. Both parties rate the order
    # Carrier rates shipper with 5 stars
    rating_c = rate_order(
        carrier,
        order.pk,
        stars=5,
        reasons=["fast_unloading", "polite"],
        comment="Pleasure doing business",
    )
    assert rating_c.stars == 5
    assert rating_c.rater == carrier
    assert rating_c.ratee == shipper
    shipper_company.refresh_from_db()
    assert shipper_company.rating_avg == Decimal("5.00")
    assert shipper_company.rating_count == 1

    # Shipper rates carrier with 4 stars
    rating_s = rate_order(
        shipper,
        order.pk,
        stars=4,
        reasons=["punctual"],
        comment="Good delivery overall",
    )
    assert rating_s.stars == 4
    assert rating_s.rater == shipper
    assert rating_s.ratee == carrier
    carrier_company.refresh_from_db()
    assert carrier_company.rating_avg == Decimal("4.00")
    assert carrier_company.rating_count == 1

    # Add a second rating for shipper from another order to test averaging: e.g. 5 and 4 -> 4.50
    order2 = OrderFactory(
        load=load,
        shipper=shipper,
        carrier=CarrierUserFactory(),
        status=Order.Status.COMPLETED,
    )
    rate_order(order2.carrier, order2.pk, stars=4, reasons=["on_time"], comment="All fine")
    shipper_company.refresh_from_db()
    assert shipper_company.rating_avg == Decimal("4.50")
    assert shipper_company.rating_count == 2


@pytest.mark.django_db
def test_wrong_role_403_for_each_status() -> None:
    """Wrong role returns 403 for each status in the matrix."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    order = OrderFactory(carrier=carrier, shipper=shipper, status=Order.Status.CREATED)

    # Shipper attempts carrier-only statuses
    for carrier_status in [
        Order.Status.RECEIVED,
        Order.Status.PICKED_UP,
        Order.Status.DELIVERED,
        Order.Status.AWAITING_CONFIRM,
    ]:
        with pytest.raises(ServiceError) as exc_info:
            change_status(shipper, order.pk, carrier_status)
        assert exc_info.value.status_code == 403
        assert exc_info.value.code in ("permission_denied", "role_not_allowed")

    # Carrier attempts shipper-only completed status
    order.status = Order.Status.AWAITING_CONFIRM
    order.save(update_fields=["status"])
    with pytest.raises(ServiceError) as exc_info:
        change_status(carrier, order.pk, Order.Status.COMPLETED)
    assert exc_info.value.status_code == 403
    assert exc_info.value.code in ("permission_denied", "role_not_allowed")


@pytest.mark.django_db
def test_every_invalid_transition_409() -> None:
    """Every invalid state transition returns 409 invalid_transition."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    order = OrderFactory(carrier=carrier, shipper=shipper, status=Order.Status.CREATED)

    # From created: carrier skipping to picked_up, delivered, awaiting_confirm
    for invalid_target in [
        Order.Status.PICKED_UP,
        Order.Status.DELIVERED,
        Order.Status.AWAITING_CONFIRM,
    ]:
        with pytest.raises(ServiceError) as exc_info:
            change_status(carrier, order.pk, invalid_target)
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "invalid_transition"

    # From created: shipper trying to complete
    with pytest.raises(ServiceError) as exc_info:
        change_status(shipper, order.pk, Order.Status.COMPLETED)
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "invalid_transition"

    # Same status: created -> created
    with pytest.raises(ServiceError) as exc_info:
        change_status(carrier, order.pk, Order.Status.CREATED)
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "invalid_transition"

    # Advance to received
    order.status = Order.Status.RECEIVED
    order.save(update_fields=["status"])

    # From received: skipping to delivered, awaiting_confirm
    for invalid_target in [Order.Status.DELIVERED, Order.Status.AWAITING_CONFIRM]:
        with pytest.raises(ServiceError) as exc_info:
            change_status(carrier, order.pk, invalid_target)
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == "invalid_transition"

    # From received: shipper trying to complete
    with pytest.raises(ServiceError) as exc_info:
        change_status(shipper, order.pk, Order.Status.COMPLETED)
    assert exc_info.value.status_code == 409

    # Advance to picked_up
    order.status = Order.Status.PICKED_UP
    order.save(update_fields=["status"])

    # From picked_up: backwards to received, or skipping to awaiting_confirm
    for invalid_target in [Order.Status.RECEIVED, Order.Status.AWAITING_CONFIRM]:
        with pytest.raises(ServiceError) as exc_info:
            change_status(carrier, order.pk, invalid_target)
        assert exc_info.value.status_code == 409

    # Advance to delivered
    order.status = Order.Status.DELIVERED
    order.save(update_fields=["status"])

    # From delivered: shipper trying to complete directly
    with pytest.raises(ServiceError) as exc_info:
        change_status(shipper, order.pk, Order.Status.COMPLETED)
    assert exc_info.value.status_code == 409

    # From delivered: carrier backwards to picked_up
    with pytest.raises(ServiceError) as exc_info:
        change_status(carrier, order.pk, Order.Status.PICKED_UP)
    assert exc_info.value.status_code == 409

    # Advance to completed (terminal state)
    order.status = Order.Status.COMPLETED
    order.save(update_fields=["status"])

    # Terminal state completed: cannot transition to anything
    for target in [Order.Status.CREATED, Order.Status.RECEIVED, Order.Status.CANCELLED]:
        with pytest.raises(ServiceError) as exc_info:
            change_status(carrier, order.pk, target)
        assert exc_info.value.status_code == 409

    # Terminal state cancelled: cannot transition to anything
    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status"])
    with pytest.raises(ServiceError) as exc_info:
        change_status(carrier, order.pk, Order.Status.RECEIVED)
    assert exc_info.value.status_code == 409


@pytest.mark.django_db
def test_non_party_404() -> None:
    """Non-party user gets 404 for status change, rating, and document upload."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    intruder = CarrierUserFactory()
    order = OrderFactory(carrier=carrier, shipper=shipper, status=Order.Status.CREATED)

    with pytest.raises(ServiceError) as exc_info:
        change_status(intruder, order.pk, Order.Status.RECEIVED)
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "not_found"

    order.status = Order.Status.COMPLETED
    order.save(update_fields=["status"])

    with pytest.raises(ServiceError) as exc_info:
        rate_order(intruder, order.pk, stars=5)
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "not_found"

    dummy_file = SimpleUploadedFile("doc.pdf", b"test content")
    with pytest.raises(ServiceError) as exc_info:
        add_document(intruder, order.pk, dummy_file, "doc.pdf")
    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "not_found"


@pytest.mark.django_db
def test_cancel_from_created_and_received_with_load_counts_restore() -> None:
    """Cancellation from created or received decrements trucks_found and restores load to active."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()

    # Cancel from created
    load1 = LoadFactory(
        shipper=shipper,
        status=Load.Status.IN_PROGRESS,
        trucks_needed=2,
        trucks_found=2,
    )
    order1 = OrderFactory(
        load=load1,
        carrier=carrier,
        shipper=shipper,
        status=Order.Status.CREATED,
    )
    order1 = change_status(carrier, order1.pk, Order.Status.CANCELLED, note="Vehicle broken")
    assert order1.status == Order.Status.CANCELLED
    assert order1.cancel_reason == "Vehicle broken"
    load1.refresh_from_db()
    assert load1.trucks_found == 1
    assert load1.status == Load.Status.ACTIVE

    # Cancel from received
    load2 = LoadFactory(
        shipper=shipper,
        status=Load.Status.IN_PROGRESS,
        trucks_needed=1,
        trucks_found=1,
    )
    order2 = OrderFactory(
        load=load2,
        carrier=carrier,
        shipper=shipper,
        status=Order.Status.RECEIVED,
    )
    order2 = change_status(shipper, order2.pk, Order.Status.CANCELLED, note="Cargo recalled")
    assert order2.status == Order.Status.CANCELLED
    assert order2.cancel_reason == "Cargo recalled"
    load2.refresh_from_db()
    assert load2.trucks_found == 0
    assert load2.status == Load.Status.ACTIVE


@pytest.mark.django_db
def test_cancel_from_picked_up_409() -> None:
    """Cancellation from picked_up is not allowed and returns 409 invalid_transition."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    order = OrderFactory(carrier=carrier, shipper=shipper, status=Order.Status.PICKED_UP)

    with pytest.raises(ServiceError) as exc_info:
        change_status(carrier, order.pk, Order.Status.CANCELLED, note="Cannot continue")
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "invalid_transition"

    with pytest.raises(ServiceError) as exc_info:
        change_status(shipper, order.pk, Order.Status.CANCELLED, note="Cannot continue")
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "invalid_transition"


@pytest.mark.django_db
def test_cancel_without_reason_400() -> None:
    """Cancellation without note/reason returns 400 validation_error."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    order = OrderFactory(carrier=carrier, shipper=shipper, status=Order.Status.CREATED)

    with pytest.raises(ServiceError) as exc_info:
        change_status(carrier, order.pk, Order.Status.CANCELLED, note="")
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "validation_error"

    with pytest.raises(ServiceError) as exc_info:
        change_status(carrier, order.pk, Order.Status.CANCELLED, note="   ")
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "validation_error"


@pytest.mark.django_db
def test_load_completes_only_after_all_trucks_orders_complete() -> None:
    """Load completes only when all needed orders reach completed status (trucks_needed=2)."""
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
        status=Order.Status.PICKED_UP,
    )

    # Shipper completes first order
    change_status(shipper, order1.pk, Order.Status.COMPLETED, note="Order 1 complete")
    load.refresh_from_db()
    # 1 of 2 completed, load should still be IN_PROGRESS
    assert load.status == Load.Status.IN_PROGRESS

    # Carrier 2 delivers and requests confirmation
    change_status(carrier2, order2.pk, Order.Status.DELIVERED)
    change_status(carrier2, order2.pk, Order.Status.AWAITING_CONFIRM)

    # Shipper completes second order
    change_status(shipper, order2.pk, Order.Status.COMPLETED, note="Order 2 complete")
    load.refresh_from_db()
    # All 2 orders complete, load becomes COMPLETED
    assert load.status == Load.Status.COMPLETED


@pytest.mark.django_db
def test_rating_validations_and_duplicate_rating_409() -> None:
    """Rating validations: completed only, 1-5 stars, duplicate rating returns 409."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    order = OrderFactory(carrier=carrier, shipper=shipper, status=Order.Status.CREATED)

    # Cannot rate non-completed order
    with pytest.raises(ServiceError) as exc_info:
        rate_order(carrier, order.pk, stars=5)
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "invalid_status"

    # Mark completed
    order.status = Order.Status.COMPLETED
    order.save(update_fields=["status"])

    # Invalid stars: 0 and 6
    with pytest.raises(ServiceError) as exc_info:
        rate_order(carrier, order.pk, stars=0)
    assert exc_info.value.status_code == 400

    with pytest.raises(ServiceError) as exc_info:
        rate_order(carrier, order.pk, stars=6)
    assert exc_info.value.status_code == 400

    # Successful rating
    rate_order(carrier, order.pk, stars=5, reasons=["prompt"], comment="Great")

    # Duplicate rating by same user returns 409
    with pytest.raises(ServiceError) as exc_info:
        rate_order(carrier, order.pk, stars=4)
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "already_rated"


@pytest.mark.django_db
def test_unverified_user_403() -> None:
    """Unverified user attempting status transition receives 403 account_not_verified."""
    unverified_carrier = UserFactory(role=User.Role.CARRIER, status=User.Status.NEW)
    shipper = ShipperUserFactory()
    order = OrderFactory(carrier=unverified_carrier, shipper=shipper, status=Order.Status.CREATED)

    with pytest.raises(ServiceError) as exc_info:
        change_status(unverified_carrier, order.pk, Order.Status.RECEIVED)
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "account_not_verified"


@pytest.mark.django_db
def test_add_document_service() -> None:
    """Test add_document computes size_kb, sets uploaded_by, and validates inputs."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    order = OrderFactory(carrier=carrier, shipper=shipper)

    content = b"a" * 2048  # 2 KB
    uploaded = SimpleUploadedFile("bill.pdf", content, content_type="application/pdf")
    doc = add_document(carrier, order.pk, uploaded, "Bill of Lading")

    assert doc.name == "Bill of Lading"
    assert doc.size_kb == 2
    assert doc.uploaded_by == carrier
    assert doc.order == order

    # Empty document name returns 400
    with pytest.raises(ServiceError) as exc_info:
        add_document(carrier, order.pk, uploaded, "")
    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "validation_error"


@pytest.mark.django_db
def test_order_change_status_twice_returns_409() -> None:
    """Submitting the same order status transition twice returns 409 invalid_transition."""
    carrier = CarrierUserFactory(status=User.Status.VERIFIED)
    shipper = ShipperUserFactory(status=User.Status.VERIFIED)
    order = OrderFactory(carrier=carrier, shipper=shipper, status=Order.Status.CREATED)

    # First transition to received succeeds
    change_status(carrier, order.pk, Order.Status.RECEIVED)
    order.refresh_from_db()
    assert order.status == Order.Status.RECEIVED

    # Second transition to received returns 409
    with pytest.raises(ServiceError) as exc_info:
        change_status(carrier, order.pk, Order.Status.RECEIVED)
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "invalid_transition"


@pytest.mark.django_db
def test_order_rate_twice_integrity_error_returns_409(monkeypatch: pytest.MonkeyPatch) -> None:
    """If unique_order_rater triggers concurrently, 409 already_rated is returned."""
    from django.db import IntegrityError

    carrier = CarrierUserFactory(status=User.Status.VERIFIED)
    shipper = ShipperUserFactory(status=User.Status.VERIFIED)
    order = OrderFactory(carrier=carrier, shipper=shipper, status=Order.Status.COMPLETED)

    def mock_create(*args: Any, **kwargs: Any) -> Any:
        raise IntegrityError("duplicate key value violates unique constraint")

    monkeypatch.setattr(Rating.objects, "create", mock_create)

    with pytest.raises(ServiceError) as exc_info:
        rate_order(carrier, order.pk, stars=5)
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "already_rated"
