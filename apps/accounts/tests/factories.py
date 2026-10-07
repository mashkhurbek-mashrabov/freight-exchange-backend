"""Model factories for accounts app."""

import datetime
from decimal import Decimal

import factory
from django.utils import timezone

from apps.accounts.models import Company, Device, OtpCode, User
from apps.accounts.services import hash_otp_code


class UserFactory(factory.django.DjangoModelFactory):
    """Factory for User model."""

    class Meta:
        model = User

    phone = factory.Sequence(lambda n: f"+99890{n:07d}")
    full_name = factory.Faker("name")
    role = User.Role.CARRIER
    language = User.Language.RU
    status = User.Status.NEW
    is_active = True
    is_staff = False
    is_superuser = False

    class Params:
        verified = factory.Trait(status=User.Status.VERIFIED)
        carrier = factory.Trait(role=User.Role.CARRIER)
        shipper = factory.Trait(role=User.Role.SHIPPER)


class VerifiedUserFactory(UserFactory):
    """Factory for verified user."""

    status = User.Status.VERIFIED


class CarrierUserFactory(UserFactory):
    """Factory for verified carrier user."""

    role = User.Role.CARRIER
    status = User.Status.VERIFIED


class ShipperUserFactory(UserFactory):
    """Factory for verified shipper user."""

    role = User.Role.SHIPPER
    status = User.Status.VERIFIED


class CompanyFactory(factory.django.DjangoModelFactory):
    """Factory for Company model."""

    class Meta:
        model = Company

    owner = factory.SubFactory(UserFactory)
    name = factory.Faker("company")
    tin = factory.Sequence(lambda n: f"{100000000 + n}")
    address = factory.Faker("address")
    rating_avg = Decimal("0.00")
    rating_count = 0


class DeviceFactory(factory.django.DjangoModelFactory):
    """Factory for Device model."""

    class Meta:
        model = Device

    user = factory.SubFactory(UserFactory)
    fcm_token = factory.Sequence(lambda n: f"fcm_token_{n}")
    platform = Device.Platform.ANDROID


class OtpCodeFactory(factory.django.DjangoModelFactory):
    """Factory for OtpCode model."""

    class Meta:
        model = OtpCode

    phone = factory.Sequence(lambda n: f"+99890{n:07d}")
    code_hash = factory.LazyAttribute(lambda o: hash_otp_code("123456"))
    attempts = 0
    expires_at = factory.LazyFunction(
        lambda: timezone.now() + datetime.timedelta(minutes=5)
    )
