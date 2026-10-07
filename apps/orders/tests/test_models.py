"""Tests for orders app models and factories."""

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.orders.models import Order, Rating
from apps.orders.tests.factories import (
    OrderDocumentFactory,
    OrderFactory,
    OrderStatusEventFactory,
    RatingFactory,
)


@pytest.mark.django_db
def test_order_defaults_and_str() -> None:
    """Verify Order default attributes and string representation."""
    order = OrderFactory()
    assert order.status == Order.Status.CREATED
    assert order.cancel_reason == ""
    assert order.completed_at is None
    assert str(order) == f"Order #{order.pk}: Load #{order.load_id} (created)"


@pytest.mark.django_db
def test_order_status_event_ordering_and_str() -> None:
    """Verify OrderStatusEvent ordering and string representation."""
    order = OrderFactory()
    event_1 = OrderStatusEventFactory(
        order=order,
        status=Order.Status.CREATED,
        note="Order created",
    )
    event_2 = OrderStatusEventFactory(
        order=order,
        status=Order.Status.RECEIVED,
        note="Carrier received order",
    )

    events = list(order.status_events.all())
    assert events == [event_1, event_2]
    assert str(event_1) == f"Order #{order.pk} -> created at {event_1.at}"


@pytest.mark.django_db
def test_order_document_and_str() -> None:
    """Verify OrderDocument creation and string representation."""
    doc = OrderDocumentFactory(name="bill_of_lading.pdf", size_kb=250)
    assert doc.size_kb == 250
    assert str(doc) == f"bill_of_lading.pdf (Order #{doc.order_id})"
    assert doc in doc.order.documents.all()


@pytest.mark.django_db
def test_rating_validators_and_str() -> None:
    """Verify Rating stars validation, reasons ArrayField, and str."""
    order = OrderFactory(status=Order.Status.COMPLETED)

    # Stars below minimum
    invalid_rating_low = Rating(
        order=order,
        rater=order.carrier,
        ratee=order.shipper,
        stars=0,
        reasons=["polite"],
    )
    with pytest.raises(ValidationError) as exc_info:
        invalid_rating_low.full_clean()
    assert "stars" in exc_info.value.message_dict

    # Stars above maximum
    invalid_rating_high = Rating(
        order=order,
        rater=order.carrier,
        ratee=order.shipper,
        stars=6,
        reasons=["polite"],
    )
    with pytest.raises(ValidationError) as exc_info:
        invalid_rating_high.full_clean()
    assert "stars" in exc_info.value.message_dict

    # Valid rating with ArrayField reasons
    valid_rating = RatingFactory(
        order=order,
        rater=order.carrier,
        ratee=order.shipper,
        stars=5,
        reasons=["fast_loading", "punctual"],
        comment="Smooth shipment",
    )
    assert valid_rating.reasons == ["fast_loading", "punctual"]
    assert str(valid_rating) == (
        f"Rating 5* by User #{order.carrier_id} on Order #{order.pk}"
    )


@pytest.mark.django_db
def test_rating_unique_constraint_per_order_rater() -> None:
    """Verify rater cannot submit more than one rating per order."""
    rating = RatingFactory()
    with pytest.raises(IntegrityError):
        Rating.objects.create(
            order=rating.order,
            rater=rating.rater,
            ratee=rating.ratee,
            stars=4,
            reasons=[],
        )
