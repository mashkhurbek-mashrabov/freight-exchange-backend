"""Tests for load list ordering options."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.tests.factories import CarrierUserFactory
from apps.loads.tests.helpers_list import create_test_load


@pytest.mark.django_db
@pytest.mark.urls("apps.loads.tests.urls_list_only")
class TestLoadListOrdering:
    """Test suite for ordering parameters including price_per_km and invalid values."""

    @pytest.fixture(autouse=True)
    def setup_client(self) -> None:
        self.user = CarrierUserFactory()
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_default_ordering_is_newest_published_first(self) -> None:
        t1 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=UTC)
        t2 = datetime(2026, 10, 5, 10, 0, 0, tzinfo=UTC)

        load_old = create_test_load(published_at=t1)
        load_new = create_test_load(published_at=t2)

        resp = self.client.get("/api/v1/loads")
        assert resp.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in resp.data["results"]]
        assert ids[0] == load_new.id
        assert ids[1] == load_old.id

    def test_ordering_published_at_ascending(self) -> None:
        t1 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=UTC)
        t2 = datetime(2026, 10, 5, 10, 0, 0, tzinfo=UTC)

        load_old = create_test_load(published_at=t1)
        load_new = create_test_load(published_at=t2)

        resp = self.client.get("/api/v1/loads?ordering=published_at")
        assert resp.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in resp.data["results"]]
        assert ids[0] == load_old.id
        assert ids[1] == load_new.id

    def test_ordering_distance_km_asc_and_desc(self) -> None:
        load_short = create_test_load(distance_km=300)
        load_long = create_test_load(distance_km=1800)

        # Ascending
        resp_asc = self.client.get("/api/v1/loads?ordering=distance_km")
        assert resp_asc.status_code == status.HTTP_200_OK
        ids_asc = [item["id"] for item in resp_asc.data["results"]]
        assert ids_asc[0] == load_short.id
        assert ids_asc[1] == load_long.id

        # Descending
        resp_desc = self.client.get("/api/v1/loads?ordering=-distance_km")
        assert resp_desc.status_code == status.HTTP_200_OK
        ids_desc = [item["id"] for item in resp_desc.data["results"]]
        assert ids_desc[0] == load_long.id
        assert ids_desc[1] == load_short.id

    def test_ordering_price_amount_asc_and_desc(self) -> None:
        load_cheap = create_test_load(price_amount=Decimal("1200.00"))
        load_pricey = create_test_load(price_amount=Decimal("5000.00"))

        # Ascending
        resp_asc = self.client.get("/api/v1/loads?ordering=price_amount")
        assert resp_asc.status_code == status.HTTP_200_OK
        ids_asc = [item["id"] for item in resp_asc.data["results"]]
        assert ids_asc[0] == load_cheap.id
        assert ids_asc[1] == load_pricey.id

        # Descending
        resp_desc = self.client.get("/api/v1/loads?ordering=-price_amount")
        assert resp_desc.status_code == status.HTTP_200_OK
        ids_desc = [item["id"] for item in resp_desc.data["results"]]
        assert ids_desc[0] == load_pricey.id
        assert ids_desc[1] == load_cheap.id

    def test_ordering_price_per_km(self) -> None:
        # Load A: 2000 / 1000 = 2.00 per km
        load_a = create_test_load(price_amount=Decimal("2000.00"), distance_km=1000)
        # Load B: 5000 / 1000 = 5.00 per km
        load_b = create_test_load(price_amount=Decimal("5000.00"), distance_km=1000)

        # Ascending price_per_km
        resp_asc = self.client.get("/api/v1/loads?ordering=price_per_km")
        assert resp_asc.status_code == status.HTTP_200_OK
        ids_asc = [item["id"] for item in resp_asc.data["results"]]
        assert ids_asc[0] == load_a.id
        assert ids_asc[1] == load_b.id

        # Descending -price_per_km
        resp_desc = self.client.get("/api/v1/loads?ordering=-price_per_km")
        assert resp_desc.status_code == status.HTTP_200_OK
        ids_desc = [item["id"] for item in resp_desc.data["results"]]
        assert ids_desc[0] == load_b.id
        assert ids_desc[1] == load_a.id

    def test_ordering_price_per_km_with_null_and_zero_distance(self) -> None:
        """Verify sorting by price_per_km handles NULL and 0 distance without dividing by zero."""
        # Normal load: 2000 / 1000 = 2.00
        load_valid = create_test_load(price_amount=Decimal("2000.00"), distance_km=1000)
        # Null distance
        load_null_dist = create_test_load(price_amount=Decimal("3000.00"), distance_km=None)
        # Zero distance
        load_zero_dist = create_test_load(price_amount=Decimal("1500.00"), distance_km=0)

        # Ascending: valid price per km comes first, null/zero distance sorted last
        resp_asc = self.client.get("/api/v1/loads?ordering=price_per_km")
        assert resp_asc.status_code == status.HTTP_200_OK
        ids_asc = [item["id"] for item in resp_asc.data["results"]]
        assert ids_asc[0] == load_valid.id
        assert set(ids_asc[1:]) == {load_null_dist.id, load_zero_dist.id}

        # Descending: valid price per km comes first, null/zero distance sorted last
        resp_desc = self.client.get("/api/v1/loads?ordering=-price_per_km")
        assert resp_desc.status_code == status.HTTP_200_OK
        ids_desc = [item["id"] for item in resp_desc.data["results"]]
        assert ids_desc[0] == load_valid.id
        assert set(ids_desc[1:]) == {load_null_dist.id, load_zero_dist.id}

    def test_invalid_ordering_value_ignored_consistently(self) -> None:
        t1 = datetime(2026, 10, 1, 10, 0, 0, tzinfo=UTC)
        t2 = datetime(2026, 10, 5, 10, 0, 0, tzinfo=UTC)

        load_old = create_test_load(published_at=t1)
        load_new = create_test_load(published_at=t2)

        # Invalid ordering string should not crash; it falls back to default -published_at
        resp = self.client.get("/api/v1/loads?ordering=invalid_column_name")
        assert resp.status_code == status.HTTP_200_OK
        ids = [item["id"] for item in resp.data["results"]]
        assert ids[0] == load_new.id
        assert ids[1] == load_old.id
