"""URL configuration for offers app."""

from django.urls import path

from apps.offers.views import (
    LoadOfferCreateView,
    OfferAcceptView,
    OfferCancelView,
    OfferCounterView,
    OfferDetailView,
    OfferListView,
    OfferRejectView,
)

urlpatterns = [
    path("loads/<int:load_id>/offers", LoadOfferCreateView.as_view(), name="load-offer-create"),
    path("offers", OfferListView.as_view(), name="offer-list"),
    path("offers/<int:pk>", OfferDetailView.as_view(), name="offer-detail"),
    path("offers/<int:pk>/accept", OfferAcceptView.as_view(), name="offer-accept"),
    path("offers/<int:pk>/reject", OfferRejectView.as_view(), name="offer-reject"),
    path("offers/<int:pk>/cancel", OfferCancelView.as_view(), name="offer-cancel"),
    path("offers/<int:pk>/counter", OfferCounterView.as_view(), name="offer-counter"),
]
