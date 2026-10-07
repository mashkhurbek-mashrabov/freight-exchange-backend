"""Tests for OpenAPI schema and documentation endpoints."""

import pytest
from rest_framework import status
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_schema_endpoint_success() -> None:
    """Verify /api/schema/ returns 200 and valid schema."""
    client = APIClient()
    response = client.get("/api/schema/")
    assert response.status_code == status.HTTP_200_OK
    assert b"openapi: 3.0.3" in response.content

    # Also verify JSON format request
    json_response = client.get("/api/schema/?format=json")
    assert json_response.status_code == status.HTTP_200_OK
    data = json_response.json()
    assert data["openapi"] == "3.0.3"
    assert data["info"]["title"] == "Freight Exchange API"


@pytest.mark.django_db
def test_swagger_ui_endpoint_success() -> None:
    """Verify /api/docs/ returns 200 and renders Swagger UI HTML."""
    client = APIClient()
    response = client.get("/api/docs/")
    assert response.status_code == status.HTTP_200_OK
    assert b"swagger-ui" in response.content.lower()


@pytest.mark.django_db
def test_redoc_endpoint_success() -> None:
    """Verify /api/redoc/ returns 200 and renders ReDoc HTML."""
    client = APIClient()
    response = client.get("/api/redoc/")
    assert response.status_code == status.HTTP_200_OK
    assert b"redoc" in response.content.lower()
