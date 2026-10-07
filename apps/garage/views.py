"""API views for garage app."""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
)
from rest_framework import generics, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.pagination import DefaultPagination
from apps.core.serializers import ErrorSerializer, ValidationErrorSerializer
from apps.garage import services as garage_services
from apps.garage.models import Vehicle, VehicleType
from apps.garage.serializers import (
    VehicleCreateUpdateSerializer,
    VehicleSerializer,
    VehicleTypeSerializer,
)


@extend_schema(
    tags=["Reference"],
    summary="List vehicle types",
    description="Retrieve all vehicle and body types, optionally filtered by kind.",
    parameters=[
        OpenApiParameter(
            name="kind",
            description="Filter by kind (tractor or trailer)",
            required=False,
            type=str,
        ),
    ],
    responses={
        200: VehicleTypeSerializer(many=True),
        401: ErrorSerializer,
    },
)
class VehicleTypeListView(generics.ListAPIView):
    """Reference endpoint listing vehicle types without pagination."""

    permission_classes = [IsAuthenticated]
    serializer_class = VehicleTypeSerializer
    pagination_class = None
    queryset = VehicleType.objects.all()

    def get_queryset(self):
        qs = VehicleType.objects.all().order_by("id")
        kind = self.request.query_params.get("kind")
        if kind:
            qs = qs.filter(kind=kind)
        return qs


@extend_schema_view(
    get=extend_schema(
        tags=["Garage"],
        summary="List user vehicles",
        description="List active vehicles belonging to the authenticated user.",
        parameters=[
            OpenApiParameter(
                name="kind",
                description="Filter by vehicle kind (tractor or trailer)",
                required=False,
                type=str,
            ),
        ],
        responses={
            200: VehicleSerializer(many=True),
            401: ErrorSerializer,
        },
    ),
    post=extend_schema(
        tags=["Garage"],
        summary="Create a vehicle",
        description=(
            "Create a new vehicle in the authenticated user's garage. "
            "Supports multipart/form-data for tech_passport_image uploads."
        ),
        request=VehicleCreateUpdateSerializer,
        responses={
            201: VehicleSerializer,
            400: ValidationErrorSerializer,
            401: ErrorSerializer,
        },
        examples=[
            OpenApiExample(
                "Create vehicle example",
                value={
                    "kind": "tractor",
                    "plate_number": "01A123AA",
                    "vehicle_type_id": 1,
                    "brand": "Mercedes-Benz",
                    "owner_full_name": "Alisher Navoiy",
                    "tech_passport_no": "AAF1234567",
                },
                request_only=True,
            ),
        ],
    ),
)
class VehicleListCreateView(generics.GenericAPIView):
    """List active user vehicles or create a new vehicle."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    pagination_class = DefaultPagination
    serializer_class = VehicleSerializer
    queryset = Vehicle.objects.none()

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False) or not self.request.user.is_authenticated:
            return Vehicle.objects.none()
        qs = (
            Vehicle.objects.filter(owner=self.request.user, is_active=True)
            .select_related("vehicle_type", "paired_vehicle")
            .order_by("-id")
        )
        kind = self.request.query_params.get("kind")
        if kind:
            qs = qs.filter(kind=kind)
        return qs

    def get(self, request: Request, *args, **kwargs) -> Response:
        qs = self.get_queryset()
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = VehicleSerializer(page, many=True, context={"request": request})
            return self.get_paginated_response(serializer.data)
        serializer = VehicleSerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)

    def post(self, request: Request, *args, **kwargs) -> Response:
        write_serializer = VehicleCreateUpdateSerializer(
            data=request.data,
            context={"request": request},
        )
        write_serializer.is_valid(raise_exception=True)
        validated_data = write_serializer.validated_data

        vehicle = garage_services.create_vehicle(
            owner=request.user,
            **validated_data,
        )
        output_serializer = VehicleSerializer(vehicle, context={"request": request})
        return Response(output_serializer.data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(
        tags=["Garage"],
        summary="Retrieve vehicle details",
        description="Retrieve an active vehicle owned by the authenticated user.",
        responses={
            200: VehicleSerializer,
            401: ErrorSerializer,
            404: ErrorSerializer,
        },
    ),
    patch=extend_schema(
        tags=["Garage"],
        summary="Update a vehicle",
        description="Partially update a vehicle owned by the authenticated user.",
        request=VehicleCreateUpdateSerializer,
        responses={
            200: VehicleSerializer,
            400: ValidationErrorSerializer,
            401: ErrorSerializer,
            404: ErrorSerializer,
        },
    ),
    delete=extend_schema(
        tags=["Garage"],
        summary="Soft delete a vehicle",
        description="Soft delete a vehicle (set is_active=False) and unpair related vehicles.",
        responses={
            204: None,
            401: ErrorSerializer,
            404: ErrorSerializer,
        },
    ),
)
class VehicleDetailView(generics.GenericAPIView):
    """Retrieve, update, or soft delete an active vehicle owned by the user."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    serializer_class = VehicleSerializer
    queryset = Vehicle.objects.none()

    def get_object(self) -> Vehicle:
        return get_object_or_404(
            Vehicle.objects.select_related("vehicle_type", "paired_vehicle"),
            pk=self.kwargs["pk"],
            owner=self.request.user,
            is_active=True,
        )

    def get(self, request: Request, *args, **kwargs) -> Response:
        vehicle = self.get_object()
        serializer = VehicleSerializer(vehicle, context={"request": request})
        return Response(serializer.data)

    def patch(self, request: Request, *args, **kwargs) -> Response:
        vehicle = self.get_object()
        write_serializer = VehicleCreateUpdateSerializer(
            vehicle,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        write_serializer.is_valid(raise_exception=True)
        updated_vehicle = garage_services.update_vehicle(
            vehicle,
            **write_serializer.validated_data,
        )
        output_serializer = VehicleSerializer(updated_vehicle, context={"request": request})
        return Response(output_serializer.data)

    def delete(self, request: Request, *args, **kwargs) -> Response:
        vehicle = self.get_object()
        garage_services.deactivate_vehicle(vehicle)
        return Response(status=status.HTTP_204_NO_CONTENT)
