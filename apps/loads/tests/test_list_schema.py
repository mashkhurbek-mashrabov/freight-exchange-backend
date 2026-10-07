"""Test OpenAPI schema validation for loads read endpoints."""

import io

import pytest
from django.core.management import call_command


@pytest.mark.django_db
def test_spectacular_schema_generation_for_loads_read_routes() -> None:
    """Ensure spectacular --validate --fail-on-warn passes for loads read routes."""
    out = io.StringIO()
    call_command(
        "spectacular",
        validate=True,
        fail_on_warn=True,
        urlconf="apps.loads.tests.urls_list_only",
        stdout=out,
    )
    schema_yaml = out.getvalue()
    assert "/api/v1/loads:" in schema_yaml
    assert "/api/v1/loads/mine:" in schema_yaml
    assert "/api/v1/loads/map:" in schema_yaml
    assert "/api/v1/me/favorites:" in schema_yaml
    assert "LoadCompact:" in schema_yaml
    assert "LoadMine:" in schema_yaml
    assert "LoadMapItem:" in schema_yaml
