"""Filter classes for offers."""

from typing import Any

import django_filters
from django.db.models import QuerySet

from apps.offers.models import Offer


class OfferFilter(django_filters.FilterSet):
    """FilterSet for Offer list endpoint."""

    direction = django_filters.ChoiceFilter(
        choices=[("outgoing", "Outgoing"), ("incoming", "Incoming")],
        method="filter_direction",
        help_text="Filter by direction: 'outgoing' (proposer=me) or 'incoming' (recipient=me).",
    )
    status = django_filters.ChoiceFilter(
        choices=Offer.Status.choices,
        help_text="Filter offers by status (pending, accepted, rejected, cancelled, countered).",
    )

    class Meta:
        model = Offer
        fields = ["direction", "status"]

    def filter_direction(
        self, queryset: QuerySet[Offer], name: str, value: Any
    ) -> QuerySet[Offer]:
        """Filter queryset by offer direction relative to request user."""
        user = getattr(self.request, "user", None)
        if not user or not user.is_authenticated:
            return queryset.none()
        if value == "outgoing":
            return queryset.filter(proposer=user)
        if value == "incoming":
            return queryset.filter(recipient=user)
        return queryset
