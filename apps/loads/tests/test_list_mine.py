"""Tests for LoadMineView: shipper's own loads list."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.tests.factories import CarrierUserFactory, ShipperUserFactory
from apps.loads.models import Load
from apps.loads.tests.helpers_list import add_offer_to_load, create_test_load


@pytest.mark.django_db
@pytest.mark.urls("apps.loads.tests.urls_list_only")
class TestLoadMineView:
    """Test suite for GET /api/v1/loads/mine."""

    def test_unauthenticated_returns_401(self) -> None:
        client = APIClient()
        response = client.get("/api/v1/loads/mine")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_mine_includes_all_statuses_and_only_own_loads(self) -> None:
        shipper = ShipperUserFactory()
        other_shipper = ShipperUserFactory()

        client = APIClient()
        client.force_authenticate(user=shipper)

        exp_date = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)

        # Create own loads across all statuses
        l_draft = create_test_load(shipper=shipper, status=Load.Status.DRAFT, expires_at=exp_date)
        l_active = create_test_load(
            shipper=shipper, status=Load.Status.ACTIVE, expires_at=exp_date
        )
        l_inp = create_test_load(
            shipper=shipper, status=Load.Status.IN_PROGRESS, expires_at=exp_date
        )
        l_comp = create_test_load(
            shipper=shipper, status=Load.Status.COMPLETED, expires_at=exp_date
        )
        l_canc = create_test_load(
            shipper=shipper, status=Load.Status.CANCELLED, expires_at=exp_date
        )
        l_exp = create_test_load(shipper=shipper, status=Load.Status.EXPIRED, expires_at=exp_date)

        # Other shipper's load
        l_other = create_test_load(shipper=other_shipper, status=Load.Status.ACTIVE)

        # Add offers to l_active
        carrier1 = CarrierUserFactory()
        carrier2 = CarrierUserFactory()
        add_offer_to_load(l_active, carrier=carrier1, amount=Decimal("2000.00"))
        add_offer_to_load(l_active, carrier=carrier2, amount=Decimal("2200.00"))

        response = client.get("/api/v1/loads/mine")
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        assert data["count"] == 6
        assert len(data["results"]) == 6

        returned_ids = {item["id"] for item in data["results"]}
        expected_ids = {
            l_draft.id,
            l_active.id,
            l_inp.id,
            l_comp.id,
            l_canc.id,
            l_exp.id,
        }
        assert returned_ids == expected_ids
        assert l_other.id not in returned_ids

        # Verify fields on LoadMineSerializer
        item_by_id = {item["id"]: item for item in data["results"]}
        active_item = item_by_id[l_active.id]
        assert active_item["status"] == Load.Status.ACTIVE
        assert active_item["offers_count"] == 2
        assert active_item["expires_at"] is not None
        assert active_item["origin"]["country"] == "UZ"
        assert active_item["destination"]["country"] == "RU"

        draft_item = item_by_id[l_draft.id]
        assert draft_item["status"] == Load.Status.DRAFT
        assert draft_item["offers_count"] == 0
