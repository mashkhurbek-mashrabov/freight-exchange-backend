"""Unit and integration tests for offer domain services."""

import threading
from decimal import Decimal
from typing import Any

import pytest
from django.db import connection

from apps.accounts.models import User
from apps.accounts.tests.factories import CarrierUserFactory, ShipperUserFactory, UserFactory
from apps.core.exceptions import ServiceError
from apps.garage.models import VehicleKind
from apps.garage.tests.factories import VehicleFactory
from apps.loads.models import Load
from apps.loads.tests.factories import LoadFactory
from apps.notifications.models import Notification
from apps.offers.models import Offer
from apps.offers.services import (
    accept_offer,
    cancel_offer,
    counter_offer,
    create_offer,
    reject_offer,
)
from apps.offers.tests.factories import OfferFactory
from apps.orders.models import Order, OrderStatusEvent


@pytest.mark.django_db
def test_create_offer_success() -> None:
    """Verify carrier can create a pending offer on an active load and recipient is notified."""
    carrier = CarrierUserFactory()
    load = LoadFactory(status=Load.Status.ACTIVE)

    offer = create_offer(
        carrier=carrier,
        load=load,
        data={
            "mode": Offer.Mode.PRICE_BID,
            "amount": Decimal("2100.00"),
            "currency": load.currency,
            "comment": "Can pick up early morning",
        },
    )

    assert offer.pk is not None
    assert offer.load == load
    assert offer.carrier == carrier
    assert offer.proposer == carrier
    assert offer.recipient == load.shipper
    assert offer.status == Offer.Status.PENDING
    assert offer.amount == Decimal("2100.00")
    assert offer.currency == load.currency
    assert offer.comment == "Can pick up early morning"

    # Notification check
    notif = Notification.objects.filter(
        user=load.shipper,
        type=Notification.NotificationType.OFFER_RECEIVED,
    ).first()
    assert notif is not None
    assert notif.payload == {"offer_id": offer.pk, "load_id": load.pk}


@pytest.mark.django_db
def test_create_offer_with_both_role() -> None:
    """Verify user with role 'both' can submit an offer."""
    user_both = UserFactory(role=User.Role.BOTH, status=User.Status.VERIFIED)
    load = LoadFactory(status=Load.Status.ACTIVE)

    offer = create_offer(
        carrier=user_both,
        load=load,
        data={
            "mode": Offer.Mode.PRICE_BID,
            "amount": Decimal("1800.00"),
            "currency": load.currency.code,
        },
    )
    assert offer.pk is not None
    assert offer.carrier == user_both


@pytest.mark.django_db
def test_create_offer_role_gate_shipper_rejected() -> None:
    """Verify shipper-only role cannot create offers (403 role_not_allowed)."""
    shipper = ShipperUserFactory()
    load = LoadFactory(status=Load.Status.ACTIVE)

    with pytest.raises(ServiceError) as exc_info:
        create_offer(
            carrier=shipper,
            load=load,
            data={"amount": Decimal("1000.00"), "currency": load.currency},
        )
    assert exc_info.value.code == "role_not_allowed"
    assert exc_info.value.status_code == 403


@pytest.mark.django_db
def test_create_offer_unverified_carrier_rejected() -> None:
    """Verify unverified carrier cannot create offers (403 account_not_verified)."""
    unverified_carrier = UserFactory(role=User.Role.CARRIER, status=User.Status.NEW)
    load = LoadFactory(status=Load.Status.ACTIVE)

    with pytest.raises(ServiceError) as exc_info:
        create_offer(
            carrier=unverified_carrier,
            load=load,
            data={"amount": Decimal("1000.00"), "currency": load.currency},
        )
    assert exc_info.value.code == "account_not_verified"
    assert exc_info.value.status_code == 403


@pytest.mark.django_db
def test_create_offer_on_non_active_load_rejected() -> None:
    """Verify offer on draft or completed load returns 409 load_not_active."""
    carrier = CarrierUserFactory()
    draft_load = LoadFactory(status=Load.Status.DRAFT)

    with pytest.raises(ServiceError) as exc_info:
        create_offer(
            carrier=carrier,
            load=draft_load,
            data={"amount": Decimal("1500.00"), "currency": draft_load.currency},
        )
    assert exc_info.value.code == "load_not_active"
    assert exc_info.value.status_code == 409


@pytest.mark.django_db
def test_create_offer_on_own_load_rejected() -> None:
    """Verify carrier cannot offer on their own load (403 own_load)."""
    user_both = UserFactory(role=User.Role.BOTH, status=User.Status.VERIFIED)
    own_load = LoadFactory(shipper=user_both, status=Load.Status.ACTIVE)

    with pytest.raises(ServiceError) as exc_info:
        create_offer(
            carrier=user_both,
            load=own_load,
            data={"amount": Decimal("1200.00"), "currency": own_load.currency},
        )
    assert exc_info.value.code == "own_load"
    assert exc_info.value.status_code == 403


@pytest.mark.django_db
def test_create_offer_non_negotiable_price_bid_rejected() -> None:
    """Verify price_bid rejected if load is non-negotiable and has price (400 code)."""
    carrier = CarrierUserFactory()
    fixed_load = LoadFactory(
        status=Load.Status.ACTIVE,
        price_negotiable=False,
        price_amount=Decimal("3000.00"),
    )

    with pytest.raises(ServiceError) as exc_info:
        create_offer(
            carrier=carrier,
            load=fixed_load,
            data={
                "mode": Offer.Mode.PRICE_BID,
                "amount": Decimal("2800.00"),
                "currency": fixed_load.currency,
            },
        )
    assert exc_info.value.code == "price_not_negotiable"
    assert exc_info.value.status_code == 400


@pytest.mark.django_db
def test_create_offer_comment_only_allowed_on_non_negotiable_load() -> None:
    """Verify comment_only offer succeeds on a non-negotiable load."""
    carrier = CarrierUserFactory()
    fixed_load = LoadFactory(
        status=Load.Status.ACTIVE,
        price_negotiable=False,
        price_amount=Decimal("3000.00"),
    )

    offer = create_offer(
        carrier=carrier,
        load=fixed_load,
        data={
            "mode": Offer.Mode.COMMENT_ONLY,
            "comment": "Accepting your fixed rate, can load today",
        },
    )
    assert offer.pk is not None
    assert offer.mode == Offer.Mode.COMMENT_ONLY
    assert offer.amount is None


@pytest.mark.django_db
def test_create_offer_price_bid_requires_amount_and_currency() -> None:
    """Verify price_bid without amount or currency returns 400 validation_error."""
    carrier = CarrierUserFactory()
    load = LoadFactory(status=Load.Status.ACTIVE)

    with pytest.raises(ServiceError) as exc_info:
        create_offer(
            carrier=carrier,
            load=load,
            data={"mode": Offer.Mode.PRICE_BID, "amount": None, "currency": None},
        )
    assert exc_info.value.code == "validation_error"
    assert exc_info.value.status_code == 400


@pytest.mark.django_db
def test_create_offer_vehicle_ownership_validation() -> None:
    """Verify vehicle/trailer must belong to the carrier (400 invalid_vehicle/invalid_trailer)."""
    carrier = CarrierUserFactory()
    other_user = CarrierUserFactory()
    load = LoadFactory(status=Load.Status.ACTIVE)

    foreign_vehicle = VehicleFactory(owner=other_user, kind=VehicleKind.TRACTOR)
    my_vehicle = VehicleFactory(owner=carrier, kind=VehicleKind.TRACTOR)
    foreign_trailer = VehicleFactory(owner=other_user, kind=VehicleKind.TRAILER)

    with pytest.raises(ServiceError) as exc_info:
        create_offer(
            carrier=carrier,
            load=load,
            data={
                "amount": Decimal("2000.00"),
                "currency": load.currency,
                "vehicle": foreign_vehicle,
            },
        )
    assert exc_info.value.code == "invalid_vehicle"

    with pytest.raises(ServiceError) as exc_info:
        create_offer(
            carrier=carrier,
            load=load,
            data={
                "amount": Decimal("2000.00"),
                "currency": load.currency,
                "vehicle": my_vehicle,
                "trailer": foreign_trailer,
            },
        )
    assert exc_info.value.code == "invalid_trailer"


@pytest.mark.django_db
def test_create_offer_duplicate_pending_rejected() -> None:
    """Verify duplicate pending offer returns 409 duplicate_offer."""
    carrier = CarrierUserFactory()
    load = LoadFactory(status=Load.Status.ACTIVE)

    create_offer(
        carrier=carrier,
        load=load,
        data={"amount": Decimal("2000.00"), "currency": load.currency},
    )

    with pytest.raises(ServiceError) as exc_info:
        create_offer(
            carrier=carrier,
            load=load,
            data={"amount": Decimal("2100.00"), "currency": load.currency},
        )
    assert exc_info.value.code == "duplicate_offer"
    assert exc_info.value.status_code == 409


@pytest.mark.django_db
def test_accept_offer_success_creates_order_event_and_notifies() -> None:
    """Verify accept creates Order, event, increments trucks_found, and notifies."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    load = LoadFactory(
        shipper=shipper,
        status=Load.Status.ACTIVE,
        trucks_needed=1,
        trucks_found=0,
    )
    my_vehicle = VehicleFactory(owner=carrier, kind=VehicleKind.TRACTOR)
    offer = OfferFactory(
        load=load,
        carrier=carrier,
        proposer=carrier,
        recipient=shipper,
        vehicle=my_vehicle,
        amount=Decimal("2500.00"),
        status=Offer.Status.PENDING,
    )

    accepted_offer = accept_offer(user=shipper, offer_id=offer.pk)

    assert accepted_offer.status == Offer.Status.ACCEPTED
    assert accepted_offer.responded_at is not None

    # Order verification
    order = Order.objects.filter(offer=accepted_offer).first()
    assert order is not None
    assert order.load == load
    assert order.shipper == shipper
    assert order.carrier == carrier
    assert order.vehicle == my_vehicle
    assert order.agreed_amount == Decimal("2500.00")
    assert order.currency == accepted_offer.currency
    assert order.status == Order.Status.CREATED

    # Event verification
    event = OrderStatusEvent.objects.filter(order=order).first()
    assert event is not None
    assert event.status == Order.Status.CREATED
    assert event.actor == shipper

    # Load verification (1 truck needed -> now in_progress)
    load.refresh_from_db()
    assert load.trucks_found == 1
    assert load.status == Load.Status.IN_PROGRESS

    # Notification verification
    notif = Notification.objects.filter(
        user=carrier,
        type=Notification.NotificationType.OFFER_ACCEPTED,
    ).first()
    assert notif is not None
    assert notif.payload == {
        "offer_id": accepted_offer.pk,
        "order_id": order.pk,
        "load_id": load.pk,
    }


@pytest.mark.django_db
def test_accept_offer_fallback_price_for_comment_only() -> None:
    """Verify agreed_amount falls back to load.price_amount for comment_only offer."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    load = LoadFactory(
        shipper=shipper,
        status=Load.Status.ACTIVE,
        price_amount=Decimal("3500.00"),
    )
    offer = OfferFactory(
        load=load,
        carrier=carrier,
        proposer=carrier,
        recipient=shipper,
        mode=Offer.Mode.COMMENT_ONLY,
        amount=None,
        status=Offer.Status.PENDING,
    )

    accepted_offer = accept_offer(user=shipper, offer_id=offer.pk)
    order = Order.objects.get(offer=accepted_offer)
    assert order.agreed_amount == Decimal("3500.00")


@pytest.mark.django_db
def test_accept_offer_only_recipient_allowed() -> None:
    """Verify non-recipient cannot accept an offer (403 permission_denied)."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    other_user = ShipperUserFactory()
    load = LoadFactory(shipper=shipper, status=Load.Status.ACTIVE)
    offer = OfferFactory(load=load, carrier=carrier, proposer=carrier, recipient=shipper)

    with pytest.raises(ServiceError) as exc_info:
        accept_offer(user=other_user, offer_id=offer.pk)
    assert exc_info.value.code == "permission_denied"
    assert exc_info.value.status_code == 403


@pytest.mark.django_db
def test_accept_offer_non_pending_rejected() -> None:
    """Verify non-pending offer cannot be accepted (409 invalid_transition)."""
    shipper = ShipperUserFactory()
    load = LoadFactory(shipper=shipper, status=Load.Status.ACTIVE)
    offer = OfferFactory(load=load, recipient=shipper, status=Offer.Status.REJECTED)

    with pytest.raises(ServiceError) as exc_info:
        accept_offer(user=shipper, offer_id=offer.pk)
    assert exc_info.value.code == "invalid_transition"
    assert exc_info.value.status_code == 409


@pytest.mark.django_db
def test_accept_offer_load_not_active_rejected() -> None:
    """Verify accepting offer when load is cancelled or completed returns 409 load_not_active."""
    shipper = ShipperUserFactory()
    load = LoadFactory(shipper=shipper, status=Load.Status.CANCELLED)
    offer = OfferFactory(load=load, recipient=shipper, status=Offer.Status.PENDING)

    with pytest.raises(ServiceError) as exc_info:
        accept_offer(user=shipper, offer_id=offer.pk)
    assert exc_info.value.code == "load_not_active"
    assert exc_info.value.status_code == 409


@pytest.mark.django_db
def test_multi_truck_load_filling_and_auto_reject() -> None:
    """Verify 2-truck load stays active on 1st accept and auto-rejects remaining on 2nd."""
    shipper = ShipperUserFactory()
    c1 = CarrierUserFactory()
    c2 = CarrierUserFactory()
    c3 = CarrierUserFactory()
    load = LoadFactory(
        shipper=shipper,
        status=Load.Status.ACTIVE,
        trucks_needed=2,
        trucks_found=0,
    )

    o1 = OfferFactory(load=load, carrier=c1, proposer=c1, recipient=shipper)
    o2 = OfferFactory(load=load, carrier=c2, proposer=c2, recipient=shipper)
    o3 = OfferFactory(load=load, carrier=c3, proposer=c3, recipient=shipper)

    # 1st acceptance
    accept_offer(user=shipper, offer_id=o1.pk)
    load.refresh_from_db()
    assert load.trucks_found == 1
    assert load.status == Load.Status.ACTIVE

    o2.refresh_from_db()
    o3.refresh_from_db()
    assert o2.status == Offer.Status.PENDING
    assert o3.status == Offer.Status.PENDING

    # 2nd acceptance -> fills load
    accept_offer(user=shipper, offer_id=o2.pk)
    load.refresh_from_db()
    assert load.trucks_found == 2
    assert load.status == Load.Status.IN_PROGRESS

    # o3 must be auto-rejected with responded_at
    o3.refresh_from_db()
    assert o3.status == Offer.Status.REJECTED
    assert o3.responded_at is not None

    # Notification sent to c3
    notif = Notification.objects.filter(
        user=c3,
        type=Notification.NotificationType.OFFER_REJECTED,
    ).first()
    assert notif is not None
    assert notif.payload == {"offer_id": o3.pk, "load_id": load.pk}

    # Exactly 2 orders created
    assert Order.objects.filter(load=load).count() == 2


@pytest.mark.django_db
def test_reject_offer_success_and_notifications() -> None:
    """Verify recipient can reject pending offer and proposer is notified."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    load = LoadFactory(shipper=shipper, status=Load.Status.ACTIVE)
    offer = OfferFactory(load=load, carrier=carrier, proposer=carrier, recipient=shipper)

    rejected_offer = reject_offer(user=shipper, offer_id=offer.pk)
    assert rejected_offer.status == Offer.Status.REJECTED
    assert rejected_offer.responded_at is not None

    notif = Notification.objects.filter(
        user=carrier,
        type=Notification.NotificationType.OFFER_REJECTED,
    ).first()
    assert notif is not None
    assert notif.payload == {"offer_id": offer.pk, "load_id": load.pk}


@pytest.mark.django_db
def test_reject_offer_permissions_and_state() -> None:
    """Verify non-recipient cannot reject and non-pending offer cannot be rejected."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    load = LoadFactory(shipper=shipper, status=Load.Status.ACTIVE)
    offer = OfferFactory(load=load, carrier=carrier, proposer=carrier, recipient=shipper)

    with pytest.raises(ServiceError) as exc_info:
        reject_offer(user=carrier, offer_id=offer.pk)
    assert exc_info.value.code == "permission_denied"

    # Reject once
    reject_offer(user=shipper, offer_id=offer.pk)

    # Reject again
    with pytest.raises(ServiceError) as exc_info:
        reject_offer(user=shipper, offer_id=offer.pk)
    assert exc_info.value.code == "invalid_transition"


@pytest.mark.django_db
def test_cancel_offer_success_and_permissions() -> None:
    """Verify proposer can cancel pending offer; non-proposer cannot."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    load = LoadFactory(shipper=shipper, status=Load.Status.ACTIVE)
    offer = OfferFactory(load=load, carrier=carrier, proposer=carrier, recipient=shipper)

    # Recipient cannot cancel
    with pytest.raises(ServiceError) as exc_info:
        cancel_offer(user=shipper, offer_id=offer.pk)
    assert exc_info.value.code == "permission_denied"

    # Proposer cancels
    cancelled = cancel_offer(user=carrier, offer_id=offer.pk)
    assert cancelled.status == Offer.Status.CANCELLED
    assert cancelled.responded_at is not None

    # Cancel again returns 409
    with pytest.raises(ServiceError) as exc_info:
        cancel_offer(user=carrier, offer_id=offer.pk)
    assert exc_info.value.code == "invalid_transition"


@pytest.mark.django_db
def test_counter_offer_chain_and_acceptance() -> None:
    """Verify A->B->A counter-offer negotiation chain and final acceptance."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    load = LoadFactory(shipper=shipper, status=Load.Status.ACTIVE)

    # Carrier makes Offer 1
    o1 = create_offer(
        carrier=carrier,
        load=load,
        data={
            "mode": Offer.Mode.PRICE_BID,
            "amount": Decimal("2000.00"),
            "currency": load.currency,
        },
    )
    assert o1.status == Offer.Status.PENDING

    # Shipper counters with Offer 2 (amount 1700)
    o2 = counter_offer(
        user=shipper,
        offer_id=o1.pk,
        data={
            "amount": Decimal("1700.00"),
            "currency": load.currency,
            "comment": "Too high, 1700 is our maximum",
        },
    )
    o1.refresh_from_db()
    assert o1.status == Offer.Status.COUNTERED
    assert o2.status == Offer.Status.PENDING
    assert o2.parent == o1
    assert o2.carrier == carrier
    assert o2.proposer == shipper
    assert o2.recipient == carrier
    assert o2.amount == Decimal("1700.00")

    # Notification sent to carrier
    notif1 = Notification.objects.filter(
        user=carrier,
        type=Notification.NotificationType.OFFER_COUNTERED,
    ).first()
    assert notif1 is not None

    # Carrier counters with Offer 3 (amount 1850)
    o3 = counter_offer(
        user=carrier,
        offer_id=o2.pk,
        data={
            "amount": Decimal("1850.00"),
            "currency": load.currency,
            "comment": "Let us split the difference at 1850",
        },
    )
    o2.refresh_from_db()
    assert o2.status == Offer.Status.COUNTERED
    assert o3.status == Offer.Status.PENDING
    assert o3.parent == o2
    assert o3.carrier == carrier
    assert o3.proposer == carrier
    assert o3.recipient == shipper
    assert o3.amount == Decimal("1850.00")

    # Shipper accepts Offer 3
    accepted = accept_offer(user=shipper, offer_id=o3.pk)
    assert accepted.status == Offer.Status.ACCEPTED

    order = Order.objects.get(offer=accepted)
    assert order.agreed_amount == Decimal("1850.00")
    assert order.carrier == carrier
    assert order.shipper == shipper


@pytest.mark.django_db(transaction=True)
def test_concurrency_simultaneous_accepts_one_winner() -> None:
    """Verify two concurrent accepts produce exactly one Order (loser gets 409)."""
    shipper = ShipperUserFactory()
    c1 = CarrierUserFactory()
    c2 = CarrierUserFactory()
    load = LoadFactory(
        shipper=shipper,
        status=Load.Status.ACTIVE,
        trucks_needed=1,
        trucks_found=0,
    )

    o1 = OfferFactory(load=load, carrier=c1, proposer=c1, recipient=shipper)
    o2 = OfferFactory(load=load, carrier=c2, proposer=c2, recipient=shipper)

    results = []
    errors = []
    barrier = threading.Barrier(2)

    def run_accept(offer_id: int) -> None:
        # Each thread needs its own db connection cleanup in django
        try:
            barrier.wait(timeout=5)
            res = accept_offer(user=shipper, offer_id=offer_id)
            results.append(res)
        except Exception as exc:
            errors.append(exc)
        finally:
            connection.close()

    t1 = threading.Thread(target=run_accept, args=(o1.pk,))
    t2 = threading.Thread(target=run_accept, args=(o2.pk,))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Exactly one thread succeeds
    assert len(results) == 1
    assert len(errors) == 1

    loser_error = errors[0]
    assert isinstance(loser_error, ServiceError)
    assert loser_error.status_code == 409
    assert loser_error.code in ("load_not_active", "invalid_transition")

    # Exactly one Order in database
    orders = list(Order.objects.filter(load=load))
    assert len(orders) == 1

    load.refresh_from_db()
    assert load.trucks_found == 1
    assert load.status == Load.Status.IN_PROGRESS


@pytest.mark.django_db
def test_accept_offer_twice_returns_409() -> None:
    """Accepting the same offer a second time returns 409 invalid_transition."""
    shipper = ShipperUserFactory(status=User.Status.VERIFIED)
    carrier = CarrierUserFactory(status=User.Status.VERIFIED)
    load = LoadFactory(shipper=shipper, status=Load.Status.ACTIVE)
    offer = OfferFactory(
        load=load,
        carrier=carrier,
        proposer=carrier,
        recipient=shipper,
        status=Offer.Status.PENDING,
    )

    # First accept succeeds
    accepted = accept_offer(shipper, offer.pk)
    assert accepted.status == Offer.Status.ACCEPTED

    # Second accept raises 409
    with pytest.raises(ServiceError) as exc_info:
        accept_offer(shipper, offer.pk)
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "invalid_transition"


@pytest.mark.django_db
def test_counter_offer_twice_returns_409() -> None:
    """Countering the same offer a second time returns 409 invalid_transition."""
    shipper = ShipperUserFactory(status=User.Status.VERIFIED)
    carrier = CarrierUserFactory(status=User.Status.VERIFIED)
    load = LoadFactory(shipper=shipper, status=Load.Status.ACTIVE)
    offer = OfferFactory(
        load=load,
        carrier=carrier,
        proposer=carrier,
        recipient=shipper,
        status=Offer.Status.PENDING,
    )

    data = {
        "amount": Decimal("2500.00"),
        "currency": load.currency.code,
        "comment": "Counter price",
    }

    # First counter succeeds
    new_offer = counter_offer(shipper, offer.pk, data)
    assert new_offer.status == Offer.Status.PENDING

    # Second counter on same original offer raises 409
    with pytest.raises(ServiceError) as exc_info:
        counter_offer(shipper, offer.pk, data)
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "invalid_transition"


@pytest.mark.django_db
def test_counter_offer_unique_constraint_surfaces_409(monkeypatch: pytest.MonkeyPatch) -> None:
    """If unique_pending_offer triggers during counter_offer, 409 is returned."""
    from django.db import IntegrityError

    shipper = ShipperUserFactory(status=User.Status.VERIFIED)
    carrier = CarrierUserFactory(status=User.Status.VERIFIED)
    load = LoadFactory(shipper=shipper, status=Load.Status.ACTIVE)
    offer = OfferFactory(
        load=load,
        carrier=carrier,
        proposer=carrier,
        recipient=shipper,
        status=Offer.Status.PENDING,
    )

    data = {
        "amount": Decimal("2500.00"),
        "currency": load.currency.code,
        "comment": "Counter price",
    }

    def mock_create(*args: Any, **kwargs: Any) -> Any:
        raise IntegrityError("duplicate key value violates unique constraint")

    monkeypatch.setattr(Offer.objects, "create", mock_create)

    with pytest.raises(ServiceError) as exc_info:
        counter_offer(shipper, offer.pk, data)
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "duplicate_offer"
