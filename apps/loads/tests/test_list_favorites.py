"""Tests for MyFavoritesView: bookmarked loads list."""

from typing import Any

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.tests.factories import CarrierUserFactory
from apps.loads.models import Load
from apps.loads.tests.helpers_list import add_favorite_to_load, create_test_load


@pytest.mark.django_db
@pytest.mark.urls("apps.loads.tests.urls_list_only")
class TestMyFavoritesView:
    """Test suite for GET /api/v1/me/favorites."""

    def test_unauthenticated_returns_401(self) -> None:
        client = APIClient()
        response = client.get("/api/v1/me/favorites")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_favorites_returns_user_bookmarks_newest_first(self) -> None:
        user = CarrierUserFactory()
        other_user = CarrierUserFactory()

        client = APIClient()
        client.force_authenticate(user=user)

        load1 = create_test_load(cargo_description="First load favorited")
        load2 = create_test_load(cargo_description="Second load favorited")
        load_other = create_test_load(cargo_description="Other user favorite")

        # Bookmark load1 first, load2 second
        add_favorite_to_load(user=user, load=load1)
        add_favorite_to_load(user=user, load=load2)
        # Other user's bookmark
        add_favorite_to_load(user=other_user, load=load_other)

        response = client.get("/api/v1/me/favorites")
        assert response.status_code == status.HTTP_200_OK

        data = response.data
        assert data["count"] == 2
        assert len(data["results"]) == 2

        # Newest bookmark first (load2, then load1)
        assert data["results"][0]["id"] == load2.id
        assert data["results"][1]["id"] == load1.id

        # Other user's bookmark excluded
        result_ids = [item["id"] for item in data["results"]]
        assert load_other.id not in result_ids

        # Verify compact serializer shape
        item = data["results"][0]
        assert "origin" in item
        assert "destination" in item
        assert "price_amount" in item
        assert "currency" in item
        assert "body_types" in item

    def test_favorites_constant_queries_independent_of_page_size(
        self, django_assert_max_num_queries: Any
    ) -> None:
        """Verify GET /me/favorites query count is identical regardless of page size."""
        user = CarrierUserFactory()
        client = APIClient()
        client.force_authenticate(user=user)

        for i in range(25):
            load = create_test_load(
                cargo_description=f"Favorite load #{i}",
                status=Load.Status.ACTIVE,
            )
            add_favorite_to_load(user=user, load=load)

        # Warm-up request for internal caches
        client.get("/api/v1/me/favorites?page_size=1")

        with django_assert_max_num_queries(10) as captured_2:
            resp_2 = client.get("/api/v1/me/favorites?page_size=2")
            assert resp_2.status_code == status.HTTP_200_OK
            assert len(resp_2.data["results"]) == 2

        with django_assert_max_num_queries(10) as captured_20:
            resp_20 = client.get("/api/v1/me/favorites?page_size=20")
            assert resp_20.status_code == status.HTTP_200_OK
            assert len(resp_20.data["results"]) == 20

        assert len(captured_2.captured_queries) == len(captured_20.captured_queries)
