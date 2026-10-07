"""Tests for accounts admin configuration."""

import pytest
from django.contrib.admin.sites import AdminSite

from apps.accounts.admin import CompanyAdmin, DeviceAdmin, OtpCodeAdmin, UserAdmin
from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory


class DummyAdminSite(AdminSite):
    pass


@pytest.mark.django_db
def test_user_admin_mark_verified_action() -> None:
    """UserAdmin bulk action mark_verified sets status=verified."""
    site = DummyAdminSite()
    user_admin = UserAdmin(User, site)

    u1 = UserFactory(status=User.Status.NEW)
    u2 = UserFactory(status=User.Status.PENDING_REVIEW)
    queryset = User.objects.filter(id__in=[u1.id, u2.id])

    user_admin.mark_verified(None, queryset)

    u1.refresh_from_db()
    u2.refresh_from_db()
    assert u1.status == User.Status.VERIFIED
    assert u2.status == User.Status.VERIFIED


def test_admin_registrations() -> None:
    """Verify ModelAdmin classes are configured with required display and filter fields."""
    assert "phone" in UserAdmin.list_display
    assert "status" in UserAdmin.list_filter
    assert "phone" in UserAdmin.search_fields

    assert "name" in CompanyAdmin.list_display
    assert "fcm_token" in DeviceAdmin.list_display
    assert "attempts" in OtpCodeAdmin.list_display
