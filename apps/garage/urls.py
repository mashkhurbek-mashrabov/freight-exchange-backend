"""URL configuration for garage app."""

from django.urls import path

from apps.garage.views import (
    VehicleDetailView,
    VehicleListCreateView,
    VehicleTypeListView,
)

urlpatterns = [
    path("vehicle-types", VehicleTypeListView.as_view(), name="vehicle-type-list"),
    path("vehicles", VehicleListCreateView.as_view(), name="vehicle-list"),
    path("vehicles/<int:pk>", VehicleDetailView.as_view(), name="vehicle-detail"),
]
