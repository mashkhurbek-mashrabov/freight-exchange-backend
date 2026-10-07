"""Tests for LoadMapView: map markers endpoint and bounding box validation."""

from decimal import Decimal

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.tests.factories import CarrierUserFactory
from apps.loads.models import Load
from apps.loads.tests.helpers_list import create_test_load


@pytest.mark.django_db
@pytest.mark.urls("apps.loads.tests.urls_list_only")
class TestLoadMapView:
    """Test suite for GET /api/v1/loads/map."""

    @pytest.fixture(autouse=True)
    def setup_client(self) -> None:
        self.user = CarrierUserFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_unauthenticated_returns_401(self) -> None:
        unauth_client = APIClient()
        response = unauth_client.get("/api/v1/loads/map?bbox=60,40,70,50")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_missing_bbox_returns_400_validation_error(self) -> None:
        response = self.client.get("/api/v1/loads/map")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["code"] == "validation_error"
        assert "bbox" in response.data["errors"]

    def test_invalid_bbox_format_returns_400(self) -> None:
        # Not 4 numbers
        resp_too_few = self.client.get("/api/v1/loads/map?bbox=60,40,70")
        assert resp_too_few.status_code == status.HTTP_400_BAD_REQUEST
        assert resp_too_few.data["code"] == "validation_error"

        # Not numbers
        resp_nan = self.client.get("/api/v1/loads/map?bbox=abc,def,ghi,jkl")
        assert resp_nan.status_code == status.HTTP_400_BAD_REQUEST
        assert resp_nan.data["code"] == "validation_error"

        # min > max
        resp_inverted = self.client.get("/api/v1/loads/map?bbox=70,40,60,50")
        assert resp_inverted.status_code == status.HTTP_400_BAD_REQUEST
        assert resp_inverted.data["code"] == "validation_error"

        # Out of degree range
        resp_oor = self.client.get("/api/v1/loads/map?bbox=-200,40,70,50")
        assert resp_oor.status_code == status.HTTP_400_BAD_REQUEST
        assert resp_oor.data["code"] == "validation_error"

    def test_valid_bbox_returns_unpaginated_list_of_markers_using_first_loading_point(
        self,
    ) -> None:
        # Tashkent: lat 41.299496, lng 69.240073 (Inside bbox 68,40,71,43)
        load_inside = create_test_load(
            origin_lat=Decimal("41.299496"),
            origin_lng=Decimal("69.240073"),
            price_amount=Decimal("1500.00"),
            currency_code="USD",
            status=Load.Status.ACTIVE,
        )

        # Samarkand: lat 39.654167, lng 66.959722 (Outside bbox 68,40,71,43)
        load_outside = create_test_load(
            origin_lat=Decimal("39.654167"),
            origin_lng=Decimal("66.959722"),
            status=Load.Status.ACTIVE,
        )

        # Inside bbox, but status is DRAFT (should be excluded)
        load_draft = create_test_load(
            origin_lat=Decimal("41.299496"),
            origin_lng=Decimal("69.240073"),
            status=Load.Status.DRAFT,
        )

        # bbox: minLng=68.0, minLat=40.0, maxLng=71.0, maxLat=43.0
        response = self.client.get("/api/v1/loads/map?bbox=68.0,40.0,71.0,43.0")
        assert response.status_code == status.HTTP_200_OK

        # Must be an unpaginated list (list type, not dict with 'results')
        assert isinstance(response.data, list)
        assert len(response.data) == 1

        marker = response.data[0]
        assert marker["id"] == load_inside.id
        assert Decimal(marker["lat"]) == Decimal("41.299496")
        assert Decimal(marker["lng"]) == Decimal("69.240073")
        assert Decimal(marker["price_amount"]) == Decimal("1500.00")
        assert marker["currency"] == "USD"

        result_ids = [m["id"] for m in response.data]
        assert load_outside.id not in result_ids
        assert load_draft.id not in result_ids

    def test_map_view_caps_at_500_items(self) -> None:
        """Verify that the map endpoint returns at most 500 items."""
        # Create 505 loads inside bbox
        for _ in range(505):
            create_test_load(
                origin_lat=Decimal("41.000000"),
                origin_lng=Decimal("69.000000"),
                status=Load.Status.ACTIVE,
            )

        response = self.client.get("/api/v1/loads/map?bbox=68.0,40.0,71.0,43.0")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)
        assert len(response.data) == 500
