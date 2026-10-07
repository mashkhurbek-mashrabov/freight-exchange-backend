"""Views for loads read side: list, mine, favorites, and map."""

from decimal import Decimal

from django.db.models import (
    Count,
    DecimalField,
    ExpressionWrapper,
    F,
    OuterRef,
    QuerySet,
    Subquery,
)
from django.db.models.functions import Coalesce, NullIf
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.pagination import DefaultPagination
from apps.core.serializers import ErrorSerializer, ValidationErrorSerializer
from apps.loads.filters import LoadFilter
from apps.loads.list_serializers import (
    LoadCompactSerializer,
    LoadMapItemSerializer,
    LoadMineSerializer,
)
from apps.loads.models import Load, RoutePoint


def get_optimized_loads_queryset() -> QuerySet[Load]:
    """Return Load queryset optimized with Subquery annotations for constant query count."""
    first_loading = RoutePoint.objects.filter(
        load=OuterRef("pk"),
        kind=RoutePoint.Kind.LOADING,
    ).order_by("seq")

    last_unloading = RoutePoint.objects.filter(
        load=OuterRef("pk"),
        kind=RoutePoint.Kind.UNLOADING,
    ).order_by("-seq")

    return (
        Load.objects.select_related("currency")
        .annotate(
            origin_country_code=Subquery(first_loading.values("country_id")[:1]),
            origin_address=Subquery(first_loading.values("address")[:1]),
            destination_country_code=Subquery(last_unloading.values("country_id")[:1]),
            destination_address=Subquery(last_unloading.values("address")[:1]),
            first_loading_planned_from=Subquery(first_loading.values("planned_from")[:1]),
            last_unloading_planned_from=Subquery(last_unloading.values("planned_from")[:1]),
            first_loading_lat=Subquery(first_loading.values("lat")[:1]),
            first_loading_lng=Subquery(first_loading.values("lng")[:1]),
            shipper_company=Coalesce("company__name", "shipper__company__name"),
            price_per_km=ExpressionWrapper(
                F("price_amount") / NullIf(F("distance_km"), 0),
                output_field=DecimalField(max_digits=18, decimal_places=2),
            ),
        )
        .prefetch_related("body_types")
    )


@extend_schema(
    tags=["Loads"],
    summary="List public active loads",
    description=(
        "Retrieve a paginated list of active loads on the board. "
        "Supports multi-field filtering, search, and sorting."
    ),
    parameters=[
        OpenApiParameter(
            name="suitable",
            type=bool,
            description="Rule 11: loads matching requester active vehicle body types.",
            required=False,
        ),
        OpenApiParameter(
            name="ordering",
            type=str,
            description=(
                "Ordering: -published_at (default), published_at, distance_km, "
                "-distance_km, price_amount, -price_amount, price_per_km, -price_per_km"
            ),
            required=False,
        ),
    ],
    responses={
        200: LoadCompactSerializer(many=True),
        400: ErrorSerializer,
        401: ErrorSerializer,
    },
)
class LoadListView(generics.ListAPIView):
    """Public load board listing active loads with filtering and sorting."""

    permission_classes = [IsAuthenticated]
    serializer_class = LoadCompactSerializer
    pagination_class = DefaultPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = LoadFilter

    def get_queryset(self) -> QuerySet[Load]:
        """Return active loads ordered by newest published date by default."""
        return (
            get_optimized_loads_queryset()
            .filter(status=Load.Status.ACTIVE)
            .order_by(F("published_at").desc(nulls_last=True), "-id")
        )


@extend_schema(
    tags=["Loads"],
    summary="List shipper's own loads",
    description="Retrieve a paginated list of loads created by the authenticated shipper.",
    responses={
        200: LoadMineSerializer(many=True),
        401: ErrorSerializer,
    },
)
class LoadMineView(generics.ListAPIView):
    """List shipper's own loads across all statuses."""

    permission_classes = [IsAuthenticated]
    serializer_class = LoadMineSerializer
    pagination_class = DefaultPagination

    def get_queryset(self) -> QuerySet[Load]:
        """Return current user's loads across all statuses with offers count."""
        if getattr(self, "swagger_fake_view", False) or not self.request.user.is_authenticated:
            return Load.objects.none()

        return (
            get_optimized_loads_queryset()
            .filter(shipper=self.request.user)
            .annotate(offers_count=Count("offers", distinct=True))
            .order_by("-created_at", "-id")
        )


@extend_schema(
    tags=["Loads"],
    summary="List user's favorite loads",
    description="Retrieve a paginated list of loads favorited by the current user.",
    responses={
        200: LoadCompactSerializer(many=True),
        401: ErrorSerializer,
    },
)
class MyFavoritesView(generics.ListAPIView):
    """List loads bookmarked as favorite by authenticated user."""

    permission_classes = [IsAuthenticated]
    serializer_class = LoadCompactSerializer
    pagination_class = DefaultPagination

    def get_queryset(self) -> QuerySet[Load]:
        """Return bookmarked loads ordered by newest favorite bookmark first."""
        if getattr(self, "swagger_fake_view", False) or not self.request.user.is_authenticated:
            return Load.objects.none()

        return (
            get_optimized_loads_queryset()
            .filter(favorites__user=self.request.user)
            .order_by("-favorites__created_at", "-id")
        )


class LoadMapView(APIView):
    """Retrieve map markers for active loads within bounding box."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Loads"],
        summary="List loads on map",
        description=(
            "Retrieve up to 500 active loads with first loading point coordinates "
            "within the specified bounding box (minLng,minLat,maxLng,maxLat)."
        ),
        parameters=[
            OpenApiParameter(
                name="bbox",
                type=str,
                required=True,
                description="Bounding box in format 'minLng,minLat,maxLng,maxLat'.",
            ),
        ],
        responses={
            200: LoadMapItemSerializer(many=True),
            400: ValidationErrorSerializer,
            401: ErrorSerializer,
        },
    )
    def get(self, request: Request) -> Response:
        """Return unpaginated marker items for active loads inside bounding box."""
        bbox = request.query_params.get("bbox")
        if not bbox:
            raise ValidationError({"bbox": "bbox query parameter is required."})

        parts = [p.strip() for p in bbox.split(",") if p.strip()]
        if len(parts) != 4:
            raise ValidationError(
                {"bbox": "Invalid bbox format. Expected minLng,minLat,maxLng,maxLat."}
            )

        try:
            min_lng = Decimal(parts[0])
            min_lat = Decimal(parts[1])
            max_lng = Decimal(parts[2])
            max_lat = Decimal(parts[3])
        except Exception:
            raise ValidationError(
                {"bbox": "Bounding box coordinates must be valid numbers."}
            ) from None

        if not (-180 <= min_lng <= 180 and -180 <= max_lng <= 180):
            raise ValidationError(
                {"bbox": "Longitude must be between -180 and 180 degrees."}
            )

        if not (-90 <= min_lat <= 90 and -90 <= max_lat <= 90):
            raise ValidationError(
                {"bbox": "Latitude must be between -90 and 90 degrees."}
            )

        if min_lng > max_lng:
            raise ValidationError({"bbox": "minLng cannot be greater than maxLng."})

        if min_lat > max_lat:
            raise ValidationError({"bbox": "minLat cannot be greater than maxLat."})

        first_loading = RoutePoint.objects.filter(
            load=OuterRef("pk"),
            kind=RoutePoint.Kind.LOADING,
        ).order_by("seq")

        qs = (
            Load.objects.filter(status=Load.Status.ACTIVE)
            .annotate(
                first_loading_lat=Subquery(first_loading.values("lat")[:1]),
                first_loading_lng=Subquery(first_loading.values("lng")[:1]),
            )
            .filter(
                first_loading_lat__isnull=False,
                first_loading_lng__isnull=False,
                first_loading_lng__gte=min_lng,
                first_loading_lng__lte=max_lng,
                first_loading_lat__gte=min_lat,
                first_loading_lat__lte=max_lat,
            )
            .order_by("-id")[:500]
        )

        serializer = LoadMapItemSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
