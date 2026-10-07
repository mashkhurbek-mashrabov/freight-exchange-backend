"""Filter classes for orders."""

from typing import Any

import django_filters
from django.db.models import QuerySet

from apps.orders.models import Order


class OrderFilter(django_filters.FilterSet):
    """Filter set for Order model."""

    tab = django_filters.CharFilter(
        method="filter_tab",
        help_text=(
            "Filter orders by tab: 'active' (not completed/cancelled) "
            "or 'history' (completed/cancelled)."
        ),
    )

    class Meta:
        model = Order
        fields = ["tab"]

    def filter_tab(
        self, queryset: QuerySet[Order], name: str, value: Any
    ) -> QuerySet[Order]:
        """Filter queryset by tab status."""
        if value == "active":
            return queryset.exclude(
                status__in=[Order.Status.COMPLETED, Order.Status.CANCELLED]
            )
        if value == "history":
            return queryset.filter(
                status__in=[Order.Status.COMPLETED, Order.Status.CANCELLED]
            )
        return queryset
