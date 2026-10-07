"""Factory definitions for orders app."""

from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from apps.offers.models import Offer
from apps.offers.tests.factories import OfferFactory
from apps.orders.models import Order, OrderDocument, OrderStatusEvent, Rating


class OrderFactory(DjangoModelFactory):
    """Factory for Order model."""

    class Meta:
        model = Order

    offer = factory.SubFactory(OfferFactory, status=Offer.Status.ACCEPTED)
    load = factory.LazyAttribute(lambda o: o.offer.load)
    shipper = factory.LazyAttribute(lambda o: o.load.shipper)
    carrier = factory.LazyAttribute(lambda o: o.offer.carrier)
    vehicle = factory.LazyAttribute(lambda o: o.offer.vehicle)
    trailer = factory.LazyAttribute(lambda o: o.offer.trailer)
    agreed_amount = factory.LazyAttribute(lambda o: o.offer.amount or Decimal("2400.00"))
    currency = factory.LazyAttribute(lambda o: o.offer.currency or o.load.currency)
    status = Order.Status.CREATED
    cancel_reason = ""
    completed_at = None


class OrderStatusEventFactory(DjangoModelFactory):
    """Factory for OrderStatusEvent model."""

    class Meta:
        model = OrderStatusEvent

    order = factory.SubFactory(OrderFactory)
    status = factory.LazyAttribute(lambda o: o.order.status)
    actor = factory.LazyAttribute(lambda o: o.order.carrier)
    note = "Status transition event"


class OrderDocumentFactory(DjangoModelFactory):
    """Factory for OrderDocument model."""

    class Meta:
        model = OrderDocument

    order = factory.SubFactory(OrderFactory)
    name = factory.Sequence(lambda n: f"Document_{n}.pdf")
    file = "orders/documents/sample.pdf"
    size_kb = 120
    uploaded_by = factory.LazyAttribute(lambda o: o.order.carrier)


class RatingFactory(DjangoModelFactory):
    """Factory for Rating model."""

    class Meta:
        model = Rating

    order = factory.SubFactory(OrderFactory, status=Order.Status.COMPLETED)
    rater = factory.LazyAttribute(lambda o: o.order.carrier)
    ratee = factory.LazyAttribute(lambda o: o.order.shipper)
    stars = 5
    reasons = factory.LazyFunction(lambda: ["fast_payment", "polite"])
    comment = "Great cooperation"
