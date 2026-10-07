"""Views for orders app."""

from typing import Any

from django.db.models import Q, QuerySet
from django.http import Http404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.pagination import DefaultPagination
from apps.core.permissions import IsVerified
from apps.core.serializers import ErrorSerializer
from apps.orders.filters import OrderFilter
from apps.orders.models import Order
from apps.orders.serializers import (
    OrderDetailSerializer,
    OrderDocumentSerializer,
    OrderDocumentUploadSerializer,
    OrderListSerializer,
    OrderRatingCreateSerializer,
    OrderStatusUpdateSerializer,
    RatingSerializer,
)
from apps.orders.services import add_document, change_status, rate_order


def get_order_detail_queryset() -> QuerySet[Order]:
    """Return pre-optimized queryset for order detail representation."""
    return (
        Order.objects.select_related(
            "load",
            "load__currency",
            "shipper",
            "shipper__company",
            "carrier",
            "carrier__company",
            "currency",
            "vehicle",
            "trailer",
        )
        .prefetch_related(
            "load__route_points",
            "load__route_points__country",
            "status_events",
            "status_events__actor",
            "documents",
            "documents__uploaded_by",
            "ratings",
            "ratings__rater",
            "ratings__ratee",
        )
    )


class OrderListView(generics.ListAPIView):
    """List orders for authenticated user as shipper or carrier."""

    permission_classes = [IsAuthenticated]
    pagination_class = DefaultPagination
    serializer_class = OrderListSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_class = OrderFilter
    queryset = Order.objects.none()

    def get_queryset(self) -> QuerySet[Order]:
        """Return orders where the user is either shipper or carrier."""
        if getattr(self, "swagger_fake_view", False) or not self.request.user.is_authenticated:
            return Order.objects.none()
        return (
            Order.objects.filter(
                Q(shipper=self.request.user) | Q(carrier=self.request.user)
            )
            .select_related(
                "load",
                "load__currency",
                "shipper",
                "shipper__company",
                "carrier",
                "carrier__company",
                "currency",
                "vehicle",
                "trailer",
            )
            .order_by("-id")
        )

    @extend_schema(
        tags=["Orders"],
        summary="List orders",
        description=(
            "Retrieve a paginated list of orders for the authenticated user "
            "(as shipper or carrier). Supports filtering by ?tab=active (in-progress orders) "
            "or ?tab=history (completed/cancelled orders). "
            "If tab parameter is omitted, all orders are returned."
        ),
        responses={
            200: OrderListSerializer(many=True),
            401: ErrorSerializer,
        },
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Handle GET request to list orders."""
        return super().get(request, *args, **kwargs)


class OrderDetailView(APIView):
    """Retrieve full details of an order."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Orders"],
        summary="Get order details",
        description=(
            "Retrieve comprehensive details of an order including load summary, route points, "
            "timeline status events, attached documents, ratings, and party contact information. "
            "Accessible only to the order's shipper and carrier."
        ),
        responses={
            200: OrderDetailSerializer,
            401: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def get(self, request: Request, pk: int) -> Response:
        """Handle GET request to fetch order details."""
        try:
            order = get_order_detail_queryset().get(pk=pk)
        except Order.DoesNotExist:
            raise Http404("Order not found.") from None

        if request.user.pk != order.carrier_id and request.user.pk != order.shipper_id:
            raise Http404("Order not found.")

        serializer = OrderDetailSerializer(order)
        return Response(serializer.data, status=status.HTTP_200_OK)


class OrderStatusView(APIView):
    """Transition order status following the role matrix."""

    permission_classes = [IsAuthenticated, IsVerified]

    @extend_schema(
        tags=["Orders"],
        summary="Update order status",
        description=(
            "Advance or cancel order status according to the strict state machine matrix.\n"
            "- Carrier-only transitions: received, picked_up, delivered, awaiting_confirm.\n"
            "- Shipper-only transition: completed (from awaiting_confirm).\n"
            "- Either party: cancelled (from created or received; note required "
            "as cancel_reason).\n"
            "Requires verified account status."
        ),
        request=OrderStatusUpdateSerializer,
        responses={
            200: OrderDetailSerializer,
            400: ErrorSerializer,
            401: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        examples=[
            OpenApiExample(
                name="Carrier advance status example",
                summary="Carrier transitions to received",
                value={
                    "status": "received",
                    "note": "Carrier received cargo at warehouse",
                },
                request_only=True,
            ),
            OpenApiExample(
                name="Cancellation example",
                summary="Party cancels order",
                value={
                    "status": "cancelled",
                    "note": "Technical failure with vehicle",
                },
                request_only=True,
            ),
            OpenApiExample(
                name="Status updated response example",
                summary="Order updated detail",
                value={
                    "id": 1,
                    "status": "received",
                    "cancel_reason": "",
                    "completed_at": None,
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request: Request, pk: int) -> Response:
        """Handle POST request to advance order status."""
        serializer = OrderStatusUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_status = serializer.validated_data["status"]
        note = (
            serializer.validated_data.get("note")
            or serializer.validated_data.get("cancel_reason")
            or ""
        )

        order = change_status(
            user=request.user,
            order_id=pk,
            new_status=new_status,
            note=note,
        )

        detail_order = get_order_detail_queryset().get(pk=order.pk)
        return Response(OrderDetailSerializer(detail_order).data, status=status.HTTP_200_OK)


class OrderDocumentUploadView(APIView):
    """Upload a document attached to an order."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @extend_schema(
        tags=["Orders"],
        summary="Upload order document",
        description=(
            "Attach a document (CMR, consignment note, invoice, photo) to an order. "
            "Accessible only to the order's parties. Automatically calculates size_kb."
        ),
        request=OrderDocumentUploadSerializer,
        responses={
            201: OrderDocumentSerializer,
            400: ErrorSerializer,
            401: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def post(self, request: Request, pk: int) -> Response:
        """Handle multipart POST request to upload order document."""
        serializer = OrderDocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        doc = add_document(
            user=request.user,
            order_id=pk,
            file=serializer.validated_data["file"],
            name=serializer.validated_data["name"],
        )
        return Response(OrderDocumentSerializer(doc).data, status=status.HTTP_201_CREATED)


class OrderRatingView(APIView):
    """Submit rating for a completed order."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Orders"],
        summary="Rate completed order",
        description=(
            "Submit a rating (1-5 stars, reason tags, and comment) for a completed order. "
            "Can only be submitted once per party. Recomputes ratee's company average rating "
            "and review count."
        ),
        request=OrderRatingCreateSerializer,
        responses={
            201: RatingSerializer,
            400: ErrorSerializer,
            401: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        examples=[
            OpenApiExample(
                name="Submit rating example",
                summary="Rate counterparty",
                value={
                    "stars": 5,
                    "reasons": ["punctual", "polite"],
                    "comment": "Excellent cooperation and fast delivery.",
                },
                request_only=True,
            ),
            OpenApiExample(
                name="Rating created response example",
                summary="Rating response",
                value={
                    "id": 1,
                    "order": 1,
                    "rater": {"id": 10, "full_name": "Carrier User"},
                    "ratee": {"id": 20, "full_name": "Shipper User"},
                    "stars": 5,
                    "reasons": ["punctual", "polite"],
                    "comment": "Excellent cooperation and fast delivery.",
                    "created_at": "2026-10-08T10:00:00Z",
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request: Request, pk: int) -> Response:
        """Handle POST request to rate an order."""
        serializer = OrderRatingCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        rating = rate_order(
            user=request.user,
            order_id=pk,
            stars=serializer.validated_data["stars"],
            reasons=serializer.validated_data.get("reasons", []),
            comment=serializer.validated_data.get("comment", ""),
        )
        return Response(RatingSerializer(rating).data, status=status.HTTP_201_CREATED)
