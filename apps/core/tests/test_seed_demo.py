"""Tests for seed_demo management command."""

import io

import pytest
from django.core.management import call_command
from django.db.models import Count

from apps.accounts.models import Company, User
from apps.garage.models import Vehicle, VehicleKind
from apps.loads.models import Load, LoadDocument, PaymentTerms, RoutePoint
from apps.offers.models import Offer
from apps.orders.models import Order, OrderStatusEvent, Rating


@pytest.mark.django_db
def test_seed_demo_command_execution_and_idempotency() -> None:
    """Test seed_demo command populates complete demo data and is strictly idempotent."""
    out = io.StringIO()
    call_command("seed_demo", stdout=out)
    output = out.getvalue()

    # Verify summary and dev login hint printed
    assert "Entity" in output
    assert "Count" in output
    assert "phone +998900000001 code 000000 (dev)" in output

    # 1. Users verification
    verified_users = User.objects.filter(status=User.Status.VERIFIED)
    assert verified_users.count() == 2

    carrier = User.objects.get(phone="+998900000001")
    assert carrier.full_name == "Demo Carrier"
    assert carrier.role == User.Role.CARRIER
    assert carrier.status == User.Status.VERIFIED
    assert carrier.language == User.Language.RU
    assert hasattr(carrier, "company")
    assert carrier.company.name == "Demo Carrier LLC"
    assert carrier.company.tin == "998000001"

    shipper = User.objects.get(phone="+998900000002")
    assert shipper.full_name == "Demo Shipper"
    assert shipper.role == User.Role.SHIPPER
    assert shipper.status == User.Status.VERIFIED
    assert shipper.language == User.Language.RU
    assert hasattr(shipper, "company")
    assert shipper.company.name == "Demo Shipper LLC"
    assert shipper.company.tin == "998000002"

    # 2. Garage verification
    tractor = Vehicle.objects.get(plate_number="01A123BC")
    trailer = Vehicle.objects.get(plate_number="01T456BC")
    assert tractor.owner == carrier
    assert trailer.owner == carrier
    assert tractor.kind == VehicleKind.TRACTOR
    assert trailer.kind == VehicleKind.TRAILER
    assert trailer.vehicle_type.code == "tent"
    assert tractor.is_active is True
    assert trailer.is_active is True
    assert tractor.paired_vehicle == trailer
    assert trailer.paired_vehicle == tractor

    # 3. Loads verification
    loads_qs = Load.objects.filter(shipper=shipper)
    total_loads = loads_qs.count()
    assert total_loads >= 30

    active_loads = loads_qs.filter(status=Load.Status.ACTIVE)
    assert active_loads.count() > 0

    draft_loads = loads_qs.filter(status=Load.Status.DRAFT)
    assert draft_loads.count() >= 3

    # Check 5-point route with border and customs
    load_5pt = (
        Load.objects.annotate(point_count=Count("route_points")).filter(point_count=5).first()
    )
    assert load_5pt is not None
    point_kinds = set(load_5pt.route_points.values_list("kind", flat=True))
    assert RoutePoint.Kind.LOADING in point_kinds
    assert RoutePoint.Kind.BORDER in point_kinds
    assert RoutePoint.Kind.CUSTOMS in point_kinds
    assert RoutePoint.Kind.TRANSIT in point_kinds
    assert RoutePoint.Kind.UNLOADING in point_kinds

    # Check distance calculation
    for load in loads_qs:
        assert load.distance_km is not None
        assert load.distance_km > 0

    # Check documents
    assert LoadDocument.objects.count() >= 1

    # Check currencies variation
    currencies = set(
        loads_qs.exclude(currency__isnull=True).values_list("currency__code", flat=True)
    )
    assert {"USD", "EUR", "RUB", "UZS"}.issubset(currencies)

    # Check ADR and temp-controlled loads
    assert loads_qs.filter(is_adr=True, adr_class__isnull=False).exists()
    assert loads_qs.filter(temp_controlled=True, temp_min_c__isnull=False).exists()

    # Check price negotiable False and no price
    assert loads_qs.filter(price_negotiable=False).exists()
    assert loads_qs.filter(price_amount__isnull=True, currency__isnull=True).exists()

    # 4. Offers verification
    carrier_offers = Offer.objects.filter(carrier=carrier)
    assert carrier_offers.filter(status=Offer.Status.PENDING, parent__isnull=True).exists()
    assert carrier_offers.filter(status=Offer.Status.REJECTED).exists()
    assert carrier_offers.filter(status=Offer.Status.COUNTERED).exists()
    # Countered chain has child pending offer
    assert Offer.objects.filter(parent__isnull=False, status=Offer.Status.PENDING).exists()

    # 5. Orders verification (one per status)
    for expected_status in Order.Status.values:
        matching_orders = Order.objects.filter(status=expected_status)
        assert matching_orders.count() == 1, (
            f"Expected exactly 1 order with status '{expected_status}'"
        )

    # Orders load status consistency
    in_progress_statuses = [
        Order.Status.CREATED,
        Order.Status.RECEIVED,
        Order.Status.PICKED_UP,
        Order.Status.DELIVERED,
        Order.Status.AWAITING_CONFIRM,
    ]
    for st in in_progress_statuses:
        order = Order.objects.get(status=st)
        assert order.load.status == Load.Status.IN_PROGRESS

    completed_order = Order.objects.get(status=Order.Status.COMPLETED)
    assert completed_order.load.status == Load.Status.COMPLETED

    cancelled_order = Order.objects.get(status=Order.Status.CANCELLED)
    assert cancelled_order.load.status == Load.Status.ACTIVE

    # 6. Ratings verification
    assert Rating.objects.count() >= 1
    carrier_company = Company.objects.get(owner=carrier)
    shipper_company = Company.objects.get(owner=shipper)
    assert carrier_company.rating_count >= 1
    assert carrier_company.rating_avg > 0
    assert shipper_company.rating_count >= 1
    assert shipper_company.rating_avg > 0

    # 7. Idempotency test (running seed_demo a second time)
    counts_before: dict[str, int] = {
        "users": User.objects.count(),
        "companies": Company.objects.count(),
        "vehicles": Vehicle.objects.count(),
        "loads": Load.objects.count(),
        "route_points": RoutePoint.objects.count(),
        "payment_terms": PaymentTerms.objects.count(),
        "load_documents": LoadDocument.objects.count(),
        "offers": Offer.objects.count(),
        "orders": Order.objects.count(),
        "order_events": OrderStatusEvent.objects.count(),
        "ratings": Rating.objects.count(),
    }

    out2 = io.StringIO()
    call_command("seed_demo", stdout=out2)

    counts_after: dict[str, int] = {
        "users": User.objects.count(),
        "companies": Company.objects.count(),
        "vehicles": Vehicle.objects.count(),
        "loads": Load.objects.count(),
        "route_points": RoutePoint.objects.count(),
        "payment_terms": PaymentTerms.objects.count(),
        "load_documents": LoadDocument.objects.count(),
        "offers": Offer.objects.count(),
        "orders": Order.objects.count(),
        "order_events": OrderStatusEvent.objects.count(),
        "ratings": Rating.objects.count(),
    }

    assert counts_before == counts_after
