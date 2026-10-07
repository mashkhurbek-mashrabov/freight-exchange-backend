"""Combined GET (board list) + POST (create) endpoint on /loads."""

from typing import Any

from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.core.serializers import ErrorSerializer
from apps.loads.list_serializers import LoadCompactSerializer
from apps.loads.list_views import LoadListView
from apps.loads.serializers import LoadDetailSerializer, LoadWriteSerializer
from apps.loads.views import CREATE_LOAD_EXAMPLE, LoadCreateView


@extend_schema_view(
    get=extend_schema(
        tags=["Loads"],
        summary="List public active loads",
        description=(
            "Paginated board of active loads. Supports multi-field filtering, search and sorting."
        ),
        parameters=[
            OpenApiParameter(
                name="suitable",
                type=bool,
                description="Only loads matching the body types of my active vehicles.",
                required=False,
            ),
            OpenApiParameter(
                name="ordering",
                type=str,
                description=(
                    "-published_at (default), distance_km, -distance_km, price_amount, "
                    "-price_amount, price_per_km, -price_per_km"
                ),
                required=False,
            ),
        ],
        responses={
            200: LoadCompactSerializer(many=True),
            400: ErrorSerializer,
            401: ErrorSerializer,
        },
    ),
    post=extend_schema(
        tags=["Loads"],
        summary="Create load",
        description="Creates a new freight load in draft status with route points and terms.",
        request=LoadWriteSerializer,
        responses={
            201: LoadDetailSerializer,
            400: ErrorSerializer,
            401: ErrorSerializer,
            403: ErrorSerializer,
            409: ErrorSerializer,
        },
        examples=[CREATE_LOAD_EXAMPLE],
    ),
)
class LoadListCreateView(generics.ListCreateAPIView):
    """GET: public board of active loads. POST: create a draft load (verified shipper)."""

    pagination_class = LoadListView.pagination_class
    filter_backends = LoadListView.filter_backends
    filterset_class = LoadListView.filterset_class
    get_queryset = LoadListView.get_queryset
    create = LoadCreateView.create

    def get_serializer_class(self) -> Any:
        if self.request.method == "POST":
            return LoadWriteSerializer
        return LoadCompactSerializer

    def get_permissions(self) -> list:
        if self.request.method == "POST":
            return [p() for p in LoadCreateView.permission_classes]
        return [IsAuthenticated()]
