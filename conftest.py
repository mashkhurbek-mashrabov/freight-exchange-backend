"""Global pytest configuration and fixtures."""

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def clear_cache() -> None:
    """Clear Django cache between tests."""
    cache.clear()
