"""Admin configuration for geo reference data."""

from typing import Any

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.geo.models import Country, Currency, ExchangeRate
from apps.geo.services import (
    invalidate_countries_cache,
    invalidate_currencies_cache,
    invalidate_exchange_rates_cache,
)


class HasFlagFilter(admin.SimpleListFilter):
    """Filter countries by whether they have a flag URL configured."""

    title = "Has Flag"
    parameter_name = "has_flag"

    def lookups(
        self, request: HttpRequest, model_admin: admin.ModelAdmin
    ) -> list[tuple[str, str]]:
        """Return filter lookup options."""
        return [("yes", "Yes"), ("no", "No")]

    def queryset(
        self, request: HttpRequest, queryset: QuerySet[Country]
    ) -> QuerySet[Country]:
        """Apply filter based on selected option."""
        if self.value() == "yes":
            return queryset.exclude(flag_url="")
        if self.value() == "no":
            return queryset.filter(flag_url="")
        return queryset


@admin.register(Country)
class CountryAdmin(admin.ModelAdmin):
    """Admin interface for Country reference data."""

    list_display = ("code", "name_en", "name_ru", "name_uz", "flag_url")
    search_fields = ("code",)
    list_filter = (HasFlagFilter,)
    ordering = ("code",)

    @admin.display(description="Name (EN)")
    def name_en(self, obj: Country) -> str:
        """Return English name."""
        return obj.name_i18n.get("en", "") if isinstance(obj.name_i18n, dict) else ""

    @admin.display(description="Name (RU)")
    def name_ru(self, obj: Country) -> str:
        """Return Russian name."""
        return obj.name_i18n.get("ru", "") if isinstance(obj.name_i18n, dict) else ""

    @admin.display(description="Name (UZ)")
    def name_uz(self, obj: Country) -> str:
        """Return Uzbek name."""
        return obj.name_i18n.get("uz", "") if isinstance(obj.name_i18n, dict) else ""

    def save_model(
        self,
        request: HttpRequest,
        obj: Country,
        form: Any,
        change: bool,
    ) -> None:
        """Save model and purge country cache."""
        super().save_model(request, obj, form, change)
        invalidate_countries_cache()

    def delete_model(self, request: HttpRequest, obj: Country) -> None:
        """Delete model and purge country cache."""
        super().delete_model(request, obj)
        invalidate_countries_cache()

    def delete_queryset(
        self, request: HttpRequest, queryset: QuerySet[Country]
    ) -> None:
        """Bulk delete models and purge country cache."""
        super().delete_queryset(request, queryset)
        invalidate_countries_cache()


@admin.register(Currency)
class CurrencyAdmin(admin.ModelAdmin):
    """Admin interface for Currency reference data."""

    list_display = ("code", "name")
    search_fields = ("code", "name")
    list_filter = ("code",)
    ordering = ("code",)

    def save_model(
        self,
        request: HttpRequest,
        obj: Currency,
        form: Any,
        change: bool,
    ) -> None:
        """Save model and purge currency and exchange rate caches."""
        super().save_model(request, obj, form, change)
        invalidate_currencies_cache()

    def delete_model(self, request: HttpRequest, obj: Currency) -> None:
        """Delete model and purge currency and exchange rate caches."""
        super().delete_model(request, obj)
        invalidate_currencies_cache()

    def delete_queryset(
        self, request: HttpRequest, queryset: QuerySet[Currency]
    ) -> None:
        """Bulk delete models and purge currency and exchange rate caches."""
        super().delete_queryset(request, queryset)
        invalidate_currencies_cache()


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    """Admin interface for ExchangeRate reference data."""

    list_display = ("base", "quote", "rate", "fetched_at")
    list_filter = ("base", "quote", "fetched_at")
    search_fields = ("base__code", "quote__code", "base__name", "quote__name")
    ordering = ("-fetched_at",)
    date_hierarchy = "fetched_at"

    def save_model(
        self,
        request: HttpRequest,
        obj: ExchangeRate,
        form: Any,
        change: bool,
    ) -> None:
        """Save model and purge exchange rate cache."""
        super().save_model(request, obj, form, change)
        invalidate_exchange_rates_cache()

    def delete_model(self, request: HttpRequest, obj: ExchangeRate) -> None:
        """Delete model and purge exchange rate cache."""
        super().delete_model(request, obj)
        invalidate_exchange_rates_cache()

    def delete_queryset(
        self, request: HttpRequest, queryset: QuerySet[ExchangeRate]
    ) -> None:
        """Bulk delete models and purge exchange rate cache."""
        super().delete_queryset(request, queryset)
        invalidate_exchange_rates_cache()
