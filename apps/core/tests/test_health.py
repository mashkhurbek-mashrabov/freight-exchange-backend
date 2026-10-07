"""Tests for health check endpoint."""

from unittest.mock import patch

import pytest
from django.db import DatabaseError
from rest_framework import status
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_health_check_success() -> None:
    """Verify health endpoint returns 200 OK and status ok when DB is connected."""
    client = APIClient()
    response = client.get("/health/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_health_check_failure() -> None:
    """Verify health endpoint returns 503 when DB query fails."""
    client = APIClient()
    with patch("django.db.connection.cursor", side_effect=DatabaseError("Connection lost")):
        response = client.get("/health/")
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert data["status"] == "error"
        assert "Connection lost" in data["detail"]
