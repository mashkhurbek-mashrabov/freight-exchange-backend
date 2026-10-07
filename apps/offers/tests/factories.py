"""Factory definitions for offers app."""

from decimal import Decimal

import factory
from factory.django import DjangoModelFactory

from apps.accounts.tests.factories import CarrierUserFactory
from apps.loads.tests.factories import LoadFactory
from apps.offers.models import Offer


class OfferFactory(DjangoModelFactory):
    """Factory for Offer model."""

    class Meta:
        model = Offer

    load = factory.SubFactory(LoadFactory)
    carrier = factory.SubFactory(CarrierUserFactory)
    proposer = factory.LazyAttribute(lambda o: o.carrier)
    recipient = factory.LazyAttribute(lambda o: o.load.shipper)
    vehicle = None
    trailer = None
    parent = None
    mode = Offer.Mode.PRICE_BID
    amount = Decimal("2400.00")
    currency = factory.LazyAttribute(lambda o: o.load.currency)
    comment = "Ready to transport immediately"
    status = Offer.Status.PENDING
    responded_at = None
