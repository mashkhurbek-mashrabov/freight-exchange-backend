"""Pytest fixtures for geo tests."""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User


@pytest.fixture
def auth_user(db: None) -> User:
    """Create a verified test user."""
    return User.objects.create_user(
        phone="+998901234567",
        full_name="Test Sevara User",
        status=User.Status.VERIFIED,
    )


@pytest.fixture
def auth_client(auth_user: User) -> APIClient:
    """Return an APIClient authenticated as auth_user."""
    client = APIClient()
    client.force_authenticate(user=auth_user)
    return client


@pytest.fixture
def api_client() -> APIClient:
    """Return an unauthenticated APIClient."""
    return APIClient()
