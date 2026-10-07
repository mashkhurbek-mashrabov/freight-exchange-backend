"""Tests for MyFavoritesView: bookmarked loads list."""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.tests.factories import CarrierUserFactory
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
