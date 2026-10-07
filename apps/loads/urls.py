"""URL configuration for loads app write and detail operations."""

from django.urls import path

from apps.loads.root_views import LoadListCreateView
from apps.loads.urls_list import urlpatterns as list_urlpatterns
from apps.loads.views import (
    LoadCancelView,
    LoadDetailView,
    LoadFavoriteView,
    LoadPublishView,
)

__all__ = [
    "LoadCancelView",
    "LoadDetailView",
    "LoadFavoriteView",
    "LoadPublishView",
    "urlpatterns",
]

urlpatterns = [
    *[u for u in list_urlpatterns if u.pattern._route != "loads"],
    # Fixed paths first
    path("loads", LoadListCreateView.as_view(), name="load-list-create"),
    # Parametric paths
    path("loads/<int:pk>", LoadDetailView.as_view(), name="load-detail"),
    path("loads/<int:pk>/publish", LoadPublishView.as_view(), name="load-publish"),
    path("loads/<int:pk>/cancel", LoadCancelView.as_view(), name="load-cancel"),
    path("loads/<int:pk>/favorite", LoadFavoriteView.as_view(), name="load-favorite"),
]
