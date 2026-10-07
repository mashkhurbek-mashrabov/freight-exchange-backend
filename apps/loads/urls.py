"""URL configuration for loads app write and detail operations."""

from django.urls import path

from apps.loads.views import (
    LoadCancelView,
    LoadCreateView,
    LoadDetailView,
    LoadFavoriteView,
    LoadPublishView,
)

__all__ = [
    "LoadCancelView",
    "LoadCreateView",
    "LoadDetailView",
    "LoadFavoriteView",
    "LoadPublishView",
    "urlpatterns",
]

urlpatterns = [
    # Fixed paths first
    path("loads", LoadCreateView.as_view(), name="load-create"),
    # Parametric paths
    path("loads/<int:pk>", LoadDetailView.as_view(), name="load-detail"),
    path("loads/<int:pk>/publish", LoadPublishView.as_view(), name="load-publish"),
    path("loads/<int:pk>/cancel", LoadCancelView.as_view(), name="load-cancel"),
    path("loads/<int:pk>/favorite", LoadFavoriteView.as_view(), name="load-favorite"),
]
