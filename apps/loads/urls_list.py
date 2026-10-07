"""URL patterns for loads read endpoints."""

from django.urls import path

from apps.loads.list_views import (
    LoadListView,
    LoadMapView,
    LoadMineView,
    MyFavoritesView,
)

urlpatterns = [
    path("loads/mine", LoadMineView.as_view(), name="loads-mine"),
    path("loads/map", LoadMapView.as_view(), name="loads-map"),
    path("me/favorites", MyFavoritesView.as_view(), name="me-favorites"),
    path("loads", LoadListView.as_view(), name="loads-list"),
]
