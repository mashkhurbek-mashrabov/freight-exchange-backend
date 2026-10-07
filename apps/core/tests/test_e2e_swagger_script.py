"""End-to-end test executing Swagger test script from plan section 7."""

from typing import Any

import pytest
from django.core.management import call_command
from rest_framework import status
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_swagger_script_e2e(settings: Any) -> None:
    """Execute end-to-end Swagger script from plan section 7."""
    settings.OTP_DEV_CODE = "000000"
    call_command("seed_demo")

    client = APIClient()
    phone = "+998900000001"

    # Step 1: Request OTP code
    request_resp = client.post(
        "/api/v1/auth/otp/request",
        {"phone": phone},
        format="json",
    )
    assert request_resp.status_code == status.HTTP_204_NO_CONTENT

    # Step 2: Verify OTP code using dev code
    verify_resp = client.post(
        "/api/v1/auth/otp/verify",
        {"phone": phone, "code": "000000"},
        format="json",
    )
    assert verify_resp.status_code == status.HTTP_200_OK
    verify_data = verify_resp.json()
    assert "access" in verify_data
    access_token = verify_data["access"]
    assert bool(access_token)

    # Step 3: Authorize client with Bearer JWT
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")

    # Step 4: GET /api/v1/loads returns seeded loads with count > 0
    loads_resp = client.get("/api/v1/loads")
    assert loads_resp.status_code == status.HTTP_200_OK
    loads_data = loads_resp.json()
    assert "count" in loads_data
    assert loads_data["count"] > 0
    assert len(loads_data["results"]) > 0

    # Step 5: GET /api/v1/me shows role carrier and status verified
    me_resp = client.get("/api/v1/me")
    assert me_resp.status_code == status.HTTP_200_OK
    me_data = me_resp.json()
    assert me_data["phone"] == phone
    assert me_data["full_name"] == "Demo Carrier"
    assert me_data["role"] == "carrier"
    assert me_data["status"] == "verified"
    assert me_data["language"] == "ru"
    assert me_data["company"]["name"] == "Demo Carrier LLC"
