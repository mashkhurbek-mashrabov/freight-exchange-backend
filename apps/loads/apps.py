"""Loads app configuration."""

from django.apps import AppConfig


class LoadsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.loads"
    label = "loads"
