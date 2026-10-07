"""Unit tests for loads Celery tasks."""

import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import CarrierUserFactory, ShipperUserFactory
from apps.geo.models import Country
from apps.loads.models import Load, RoutePoint
from apps.loads.services import create_load, publish_load
from apps.loads.tasks import expire_loads
from apps.notifications.models import Notification
from apps.offers.models import Offer
from apps.offers.tests.factories import OfferFactory


@pytest.fixture
def countries(db: None) -> tuple[Country, Country]:
    uz, _ = Country.objects.get_or_create(
        code="UZ",
        defaults={"name_i18n": {"en": "Uzbekistan", "ru": "Узбекистан"}},
    )
    ru, _ = Country.objects.get_or_create(
        code="RU",
        defaults={"name_i18n": {"en": "Russia", "ru": "Россия"}},
    )
    return uz, ru


@pytest.mark.django_db
def test_expire_loads_updates_status_and_rejects_pending_offers(
    countries: tuple[Country, Country],
) -> None:
    shipper = ShipperUserFactory()
    carrier = CarrierUserFactory()

    data = {
        "cargo_description": "Expiring load",
        "weight_t": Decimal("15.000"),
        "route_points": [
            {
                "seq": 1,
                "kind": RoutePoint.Kind.LOADING,
                "country": "UZ",
                "lat": Decimal("41.0"),
                "lng": Decimal("69.0"),
            },
            {
                "seq": 2,
                "kind": RoutePoint.Kind.UNLOADING,
                "country": "RU",
                "lat": Decimal("55.0"),
                "lng": Decimal("37.0"),
            },
        ],
    }

    # Load 1: Expired active load
    load_expiring = create_load(shipper, data)
    publish_load(load_expiring, user=shipper)
    load_expiring.expires_at = timezone.now() - datetime.timedelta(hours=2)
    load_expiring.save(update_fields=["expires_at"])

    # Load 2: Non-expired active load
    load_future = create_load(shipper, data)
    publish_load(load_future, user=shipper)
    load_future.expires_at = timezone.now() + datetime.timedelta(days=3)
    load_future.save(update_fields=["expires_at"])

    # Load 3: Draft load with past expiry
    load_draft = create_load(shipper, data)
    load_draft.expires_at = timezone.now() - datetime.timedelta(hours=2)
    load_draft.save(update_fields=["expires_at"])

    # Offer on expiring load (pending)
    pending_offer = OfferFactory(
        load=load_expiring,
        carrier=carrier,
        proposer=carrier,
        recipient=shipper,
        status=Offer.Status.PENDING,
    )

    # Offer on expiring load (already accepted)
    accepted_offer = OfferFactory(
        load=load_expiring,
        carrier=CarrierUserFactory(),
        proposer=carrier,
        recipient=shipper,
        status=Offer.Status.ACCEPTED,
    )

    # Run expire_loads
    expired_count = expire_loads()
    assert expired_count == 1

    load_expiring.refresh_from_db()
    assert load_expiring.status == Load.Status.EXPIRED

    load_future.refresh_from_db()
    assert load_future.status == Load.Status.ACTIVE

    load_draft.refresh_from_db()
    assert load_draft.status == Load.Status.DRAFT

    pending_offer.refresh_from_db()
    assert pending_offer.status == Offer.Status.REJECTED
    assert pending_offer.responded_at is not None

    accepted_offer.refresh_from_db()
    assert accepted_offer.status == Offer.Status.ACCEPTED

    notif = Notification.objects.filter(
        user=carrier,
        type=Notification.NotificationType.OFFER_REJECTED,
    ).first()
    assert notif is not None
    assert notif.payload.get("reason") == "load_expired"

    # Idempotent re-run
    second_count = expire_loads()
    assert second_count == 0
