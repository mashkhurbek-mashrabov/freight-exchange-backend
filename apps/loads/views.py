"""Views for loads app write and detail operations."""

from typing import Any

from django.http import Http404
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import generics, serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.core.permissions import HasRole, IsVerified
from apps.core.serializers import ErrorSerializer
from apps.loads.models import Load
from apps.loads.serializers import LoadDetailSerializer, LoadWriteSerializer
from apps.loads.services import (
    add_favorite,
    cancel_load,
    create_load,
    publish_load,
    remove_favorite,
    update_load,
)

CREATE_LOAD_EXAMPLE = OpenApiExample(
    name="Create load example",
    summary="Create load with 3-point route and payment terms",
    description=(
        "Payload creating a draft load with Tashkent -> Border -> Moscow route and payment terms."
    ),
    value={
        "cargo_description": "Electronics and consumer appliances",
        "cargo_type": "appliances",
        "weight_t": "18.500",
        "volume_m3": "86.000",
        "length_m": "13.60",
        "packaging": "pallet",
        "transport_mode": "FTL",
        "vehicle_category": "curtainsider",
        "trucks_needed": 1,
        "is_adr": False,
        "temp_controlled": False,
        "price_amount": "3200.00",
        "currency": "USD",
        "vat_included": False,
        "price_negotiable": True,
        "body_types": [1],
        "route_points": [
            {
                "seq": 1,
                "kind": "loading",
                "country": "UZ",
                "address": "Tashkent, Uzbekistan",
                "lat": "41.299496",
                "lng": "69.240073",
                "asap": True,
                "ready_to_load": True,
                "comment": "Warehouse gate #4",
            },
            {
                "seq": 2,
                "kind": "customs",
                "country": "KZ",
                "address": "Zhibek Zholy customs post",
                "lat": "43.344990",
                "lng": "68.257320",
                "comment": "Customs clearance checkpoint",
            },
            {
                "seq": 3,
                "kind": "unloading",
                "country": "RU",
                "address": "Moscow, Russia",
                "lat": "55.755826",
                "lng": "37.617300",
                "comment": "Central distribution terminal",
            },
        ],
        "payment_terms": {
            "prepay_amount": "1000.00",
            "prepay_method": "transfer",
            "paid_amount": "2200.00",
            "paid_method": "transfer",
            "remaining_amount": "0.00",
            "payment_due_days": 7,
            "conditions": "Payment within 7 days upon delivery and invoice receipt.",
        },
    },
    request_only=True,
)


@extend_schema(
    tags=["Loads"],
    summary="Create load",
    description="Creates a new freight load in draft status with route points and payment terms.",
    request=LoadWriteSerializer,
    responses={
        201: LoadDetailSerializer,
        400: ErrorSerializer,
        401: ErrorSerializer,
        403: ErrorSerializer,
        409: ErrorSerializer,
    },
    examples=[CREATE_LOAD_EXAMPLE],
)
class LoadCreateView(generics.CreateAPIView):
    """Endpoint for posting new loads (shipper role and verified account required)."""

    permission_classes = [IsVerified, HasRole.of("shipper", "both")]
    serializer_class = LoadWriteSerializer

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        load = create_load(request.user, serializer.validated_data)
        response_serializer = LoadDetailSerializer(load, context={"request": request})
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class LoadDetailView(generics.GenericAPIView):
    """Retrieve load details or partially update load attributes."""

    permission_classes = [IsAuthenticated]
    serializer_class = LoadDetailSerializer

    @extend_schema(
        tags=["Loads"],
        summary="Get load details",
        description=(
            "Retrieve full load details. Draft loads are visible only to the posting shipper."
        ),
        responses={
            200: LoadDetailSerializer,
            401: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def get(self, request: Request, pk: int, *args: Any, **kwargs: Any) -> Response:
        load = get_object_or_404(
            Load.objects.select_related(
                "company", "shipper", "shipper__company", "currency"
            ).prefetch_related(
                "route_points__country", "body_types", "documents"
            ),
            pk=pk,
        )
        if load.status == Load.Status.DRAFT and load.shipper_id != request.user.id:
            raise Http404("Load not found.")
        serializer = LoadDetailSerializer(load, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        tags=["Loads"],
        summary="Update load",
        description="Update draft or active load. Only the owning shipper may update.",
        request=LoadWriteSerializer,
        responses={
            200: LoadDetailSerializer,
            400: ErrorSerializer,
            401: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def patch(self, request: Request, pk: int, *args: Any, **kwargs: Any) -> Response:
        load = get_object_or_404(Load, pk=pk)
        write_serializer = LoadWriteSerializer(data=request.data, partial=True)
        write_serializer.is_valid(raise_exception=True)
        updated_load = update_load(load, write_serializer.validated_data, user=request.user)
        response_serializer = LoadDetailSerializer(updated_load, context={"request": request})
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class LoadPublishView(generics.GenericAPIView):
    """Publish a draft load to active status."""

    permission_classes = [IsVerified]
    serializer_class = LoadDetailSerializer

    @extend_schema(
        tags=["Loads"],
        summary="Publish load",
        description="Transition load from draft to active, setting published_at and expires_at.",
        request=None,
        responses={
            200: LoadDetailSerializer,
            400: ErrorSerializer,
            401: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request, pk: int, *args: Any, **kwargs: Any) -> Response:
        load = get_object_or_404(Load, pk=pk)
        published_load = publish_load(load, user=request.user)
        serializer = LoadDetailSerializer(published_load, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class LoadCancelView(generics.GenericAPIView):
    """Cancel a draft or active load."""

    permission_classes = [IsAuthenticated]
    serializer_class = LoadDetailSerializer

    @extend_schema(
        tags=["Loads"],
        summary="Cancel load",
        description="Cancel a load and reject any pending offers, notifying carriers.",
        request=None,
        responses={
            200: LoadDetailSerializer,
            400: ErrorSerializer,
            401: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request, pk: int, *args: Any, **kwargs: Any) -> Response:
        load = get_object_or_404(Load, pk=pk)
        cancelled_load = cancel_load(load, user=request.user)
        serializer = LoadDetailSerializer(cancelled_load, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class LoadFavoriteView(generics.GenericAPIView):
    """Bookmark or unbookmark a load in favorites."""

    permission_classes = [IsAuthenticated]
    serializer_class = serializers.Serializer

    @extend_schema(
        tags=["Loads"],
        summary="Add load to favorites",
        description="Add the load to the current user's favorites (idempotent).",
        request=None,
        responses={
            204: None,
            401: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def post(self, request: Request, pk: int, *args: Any, **kwargs: Any) -> Response:
        load = get_object_or_404(Load, pk=pk)
        if load.status == Load.Status.DRAFT and load.shipper_id != request.user.id:
            raise Http404("Load not found.")
        add_favorite(request.user, load)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        tags=["Loads"],
        summary="Remove load from favorites",
        description="Remove the load from the current user's favorites (idempotent).",
        request=None,
        responses={
            204: None,
            401: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def delete(self, request: Request, pk: int, *args: Any, **kwargs: Any) -> Response:
        load = get_object_or_404(Load, pk=pk)
        if load.status == Load.Status.DRAFT and load.shipper_id != request.user.id:
            raise Http404("Load not found.")
        remove_favorite(request.user, load)
        return Response(status=status.HTTP_204_NO_CONTENT)
