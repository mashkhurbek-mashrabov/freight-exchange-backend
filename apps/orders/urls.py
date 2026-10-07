"""URL configuration for orders app."""

from django.urls import path

from apps.orders import views

urlpatterns = [
    path("orders", views.OrderListView.as_view(), name="order-list"),
    path("orders/<int:pk>", views.OrderDetailView.as_view(), name="order-detail"),
    path("orders/<int:pk>/status", views.OrderStatusView.as_view(), name="order-status"),
    path(
        "orders/<int:pk>/documents",
        views.OrderDocumentUploadView.as_view(),
        name="order-documents",
    ),
    path("orders/<int:pk>/rating", views.OrderRatingView.as_view(), name="order-rating"),
]
