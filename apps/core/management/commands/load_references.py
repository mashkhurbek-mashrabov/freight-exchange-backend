"""Management command to load reference data idempotently."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils.dateparse import parse_datetime

from apps.garage.models import VehicleType
from apps.geo.models import Country, Currency, ExchangeRate
from apps.geo.services import invalidate_all_geo_caches


class Command(BaseCommand):
    """Load reference data fixtures idempotently into the database."""

    help = "Load countries, currencies, exchange rates, and vehicle types idempotently."

    def add_arguments(self, parser: CommandParser) -> None:
        """Add command arguments."""
        parser.add_argument(
            "--force",
            action="store_true",
            help="Update fields of existing rows from fixtures (update_or_create).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        """Execute reference loading inside atomic transaction."""
        force: bool = bool(options.get("force", False))
        verbosity: int = int(options.get("verbosity", 1))

        geo_fixtures = Path(apps.get_app_config("geo").path) / "fixtures"
        garage_fixtures = Path(apps.get_app_config("garage").path) / "fixtures"

        countries_file = geo_fixtures / "countries.json"
        currencies_file = geo_fixtures / "currencies.json"
        exchange_rates_file = geo_fixtures / "exchange_rates.json"
        vehicle_types_file = garage_fixtures / "vehicle_types.json"

        for file_path in (countries_file, currencies_file, exchange_rates_file, vehicle_types_file):
            if not file_path.is_file():
                raise CommandError(f"Fixture file not found: {file_path}")

        with transaction.atomic():
            stats: dict[str, dict[str, int]] = {
                "Country": self._load_countries(countries_file, force=force),
                "Currency": self._load_currencies(currencies_file, force=force),
                "VehicleType": self._load_vehicle_types(vehicle_types_file, force=force),
                "ExchangeRate": self._load_exchange_rates(exchange_rates_file, force=force),
            }

        invalidate_all_geo_caches()

        if verbosity > 0:
            for model_name, counts in stats.items():
                self.stdout.write(
                    f"{model_name}: {counts['created']} created, {counts['existing']} existing"
                )

    def _load_countries(self, file_path: Path, *, force: bool) -> dict[str, int]:
        """Load Country fixtures by pk."""
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        created_count = 0
        existing_count = 0

        for item in data:
            pk = item["pk"]
            fields = item.get("fields", {})
            defaults = {
                "name_i18n": fields.get("name_i18n", {}),
                "flag_url": fields.get("flag_url", ""),
            }
            if force:
                _, created = Country.objects.update_or_create(code=pk, defaults=defaults)
            else:
                _, created = Country.objects.get_or_create(code=pk, defaults=defaults)

            if created:
                created_count += 1
            else:
                existing_count += 1

        return {"created": created_count, "existing": existing_count}

    def _load_currencies(self, file_path: Path, *, force: bool) -> dict[str, int]:
        """Load Currency fixtures by pk."""
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        created_count = 0
        existing_count = 0

        for item in data:
            pk = item["pk"]
            fields = item.get("fields", {})
            defaults = {
                "name": fields.get("name", pk),
            }
            if force:
                _, created = Currency.objects.update_or_create(code=pk, defaults=defaults)
            else:
                _, created = Currency.objects.get_or_create(code=pk, defaults=defaults)

            if created:
                created_count += 1
            else:
                existing_count += 1

        return {"created": created_count, "existing": existing_count}

    def _load_vehicle_types(self, file_path: Path, *, force: bool) -> dict[str, int]:
        """Load VehicleType fixtures by code (ignoring fixture pk)."""
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        created_count = 0
        existing_count = 0

        for item in data:
            fields = item.get("fields", {})
            code = fields["code"]
            defaults = {
                "name_i18n": fields.get("name_i18n", {}),
                "image_url": fields.get("image_url", ""),
                "kind": fields["kind"],
            }
            if force:
                _, created = VehicleType.objects.update_or_create(code=code, defaults=defaults)
            else:
                _, created = VehicleType.objects.get_or_create(code=code, defaults=defaults)

            if created:
                created_count += 1
            else:
                existing_count += 1

        return {"created": created_count, "existing": existing_count}

    def _load_exchange_rates(self, file_path: Path, *, force: bool) -> dict[str, int]:
        """Load ExchangeRate fixtures by (base, quote, fetched_at)."""
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)

        created_count = 0
        existing_count = 0

        for item in data:
            fields = item.get("fields", {})
            base_code = fields["base"]
            quote_code = fields["quote"]
            raw_fetched_at = fields["fetched_at"]
            fetched_at = parse_datetime(raw_fetched_at)
            if fetched_at is None:
                raise CommandError(f"Invalid fetched_at datetime: {raw_fetched_at}")

            rate = Decimal(str(fields["rate"]))
            lookup = {
                "base_id": base_code,
                "quote_id": quote_code,
                "fetched_at": fetched_at,
            }
            defaults = {"rate": rate}

            if force:
                _, created = ExchangeRate.objects.update_or_create(**lookup, defaults=defaults)
            else:
                _, created = ExchangeRate.objects.get_or_create(**lookup, defaults=defaults)

            if created:
                created_count += 1
            else:
                existing_count += 1

        return {"created": created_count, "existing": existing_count}
