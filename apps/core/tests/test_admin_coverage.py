"""Tests for Django admin registration and changelist coverage across all project models."""

import pytest
from django.apps import apps
from django.contrib import admin
from django.test import Client, override_settings
from django.urls import reverse

from apps.accounts.tests.factories import UserFactory

PROJECT_APP_LABELS = [
    "core",
    "accounts",
    "geo",
    "garage",
    "loads",
    "offers",
    "orders",
    "notifications",
]


def get_all_project_models():
    """Retrieve all concrete models belonging to the 8 project apps."""
    models = []
    for label in PROJECT_APP_LABELS:
        app_config = apps.get_app_config(label)
        models.extend(app_config.get_models())
    return models


def test_all_project_models_are_registered_in_admin():
    """Ensure every model across the 8 project apps is registered with Django admin."""
    project_models = get_all_project_models()
    assert len(project_models) > 0, "No models found in project apps"

    unregistered = []
    for model in project_models:
        if model not in admin.site._registry:
            unregistered.append(f"{model._meta.app_label}.{model.__name__}")

    assert not unregistered, f"Models not registered in admin: {unregistered}"


def test_admin_classes_have_useful_configurations():
    """Ensure every ModelAdmin has non-empty list_display, list_filter, and search_fields."""
    project_models = get_all_project_models()

    for model in project_models:
        model_admin = admin.site._registry.get(model)
        assert model_admin is not None, f"{model.__name__} is not registered in admin"

        # Check list_display
        list_display = getattr(model_admin, "list_display", ())
        assert list_display, f"{model.__name__} ModelAdmin has empty list_display"

        # Check list_filter
        list_filter = getattr(model_admin, "list_filter", ())
        assert list_filter, f"{model.__name__} ModelAdmin has empty list_filter"

        # Check search_fields
        search_fields = getattr(model_admin, "search_fields", ())
        assert search_fields, f"{model.__name__} ModelAdmin has empty search_fields"


@pytest.mark.django_db
@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    }
)
def test_admin_changelist_smoke_tests():
    """Verify that a superuser can access changelists for all project models (HTTP 200)."""
    superuser = UserFactory(is_staff=True, is_superuser=True)
    client = Client()
    client.force_login(superuser)

    project_models = get_all_project_models()
    for model in project_models:
        opts = model._meta
        url = reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist")
        response = client.get(url)
        assert response.status_code == 200, (
            f"Admin changelist for {opts.app_label}.{opts.model_name} "
            f"returned {response.status_code} at {url}"
        )
