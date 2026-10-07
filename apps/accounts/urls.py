"""URL configuration for accounts app."""

from django.urls import path

from apps.accounts import views

urlpatterns = [
    path("auth/otp/request", views.OtpRequestView.as_view(), name="otp-request"),
    path("auth/otp/verify", views.OtpVerifyView.as_view(), name="otp-verify"),
    path(
        "auth/token/refresh",
        views.TokenRefreshCustomView.as_view(),
        name="token-refresh",
    ),
    path("auth/logout", views.LogoutView.as_view(), name="logout"),
    path("me", views.MeView.as_view(), name="me"),
    path("me/company", views.MeCompanyView.as_view(), name="me-company"),
    path("me/devices", views.MeDeviceView.as_view(), name="me-devices"),
    path(
        "me/devices/<str:token>",
        views.MeDeviceDeleteView.as_view(),
        name="me-device-delete",
    ),
]
