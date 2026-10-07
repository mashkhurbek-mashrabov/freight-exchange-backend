"""Factory definitions for garage models."""

import uuid

import factory
from factory.django import DjangoModelFactory

from apps.accounts.models import User
from apps.garage.models import Vehicle, VehicleKind, VehicleType


def _generate_unique_phone() -> str:
    unique_digits = uuid.uuid4().int % 1000000000
    return f"+99890{unique_digits:07d}"[:13]


class VehicleTypeFactory(DjangoModelFactory):
    """Factory for VehicleType model."""

    class Meta:
        model = VehicleType
        django_get_or_create = ("code",)

    code = factory.Sequence(lambda n: f"type_{n}")
    name_i18n = factory.LazyFunction(
        lambda: {"uz": "Tent", "ru": "Тент", "en": "Tent trailer"}
    )
    image_url = ""
    kind = VehicleKind.TRACTOR


class VehicleFactory(DjangoModelFactory):
    """Factory for Vehicle model."""

    class Meta:
        model = Vehicle

    owner = factory.LazyFunction(
        lambda: User.objects.create_user(phone=_generate_unique_phone())
    )
    kind = VehicleKind.TRACTOR
    vehicle_type = factory.SubFactory(
        VehicleTypeFactory,
        kind=factory.SelfAttribute("..kind"),
    )
    plate_number = factory.Sequence(lambda n: f"01A{n % 1000:03d}AA")
    tech_passport_no = factory.Sequence(lambda n: f"AAF{n:06d}")
    owner_full_name = "Rustam Aliyev"
    brand = "MAN"
    tech_passport_image = None
    paired_vehicle = None
    is_active = True
