"""FilterSet definitions for loads read endpoints."""

from typing import Any

import django_filters
from django import forms
from django.db.models import Exists, F, OuterRef, Q, QuerySet

from apps.garage.models import Vehicle, VehicleType
from apps.loads.models import Load
from apps.offers.models import Offer


class CommaSeparatedModelMultipleChoiceField(forms.ModelMultipleChoiceField):
    """Multiple choice field accepting both comma-separated and repeated values."""

    def to_python(self, value: Any) -> Any:
        if not value:
            return []
        if isinstance(value, str):
            value = [v.strip() for v in value.split(",") if v.strip()]
        elif isinstance(value, (list, tuple)):
            expanded = []
            for item in value:
                if isinstance(item, str) and "," in item:
                    expanded.extend([v.strip() for v in item.split(",") if v.strip()])
                else:
                    expanded.append(item)
            value = expanded
        return super().to_python(value)


class BodyTypesFilter(django_filters.ModelMultipleChoiceFilter):
    """Filter loads by vehicle body types, supporting multiple and comma-separated IDs."""

    field_class = CommaSeparatedModelMultipleChoiceField

    def filter(self, qs: QuerySet[Load], value: Any) -> QuerySet[Load]:
        if not value:
            return qs
        return qs.filter(body_types__in=value).distinct()


class LoadFilter(django_filters.FilterSet):
    """Comprehensive filter set for load search and listing."""

    origin_country = django_filters.CharFilter(
        method="filter_origin_country",
        help_text="Country code of origin (first loading point).",
    )
    destination_country = django_filters.CharFilter(
        method="filter_destination_country",
        help_text="Country code of destination (last unloading point).",
    )
    body_types = BodyTypesFilter(
        queryset=VehicleType.objects.all(),
        help_text="Body type IDs (repeated or comma-separated).",
    )
    weight_min = django_filters.NumberFilter(
        field_name="weight_t",
        lookup_expr="gte",
        help_text="Minimum cargo weight in tonnes.",
    )
    weight_max = django_filters.NumberFilter(
        field_name="weight_t",
        lookup_expr="lte",
        help_text="Maximum cargo weight in tonnes.",
    )
    volume_min = django_filters.NumberFilter(
        field_name="volume_m3",
        lookup_expr="gte",
        help_text="Minimum cargo volume in cubic meters.",
    )
    volume_max = django_filters.NumberFilter(
        field_name="volume_m3",
        lookup_expr="lte",
        help_text="Maximum cargo volume in cubic meters.",
    )
    price_min = django_filters.NumberFilter(
        field_name="price_amount",
        lookup_expr="gte",
        help_text="Minimum price amount.",
    )
    price_max = django_filters.NumberFilter(
        field_name="price_amount",
        lookup_expr="lte",
        help_text="Maximum price amount.",
    )
    currency = django_filters.CharFilter(
        field_name="currency__code",
        lookup_expr="iexact",
        help_text="Currency 3-letter code (e.g. USD, UZS).",
    )
    loading_from = django_filters.IsoDateTimeFilter(
        method="filter_loading_from",
        help_text="Earliest planned loading date/time (ISO 8601).",
    )
    loading_to = django_filters.IsoDateTimeFilter(
        method="filter_loading_to",
        help_text="Latest planned loading date/time (ISO 8601).",
    )
    unloading_from = django_filters.IsoDateTimeFilter(
        method="filter_unloading_from",
        help_text="Earliest planned unloading date/time (ISO 8601).",
    )
    unloading_to = django_filters.IsoDateTimeFilter(
        method="filter_unloading_to",
        help_text="Latest planned unloading date/time (ISO 8601).",
    )
    is_adr = django_filters.BooleanFilter(
        field_name="is_adr",
        help_text="Filter dangerous goods (ADR).",
    )
    temp_controlled = django_filters.BooleanFilter(
        field_name="temp_controlled",
        help_text="Filter temperature controlled cargo.",
    )
    has_offers = django_filters.BooleanFilter(
        method="filter_has_offers",
        help_text="Filter loads with (true) or without (false) offers.",
    )
    transport_mode = django_filters.ChoiceFilter(
        choices=Load.TransportMode.choices,
        help_text="Transport mode: FTL or LTL.",
    )
    suitable = django_filters.BooleanFilter(
        method="filter_suitable",
        help_text="Rule 11: Filter loads matching requester's active vehicle body types.",
    )
    search = django_filters.CharFilter(
        method="filter_search",
        help_text="Search text in cargo description, origin, and destination address.",
    )
    ordering = django_filters.CharFilter(
        method="filter_ordering",
        help_text="Ordering: -published_at, distance_km, -price_amount, price_per_km, etc.",
    )

    ORDERING_MAP = {
        "-published_at": F("published_at").desc(nulls_last=True),
        "published_at": F("published_at").asc(nulls_last=True),
        "distance_km": F("distance_km").asc(nulls_last=True),
        "-distance_km": F("distance_km").desc(nulls_last=True),
        "price_amount": F("price_amount").asc(nulls_last=True),
        "-price_amount": F("price_amount").desc(nulls_last=True),
        "price_per_km": F("price_per_km").asc(nulls_last=True),
        "-price_per_km": F("price_per_km").desc(nulls_last=True),
    }

    class Meta:
        model = Load
        fields = [
            "origin_country",
            "destination_country",
            "body_types",
            "weight_min",
            "weight_max",
            "volume_min",
            "volume_max",
            "price_min",
            "price_max",
            "currency",
            "loading_from",
            "loading_to",
            "unloading_from",
            "unloading_to",
            "is_adr",
            "temp_controlled",
            "has_offers",
            "transport_mode",
            "suitable",
            "search",
            "ordering",
        ]

    def filter_origin_country(
        self, queryset: QuerySet[Load], name: str, value: Any
    ) -> QuerySet[Load]:
        if not value:
            return queryset
        return queryset.filter(origin_country_code__iexact=str(value).strip())

    def filter_destination_country(
        self, queryset: QuerySet[Load], name: str, value: Any
    ) -> QuerySet[Load]:
        if not value:
            return queryset
        return queryset.filter(destination_country_code__iexact=str(value).strip())

    def filter_loading_from(
        self, queryset: QuerySet[Load], name: str, value: Any
    ) -> QuerySet[Load]:
        if not value:
            return queryset
        return queryset.filter(first_loading_planned_from__gte=value)

    def filter_loading_to(
        self, queryset: QuerySet[Load], name: str, value: Any
    ) -> QuerySet[Load]:
        if not value:
            return queryset
        return queryset.filter(first_loading_planned_from__lte=value)

    def filter_unloading_from(
        self, queryset: QuerySet[Load], name: str, value: Any
    ) -> QuerySet[Load]:
        if not value:
            return queryset
        return queryset.filter(last_unloading_planned_from__gte=value)

    def filter_unloading_to(
        self, queryset: QuerySet[Load], name: str, value: Any
    ) -> QuerySet[Load]:
        if not value:
            return queryset
        return queryset.filter(last_unloading_planned_from__lte=value)

    def filter_has_offers(
        self, queryset: QuerySet[Load], name: str, value: Any
    ) -> QuerySet[Load]:
        if value is True:
            return queryset.filter(Exists(Offer.objects.filter(load=OuterRef("pk"))))
        if value is False:
            return queryset.filter(~Exists(Offer.objects.filter(load=OuterRef("pk"))))
        return queryset

    def filter_suitable(
        self, queryset: QuerySet[Load], name: str, value: Any
    ) -> QuerySet[Load]:
        if value is None:
            return queryset
        user = getattr(self.request, "user", None)
        if not user or not user.is_authenticated:
            return queryset.none() if value is True else queryset

        active_type_ids = set(
            Vehicle.objects.filter(
                owner=user,
                is_active=True,
                vehicle_type__isnull=False,
            ).values_list("vehicle_type_id", flat=True)
        )

        if value is True:
            if not active_type_ids:
                return queryset.filter(body_types__isnull=True).distinct()
            return queryset.filter(
                Q(body_types__isnull=True) | Q(body_types__id__in=active_type_ids)
            ).distinct()

        if value is False:
            if not active_type_ids:
                return queryset.filter(body_types__isnull=False).distinct()
            return (
                queryset.filter(body_types__isnull=False)
                .exclude(body_types__id__in=active_type_ids)
                .distinct()
            )

        return queryset

    def filter_search(
        self, queryset: QuerySet[Load], name: str, value: Any
    ) -> QuerySet[Load]:
        if not value or not str(value).strip():
            return queryset
        term = str(value).strip()
        return queryset.filter(
            Q(cargo_description__icontains=term)
            | Q(origin_address__icontains=term)
            | Q(destination_address__icontains=term)
        ).distinct()

    def filter_ordering(
        self, queryset: QuerySet[Load], name: str, value: Any
    ) -> QuerySet[Load]:
        if not value:
            return queryset.order_by(F("published_at").desc(nulls_last=True), "-id")
        tokens = [v.strip() for v in str(value).split(",") if v.strip()]
        order_exprs = []
        for token in tokens:
            if token in self.ORDERING_MAP:
                order_exprs.append(self.ORDERING_MAP[token])
        if order_exprs:
            return queryset.order_by(*order_exprs, "-id")
        return queryset.order_by(F("published_at").desc(nulls_last=True), "-id")
