"""Offer domain services."""

from decimal import Decimal
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.core.exceptions import ServiceError
from apps.garage.models import Vehicle
from apps.geo.models import Currency
from apps.loads.models import Load
from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.offers.models import Offer
from apps.orders.models import Order, OrderStatusEvent


def _resolve_currency(currency_val: Any) -> Currency | None:
    """Resolve currency model instance from code string, PK, or instance."""
    if currency_val is None:
        return None
    if isinstance(currency_val, Currency):
        return currency_val
    try:
        return Currency.objects.get(code=str(currency_val).strip())
    except Currency.DoesNotExist:
        raise ServiceError(
            detail=f"Currency '{currency_val}' not found.",
            code="validation_error",
            status_code=400,
        ) from None


def _resolve_vehicle(vehicle_val: Any, carrier: User, field_name: str) -> Vehicle | None:
    """Resolve and validate vehicle ownership by carrier."""
    if vehicle_val is None:
        return None
    if isinstance(vehicle_val, Vehicle):
        vehicle = vehicle_val
    else:
        try:
            vehicle = Vehicle.objects.get(pk=int(vehicle_val))
        except (Vehicle.DoesNotExist, ValueError, TypeError):
            raise ServiceError(
                detail=f"Vehicle '{vehicle_val}' not found.",
                code=f"invalid_{field_name}",
                status_code=400,
            ) from None

    if vehicle.owner_id != carrier.pk:
        raise ServiceError(
            detail=f"{field_name.capitalize()} does not belong to the carrier.",
            code=f"invalid_{field_name}",
            status_code=400,
        )
    return vehicle


@transaction.atomic
def create_offer(carrier: User, load: Load, data: dict[str, Any]) -> Offer:
    """Create a new offer on an active load by a verified carrier."""
    if carrier.status != User.Status.VERIFIED:
        raise ServiceError(
            detail="Account is not verified.",
            code="account_not_verified",
            status_code=403,
        )

    if carrier.role not in (User.Role.CARRIER, User.Role.BOTH):
        raise ServiceError(
            detail="Role not allowed for this action.",
            code="role_not_allowed",
            status_code=403,
        )

    # Lock load to inspect authoritative state
    load = Load.objects.select_for_update().get(pk=load.pk)

    if load.status != Load.Status.ACTIVE or load.trucks_found >= load.trucks_needed:
        raise ServiceError(
            detail="Load is not active.",
            code="load_not_active",
            status_code=409,
        )

    if load.shipper_id == carrier.pk:
        raise ServiceError(
            detail="Cannot make an offer on your own load.",
            code="own_load",
            status_code=403,
        )

    mode = data.get("mode", Offer.Mode.PRICE_BID)
    raw_amount = data.get("amount")
    raw_currency = data.get("currency")

    if mode == Offer.Mode.PRICE_BID:
        if raw_amount is None or raw_currency is None or raw_currency == "":
            raise ServiceError(
                detail="Price bid requires amount and currency.",
                code="validation_error",
                status_code=400,
            )
        if not load.price_negotiable and load.price_amount is not None:
            raise ServiceError(
                detail="Price is not negotiable for this load.",
                code="price_not_negotiable",
                status_code=400,
            )
        amount = Decimal(str(raw_amount))
        if amount <= Decimal("0"):
            raise ServiceError(
                detail="Amount must be greater than zero.",
                code="validation_error",
                status_code=400,
            )
        currency = _resolve_currency(raw_currency)
    else:
        amount = Decimal(str(raw_amount)) if raw_amount is not None else None
        if amount is not None and amount <= Decimal("0"):
            raise ServiceError(
                detail="Amount must be greater than zero.",
                code="validation_error",
                status_code=400,
            )
        currency = _resolve_currency(raw_currency) if raw_currency else None

    if load.currency_id and currency and load.currency_id != currency.code:
        raise ServiceError(
            detail="Offer currency must match load currency.",
            code="currency_mismatch",
            status_code=400,
        )

    vehicle = _resolve_vehicle(
        data.get("vehicle") or data.get("vehicle_id"),
        carrier=carrier,
        field_name="vehicle",
    )
    trailer = _resolve_vehicle(
        data.get("trailer") or data.get("trailer_id"),
        carrier=carrier,
        field_name="trailer",
    )

    if Offer.objects.filter(load=load, carrier=carrier, status=Offer.Status.PENDING).exists():
        raise ServiceError(
            detail="A pending offer already exists for this carrier on this load.",
            code="duplicate_offer",
            status_code=409,
        )

    try:
        offer = Offer.objects.create(
            load=load,
            carrier=carrier,
            proposer=carrier,
            recipient=load.shipper,
            vehicle=vehicle,
            trailer=trailer,
            mode=mode,
            amount=amount,
            currency=currency,
            comment=str(data.get("comment") or "").strip(),
            status=Offer.Status.PENDING,
        )
    except IntegrityError as exc:
        raise ServiceError(
            detail="A pending offer already exists for this carrier on this load.",
            code="duplicate_offer",
            status_code=409,
        ) from exc

    notify(
        user=load.shipper,
        type=Notification.NotificationType.OFFER_RECEIVED,
        payload={"offer_id": offer.pk, "load_id": load.pk},
    )
    return offer


@transaction.atomic
def accept_offer(user: User, offer_id: int) -> Offer:
    """Accept a pending offer, create an Order, update load truck count, and notify parties."""
    if user.status != User.Status.VERIFIED:
        raise ServiceError(
            detail="Account is not verified.",
            code="account_not_verified",
            status_code=403,
        )

    try:
        pre_offer = Offer.objects.select_related("load").get(pk=offer_id)
    except Offer.DoesNotExist:
        raise ServiceError(
            detail="Offer not found.",
            code="not_found",
            status_code=404,
        ) from None

    if pre_offer.recipient_id != user.pk:
        raise ServiceError(
            detail="Only the recipient can accept this offer.",
            code="permission_denied",
            status_code=403,
        )

    if pre_offer.status != Offer.Status.PENDING:
        raise ServiceError(
            detail="Offer is not pending.",
            code="invalid_transition",
            status_code=409,
        )

    # Concurrency control: lock load then offer
    load = Load.objects.select_for_update().get(pk=pre_offer.load_id)
    offer = Offer.objects.select_for_update().get(pk=offer_id)

    if offer.status != Offer.Status.PENDING:
        raise ServiceError(
            detail="Offer is not pending.",
            code="invalid_transition",
            status_code=409,
        )

    if load.status != Load.Status.ACTIVE or load.trucks_found >= load.trucks_needed:
        raise ServiceError(
            detail="Load is not active.",
            code="load_not_active",
            status_code=409,
        )

    now = timezone.now()
    offer.status = Offer.Status.ACCEPTED
    offer.responded_at = now
    offer.save(update_fields=["status", "responded_at", "updated_at"])

    agreed_amount = offer.amount if offer.amount is not None else load.price_amount
    agreed_currency = offer.currency if offer.currency is not None else load.currency

    order = Order.objects.create(
        offer=offer,
        load=load,
        shipper=load.shipper,
        carrier=offer.carrier,
        vehicle=offer.vehicle,
        trailer=offer.trailer,
        agreed_amount=agreed_amount,
        currency=agreed_currency,
        status=Order.Status.CREATED,
    )

    OrderStatusEvent.objects.create(
        order=order,
        status=Order.Status.CREATED,
        actor=user,
        note="Order created upon offer acceptance",
    )

    load.trucks_found += 1
    if load.trucks_found >= load.trucks_needed:
        load.status = Load.Status.IN_PROGRESS
        load.save(update_fields=["trucks_found", "status", "updated_at"])

        other_pending_offers = list(
            Offer.objects.select_for_update()
            .filter(load=load, status=Offer.Status.PENDING)
            .exclude(pk=offer.pk)
        )
        for other_offer in other_pending_offers:
            other_offer.status = Offer.Status.REJECTED
            other_offer.responded_at = now
            other_offer.save(update_fields=["status", "responded_at", "updated_at"])
            notify(
                user=other_offer.carrier,
                type=Notification.NotificationType.OFFER_REJECTED,
                payload={"offer_id": other_offer.pk, "load_id": load.pk},
            )
    else:
        load.save(update_fields=["trucks_found", "updated_at"])

    notify(
        user=offer.proposer,
        type=Notification.NotificationType.OFFER_ACCEPTED,
        payload={"offer_id": offer.pk, "order_id": order.pk, "load_id": load.pk},
    )
    return offer


@transaction.atomic
def reject_offer(user: User, offer_id: int) -> Offer:
    """Reject a pending offer and notify proposer."""
    if user.status != User.Status.VERIFIED:
        raise ServiceError(
            detail="Account is not verified.",
            code="account_not_verified",
            status_code=403,
        )

    try:
        offer = Offer.objects.get(pk=offer_id)
    except Offer.DoesNotExist:
        raise ServiceError(
            detail="Offer not found.",
            code="not_found",
            status_code=404,
        ) from None

    if offer.recipient_id != user.pk:
        raise ServiceError(
            detail="Only the recipient can reject this offer.",
            code="permission_denied",
            status_code=403,
        )

    if offer.status != Offer.Status.PENDING:
        raise ServiceError(
            detail="Offer is not pending.",
            code="invalid_transition",
            status_code=409,
        )

    offer = Offer.objects.select_for_update().get(pk=offer_id)
    if offer.status != Offer.Status.PENDING:
        raise ServiceError(
            detail="Offer is not pending.",
            code="invalid_transition",
            status_code=409,
        )

    now = timezone.now()
    offer.status = Offer.Status.REJECTED
    offer.responded_at = now
    offer.save(update_fields=["status", "responded_at", "updated_at"])

    notify(
        user=offer.proposer,
        type=Notification.NotificationType.OFFER_REJECTED,
        payload={"offer_id": offer.pk, "load_id": offer.load_id},
    )
    return offer


@transaction.atomic
def cancel_offer(user: User, offer_id: int) -> Offer:
    """Cancel a pending offer by its proposer."""
    if user.status != User.Status.VERIFIED:
        raise ServiceError(
            detail="Account is not verified.",
            code="account_not_verified",
            status_code=403,
        )

    try:
        offer = Offer.objects.get(pk=offer_id)
    except Offer.DoesNotExist:
        raise ServiceError(
            detail="Offer not found.",
            code="not_found",
            status_code=404,
        ) from None

    if offer.proposer_id != user.pk:
        raise ServiceError(
            detail="Only the proposer can cancel this offer.",
            code="permission_denied",
            status_code=403,
        )

    if offer.status != Offer.Status.PENDING:
        raise ServiceError(
            detail="Offer is not pending.",
            code="invalid_transition",
            status_code=409,
        )

    offer = Offer.objects.select_for_update().get(pk=offer_id)
    if offer.status != Offer.Status.PENDING:
        raise ServiceError(
            detail="Offer is not pending.",
            code="invalid_transition",
            status_code=409,
        )

    offer.status = Offer.Status.CANCELLED
    offer.responded_at = timezone.now()
    offer.save(update_fields=["status", "responded_at", "updated_at"])
    return offer


@transaction.atomic
def counter_offer(user: User, offer_id: int, data: dict[str, Any]) -> Offer:
    """Counter a pending offer by marking it countered and creating a new pending offer."""
    if user.status != User.Status.VERIFIED:
        raise ServiceError(
            detail="Account is not verified.",
            code="account_not_verified",
            status_code=403,
        )

    try:
        pre_offer = Offer.objects.get(pk=offer_id)
    except Offer.DoesNotExist:
        raise ServiceError(
            detail="Offer not found.",
            code="not_found",
            status_code=404,
        ) from None

    if pre_offer.recipient_id != user.pk:
        raise ServiceError(
            detail="Only the recipient can counter this offer.",
            code="permission_denied",
            status_code=403,
        )

    if pre_offer.status != Offer.Status.PENDING:
        raise ServiceError(
            detail="Offer is not pending.",
            code="invalid_transition",
            status_code=409,
        )

    load = Load.objects.select_for_update().get(pk=pre_offer.load_id)
    old_offer = Offer.objects.select_for_update().get(pk=offer_id)

    if old_offer.status != Offer.Status.PENDING:
        raise ServiceError(
            detail="Offer is not pending.",
            code="invalid_transition",
            status_code=409,
        )

    if load.status != Load.Status.ACTIVE or load.trucks_found >= load.trucks_needed:
        raise ServiceError(
            detail="Load is not active.",
            code="load_not_active",
            status_code=409,
        )

    raw_amount = data.get("amount")
    raw_currency = data.get("currency")
    if raw_amount is None or raw_currency is None or raw_currency == "":
        raise ServiceError(
            detail="Counter offer requires amount and currency.",
            code="validation_error",
            status_code=400,
        )

    if not load.price_negotiable and load.price_amount is not None:
        raise ServiceError(
            detail="Price is not negotiable for this load.",
            code="price_not_negotiable",
            status_code=400,
        )

    amount = Decimal(str(raw_amount))
    if amount <= Decimal("0"):
        raise ServiceError(
            detail="Amount must be greater than zero.",
            code="validation_error",
            status_code=400,
        )
    currency = _resolve_currency(raw_currency)

    if load.currency_id and currency and load.currency_id != currency.code:
        raise ServiceError(
            detail="Offer currency must match load currency.",
            code="currency_mismatch",
            status_code=400,
        )

    # Mark old offer countered first to satisfy unique pending constraint
    now = timezone.now()
    old_offer.status = Offer.Status.COUNTERED
    old_offer.responded_at = now
    old_offer.save(update_fields=["status", "responded_at", "updated_at"])

    new_offer = Offer.objects.create(
        load=load,
        carrier=old_offer.carrier,
        proposer=old_offer.recipient,
        recipient=old_offer.proposer,
        vehicle=old_offer.vehicle,
        trailer=old_offer.trailer,
        parent=old_offer,
        mode=Offer.Mode.PRICE_BID,
        amount=amount,
        currency=currency,
        comment=str(data.get("comment") or "").strip(),
        status=Offer.Status.PENDING,
    )

    notify(
        user=new_offer.recipient,
        type=Notification.NotificationType.OFFER_COUNTERED,
        payload={"offer_id": new_offer.pk, "load_id": load.pk},
    )
    return new_offer
