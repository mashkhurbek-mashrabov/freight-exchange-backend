"""URL configuration for geo app."""

from django.urls import path

from apps.geo.views import CountryListView, CurrencyListView, ExchangeRateListView

urlpatterns = [
    path("countries", CountryListView.as_view(), name="country-list"),
    path("currencies", CurrencyListView.as_view(), name="currency-list"),
    path("exchange-rates", ExchangeRateListView.as_view(), name="exchange-rate-list"),
]
