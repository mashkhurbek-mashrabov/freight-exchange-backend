"""Seed demo database command with realistic data."""

import datetime
from decimal import Decimal
from typing import Any

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Company, User
from apps.garage.models import Vehicle, VehicleKind, VehicleType
from apps.geo.models import ExchangeRate
from apps.loads.models import Load, LoadDocument, RoutePoint
from apps.loads.services import create_load, publish_load
from apps.offers.models import Offer
from apps.offers.services import accept_offer, counter_offer, create_offer, reject_offer
from apps.orders.models import Order, Rating
from apps.orders.services import change_status, rate_order


class Command(BaseCommand):
    """Seed demo fixtures, carrier, shipper, garage, loads, offers, and orders."""

    help = "Seed demo database idempotently with test carrier, shipper, loads, and orders."

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        """Execute seeding workflow inside an atomic transaction."""
        self.seed_fixtures()
        carrier, shipper = self.seed_users()
        tractor, trailer = self.seed_garage(carrier)
        loads = self.seed_loads(shipper)
        self.seed_negotiations(carrier, shipper, tractor, trailer, loads)
        self.print_summary()

    def seed_fixtures(self) -> None:
        """Load initial geo and garage fixtures idempotently."""
        if ExchangeRate.objects.exists():
            call_command("loaddata", "countries", "currencies", "vehicle_types", verbosity=0)
        else:
            call_command(
                "loaddata",
                "countries",
                "currencies",
                "exchange_rates",
                "vehicle_types",
                verbosity=0,
            )

    def seed_users(self) -> tuple[User, User]:
        """Create or update verified demo carrier and shipper with companies."""
        carrier, _ = User.objects.get_or_create(
            phone="+998900000001",
            defaults={
                "full_name": "Demo Carrier",
                "role": User.Role.CARRIER,
                "status": User.Status.VERIFIED,
                "language": User.Language.RU,
                "is_active": True,
            },
        )
        carrier.full_name = "Demo Carrier"
        carrier.role = User.Role.CARRIER
        carrier.status = User.Status.VERIFIED
        carrier.language = User.Language.RU
        carrier.is_active = True
        carrier.save()

        Company.objects.update_or_create(
            owner=carrier,
            defaults={
                "name": "Demo Carrier LLC",
                "tin": "998000001",
                "address": "Tashkent, Chilanzar district, 12",
            },
        )

        shipper, _ = User.objects.get_or_create(
            phone="+998900000002",
            defaults={
                "full_name": "Demo Shipper",
                "role": User.Role.SHIPPER,
                "status": User.Status.VERIFIED,
                "language": User.Language.RU,
                "is_active": True,
            },
        )
        shipper.full_name = "Demo Shipper"
        shipper.role = User.Role.SHIPPER
        shipper.status = User.Status.VERIFIED
        shipper.language = User.Language.RU
        shipper.is_active = True
        shipper.save()

        Company.objects.update_or_create(
            owner=shipper,
            defaults={
                "name": "Demo Shipper LLC",
                "tin": "998000002",
                "address": "Tashkent, Mirabad district, 45",
            },
        )

        return carrier, shipper

    def seed_garage(self, carrier: User) -> tuple[Vehicle, Vehicle]:
        """Create or update carrier tractor and trailer paired with each other."""
        tractor_type = VehicleType.objects.filter(kind=VehicleKind.TRACTOR).first()
        trailer_type = VehicleType.objects.get(code="tent")

        tractor, _ = Vehicle.objects.get_or_create(
            plate_number="01A123BC",
            defaults={
                "owner": carrier,
                "kind": VehicleKind.TRACTOR,
                "vehicle_type": tractor_type,
                "brand": "Volvo FH 500",
                "tech_passport_no": "AA1234567",
                "owner_full_name": carrier.full_name,
                "is_active": True,
            },
        )
        tractor.owner = carrier
        tractor.kind = VehicleKind.TRACTOR
        tractor.vehicle_type = tractor_type
        tractor.is_active = True
        tractor.save()

        trailer, _ = Vehicle.objects.get_or_create(
            plate_number="01T456BC",
            defaults={
                "owner": carrier,
                "kind": VehicleKind.TRAILER,
                "vehicle_type": trailer_type,
                "brand": "Krone Profi Liner",
                "tech_passport_no": "BB7654321",
                "owner_full_name": carrier.full_name,
                "is_active": True,
            },
        )
        trailer.owner = carrier
        trailer.kind = VehicleKind.TRAILER
        trailer.vehicle_type = trailer_type
        trailer.is_active = True
        trailer.save()

        if tractor.paired_vehicle_id != trailer.pk:
            tractor.paired_vehicle = trailer
            tractor.save(update_fields=["paired_vehicle"])

        if trailer.paired_vehicle_id != tractor.pk:
            trailer.paired_vehicle = tractor
            trailer.save(update_fields=["paired_vehicle"])

        return tractor, trailer

    def seed_loads(self, shipper: User) -> dict[int, Load]:
        """Create ~30 loads with varied routes, statuses, and options."""
        now = timezone.now()
        tent = VehicleType.objects.get(code="tent")
        reefer = VehicleType.objects.get(code="reefer")
        container = VehicleType.objects.get(code="container")
        board = VehicleType.objects.get(code="board")

        load_configs = self._get_load_configs(tent, reefer, container, board)
        loads: dict[int, Load] = {}

        for idx, cfg in enumerate(load_configs, start=1):
            marker = f"[demo] {idx:02d}:"
            existing = Load.objects.filter(cargo_description__startswith=marker).first()
            if existing:
                loads[idx] = existing
                continue

            load_data = dict(cfg["data"])
            load_data["cargo_description"] = f"{marker} {load_data['cargo_description']}"

            load = create_load(shipper, load_data)

            docs = cfg.get("documents", [])
            for doc_name in docs:
                LoadDocument.objects.create(load=load, name=doc_name, file=None)

            if cfg.get("is_active", True):
                publish_load(load, user=shipper)
                day_offset = (idx * 0.35) % 9.5
                load.published_at = now - datetime.timedelta(days=day_offset)
                load.expires_at = now + datetime.timedelta(days=7)
                load.save(update_fields=["published_at", "expires_at"])

            loads[idx] = load

        return loads

    def _get_load_configs(
        self,
        tent: VehicleType,
        reefer: VehicleType,
        container: VehicleType,
        board: VehicleType,
    ) -> list[dict[str, Any]]:
        """Return specification configs for all 32 seed loads."""
        return [
            # 1: Dedicated for Offer 1 (pending)
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Textile fabrics and yarn on pallets",
                    "cargo_type": "Textiles",
                    "weight_t": Decimal("19.500"),
                    "volume_m3": Decimal("82.000"),
                    "length_m": Decimal("13.60"),
                    "packaging": "Pallets",
                    "transport_mode": "FTL",
                    "vehicle_category": "Standard",
                    "trucks_needed": 1,
                    "is_adr": False,
                    "price_amount": Decimal("2500.00"),
                    "currency": "USD",
                    "price_negotiable": True,
                    "body_types": [tent.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Tashkent, Chilanzar district",
                            "lat": Decimal("41.299500"),
                            "lng": Decimal("69.240100"),
                            "asap": True,
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "KZ",
                            "address": "Almaty, Turksib district",
                            "lat": Decimal("43.222000"),
                            "lng": Decimal("76.851200"),
                        },
                    ],
                    "payment_terms": {
                        "prepay_amount": Decimal("500.00"),
                        "prepay_method": "transfer",
                        "remaining_amount": Decimal("2000.00"),
                        "payment_due_days": 5,
                        "conditions": "Payment upon CMR confirmation",
                    },
                },
                "documents": ["CMR Waybill", "Commercial Invoice"],
            },
            # 2: Dedicated for Offer 2 (rejected)
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Cotton yarn and raw fabric rolls",
                    "cargo_type": "Textiles",
                    "weight_t": Decimal("20.000"),
                    "volume_m3": Decimal("86.000"),
                    "packaging": "Rolls",
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "price_amount": Decimal("4200.00"),
                    "currency": "USD",
                    "price_negotiable": True,
                    "body_types": [tent.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Tashkent, Sergeli Industrial Zone",
                            "lat": Decimal("41.218500"),
                            "lng": Decimal("69.223500"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "RU",
                            "address": "Moscow, South Port Warehouse",
                            "lat": Decimal("55.701200"),
                            "lng": Decimal("37.689000"),
                        },
                    ],
                    "payment_terms": {
                        "payment_due_days": 7,
                        "conditions": "100% bank transfer after unloading",
                    },
                },
            },
            # 3: Dedicated for Offer 3 (countered chain)
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Ceramic tiles and bathroom fixtures",
                    "cargo_type": "Building materials",
                    "weight_t": Decimal("21.500"),
                    "volume_m3": Decimal("75.000"),
                    "packaging": "Pallets",
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "price_amount": Decimal("3200.00"),
                    "currency": "USD",
                    "price_negotiable": True,
                    "body_types": [tent.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Samarkand, Industrial Area",
                            "lat": Decimal("39.654200"),
                            "lng": Decimal("66.959700"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "KG",
                            "address": "Bishkek, Chuy Avenue Terminal",
                            "lat": Decimal("42.874600"),
                            "lng": Decimal("74.569800"),
                        },
                    ],
                    "payment_terms": {
                        "prepay_amount": Decimal("800.00"),
                        "prepay_method": "transfer",
                        "remaining_amount": Decimal("2400.00"),
                        "payment_due_days": 3,
                    },
                },
            },
            # 4: Dedicated for Order 1 (created)
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Agricultural equipment spare parts",
                    "cargo_type": "Machinery",
                    "weight_t": Decimal("14.000"),
                    "volume_m3": Decimal("60.000"),
                    "packaging": "Crates",
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "price_amount": Decimal("2100.00"),
                    "currency": "USD",
                    "price_negotiable": True,
                    "body_types": [tent.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Bukhara, Kagan Road",
                            "lat": Decimal("39.768100"),
                            "lng": Decimal("64.455600"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "KZ",
                            "address": "Shymkent, Logistics Park",
                            "lat": Decimal("42.341700"),
                            "lng": Decimal("69.590100"),
                        },
                    ],
                },
                "documents": ["Packing List"],
            },
            # 5: Dedicated for Order 2 (received)
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Plastics and PVC granules in big bags",
                    "cargo_type": "Chemicals",
                    "weight_t": Decimal("20.500"),
                    "volume_m3": Decimal("80.000"),
                    "packaging": "Big bags",
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "price_amount": Decimal("3800.00"),
                    "currency": "USD",
                    "price_negotiable": True,
                    "body_types": [tent.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Tashkent, Yangihayot district",
                            "lat": Decimal("41.225000"),
                            "lng": Decimal("69.210000"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "RU",
                            "address": "Kazan, Khimgrad Technopark",
                            "lat": Decimal("55.796100"),
                            "lng": Decimal("49.106400"),
                        },
                    ],
                },
            },
            # 6: Dedicated for Order 3 (picked_up)
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Processed dried fruits and nuts",
                    "cargo_type": "Foodstuffs",
                    "weight_t": Decimal("18.000"),
                    "volume_m3": Decimal("72.000"),
                    "packaging": "Boxes",
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "price_amount": Decimal("2800.00"),
                    "currency": "USD",
                    "price_negotiable": True,
                    "body_types": [tent.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Samarkand, Pastdargom district",
                            "lat": Decimal("39.630000"),
                            "lng": Decimal("66.850000"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "KZ",
                            "address": "Astana, Transport hub",
                            "lat": Decimal("51.169400"),
                            "lng": Decimal("71.449100"),
                        },
                    ],
                },
            },
            # 7: Dedicated for Order 4 (delivered)
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Automotive cable harnesses and wires",
                    "cargo_type": "Automotive",
                    "weight_t": Decimal("16.000"),
                    "volume_m3": Decimal("68.000"),
                    "packaging": "Crates",
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "price_amount": Decimal("3900.00"),
                    "currency": "USD",
                    "price_negotiable": True,
                    "body_types": [tent.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Tashkent, Bektemir district",
                            "lat": Decimal("41.240000"),
                            "lng": Decimal("69.340000"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "RU",
                            "address": "Yekaterinburg, Koltsovo Logistics Hub",
                            "lat": Decimal("56.838900"),
                            "lng": Decimal("60.605700"),
                        },
                    ],
                },
            },
            # 8: Dedicated for Order 5 (awaiting_confirm)
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Metal pipes and fittings",
                    "cargo_type": "Metal products",
                    "weight_t": Decimal("22.000"),
                    "volume_m3": Decimal("65.000"),
                    "packaging": "Bundles",
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "price_amount": Decimal("4100.00"),
                    "currency": "USD",
                    "price_negotiable": True,
                    "body_types": [tent.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Fergana, Kirguli district",
                            "lat": Decimal("40.384200"),
                            "lng": Decimal("71.784300"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "RU",
                            "address": "Novosibirsk, Kleshchikha Cargo Station",
                            "lat": Decimal("55.008400"),
                            "lng": Decimal("82.935700"),
                        },
                    ],
                },
            },
            # 9: Dedicated for Order 6 (completed, rated)
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Textile home products and bedding sets",
                    "cargo_type": "Consumer goods",
                    "weight_t": Decimal("15.000"),
                    "volume_m3": Decimal("80.000"),
                    "packaging": "Cartons",
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "price_amount": Decimal("1900.00"),
                    "currency": "USD",
                    "price_negotiable": True,
                    "body_types": [tent.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Tashkent, Uchtepa district",
                            "lat": Decimal("41.285000"),
                            "lng": Decimal("69.175000"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "TJ",
                            "address": "Dushanbe, Somoni Cargo Terminal",
                            "lat": Decimal("38.559800"),
                            "lng": Decimal("68.787000"),
                        },
                    ],
                    "payment_terms": {
                        "prepay_amount": Decimal("500.00"),
                        "prepay_method": "transfer",
                        "remaining_amount": Decimal("1400.00"),
                        "payment_due_days": 3,
                    },
                },
                "documents": ["CMR Consignment Note", "Invoice", "Packing List"],
            },
            # 10: Dedicated for Order 7 (cancelled, active load again)
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Beverages and mineral water in shrink packs",
                    "cargo_type": "Beverages",
                    "weight_t": Decimal("19.000"),
                    "volume_m3": Decimal("60.000"),
                    "packaging": "Shrink pack",
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "price_amount": Decimal("1200.00"),
                    "currency": "USD",
                    "price_negotiable": True,
                    "body_types": [tent.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Andijan, Industrial park",
                            "lat": Decimal("40.782100"),
                            "lng": Decimal("72.344200"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "KG",
                            "address": "Osh, Kurmanjan Datka street",
                            "lat": Decimal("40.514000"),
                            "lng": Decimal("72.816100"),
                        },
                    ],
                },
            },
            # 11: 5-point route (loading, border, customs, transit, unloading)
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Silk fabrics and artisanal carpets for Moscow boutiques",
                    "cargo_type": "Luxury textiles",
                    "weight_t": Decimal("18.500"),
                    "volume_m3": Decimal("85.000"),
                    "packaging": "Special wooden crates",
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "price_amount": Decimal("4500.00"),
                    "currency": "USD",
                    "price_negotiable": True,
                    "body_types": [tent.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Tashkent Central Cargo Depot",
                            "lat": Decimal("41.299500"),
                            "lng": Decimal("69.240100"),
                            "asap": True,
                            "ready_to_load": True,
                            "comment": "Main terminal gate 4",
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.BORDER,
                            "country": "UZ",
                            "address": "Gisht-Kuprik Border Checkpoint",
                            "lat": Decimal("41.468300"),
                            "lng": Decimal("69.378900"),
                            "comment": "UZ/KZ border crossing point",
                        },
                        {
                            "seq": 3,
                            "kind": RoutePoint.Kind.CUSTOMS,
                            "country": "KZ",
                            "address": "Shymkent Customs Clearance Post",
                            "lat": Decimal("42.341700"),
                            "lng": Decimal("69.590100"),
                            "comment": "Customs inspection & transit seals",
                        },
                        {
                            "seq": 4,
                            "kind": RoutePoint.Kind.TRANSIT,
                            "country": "RU",
                            "address": "Samara Transit Logistics Hub",
                            "lat": Decimal("53.241500"),
                            "lng": Decimal("50.221200"),
                            "comment": "Intermediate driver rest and refuel",
                        },
                        {
                            "seq": 5,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "RU",
                            "address": "Moscow North Distribution Center",
                            "lat": Decimal("55.755800"),
                            "lng": Decimal("37.617300"),
                            "comment": "Final boutique warehouse unloading",
                        },
                    ],
                    "payment_terms": {
                        "prepay_amount": Decimal("1500.00"),
                        "prepay_method": "transfer",
                        "remaining_amount": Decimal("3000.00"),
                        "payment_due_days": 5,
                        "conditions": "30% advance, balance upon final customs release in Moscow",
                    },
                },
                "documents": [
                    "International CMR",
                    "Customs Transit Declaration T1",
                    "Origin Certificate ST-1",
                ],
            },
            # 12: Tashkent -> Baku -> Istanbul (3 points, EUR)
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Copper cathode sheets and raw wire",
                    "cargo_type": "Metals",
                    "weight_t": Decimal("22.000"),
                    "volume_m3": Decimal("45.000"),
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "price_amount": Decimal("5800.00"),
                    "currency": "EUR",
                    "price_negotiable": True,
                    "body_types": [tent.pk, board.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Tashkent, Almalyk Mining Hub",
                            "lat": Decimal("40.850000"),
                            "lng": Decimal("69.600000"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.STOP,
                            "country": "AZ",
                            "address": "Baku International Sea Port",
                            "lat": Decimal("40.409300"),
                            "lng": Decimal("49.867100"),
                        },
                        {
                            "seq": 3,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "TR",
                            "address": "Istanbul, Tuzla Industrial Zone",
                            "lat": Decimal("41.008200"),
                            "lng": Decimal("28.978400"),
                        },
                    ],
                    "payment_terms": {
                        "payment_due_days": 10,
                        "conditions": "SWIFT transfer against B/L and CMR",
                    },
                },
            },
            # 13: Samarkand -> Osh -> Urumqi (3 points, USD)
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Natural licorice extract and herbs",
                    "cargo_type": "Pharmaceutical raw materials",
                    "weight_t": Decimal("18.000"),
                    "volume_m3": Decimal("70.000"),
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "price_amount": Decimal("3600.00"),
                    "currency": "USD",
                    "price_negotiable": True,
                    "body_types": [container.pk, tent.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Samarkand, Airport cargo zone",
                            "lat": Decimal("39.700000"),
                            "lng": Decimal("66.980000"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.STOP,
                            "country": "KG",
                            "address": "Osh Transit Logistics Terminal",
                            "lat": Decimal("40.514000"),
                            "lng": Decimal("72.816100"),
                        },
                        {
                            "seq": 3,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "CN",
                            "address": "Urumqi Comprehensive Bonded Zone",
                            "lat": Decimal("43.825600"),
                            "lng": Decimal("87.616800"),
                        },
                    ],
                },
            },
            # 14: Bukhara -> Baku (2 points, USD)
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Petrochemical polymer pellets",
                    "cargo_type": "Petrochemicals",
                    "weight_t": Decimal("20.000"),
                    "volume_m3": Decimal("80.000"),
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "price_amount": Decimal("3100.00"),
                    "currency": "USD",
                    "price_negotiable": True,
                    "body_types": [tent.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Bukhara Refinery Depot",
                            "lat": Decimal("39.768100"),
                            "lng": Decimal("64.455600"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "AZ",
                            "address": "Baku Alat Port Logistics Terminal",
                            "lat": Decimal("40.409300"),
                            "lng": Decimal("49.867100"),
                        },
                    ],
                },
            },
            # 15: Temp controlled (reefer, frozen fruits, -20 to -18)
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Frozen IQF cherries and strawberries",
                    "cargo_type": "Frozen Food",
                    "weight_t": Decimal("18.000"),
                    "volume_m3": Decimal("80.000"),
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "temp_controlled": True,
                    "temp_min_c": Decimal("-20.00"),
                    "temp_max_c": Decimal("-18.00"),
                    "price_amount": Decimal("4900.00"),
                    "currency": "USD",
                    "price_negotiable": True,
                    "body_types": [reefer.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Tashkent, Agro Freez Cold Storage",
                            "lat": Decimal("41.250000"),
                            "lng": Decimal("69.300000"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "RU",
                            "address": "Moscow, Food City Cold Terminal",
                            "lat": Decimal("55.600000"),
                            "lng": Decimal("37.450000"),
                        },
                    ],
                    "payment_terms": {
                        "payment_due_days": 3,
                        "conditions": "Temperature logger verification required before payment",
                    },
                },
                "documents": ["Veterinary Certificate", "Phytosanitary Certificate"],
            },
            # 16: Temp controlled (reefer, fresh grapes, +2 to +6)
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Fresh premium grapes and peaches",
                    "cargo_type": "Fresh Fruit",
                    "weight_t": Decimal("19.000"),
                    "volume_m3": Decimal("82.000"),
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "temp_controlled": True,
                    "temp_min_c": Decimal("2.00"),
                    "temp_max_c": Decimal("6.00"),
                    "price_amount": Decimal("5200.00"),
                    "currency": "USD",
                    "price_negotiable": True,
                    "body_types": [reefer.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Fergana Valley Fruit Distribution Hub",
                            "lat": Decimal("40.384200"),
                            "lng": Decimal("71.784300"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "RU",
                            "address": "Saint Petersburg, Shushary Agro Hub",
                            "lat": Decimal("59.810000"),
                            "lng": Decimal("30.380000"),
                        },
                    ],
                },
            },
            # 17: ADR hazardous (flammable liquids, class 3)
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Industrial solvents and paints",
                    "cargo_type": "Hazardous materials",
                    "weight_t": Decimal("17.000"),
                    "volume_m3": Decimal("65.000"),
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "is_adr": True,
                    "adr_class": 3,
                    "price_amount": Decimal("3400.00"),
                    "currency": "USD",
                    "price_negotiable": True,
                    "body_types": [tent.pk, container.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Navoi Free Industrial Zone",
                            "lat": Decimal("40.084400"),
                            "lng": Decimal("65.379200"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "KZ",
                            "address": "Almaty, Zhetysu Chemical Depot",
                            "lat": Decimal("43.222000"),
                            "lng": Decimal("76.851200"),
                        },
                    ],
                    "payment_terms": {
                        "prepay_amount": Decimal("1000.00"),
                        "prepay_method": "transfer",
                        "remaining_amount": Decimal("2400.00"),
                        "payment_due_days": 5,
                    },
                },
                "documents": ["ADR Safety Data Sheet", "Multimodal Dangerous Goods Form"],
            },
            # 18: ADR hazardous (corrosive substances, class 8)
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Battery acid and technical caustic soda",
                    "cargo_type": "Hazardous materials",
                    "weight_t": Decimal("19.500"),
                    "volume_m3": Decimal("60.000"),
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "is_adr": True,
                    "adr_class": 8,
                    "price_amount": Decimal("4700.00"),
                    "currency": "USD",
                    "price_negotiable": True,
                    "body_types": [tent.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Tashkent, Chirchik Chemical Complex",
                            "lat": Decimal("41.468000"),
                            "lng": Decimal("69.582000"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "RU",
                            "address": "Moscow, Podolsk Chemical Depot",
                            "lat": Decimal("55.431200"),
                            "lng": Decimal("37.545600"),
                        },
                    ],
                },
            },
            # 19: Domestic Uzbekistan, UZS currency
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Construction cement and dry mortar mixtures",
                    "cargo_type": "Building materials",
                    "weight_t": Decimal("22.000"),
                    "volume_m3": Decimal("50.000"),
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "price_amount": Decimal("15000000.00"),
                    "currency": "UZS",
                    "vat_included": True,
                    "price_negotiable": True,
                    "body_types": [tent.pk, board.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Tashkent, Bekabad Cement Plant",
                            "lat": Decimal("40.216700"),
                            "lng": Decimal("69.216700"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "UZ",
                            "address": "Samarkand, New City Construction Site",
                            "lat": Decimal("39.654200"),
                            "lng": Decimal("66.959700"),
                        },
                    ],
                    "payment_terms": {
                        "conditions": "100% cashless transfer with VAT upon delivery",
                    },
                },
            },
            # 20: Domestic Uzbekistan, UZS currency
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Refined sunflower oil in 5L bottles",
                    "cargo_type": "Foodstuffs",
                    "weight_t": Decimal("20.000"),
                    "volume_m3": Decimal("75.000"),
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "price_amount": Decimal("22000000.00"),
                    "currency": "UZS",
                    "vat_included": True,
                    "price_negotiable": True,
                    "body_types": [tent.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Tashkent, Chorsu Wholesale Depot",
                            "lat": Decimal("41.325000"),
                            "lng": Decimal("69.235000"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "UZ",
                            "address": "Bukhara, Central Supermarket Distribution",
                            "lat": Decimal("39.768100"),
                            "lng": Decimal("64.455600"),
                        },
                    ],
                },
            },
            # 21: RUB currency
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Household plastic goods and kitchenware",
                    "cargo_type": "Consumer goods",
                    "weight_t": Decimal("12.500"),
                    "volume_m3": Decimal("90.000"),
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "price_amount": Decimal("350000.00"),
                    "currency": "RUB",
                    "price_negotiable": True,
                    "body_types": [tent.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Tashkent, Artel Industrial Cluster",
                            "lat": Decimal("41.270000"),
                            "lng": Decimal("69.190000"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "RU",
                            "address": "Moscow, Domodedovo Logistics Hub",
                            "lat": Decimal("55.440000"),
                            "lng": Decimal("37.750000"),
                        },
                    ],
                },
                "documents": ["Quality Certificate"],
            },
            # 22: RUB currency
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Confectionery and dried halva in branded boxes",
                    "cargo_type": "Foodstuffs",
                    "weight_t": Decimal("16.000"),
                    "volume_m3": Decimal("78.000"),
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "price_amount": Decimal("310000.00"),
                    "currency": "RUB",
                    "price_negotiable": True,
                    "body_types": [tent.pk, reefer.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Samarkand, Confectionery Factory",
                            "lat": Decimal("39.654200"),
                            "lng": Decimal("66.959700"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "RU",
                            "address": "Kazan, Vakhitovsky Food Base",
                            "lat": Decimal("55.796100"),
                            "lng": Decimal("49.106400"),
                        },
                    ],
                },
            },
            # 23: EUR currency
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Handmade silk tapestries and embroideries",
                    "cargo_type": "Handicrafts",
                    "weight_t": Decimal("8.000"),
                    "volume_m3": Decimal("45.000"),
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "price_amount": Decimal("4200.00"),
                    "currency": "EUR",
                    "price_negotiable": True,
                    "body_types": [tent.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Tashkent, Old City Craft Center",
                            "lat": Decimal("41.330000"),
                            "lng": Decimal("69.240000"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "TR",
                            "address": "Istanbul, Laleli Commercial Hub",
                            "lat": Decimal("41.008200"),
                            "lng": Decimal("28.978400"),
                        },
                    ],
                },
            },
            # 24: No price specified (open for carrier bids)
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Furniture sets in flat cardboard packaging",
                    "cargo_type": "Furniture",
                    "weight_t": Decimal("15.500"),
                    "volume_m3": Decimal("85.000"),
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "price_amount": None,
                    "currency": None,
                    "price_negotiable": True,
                    "body_types": [tent.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Tashkent, Juma Bazaar Industrial Zone",
                            "lat": Decimal("41.299500"),
                            "lng": Decimal("69.240100"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "KG",
                            "address": "Bishkek, Dordoi Wholesale Market",
                            "lat": Decimal("42.874600"),
                            "lng": Decimal("74.569800"),
                        },
                    ],
                },
            },
            # 25: Fixed price, price_negotiable = False
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Automotive lead-acid starter batteries",
                    "cargo_type": "Automotive",
                    "weight_t": Decimal("21.000"),
                    "volume_m3": Decimal("55.000"),
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "price_amount": Decimal("2000.00"),
                    "currency": "USD",
                    "price_negotiable": False,
                    "body_types": [tent.pk, board.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Tashkent, Dzhizak Battery Plant Depot",
                            "lat": Decimal("40.115800"),
                            "lng": Decimal("67.842200"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "KZ",
                            "address": "Almaty, Rayimbek Avenue Depot",
                            "lat": Decimal("43.222000"),
                            "lng": Decimal("76.851200"),
                        },
                    ],
                },
            },
            # 26: LTL transport mode (part load)
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Footwear sample boxes and accessories",
                    "cargo_type": "Consumer goods",
                    "weight_t": Decimal("3.500"),
                    "volume_m3": Decimal("15.000"),
                    "transport_mode": "LTL",
                    "trucks_needed": 1,
                    "price_amount": Decimal("800.00"),
                    "currency": "USD",
                    "price_negotiable": True,
                    "body_types": [tent.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Namangan, Shoes Industrial Cluster",
                            "lat": Decimal("40.998300"),
                            "lng": Decimal("71.672600"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "TJ",
                            "address": "Dushanbe, Korvon Market",
                            "lat": Decimal("38.559800"),
                            "lng": Decimal("68.787000"),
                        },
                    ],
                },
            },
            # 27: trucks_needed = 2
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Bulk ceramic building tiles and sanitary porcelain",
                    "cargo_type": "Building materials",
                    "weight_t": Decimal("22.000"),
                    "volume_m3": Decimal("75.000"),
                    "transport_mode": "FTL",
                    "trucks_needed": 2,
                    "price_amount": Decimal("2800.00"),
                    "currency": "USD",
                    "price_negotiable": True,
                    "body_types": [tent.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Tashkent, Ceramic Production Line",
                            "lat": Decimal("41.299500"),
                            "lng": Decimal("69.240100"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "TM",
                            "address": "Ashgabat, Bitarap Avenue Warehouse",
                            "lat": Decimal("37.960100"),
                            "lng": Decimal("58.326100"),
                        },
                    ],
                },
            },
            # 28: trucks_needed = 3
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Refined white sugar in 50kg bags",
                    "cargo_type": "Foodstuffs",
                    "weight_t": Decimal("22.500"),
                    "volume_m3": Decimal("70.000"),
                    "transport_mode": "FTL",
                    "trucks_needed": 3,
                    "price_amount": Decimal("3300.00"),
                    "currency": "USD",
                    "price_negotiable": True,
                    "body_types": [tent.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Samarkand, Sugar Factory Rail Terminal",
                            "lat": Decimal("39.654200"),
                            "lng": Decimal("66.959700"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "TM",
                            "address": "Turkmenbashi, Seaport Free Zone",
                            "lat": Decimal("40.023100"),
                            "lng": Decimal("52.969700"),
                        },
                    ],
                },
            },
            # 29: Bukhara -> Khujand (2 points, USD)
            {
                "is_active": True,
                "data": {
                    "cargo_description": "Raw gypsum and building chalk in bags",
                    "cargo_type": "Minerals",
                    "weight_t": Decimal("21.000"),
                    "volume_m3": Decimal("60.000"),
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "price_amount": Decimal("1600.00"),
                    "currency": "USD",
                    "price_negotiable": True,
                    "body_types": [tent.pk, board.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Bukhara, Gypsum Quarry Facility",
                            "lat": Decimal("39.768100"),
                            "lng": Decimal("64.455600"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "TJ",
                            "address": "Khujand, Lenin Street Warehouse",
                            "lat": Decimal("40.282600"),
                            "lng": Decimal("69.622200"),
                        },
                    ],
                },
            },
            # 30: Draft load 1 (not published)
            {
                "is_active": False,
                "data": {
                    "cargo_description": "Commercial glass bottles in shrink wrapped pallets",
                    "cargo_type": "Glassware",
                    "weight_t": Decimal("17.000"),
                    "volume_m3": Decimal("75.000"),
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "price_amount": Decimal("2300.00"),
                    "currency": "USD",
                    "price_negotiable": True,
                    "body_types": [tent.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Tashkent, Glass Factory Depot",
                            "lat": Decimal("41.299500"),
                            "lng": Decimal("69.240100"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "KZ",
                            "address": "Almaty, Beverages Bottling Hub",
                            "lat": Decimal("43.222000"),
                            "lng": Decimal("76.851200"),
                        },
                    ],
                },
            },
            # 31: Draft load 2 (not published)
            {
                "is_active": False,
                "data": {
                    "cargo_description": "Packaging cardboard and corrugated boxes",
                    "cargo_type": "Packaging",
                    "weight_t": Decimal("11.000"),
                    "volume_m3": Decimal("92.000"),
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "price_amount": Decimal("4100.00"),
                    "currency": "USD",
                    "price_negotiable": True,
                    "body_types": [tent.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Samarkand, Cardboard Factory",
                            "lat": Decimal("39.654200"),
                            "lng": Decimal("66.959700"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "RU",
                            "address": "Moscow, Packaging Logistics Point",
                            "lat": Decimal("55.755800"),
                            "lng": Decimal("37.617300"),
                        },
                    ],
                },
            },
            # 32: Draft load 3 (not published)
            {
                "is_active": False,
                "data": {
                    "cargo_description": "Agricultural seed bags for spring planting",
                    "cargo_type": "Agriculture",
                    "weight_t": Decimal("15.000"),
                    "volume_m3": Decimal("65.000"),
                    "transport_mode": "FTL",
                    "trucks_needed": 1,
                    "price_amount": Decimal("1100.00"),
                    "currency": "USD",
                    "price_negotiable": True,
                    "body_types": [tent.pk],
                    "route_points": [
                        {
                            "seq": 1,
                            "kind": RoutePoint.Kind.LOADING,
                            "country": "UZ",
                            "address": "Fergana, Regional Seed Selection Depot",
                            "lat": Decimal("40.384200"),
                            "lng": Decimal("71.784300"),
                        },
                        {
                            "seq": 2,
                            "kind": RoutePoint.Kind.UNLOADING,
                            "country": "KG",
                            "address": "Bishkek, Agricultural Exchange",
                            "lat": Decimal("42.874600"),
                            "lng": Decimal("74.569800"),
                        },
                    ],
                },
            },
        ]

    def seed_negotiations(
        self,
        carrier: User,
        shipper: User,
        tractor: Vehicle,
        trailer: Vehicle,
        loads: dict[int, Load],
    ) -> None:
        """Seed offers, counter-offer chains, and all 7 order lifecycle states."""
        # Offer 1 on Load 1: PENDING
        load_1 = loads[1]
        if not Offer.objects.filter(load=load_1, carrier=carrier).exists():
            create_offer(
                carrier,
                load_1,
                {
                    "amount": Decimal("2400.00"),
                    "currency": "USD",
                    "comment": "Ready for loading tomorrow morning.",
                    "vehicle": tractor.pk,
                    "trailer": trailer.pk,
                },
            )

        # Offer 2 on Load 2: REJECTED
        load_2 = loads[2]
        if not Offer.objects.filter(load=load_2, carrier=carrier).exists():
            offer_2 = create_offer(
                carrier,
                load_2,
                {
                    "amount": Decimal("4000.00"),
                    "currency": "USD",
                    "comment": "Can take this route immediately.",
                    "vehicle": tractor.pk,
                    "trailer": trailer.pk,
                },
            )
            reject_offer(shipper, offer_2.pk)

        # Offer 3 on Load 3: COUNTERED -> child PENDING
        load_3 = loads[3]
        if not Offer.objects.filter(load=load_3, carrier=carrier).exists():
            offer_3 = create_offer(
                carrier,
                load_3,
                {
                    "amount": Decimal("3500.00"),
                    "currency": "USD",
                    "comment": "Initial carrier proposal with guaranteed transit time.",
                    "vehicle": tractor.pk,
                    "trailer": trailer.pk,
                },
            )
            counter_offer(
                shipper,
                offer_3.pk,
                {
                    "amount": Decimal("3100.00"),
                    "currency": "USD",
                    "comment": "We can offer 3100 USD max for this shipment.",
                },
            )

        # Order 1 on Load 4: CREATED
        load_4 = loads[4]
        if not Order.objects.filter(load=load_4).exists():
            off_4 = create_offer(
                carrier,
                load_4,
                {
                    "amount": Decimal("2100.00"),
                    "currency": "USD",
                    "comment": "Standard offer",
                    "vehicle": tractor.pk,
                    "trailer": trailer.pk,
                },
            )
            accept_offer(shipper, off_4.pk)

        # Order 2 on Load 5: RECEIVED
        load_5 = loads[5]
        if not Order.objects.filter(load=load_5).exists():
            off_5 = create_offer(
                carrier,
                load_5,
                {
                    "amount": Decimal("3800.00"),
                    "currency": "USD",
                    "comment": "Standard offer",
                    "vehicle": tractor.pk,
                    "trailer": trailer.pk,
                },
            )
            accept_offer(shipper, off_5.pk)
            ord_5 = Order.objects.get(load=load_5)
            change_status(
                carrier,
                ord_5.pk,
                Order.Status.RECEIVED,
                note="Vehicle arrived at loading warehouse",
            )

        # Order 3 on Load 6: PICKED_UP
        load_6 = loads[6]
        if not Order.objects.filter(load=load_6).exists():
            off_6 = create_offer(
                carrier,
                load_6,
                {
                    "amount": Decimal("2800.00"),
                    "currency": "USD",
                    "comment": "Standard offer",
                    "vehicle": tractor.pk,
                    "trailer": trailer.pk,
                },
            )
            accept_offer(shipper, off_6.pk)
            ord_6 = Order.objects.get(load=load_6)
            change_status(
                carrier,
                ord_6.pk,
                Order.Status.RECEIVED,
                note="Vehicle arrived at pickup location",
            )
            change_status(
                carrier,
                ord_6.pk,
                Order.Status.PICKED_UP,
                note="Cargo loaded, inspected, and strapped",
            )

        # Order 4 on Load 7: DELIVERED
        load_7 = loads[7]
        if not Order.objects.filter(load=load_7).exists():
            off_7 = create_offer(
                carrier,
                load_7,
                {
                    "amount": Decimal("3900.00"),
                    "currency": "USD",
                    "comment": "Standard offer",
                    "vehicle": tractor.pk,
                    "trailer": trailer.pk,
                },
            )
            accept_offer(shipper, off_7.pk)
            ord_7 = Order.objects.get(load=load_7)
            change_status(
                carrier,
                ord_7.pk,
                Order.Status.RECEIVED,
                note="Vehicle arrived at pickup point",
            )
            change_status(
                carrier,
                ord_7.pk,
                Order.Status.PICKED_UP,
                note="Cargo loaded and sealed",
            )
            change_status(
                carrier,
                ord_7.pk,
                Order.Status.DELIVERED,
                note="Cargo arrived at destination warehouse and unloaded",
            )

        # Order 5 on Load 8: AWAITING_CONFIRM
        load_8 = loads[8]
        if not Order.objects.filter(load=load_8).exists():
            off_8 = create_offer(
                carrier,
                load_8,
                {
                    "amount": Decimal("4100.00"),
                    "currency": "USD",
                    "comment": "Standard offer",
                    "vehicle": tractor.pk,
                    "trailer": trailer.pk,
                },
            )
            accept_offer(shipper, off_8.pk)
            ord_8 = Order.objects.get(load=load_8)
            change_status(
                carrier,
                ord_8.pk,
                Order.Status.RECEIVED,
                note="Vehicle arrived at pickup warehouse",
            )
            change_status(
                carrier,
                ord_8.pk,
                Order.Status.PICKED_UP,
                note="Cargo loaded into trailer",
            )
            change_status(
                carrier,
                ord_8.pk,
                Order.Status.DELIVERED,
                note="Cargo delivered to receiver",
            )
            change_status(
                carrier,
                ord_8.pk,
                Order.Status.AWAITING_CONFIRM,
                note="Driver uploaded signed CMR copy, awaiting shipper confirmation",
            )

        # Order 6 on Load 9: COMPLETED (rated by carrier and shipper)
        load_9 = loads[9]
        if not Order.objects.filter(load=load_9).exists():
            off_9 = create_offer(
                carrier,
                load_9,
                {
                    "amount": Decimal("1900.00"),
                    "currency": "USD",
                    "comment": "Standard offer",
                    "vehicle": tractor.pk,
                    "trailer": trailer.pk,
                },
            )
            accept_offer(shipper, off_9.pk)
            ord_9 = Order.objects.get(load=load_9)
            change_status(
                carrier,
                ord_9.pk,
                Order.Status.RECEIVED,
                note="Vehicle arrived at pickup point",
            )
            change_status(
                carrier,
                ord_9.pk,
                Order.Status.PICKED_UP,
                note="Cargo picked up",
            )
            change_status(
                carrier,
                ord_9.pk,
                Order.Status.DELIVERED,
                note="Cargo delivered to destination",
            )
            change_status(
                carrier,
                ord_9.pk,
                Order.Status.AWAITING_CONFIRM,
                note="Signed delivery note provided",
            )
            change_status(
                shipper,
                ord_9.pk,
                Order.Status.COMPLETED,
                note="Confirmed delivery, payment released to carrier",
            )
            rate_order(
                carrier,
                ord_9.pk,
                stars=5,
                reasons=["punctual_payment", "accurate_cargo"],
                comment="Great shipper to work with, fast unloading.",
            )
            rate_order(
                shipper,
                ord_9.pk,
                stars=5,
                reasons=["on_time", "clean_trailer"],
                comment="Reliable carrier, fast delivery without cargo damage.",
            )

        # Order 7 on Load 10: CANCELLED (load restored to ACTIVE)
        load_10 = loads[10]
        if not Order.objects.filter(load=load_10).exists():
            off_10 = create_offer(
                carrier,
                load_10,
                {
                    "amount": Decimal("1200.00"),
                    "currency": "USD",
                    "comment": "Standard offer",
                    "vehicle": tractor.pk,
                    "trailer": trailer.pk,
                },
            )
            accept_offer(shipper, off_10.pk)
            ord_10 = Order.objects.get(load=load_10)
            change_status(
                shipper,
                ord_10.pk,
                Order.Status.CANCELLED,
                note="Shipper cancelled: client cancelled shipment request",
            )

    def print_summary(self) -> None:
        """Print counts summary table and developer login hint."""
        summary_rows = [
            ("Users", User.objects.count()),
            ("Companies", Company.objects.count()),
            ("Vehicles", Vehicle.objects.count()),
            ("Loads", Load.objects.count()),
            ("Offers", Offer.objects.count()),
            ("Orders", Order.objects.count()),
            ("Ratings", Rating.objects.count()),
        ]

        self.stdout.write("----------------------------------------")
        self.stdout.write(f"{'Entity':<24}{'Count':>16}")
        self.stdout.write("----------------------------------------")
        for entity, count in summary_rows:
            self.stdout.write(f"{entity:<24}{count:>16}")
        self.stdout.write("----------------------------------------")
        self.stdout.write("phone +998900000001 code 000000 (dev)")
