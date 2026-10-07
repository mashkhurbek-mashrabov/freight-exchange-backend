"""Test data builder helpers for loads read side tests."""

from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.accounts.models import Company, User
from apps.accounts.tests.factories import CarrierUserFactory, CompanyFactory, ShipperUserFactory
from apps.garage.models import Vehicle, VehicleKind, VehicleType
from apps.garage.tests.factories import VehicleFactory, VehicleTypeFactory
from apps.geo.models import Country, Currency
from apps.geo.tests.factories import CountryFactory, CurrencyFactory
from apps.loads.models import Favorite, Load, RoutePoint
from apps.loads.tests.factories import LoadFactory, RoutePointFactory
from apps.offers.models import Offer
from apps.offers.tests.factories import OfferFactory


def get_or_create_country(code: str, name_en: str = "") -> Country:
    """Return existing or new Country by code."""
    country = Country.objects.filter(code=code.upper()).first()
    if country:
        return country
    return CountryFactory(
        code=code.upper(),
        name_i18n={"en": name_en or code.upper(), "ru": name_en or code.upper()},
    )


def get_or_create_currency(code: str = "USD", name: str = "US Dollar") -> Currency:
    """Return existing or new Currency by code."""
    curr = Currency.objects.filter(code=code.upper()).first()
    if curr:
        return curr
    return CurrencyFactory(code=code.upper(), name=name)


def create_carrier_with_vehicle(
    vehicle_type: VehicleType | None = None,
    is_active: bool = True,
    **user_kwargs: Any,
) -> tuple[User, Vehicle]:
    """Create a carrier user with a vehicle of given type."""
    carrier = CarrierUserFactory(**user_kwargs)
    if vehicle_type is None:
        vehicle_type = VehicleTypeFactory(kind=VehicleKind.TRAILER)
    vehicle = VehicleFactory(
        owner=carrier,
        kind=vehicle_type.kind,
        vehicle_type=vehicle_type,
        is_active=is_active,
    )
    return carrier, vehicle


def create_shipper_with_company(
    company_name: str = "FastTrans LLC",
    **user_kwargs: Any,
) -> tuple[User, Company]:
    """Create a shipper user with an associated company."""
    shipper = ShipperUserFactory(**user_kwargs)
    company = CompanyFactory(owner=shipper, name=company_name)
    return shipper, company


def create_test_load(
    shipper: User | None = None,
    status: str = Load.Status.ACTIVE,
    origin_country: str = "UZ",
    origin_address: str = "Tashkent, Uzbekistan",
    origin_lat: Decimal = Decimal("41.299496"),
    origin_lng: Decimal = Decimal("69.240073"),
    origin_planned_from: Any = None,
    destination_country: str = "RU",
    destination_address: str = "Moscow, Russia",
    destination_lat: Decimal = Decimal("55.755826"),
    destination_lng: Decimal = Decimal("37.617300"),
    destination_planned_from: Any = None,
    body_types: list[VehicleType] | None = None,
    price_amount: Decimal | None = Decimal("2500.00"),
    currency_code: str = "USD",
    distance_km: int | None = 1000,
    weight_t: Decimal = Decimal("20.000"),
    volume_m3: Decimal | None = Decimal("86.000"),
    published_at: Any = None,
    expires_at: Any = None,
    is_adr: bool = False,
    adr_class: int | None = None,
    temp_controlled: bool = False,
    temp_min_c: Decimal | None = None,
    temp_max_c: Decimal | None = None,
    transport_mode: str = Load.TransportMode.FTL,
    cargo_description: str = "Electronics pallets",
    price_negotiable: bool = True,
    trucks_needed: int = 1,
    trucks_found: int = 0,
    company: Company | None = None,
) -> Load:
    """Create a fully assembled load with loading (seq 1) and unloading (seq 2) points."""
    if shipper is None:
        shipper = ShipperUserFactory()

    currency = get_or_create_currency(currency_code)
    now = timezone.now()
    if published_at is None and status == Load.Status.ACTIVE:
        published_at = now

    load_kwargs: dict[str, Any] = {
        "shipper": shipper,
        "company": company,
        "status": status,
        "price_amount": price_amount,
        "currency": currency,
        "distance_km": distance_km,
        "weight_t": weight_t,
        "volume_m3": volume_m3,
        "published_at": published_at,
        "expires_at": expires_at,
        "is_adr": is_adr,
        "adr_class": adr_class if is_adr else None,
        "temp_controlled": temp_controlled,
        "temp_min_c": temp_min_c if temp_controlled else None,
        "temp_max_c": temp_max_c if temp_controlled else None,
        "transport_mode": transport_mode,
        "cargo_description": cargo_description,
        "price_negotiable": price_negotiable,
        "trucks_needed": trucks_needed,
        "trucks_found": trucks_found,
    }

    load = LoadFactory(**load_kwargs)

    if body_types is not None:
        load.body_types.set(body_types)

    c_origin = get_or_create_country(origin_country)
    c_dest = get_or_create_country(destination_country)

    RoutePointFactory(
        load=load,
        seq=1,
        kind=RoutePoint.Kind.LOADING,
        country=c_origin,
        address=origin_address,
        lat=origin_lat,
        lng=origin_lng,
        planned_from=origin_planned_from,
    )

    RoutePointFactory(
        load=load,
        seq=2,
        kind=RoutePoint.Kind.UNLOADING,
        country=c_dest,
        address=destination_address,
        lat=destination_lat,
        lng=destination_lng,
        planned_from=destination_planned_from,
    )

    return load


def add_offer_to_load(
    load: Load,
    carrier: User | None = None,
    status: str = Offer.Status.PENDING,
    amount: Decimal = Decimal("2400.00"),
) -> Offer:
    """Add an offer to a load."""
    if carrier is None:
        carrier = CarrierUserFactory()
    return OfferFactory(
        load=load,
        carrier=carrier,
        status=status,
        amount=amount,
        currency=load.currency,
    )


def add_favorite_to_load(user: User, load: Load) -> Favorite:
    """Create a user favorite bookmark for a load."""
    return Favorite.objects.create(user=user, load=load)
