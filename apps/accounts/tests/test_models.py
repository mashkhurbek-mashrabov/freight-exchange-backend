"""Tests for User model and custom UserManager."""

import pytest

from apps.accounts.models import User


@pytest.mark.django_db
def test_create_user_defaults() -> None:
    """Verify create_user sets correct defaults and unusable password."""
    user = User.objects.create_user(phone="+998901234567")
    assert user.phone == "+998901234567"
    assert user.role == User.Role.CARRIER
    assert user.language == User.Language.RU
    assert user.status == User.Status.NEW
    assert user.is_active is True
    assert user.is_staff is False
    assert user.is_superuser is False
    assert not user.has_usable_password()
    assert str(user) == "+998901234567 (carrier)"


@pytest.mark.django_db
def test_create_superuser() -> None:
    """Verify create_superuser sets staff and superuser permissions."""
    admin_user = User.objects.create_superuser(
        phone="+998909999999", password="secretpassword"
    )
    assert admin_user.phone == "+998909999999"
    assert admin_user.is_staff is True
    assert admin_user.is_superuser is True
    assert admin_user.has_usable_password()


@pytest.mark.django_db
def test_create_user_empty_phone_raises_error() -> None:
    """Verify ValueError is raised if phone is empty."""
    with pytest.raises(ValueError, match="The phone number must be set."):
        User.objects.create_user(phone="")


@pytest.mark.django_db
def test_create_superuser_invalid_flags() -> None:
    """Verify ValueError is raised when superuser flags are overridden with False."""
    with pytest.raises(ValueError, match="Superuser must have is_staff=True."):
        User.objects.create_superuser(phone="+998901111111", is_staff=False)

    with pytest.raises(ValueError, match="Superuser must have is_superuser=True."):
        User.objects.create_superuser(phone="+998901111111", is_superuser=False)
