"""Tests for rate throttling and 429 responses."""

import pytest
from django.core.cache import cache
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIClient, force_authenticate
from rest_framework.views import APIView

from apps.accounts.tests.factories import UserFactory
from apps.core.throttles import AnonRateThrottle, ScopedRateThrottle, UserRateThrottle


class DummyAnonView(APIView):
    """View protected by AnonRateThrottle."""

    permission_classes = []
    throttle_classes = [AnonRateThrottle]

    def get(self, request):
        return Response({"status": "ok"})


class DummyUserView(APIView):
    """View protected by UserRateThrottle."""

    throttle_classes = [UserRateThrottle]

    def get(self, request):
        return Response({"status": "ok"})


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
def test_otp_request_throttling_per_ip(client: APIClient, monkeypatch: pytest.MonkeyPatch):
    """OTP request endpoint returns 429 with code 'throttled' when exceeding rate."""
    monkeypatch.setattr(
        ScopedRateThrottle,
        "THROTTLE_RATES",
        {"otp": "2/min", "otp_verify": "2/min"},
    )

    url = "/api/v1/auth/otp/request"
    payload = {"phone": "+998901112233"}

    # 1st and 2nd requests within limit
    resp1 = client.post(url, payload, format="json", REMOTE_ADDR="192.168.1.100")
    assert resp1.status_code == status.HTTP_204_NO_CONTENT

    resp2 = client.post(url, payload, format="json", REMOTE_ADDR="192.168.1.100")
    assert resp2.status_code == status.HTTP_204_NO_CONTENT

    # 3rd request from same IP throttled
    resp3 = client.post(url, payload, format="json", REMOTE_ADDR="192.168.1.100")
    assert resp3.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    data = resp3.json()
    assert data["code"] == "throttled"
    assert "detail" in data
    assert "Retry-After" in resp3.headers
    assert int(resp3.headers["Retry-After"]) >= 1

    # Request from different IP succeeds
    resp_other = client.post(url, payload, format="json", REMOTE_ADDR="192.168.1.200")
    assert resp_other.status_code == status.HTTP_204_NO_CONTENT


@pytest.mark.django_db
def test_otp_verify_throttling_per_ip(client: APIClient, monkeypatch: pytest.MonkeyPatch):
    """OTP verify endpoint returns 429 with code 'throttled' and Retry-After header."""
    monkeypatch.setattr(
        ScopedRateThrottle,
        "THROTTLE_RATES",
        {"otp": "2/min", "otp_verify": "2/min"},
    )

    url = "/api/v1/auth/otp/verify"
    payload = {"phone": "+998901112233", "code": "123456"}

    # First two calls hit normal service/validation logic (e.g. 400 for bad OTP)
    resp1 = client.post(url, payload, format="json", REMOTE_ADDR="10.0.0.1")
    assert resp1.status_code != status.HTTP_429_TOO_MANY_REQUESTS

    resp2 = client.post(url, payload, format="json", REMOTE_ADDR="10.0.0.1")
    assert resp2.status_code != status.HTTP_429_TOO_MANY_REQUESTS

    # 3rd call is throttled
    resp3 = client.post(url, payload, format="json", REMOTE_ADDR="10.0.0.1")
    assert resp3.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    data = resp3.json()
    assert data["code"] == "throttled"
    assert "detail" in data
    assert "Retry-After" in resp3.headers


def test_anon_rate_throttle(rf, monkeypatch: pytest.MonkeyPatch):
    """AnonRateThrottle returns 429 when anonymous user exceeds limit."""
    monkeypatch.setattr(AnonRateThrottle, "THROTTLE_RATES", {"anon": "2/min"})

    view = DummyAnonView.as_view()

    req1 = rf.get("/dummy", REMOTE_ADDR="127.0.0.1")
    resp1 = view(req1)
    assert resp1.status_code == status.HTTP_200_OK

    req2 = rf.get("/dummy", REMOTE_ADDR="127.0.0.1")
    resp2 = view(req2)
    assert resp2.status_code == status.HTTP_200_OK

    req3 = rf.get("/dummy", REMOTE_ADDR="127.0.0.1")
    resp3 = view(req3)
    assert resp3.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    data = resp3.data
    assert data["code"] == "throttled"
    assert "Retry-After" in resp3.headers


@pytest.mark.django_db
def test_user_rate_throttle(rf, monkeypatch: pytest.MonkeyPatch):
    """UserRateThrottle returns 429 when authenticated user exceeds limit."""
    monkeypatch.setattr(UserRateThrottle, "THROTTLE_RATES", {"user": "2/min"})

    user = UserFactory()
    view = DummyUserView.as_view()

    req1 = rf.get("/dummy")
    force_authenticate(req1, user=user)
    resp1 = view(req1)
    assert resp1.status_code == status.HTTP_200_OK

    req2 = rf.get("/dummy")
    force_authenticate(req2, user=user)
    resp2 = view(req2)
    assert resp2.status_code == status.HTTP_200_OK

    req3 = rf.get("/dummy")
    force_authenticate(req3, user=user)
    resp3 = view(req3)
    assert resp3.status_code == status.HTTP_429_TOO_MANY_REQUESTS
    data = resp3.data
    assert data["code"] == "throttled"
    assert "Retry-After" in resp3.headers
