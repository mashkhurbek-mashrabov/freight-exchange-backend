"""URL configuration for notifications app."""

from django.urls import path

from apps.notifications.views import (
    NotificationListView,
    NotificationReadAllView,
    NotificationReadView,
)

urlpatterns = [
    path("notifications", NotificationListView.as_view(), name="notification-list"),
    path("notifications/<int:pk>/read", NotificationReadView.as_view(), name="notification-read"),
    path("notifications/read-all", NotificationReadAllView.as_view(), name="notification-read-all"),
]
