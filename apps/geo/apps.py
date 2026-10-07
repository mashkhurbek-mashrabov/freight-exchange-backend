"""Geo app configuration."""

from django.apps import AppConfig


class GeoConfig(AppConfig):
    """Geo application configuration registering invalidation signals."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.geo"
    label = "geo"

    def ready(self) -> None:
        """Register signal receivers upon application startup."""
        import apps.geo.signals  # noqa: F401
