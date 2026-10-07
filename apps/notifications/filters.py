"""Filter classes for notifications."""

from typing import Any

import django_filters
from django.db.models import QuerySet

from apps.notifications.models import Notification


class NotificationFilter(django_filters.FilterSet):
    """Filter set for Notification model."""

    unread = django_filters.BooleanFilter(
        method="filter_unread",
        help_text="Filter unread notifications (true) or read notifications (false).",
    )

    class Meta:
        model = Notification
        fields = ["unread"]

    def filter_unread(
        self, queryset: QuerySet[Notification], name: str, value: Any
    ) -> QuerySet[Notification]:
        """Filter queryset by read status."""
        if value is True:
            return queryset.filter(read_at__isnull=True)
        if value is False:
            return queryset.filter(read_at__isnull=False)
        return queryset
