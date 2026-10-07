"""Orders domain services."""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Company, User
from apps.core.exceptions import ServiceError
from apps.loads.models import Load
from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.orders.models import Order, OrderDocument, OrderStatusEvent, Rating

CARRIER_STATUSES = {
    Order.Status.RECEIVED,
    Order.Status.PICKED_UP,
    Order.Status.DELIVERED,
    Order.Status.AWAITING_CONFIRM,
}

SHIPPER_STATUSES = {
    Order.Status.COMPLETED,
}


def change_status(
    user: User,
    order_id: int,
    new_status: str,
    note: str = "",
) -> Order:
    """Transition an order to a new status according to the role matrix.

    Role matrix:
    - received, picked_up, delivered, awaiting_confirm: carrier-only
      (strict sequence: created -> received -> picked_up -> delivered -> awaiting_confirm)
    - completed: shipper-only (only from awaiting_confirm)
    - cancelled: either party (only from created or received, requires note as cancel_reason)

    Transitions record an OrderStatusEvent and notify the other party.
    On cancellation, load trucks_found is decremented and status is restored to active if
    in_progress. On completion, the load is marked completed once all needed truck orders
    are completed.
    """
    if getattr(user, "status", None) != User.Status.VERIFIED:
        raise ServiceError(
            detail="Account is not verified.",
            code="account_not_verified",
            status_code=403,
        )

    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().select_related("load").get(pk=order_id)
        except Order.DoesNotExist:
            raise ServiceError(
                detail="Order not found.",
                code="not_found",
                status_code=404,
            ) from None

        load = Load.objects.select_for_update().get(pk=order.load_id)

        # Non-party users cannot view or mutate orders
        if user.pk != order.carrier_id and user.pk != order.shipper_id:
            raise ServiceError(
                detail="Order not found.",
                code="not_found",
                status_code=404,
            )

        # Terminal state check
        if order.status in (Order.Status.COMPLETED, Order.Status.CANCELLED):
            raise ServiceError(
                detail=f"Cannot transition order from terminal status '{order.status}'.",
                code="invalid_transition",
                status_code=409,
            )

        if new_status == order.status:
            raise ServiceError(
                detail=f"Order is already in status '{order.status}'.",
                code="invalid_transition",
                status_code=409,
            )

        # Role gate per target status
        if new_status in CARRIER_STATUSES and user.pk != order.carrier_id:
            raise ServiceError(
                detail="Only the carrier can transition order to this status.",
                code="permission_denied",
                status_code=403,
            )

        if new_status in SHIPPER_STATUSES and user.pk != order.shipper_id:
            raise ServiceError(
                detail="Only the shipper can complete the order.",
                code="permission_denied",
                status_code=403,
            )

        # Cannot transition back to created
        if new_status == Order.Status.CREATED:
            raise ServiceError(
                detail="Cannot transition back to created status.",
                code="invalid_transition",
                status_code=409,
            )

        # Transition validation
        if new_status == Order.Status.RECEIVED:
            if order.status != Order.Status.CREATED:
                raise ServiceError(
                    detail="Can only transition to received from created status.",
                    code="invalid_transition",
                    status_code=409,
                )
        elif new_status == Order.Status.PICKED_UP:
            if order.status != Order.Status.RECEIVED:
                raise ServiceError(
                    detail="Can only transition to picked_up from received status.",
                    code="invalid_transition",
                    status_code=409,
                )
        elif new_status == Order.Status.DELIVERED:
            if order.status != Order.Status.PICKED_UP:
                raise ServiceError(
                    detail="Can only transition to delivered from picked_up status.",
                    code="invalid_transition",
                    status_code=409,
                )
        elif new_status == Order.Status.AWAITING_CONFIRM:
            if order.status != Order.Status.DELIVERED:
                raise ServiceError(
                    detail="Can only transition to awaiting_confirm from delivered status.",
                    code="invalid_transition",
                    status_code=409,
                )
        elif new_status == Order.Status.COMPLETED:
            if order.status != Order.Status.AWAITING_CONFIRM:
                raise ServiceError(
                    detail="Can only complete order from awaiting_confirm status.",
                    code="invalid_transition",
                    status_code=409,
                )
        elif new_status == Order.Status.CANCELLED:
            if order.status not in (Order.Status.CREATED, Order.Status.RECEIVED):
                raise ServiceError(
                    detail="Can only cancel order from created or received status.",
                    code="invalid_transition",
                    status_code=409,
                )
            cancel_reason = note.strip()
            if not cancel_reason:
                raise ServiceError(
                    detail="Cancellation reason is required.",
                    code="validation_error",
                    status_code=400,
                )
        else:
            raise ServiceError(
                detail=f"Invalid target status '{new_status}'.",
                code="invalid_transition",
                status_code=409,
            )

        # Apply state changes
        if new_status == Order.Status.CANCELLED:
            order.status = Order.Status.CANCELLED
            order.cancel_reason = note.strip()
            order.save(update_fields=["status", "cancel_reason", "updated_at"])

            # Decrement trucks_found (never below 0)
            if load.trucks_found > 0:
                load.trucks_found -= 1
            if load.status == Load.Status.IN_PROGRESS:
                load.status = Load.Status.ACTIVE
            load.save(update_fields=["trucks_found", "status", "updated_at"])

        elif new_status == Order.Status.COMPLETED:
            order.status = Order.Status.COMPLETED
            order.completed_at = timezone.now()
            order.save(update_fields=["status", "completed_at", "updated_at"])

            # Load completes when no unsettled orders remain and count of completed == trucks_needed
            has_unsettled_orders = (
                Order.objects.filter(load=load)
                .exclude(status__in=[Order.Status.COMPLETED, Order.Status.CANCELLED])
                .exists()
            )
            completed_count = (
                Order.objects.filter(load=load, status=Order.Status.COMPLETED).count()
            )
            if not has_unsettled_orders and completed_count == load.trucks_needed:
                load.status = Load.Status.COMPLETED
                load.save(update_fields=["status", "updated_at"])

        else:
            order.status = new_status
            order.save(update_fields=["status", "updated_at"])

        # Write audit event
        OrderStatusEvent.objects.create(
            order=order,
            status=new_status,
            actor=user,
            note=note,
        )

        # Notify the counterparty
        other_party = order.shipper if user.pk == order.carrier_id else order.carrier
        notify(
            user=other_party,
            type=Notification.NotificationType.ORDER_STATUS,
            payload={
                "order_id": order.pk,
                "status": new_status,
            },
        )

        return order


def add_document(
    user: User,
    order_id: int,
    file: Any,
    name: str,
) -> OrderDocument:
    """Attach a document to an order."""
    try:
        order = Order.objects.get(pk=order_id)
    except Order.DoesNotExist:
        raise ServiceError(
            detail="Order not found.",
            code="not_found",
            status_code=404,
        ) from None

    if user.pk != order.carrier_id and user.pk != order.shipper_id:
        raise ServiceError(
            detail="Order not found.",
            code="not_found",
            status_code=404,
        )

    clean_name = (name or "").strip()
    if not clean_name:
        raise ServiceError(
            detail="Document name is required.",
            code="validation_error",
            status_code=400,
        )

    if not file:
        raise ServiceError(
            detail="File is required.",
            code="validation_error",
            status_code=400,
        )

    file_size = getattr(file, "size", 0)
    size_kb = max(1, round(file_size / 1024)) if file_size > 0 else 0

    return OrderDocument.objects.create(
        order=order,
        name=clean_name,
        file=file,
        size_kb=size_kb,
        uploaded_by=user,
    )


def rate_order(
    user: User,
    order_id: int,
    stars: int,
    reasons: list[str] | None = None,
    comment: str = "",
) -> Rating:
    """Submit a rating for a completed order and recompute the ratee's company average."""
    if reasons is None:
        reasons = []

    if stars is None or not isinstance(stars, int) or stars < 1 or stars > 5:
        raise ServiceError(
            detail="Stars must be an integer between 1 and 5.",
            code="validation_error",
            status_code=400,
        )

    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(pk=order_id)
        except Order.DoesNotExist:
            raise ServiceError(
                detail="Order not found.",
                code="not_found",
                status_code=404,
            ) from None

        if user.pk != order.carrier_id and user.pk != order.shipper_id:
            raise ServiceError(
                detail="Order not found.",
                code="not_found",
                status_code=404,
            )

        if order.status != Order.Status.COMPLETED:
            raise ServiceError(
                detail="Can only rate completed orders.",
                code="invalid_status",
                status_code=409,
            )

        if Rating.objects.filter(order=order, rater=user).exists():
            raise ServiceError(
                detail="Order has already been rated by this user.",
                code="already_rated",
                status_code=409,
            )

        ratee = order.shipper if user.pk == order.carrier_id else order.carrier

        rating = Rating.objects.create(
            order=order,
            rater=user,
            ratee=ratee,
            stars=stars,
            reasons=reasons,
            comment=comment or "",
        )

        # Recompute ratee company rating within the same transaction
        try:
            company = Company.objects.select_for_update().get(owner=ratee)
        except Company.DoesNotExist:
            company = None

        if company is not None:
            ratings_qs = Rating.objects.filter(ratee=ratee)
            total_count = ratings_qs.count()
            if total_count > 0:
                total_stars = sum(r.stars for r in ratings_qs)
                avg = Decimal(total_stars) / Decimal(total_count)
                rating_avg = avg.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                rating_avg = Decimal("0.00")

            company.rating_avg = rating_avg
            company.rating_count = total_count
            company.save(update_fields=["rating_avg", "rating_count", "updated_at"])

        return rating
