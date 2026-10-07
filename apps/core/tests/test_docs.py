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


@pytest.mark.django_db
def test_openapi_schema_quality_and_spec_rules() -> None:
    """Verify OpenAPI schema conforms to all plan requirements."""
    client = APIClient()
    response = client.get("/api/schema/?format=json")
    assert response.status_code == status.HTTP_200_OK
    schema = response.json()

    valid_tags = {
        "Auth",
        "Profile",
        "Reference",
        "Garage",
        "Loads",
        "Offers",
        "Orders",
        "Notifications",
        "Service",
    }
    paths = schema.get("paths", {})

    for path, methods in paths.items():
        for method, op in methods.items():
            if method in ["parameters"]:
                continue
            assert op.get("summary"), f"Missing summary for {method.upper()} {path}"
            tags = op.get("tags", [])
            assert tags, f"Missing tags for {method.upper()} {path}"
            for t in tags:
                assert t in valid_tags, f"Invalid tag '{t}' in {method.upper()} {path}"

    # BearerAuth security scheme
    sec_schemes = schema.get("components", {}).get("securitySchemes", {})
    assert "bearerAuth" in sec_schemes
    assert sec_schemes["bearerAuth"]["scheme"] == "bearer"

    # Health tag
    health_op = paths.get("/health/", {}).get("get", {})
    assert "Service" in health_op.get("tags", [])

    # Examples check
    otp_req = paths.get("/api/v1/auth/otp/request", {}).get("post", {})
    assert "examples" in otp_req.get("requestBody", {}).get("content", {}).get(
        "application/json", {}
    )

    otp_ver = paths.get("/api/v1/auth/otp/verify", {}).get("post", {})
    assert "examples" in otp_ver.get("requestBody", {}).get("content", {}).get(
        "application/json", {}
    )

    loads_post = paths.get("/api/v1/loads", {}).get("post", {})
    assert "examples" in loads_post.get("requestBody", {}).get("content", {}).get(
        "application/json", {}
    )

    offers_post = paths.get("/api/v1/loads/{load_id}/offers", {}).get("post", {})
    assert "examples" in offers_post.get("requestBody", {}).get("content", {}).get(
        "application/json", {}
    )

    counter_post = paths.get("/api/v1/offers/{id}/counter", {}).get("post", {})
    assert "examples" in counter_post.get("requestBody", {}).get("content", {}).get(
        "application/json", {}
    )

    status_post = paths.get("/api/v1/orders/{id}/status", {}).get("post", {})
    assert "examples" in status_post.get("requestBody", {}).get("content", {}).get(
        "application/json", {}
    )
