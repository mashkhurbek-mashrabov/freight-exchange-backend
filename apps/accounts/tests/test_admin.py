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


@pytest.mark.django_db
def test_mark_verified_sets_status_and_notifies():
    from apps.accounts import services
    from apps.notifications.models import Notification

    u = UserFactory(status=User.Status.NEW)
    assert services.mark_verified(User.objects.filter(pk=u.pk)) == 1
    u.refresh_from_db()
    assert u.status == User.Status.VERIFIED
    assert Notification.objects.filter(user=u, type="account_verified").count() == 1
    assert services.mark_verified(User.objects.filter(pk=u.pk)) == 0


@pytest.mark.django_db
def test_user_admin_save_model_notifies_when_verified() -> None:
    """UserAdmin.save_model sends account_verified notification on transition to verified."""
    from apps.notifications.models import Notification

    site = DummyAdminSite()
    user_admin = UserAdmin(User, site)

    user = UserFactory(status=User.Status.PENDING_REVIEW)
    user.status = User.Status.VERIFIED

    user_admin.save_model(None, user, None, change=True)
    assert Notification.objects.filter(user=user, type="account_verified").count() == 1
