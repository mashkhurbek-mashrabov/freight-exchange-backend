"""Tests for DefaultPagination."""

from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.core.pagination import DefaultPagination


def test_default_pagination_size() -> None:
    """Verify default page size is 20 and response keys are standardized."""
    factory = APIRequestFactory()
    request = Request(factory.get("/dummy/"))
    paginator = DefaultPagination()
    data = list(range(50))
    page = paginator.paginate_queryset(data, request)
    assert page is not None
    assert len(page) == 20
    response = paginator.get_paginated_response(page)
    assert response.data["count"] == 50
    assert response.data["next"] is not None
    assert response.data["previous"] is None
    assert len(response.data["results"]) == 20


def test_custom_page_size_query_param() -> None:
    """Verify page_size query parameter is respected up to max_page_size."""
    factory = APIRequestFactory()
    request = Request(factory.get("/dummy/?page_size=40"))
    paginator = DefaultPagination()
    data = list(range(100))
    page = paginator.paginate_queryset(data, request)
    assert page is not None
    assert len(page) == 40


def test_pagination_max_page_size_cap() -> None:
    """Verify page_size exceeding max_page_size (100) is capped at 100."""
    factory = APIRequestFactory()
    request = Request(factory.get("/dummy/?page_size=250"))
    paginator = DefaultPagination()
    data = list(range(200))
    page = paginator.paginate_queryset(data, request)
    assert page is not None
    assert len(page) == 100
