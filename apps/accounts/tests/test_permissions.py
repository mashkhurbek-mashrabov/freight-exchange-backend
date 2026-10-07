"""Tests for core permissions IsVerified and HasRole."""

import pytest
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.tests.factories import UserFactory
from apps.core.permissions import HasRole, IsVerified


class MockVerifiedView(APIView):
    permission_classes = [IsVerified]

    def get(self, request):
        return Response({"status": "ok"})


class MockShipperOnlyView(APIView):
    permission_classes = [HasRole.of("shipper", "both")]

    def get(self, request):
        return Response({"status": "ok"})


class MockCarrierOnlyView(APIView):
    permission_classes = [HasRole.of("carrier")]

    def get(self, request):
        return Response({"status": "ok"})


@pytest.fixture
def rf() -> APIRequestFactory:
    return APIRequestFactory()


@pytest.mark.django_db
def test_is_verified_unauthenticated(rf: APIRequestFactory) -> None:
    """IsVerified rejects unauthenticated requests with 401."""
    request = rf.get("/dummy")
    view = MockVerifiedView.as_view()
    response = view(request)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["code"] == "not_authenticated"


@pytest.mark.django_db
def test_is_verified_new_user_forbidden(rf: APIRequestFactory) -> None:
    """IsVerified returns 403 with code account_not_verified for unverified users."""
    user = UserFactory(status=User.Status.NEW)
    request = rf.get("/dummy")
    force_authenticate(request, user=user)

    view = MockVerifiedView.as_view()
    response = view(request)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data == {
        "detail": "Account is not verified.",
        "code": "account_not_verified",
    }


@pytest.mark.django_db
def test_is_verified_pending_user_forbidden(rf: APIRequestFactory) -> None:
    """IsVerified returns 403 for pending_review users."""
    user = UserFactory(status=User.Status.PENDING_REVIEW)
    request = rf.get("/dummy")
    force_authenticate(request, user=user)

    view = MockVerifiedView.as_view()
    response = view(request)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "account_not_verified"


@pytest.mark.django_db
def test_is_verified_verified_user_allowed(rf: APIRequestFactory) -> None:
    """IsVerified allows access for status=verified."""
    user = UserFactory(status=User.Status.VERIFIED)
    request = rf.get("/dummy")
    force_authenticate(request, user=user)

    view = MockVerifiedView.as_view()
    response = view(request)
    assert response.status_code == status.HTTP_200_OK
    assert response.data == {"status": "ok"}


@pytest.mark.django_db
def test_has_role_unauthenticated(rf: APIRequestFactory) -> None:
    """HasRole rejects unauthenticated requests with 401."""
    request = rf.get("/dummy")
    view = MockShipperOnlyView.as_view()
    response = view(request)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["code"] == "not_authenticated"


@pytest.mark.django_db
def test_has_role_forbidden_role(rf: APIRequestFactory) -> None:
    """HasRole rejects disallowed role with 403 role_not_allowed."""
    carrier = UserFactory(role=User.Role.CARRIER)
    request = rf.get("/dummy")
    force_authenticate(request, user=carrier)

    view = MockShipperOnlyView.as_view()
    response = view(request)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data == {
        "detail": "Role not allowed for this action.",
        "code": "role_not_allowed",
    }


@pytest.mark.django_db
def test_has_role_allowed_roles(rf: APIRequestFactory) -> None:
    """HasRole allows users with matching or both roles."""
    shipper = UserFactory(role=User.Role.SHIPPER)
    both = UserFactory(role=User.Role.BOTH)

    request1 = rf.get("/dummy")
    force_authenticate(request1, user=shipper)
    view = MockShipperOnlyView.as_view()
    assert view(request1).status_code == status.HTTP_200_OK

    request2 = rf.get("/dummy")
    force_authenticate(request2, user=both)
    assert view(request2).status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_has_role_carrier_only(rf: APIRequestFactory) -> None:
    """HasRole.of('carrier') allows only carrier."""
    carrier = UserFactory(role=User.Role.CARRIER)
    shipper = UserFactory(role=User.Role.SHIPPER)

    view = MockCarrierOnlyView.as_view()

    req_carrier = rf.get("/dummy")
    force_authenticate(req_carrier, user=carrier)
    assert view(req_carrier).status_code == status.HTTP_200_OK

    req_shipper = rf.get("/dummy")
    force_authenticate(req_shipper, user=shipper)
    res_shipper = view(req_shipper)
    assert res_shipper.status_code == status.HTTP_403_FORBIDDEN
    assert res_shipper.data["code"] == "role_not_allowed"
