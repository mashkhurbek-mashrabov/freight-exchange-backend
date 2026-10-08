"""Domain services for loads app."""

import datetime
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import ServiceError
from apps.geo.models import Country, Currency
from apps.loads.distance import route_distance_km
from apps.loads.models import Favorite, Load, PaymentTerms, RoutePoint
from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.offers.models import Offer


def compute_distance_km(points: Iterable[Any]) -> int:
    """Compute total route distance across consecutive points in kilometers.

    Accepts RoutePoint instances, dicts with 'lat' and 'lng', or (lat, lng) sequences.
    """
    coords: list[tuple[float | Decimal, float | Decimal]] = []
    for p in points:
        if isinstance(p, dict):
            coords.append((p["lat"], p["lng"]))
        elif hasattr(p, "lat") and hasattr(p, "lng"):
            coords.append((p.lat, p.lng))
        elif isinstance(p, (list, tuple)) and len(p) >= 2:
            coords.append((p[0], p[1]))
    return route_distance_km(coords)


def _validate_route_points_data(points_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Validate route points structure and sequence rules."""
    if not points_data:
        raise ServiceError(
            "At least one route point is required.",
            code="validation_error",
            status_code=400,
        )

    seqs = [p.get("seq") for p in points_data if p.get("seq") is not None]
    if len(seqs) != len(points_data) or len(set(seqs)) != len(seqs):
        raise ServiceError(
            "Route point sequence numbers must be unique.",
            code="validation_error",
            status_code=400,
        )

    sorted_points = sorted(points_data, key=lambda p: p["seq"])

    first_kind = sorted_points[0].get("kind")
    if first_kind != RoutePoint.Kind.LOADING:
        raise ServiceError(
            "First route point must be loading.",
            code="validation_error",
            status_code=400,
        )

    last_kind = sorted_points[-1].get("kind")
    if last_kind != RoutePoint.Kind.UNLOADING:
        raise ServiceError(
            "Last route point must be unloading.",
            code="validation_error",
            status_code=400,
        )

    return sorted_points


def _validate_load_constraints(
    *,
    weight_t: Any,
    trucks_needed: Any,
    is_adr: bool,
    adr_class: Any,
    temp_controlled: bool,
    temp_min_c: Any,
    temp_max_c: Any,
    price_amount: Any,
    currency: Any,
) -> None:
    """Validate cross-field load constraints."""
    if weight_t is not None and weight_t <= 0:
        raise ServiceError(
            "weight_t must be greater than 0.",
            code="validation_error",
            status_code=400,
        )

    if trucks_needed is not None and trucks_needed < 1:
        raise ServiceError(
            "trucks_needed must be at least 1.",
            code="validation_error",
            status_code=400,
        )

    if is_adr and adr_class is None:
        raise ServiceError(
            "ADR class is required when is_adr is true.",
            code="validation_error",
            status_code=400,
        )

    if temp_controlled:
        if temp_min_c is None or temp_max_c is None:
            raise ServiceError(
                "Both temp_min_c and temp_max_c are required when temp_controlled is true.",
                code="validation_error",
                status_code=400,
            )
        if temp_min_c > temp_max_c:
            raise ServiceError(
                "temp_min_c cannot be greater than temp_max_c.",
                code="validation_error",
                status_code=400,
            )

    if price_amount is not None and price_amount <= 0:
        raise ServiceError(
            "price_amount must be greater than 0.",
            code="validation_error",
            status_code=400,
        )

    if price_amount is not None and not currency:
        raise ServiceError(
            "Currency is required when price_amount is provided.",
            code="validation_error",
            status_code=400,
        )


def _validate_payment_terms_amounts(pt_data: dict[str, Any] | None) -> None:
    """Validate payment terms amounts cannot be negative."""
    if not pt_data:
        return
    for field in ("prepay_amount", "paid_amount", "remaining_amount"):
        val = pt_data.get(field)
        if val is not None and val < 0:
            raise ServiceError(
                f"{field} cannot be negative.",
                code="validation_error",
                status_code=400,
            )


def create_load(user: Any, data: dict[str, Any]) -> Load:
    """Create a new load in draft status with nested route points and payment terms."""
    if getattr(user, "status", None) != "verified":
        raise ServiceError(
            "Account is not verified.",
            code="account_not_verified",
            status_code=403,
        )
    if getattr(user, "role", None) not in ("shipper", "both"):
        raise ServiceError(
            "Role not allowed for this action.",
            code="role_not_allowed",
            status_code=403,
        )

    weight_t = data.get("weight_t")
    if weight_t is None:
        raise ServiceError(
            "weight_t is required.",
            code="validation_error",
            status_code=400,
        )

    trucks_needed = data.get("trucks_needed", 1)
    is_adr = bool(data.get("is_adr", False))
    adr_class = data.get("adr_class") if is_adr else None
    temp_controlled = bool(data.get("temp_controlled", False))
    temp_min_c = data.get("temp_min_c") if temp_controlled else None
    temp_max_c = data.get("temp_max_c") if temp_controlled else None
    price_amount = data.get("price_amount")
    currency = data.get("currency") or data.get("currency_id")
    if isinstance(currency, str):
        currency = Currency.objects.filter(code=currency).first()

    _validate_load_constraints(
        weight_t=weight_t,
        trucks_needed=trucks_needed,
        is_adr=is_adr,
        adr_class=adr_class,
        temp_controlled=temp_controlled,
        temp_min_c=temp_min_c,
        temp_max_c=temp_max_c,
        price_amount=price_amount,
        currency=currency,
    )

    route_points_data = data.get("route_points", [])
    sorted_points = _validate_route_points_data(route_points_data)

    client_distance = data.get("distance_km")
    if client_distance is not None:
        distance_km = client_distance
    else:
        distance_km = compute_distance_km(sorted_points)

    company = getattr(user, "company", None)

    with transaction.atomic():
        load = Load.objects.create(
            shipper=user,
            company=company,
            cargo_description=data.get("cargo_description", ""),
            cargo_type=data.get("cargo_type", ""),
            weight_t=weight_t,
            volume_m3=data.get("volume_m3"),
            length_m=data.get("length_m"),
            packaging=data.get("packaging", ""),
            transport_mode=data.get("transport_mode", Load.TransportMode.FTL),
            vehicle_category=data.get("vehicle_category", ""),
            trucks_needed=trucks_needed,
            trucks_found=0,
            is_adr=is_adr,
            adr_class=adr_class,
            temp_controlled=temp_controlled,
            temp_min_c=temp_min_c,
            temp_max_c=temp_max_c,
            price_amount=price_amount,
            currency=currency,
            vat_included=bool(data.get("vat_included", False)),
            price_negotiable=bool(data.get("price_negotiable", True)),
            distance_km=distance_km,
            status=Load.Status.DRAFT,
            expires_at=data.get("expires_at"),
        )

        body_types = data.get("body_types")
        if body_types is not None:
            load.body_types.set(body_types)

        for pt_data in sorted_points:
            pt_kwargs = dict(pt_data)
            country = pt_kwargs.pop("country", None) or pt_kwargs.pop("country_id", None)
            if isinstance(country, str):
                country = Country.objects.get(code=country)
            RoutePoint.objects.create(
                load=load,
                country=country,
                **pt_kwargs,
            )

        payment_terms_data = data.get("payment_terms")
        if payment_terms_data:
            _validate_payment_terms_amounts(payment_terms_data)
            PaymentTerms.objects.create(
                load=load,
                **payment_terms_data,
            )

    return load


def update_load(load: Load, data: dict[str, Any], user: Any = None) -> Load:
    """Update a load atomically, replacing route points, payment terms, or body types.

    Only the load owner may update, and only when the load is in draft or active status.
    """
    with transaction.atomic():
        locked_load = Load.objects.select_for_update().get(pk=load.pk)

        if user is not None and locked_load.shipper_id != user.id:
            raise ServiceError(
                "You do not have permission to modify this load.",
                code="permission_denied",
                status_code=403,
            )

        if locked_load.status not in (Load.Status.DRAFT, Load.Status.ACTIVE):
            raise ServiceError(
                f"Cannot update load with status '{locked_load.status}'. "
                "Only draft or active loads can be updated.",
                code="invalid_transition",
                status_code=409,
            )

        # Merge new attributes with existing
        weight_t = data.get("weight_t", locked_load.weight_t)
        trucks_needed = data.get("trucks_needed", locked_load.trucks_needed)
        is_adr = data.get("is_adr", locked_load.is_adr)
        adr_class = data.get("adr_class", locked_load.adr_class) if is_adr else None
        temp_controlled = data.get("temp_controlled", locked_load.temp_controlled)
        temp_min_c = data.get("temp_min_c", locked_load.temp_min_c) if temp_controlled else None
        temp_max_c = data.get("temp_max_c", locked_load.temp_max_c) if temp_controlled else None
        price_amount = data.get("price_amount", locked_load.price_amount)

        if "currency" in data:
            currency = data.get("currency")
        elif "currency_id" in data:
            currency = data.get("currency_id")
        else:
            currency = locked_load.currency

        if isinstance(currency, str):
            currency = Currency.objects.filter(code=currency).first()

        _validate_load_constraints(
            weight_t=weight_t,
            trucks_needed=trucks_needed,
            is_adr=is_adr,
            adr_class=adr_class,
            temp_controlled=temp_controlled,
            temp_min_c=temp_min_c,
            temp_max_c=temp_max_c,
            price_amount=price_amount,
            currency=currency,
        )

        # Update scalar fields
        if "cargo_description" in data:
            locked_load.cargo_description = data["cargo_description"]
        if "cargo_type" in data:
            locked_load.cargo_type = data["cargo_type"]
        if "weight_t" in data:
            locked_load.weight_t = weight_t
        if "volume_m3" in data:
            locked_load.volume_m3 = data["volume_m3"]
        if "length_m" in data:
            locked_load.length_m = data["length_m"]
        if "packaging" in data:
            locked_load.packaging = data["packaging"]
        if "transport_mode" in data:
            locked_load.transport_mode = data["transport_mode"]
        if "vehicle_category" in data:
            locked_load.vehicle_category = data["vehicle_category"]
        if "trucks_needed" in data:
            locked_load.trucks_needed = trucks_needed
        if "is_adr" in data:
            locked_load.is_adr = is_adr
            locked_load.adr_class = adr_class
        elif "adr_class" in data and is_adr:
            locked_load.adr_class = adr_class
        if "temp_controlled" in data:
            locked_load.temp_controlled = temp_controlled
            locked_load.temp_min_c = temp_min_c
            locked_load.temp_max_c = temp_max_c
        elif temp_controlled:
            if "temp_min_c" in data:
                locked_load.temp_min_c = temp_min_c
            if "temp_max_c" in data:
                locked_load.temp_max_c = temp_max_c
        if "price_amount" in data:
            locked_load.price_amount = price_amount
        if "currency" in data or "currency_id" in data:
            locked_load.currency = currency
        if "vat_included" in data:
            locked_load.vat_included = bool(data["vat_included"])
        if "price_negotiable" in data:
            locked_load.price_negotiable = bool(data["price_negotiable"])
        if "expires_at" in data:
            locked_load.expires_at = data["expires_at"]

        if "body_types" in data:
            locked_load.body_types.set(data["body_types"])

        if "route_points" in data:
            sorted_points = _validate_route_points_data(data["route_points"])
            locked_load.route_points.all().delete()
            for pt_data in sorted_points:
                pt_kwargs = dict(pt_data)
                country = pt_kwargs.pop("country", None) or pt_kwargs.pop("country_id", None)
                if isinstance(country, str):
                    country = Country.objects.get(code=country)
                RoutePoint.objects.create(
                    load=locked_load,
                    country=country,
                    **pt_kwargs,
                )
            if "distance_km" in data and data["distance_km"] is not None:
                locked_load.distance_km = data["distance_km"]
            else:
                locked_load.distance_km = compute_distance_km(sorted_points)
        elif "distance_km" in data and data["distance_km"] is not None:
            locked_load.distance_km = data["distance_km"]

        if "payment_terms" in data:
            pt_data = data["payment_terms"]
            if pt_data is not None:
                _validate_payment_terms_amounts(pt_data)
                PaymentTerms.objects.update_or_create(
                    load=locked_load,
                    defaults=pt_data,
                )
            else:
                PaymentTerms.objects.filter(load=locked_load).delete()

        locked_load.save()
        return locked_load


def publish_load(load: Load, user: Any = None) -> Load:
    """Transition a draft load to active status.

    Validates route points, sets published_at to now, and defaults expires_at to +7 days.
    """
    with transaction.atomic():
        locked_load = Load.objects.select_for_update().get(pk=load.pk)

        if user is not None and getattr(user, "status", None) != "verified":
            raise ServiceError(
                "Account is not verified.",
                code="account_not_verified",
                status_code=403,
            )

        if user is not None and locked_load.shipper_id != user.id:
            raise ServiceError(
                "You do not have permission to publish this load.",
                code="permission_denied",
                status_code=403,
            )

        if locked_load.status != Load.Status.DRAFT:
            raise ServiceError(
                f"Cannot publish load with status '{locked_load.status}'. "
                "Only draft loads can be published.",
                code="invalid_transition",
                status_code=409,
            )

        route_points = list(locked_load.route_points.order_by("seq"))
        if not route_points:
            raise ServiceError(
                "At least one route point is required.",
                code="validation_error",
                status_code=400,
            )

        first_kind = route_points[0].kind
        last_kind = route_points[-1].kind
        if first_kind != RoutePoint.Kind.LOADING:
            raise ServiceError(
                "First route point must be loading.",
                code="validation_error",
                status_code=400,
            )
        if last_kind != RoutePoint.Kind.UNLOADING:
            raise ServiceError(
                "Last route point must be unloading.",
                code="validation_error",
                status_code=400,
            )

        _validate_load_constraints(
            weight_t=locked_load.weight_t,
            trucks_needed=locked_load.trucks_needed,
            is_adr=locked_load.is_adr,
            adr_class=locked_load.adr_class,
            temp_controlled=locked_load.temp_controlled,
            temp_min_c=locked_load.temp_min_c,
            temp_max_c=locked_load.temp_max_c,
            price_amount=locked_load.price_amount,
            currency=locked_load.currency,
        )

        now = timezone.now()
        locked_load.status = Load.Status.ACTIVE
        locked_load.published_at = now
        if not locked_load.expires_at:
            locked_load.expires_at = now + datetime.timedelta(days=7)

        locked_load.save(update_fields=["status", "published_at", "expires_at", "updated_at"])
        return locked_load


def cancel_load(load: Load, user: Any = None) -> Load:
    """Cancel a draft or active load and automatically reject any pending offers."""
    with transaction.atomic():
        locked_load = Load.objects.select_for_update().get(pk=load.pk)

        if user is not None and locked_load.shipper_id != user.id:
            raise ServiceError(
                "You do not have permission to cancel this load.",
                code="permission_denied",
                status_code=403,
            )

        if locked_load.status not in (Load.Status.DRAFT, Load.Status.ACTIVE):
            raise ServiceError(
                f"Cannot cancel load with status '{locked_load.status}'. "
                "Only draft or active loads can be cancelled.",
                code="invalid_transition",
                status_code=409,
            )

        locked_load.status = Load.Status.CANCELLED
        locked_load.save(update_fields=["status", "updated_at"])

        pending_offers = locked_load.offers.select_for_update().filter(status=Offer.Status.PENDING)
        now = timezone.now()
        for offer in pending_offers:
            offer.status = Offer.Status.REJECTED
            offer.responded_at = now
            offer.save(update_fields=["status", "responded_at", "updated_at"])
            notify(
                offer.carrier,
                Notification.NotificationType.OFFER_REJECTED,
                {
                    "load_id": locked_load.id,
                    "offer_id": offer.id,
                    "reason": "load_cancelled",
                },
            )

        return locked_load


def add_favorite(user: Any, load: Load) -> Favorite:
    """Add load to user favorites idempotently."""
    favorite, _ = Favorite.objects.get_or_create(user=user, load=load)
    return favorite


def remove_favorite(user: Any, load: Load) -> bool:
    """Remove load from user favorites idempotently."""
    deleted_count, _ = Favorite.objects.filter(user=user, load=load).delete()
    return deleted_count > 0
