"""Tests for offers app models and factories."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.accounts.tests.factories import CarrierUserFactory, ShipperUserFactory
from apps.loads.tests.factories import LoadFactory
from apps.offers.models import Offer
from apps.offers.tests.factories import OfferFactory


@pytest.mark.django_db
def test_offer_defaults_and_str() -> None:
    """Verify Offer default values and string representation."""
    offer = OfferFactory()
    assert offer.status == Offer.Status.PENDING
    assert offer.mode == Offer.Mode.PRICE_BID
    assert offer.amount == Decimal("2400.00")
    assert str(offer) == f"Offer #{offer.pk}: Load #{offer.load_id} (pending)"


@pytest.mark.django_db
def test_offer_proposer_cannot_be_recipient() -> None:
    """Verify proposer and recipient cannot be the same user."""
    carrier = CarrierUserFactory()
    load = LoadFactory()

    # Model clean validation
    invalid_offer = Offer(
        load=load,
        carrier=carrier,
        proposer=carrier,
        recipient=carrier,
        mode=Offer.Mode.PRICE_BID,
        amount=Decimal("1500.00"),
    )
    with pytest.raises(ValidationError) as exc_info:
        invalid_offer.full_clean()
    assert "recipient" in exc_info.value.message_dict

    # Database check constraint
    with pytest.raises(IntegrityError):
        Offer.objects.create(
            load=load,
            carrier=carrier,
            proposer=carrier,
            recipient=carrier,
            mode=Offer.Mode.PRICE_BID,
            amount=Decimal("1500.00"),
        )


@pytest.mark.django_db
def test_offer_price_bid_requires_amount() -> None:
    """Verify price_bid mode requires non-null amount."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    load = LoadFactory(shipper=shipper)

    # Model clean validation
    bid_without_amount = Offer(
        load=load,
        carrier=carrier,
        proposer=carrier,
        recipient=shipper,
        mode=Offer.Mode.PRICE_BID,
        amount=None,
    )
    with pytest.raises(ValidationError) as exc_info:
        bid_without_amount.full_clean()
    assert "amount" in exc_info.value.message_dict

    # Database check constraint
    with pytest.raises(IntegrityError):
        Offer.objects.create(
            load=load,
            carrier=carrier,
            proposer=carrier,
            recipient=shipper,
            mode=Offer.Mode.PRICE_BID,
            amount=None,
        )


@pytest.mark.django_db
def test_offer_comment_only_mode_allows_null_amount() -> None:
    """Verify comment_only mode does not require amount."""
    carrier = CarrierUserFactory()
    shipper = ShipperUserFactory()
    load = LoadFactory(shipper=shipper)

    comment_offer = Offer(
        load=load,
        carrier=carrier,
        proposer=carrier,
        recipient=shipper,
        mode=Offer.Mode.COMMENT_ONLY,
        amount=None,
        comment="Can pickup tomorrow morning",
    )
    comment_offer.full_clean()
    comment_offer.save()

    assert comment_offer.pk is not None
    assert comment_offer.amount is None


@pytest.mark.django_db
def test_unique_pending_offer_per_carrier_load() -> None:
    """Verify only one pending offer per carrier per load is allowed."""
    carrier = CarrierUserFactory()
    load = LoadFactory()

    OfferFactory(load=load, carrier=carrier, status=Offer.Status.PENDING)

    # Second pending offer from same carrier for same load violates unique constraint
    with pytest.raises(IntegrityError):
        OfferFactory(load=load, carrier=carrier, status=Offer.Status.PENDING)


@pytest.mark.django_db
def test_multiple_non_pending_offers_per_carrier_load_allowed() -> None:
    """Verify multiple offers allowed once previous is no longer pending."""
    carrier = CarrierUserFactory()
    load = LoadFactory()

    old_offer = OfferFactory(load=load, carrier=carrier, status=Offer.Status.COUNTERED)
    new_offer = OfferFactory(
        load=load,
        carrier=carrier,
        parent=old_offer,
        status=Offer.Status.PENDING,
    )

    assert old_offer.pk is not None
    assert new_offer.pk is not None
    assert new_offer.parent == old_offer
    assert list(old_offer.counters.all()) == [new_offer]
