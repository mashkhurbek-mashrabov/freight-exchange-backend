"""API views for offers app."""

from typing import Any

from django.db.models import Prefetch, Q, QuerySet
from django.http import Http404
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.core.pagination import DefaultPagination
from apps.core.permissions import HasRole, IsVerified
from apps.core.serializers import ErrorSerializer
from apps.loads.models import Load, RoutePoint
from apps.offers import services
from apps.offers.filters import OfferFilter
from apps.offers.models import Offer
from apps.offers.serializers import (
    CounterOfferSerializer,
    OfferCreateSerializer,
    OfferSerializer,
)


def _offer_base_queryset() -> QuerySet[Offer]:
    """Return base Offer queryset with optimal select_related and prefetch_related."""
    return (
        Offer.objects.select_related(
            "load",
            "load__shipper",
            "load__currency",
            "carrier",
            "proposer",
            "recipient",
            "vehicle",
            "trailer",
            "parent",
            "currency",
        )
        .prefetch_related(
            Prefetch(
                "load__route_points",
                queryset=RoutePoint.objects.select_related("country").order_by("seq"),
            )
        )
    )


class LoadOfferCreateView(APIView):
    """Create an offer on a load."""

    permission_classes = [
        IsAuthenticated,
        IsVerified,
        HasRole.of(User.Role.CARRIER, User.Role.BOTH),
    ]

    @extend_schema(
        tags=["Offers"],
        summary="Create an offer on a load",
        description=(
            "Submit a new offer (price bid or comment only) on an active load. "
            "Requires verified carrier or both role. Load must be active and not owned by user."
        ),
        request=OfferCreateSerializer,
        responses={
            201: OfferSerializer,
            400: ErrorSerializer,
            401: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        examples=[
            OpenApiExample(
                "Create offer price bid example",
                value={
                    "mode": "price_bid",
                    "amount": "2400.00",
                    "currency": "USD",
                    "vehicle_id": 1,
                    "trailer_id": 2,
                    "comment": "Ready for pickup tomorrow at 9 AM.",
                },
                request_only=True,
            ),
        ],
    )
    def post(self, request: Request, load_id: int) -> Response:
        """Handle POST request to create an offer on a load."""
        serializer = OfferCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        load = get_object_or_404(Load, pk=load_id)
        offer = services.create_offer(
            carrier=request.user,
            load=load,
            data=serializer.validated_data,
        )
        # Re-fetch with select_related for complete representation
        offer = _offer_base_queryset().get(pk=offer.pk)
        return Response(OfferSerializer(offer).data, status=status.HTTP_201_CREATED)


class OfferListView(generics.ListAPIView):
    """List offers involving the authenticated user."""

    permission_classes = [IsAuthenticated]
    serializer_class = OfferSerializer
    pagination_class = DefaultPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = OfferFilter
    queryset = Offer.objects.none()

    def get_queryset(self) -> QuerySet[Offer]:
        """Return offers for current user ordered by newest first with constant query count."""
        if getattr(self, "swagger_fake_view", False) or not self.request.user.is_authenticated:
            return Offer.objects.none()
        user = self.request.user
        return (
            _offer_base_queryset()
            .filter(Q(proposer=user) | Q(recipient=user))
            .order_by("-created_at", "-id")
        )

    @extend_schema(
        tags=["Offers"],
        summary="List user offers",
        description=(
            "Retrieve a paginated list of offers involving the authenticated user (newest first). "
            "Filterable by direction (outgoing = proposer, incoming = recipient) and status."
        ),
        responses={
            200: OfferSerializer(many=True),
            401: ErrorSerializer,
        },
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Handle GET request to list offers."""
        return super().get(request, *args, **kwargs)


class OfferDetailView(APIView):
    """Retrieve details of a single offer."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Offers"],
        summary="Get offer details",
        description=(
            "Retrieve details of an offer. Accessible only by parties of the negotiation "
            "(proposer, recipient, or carrier); returns 404 otherwise."
        ),
        responses={
            200: OfferSerializer,
            401: ErrorSerializer,
            404: ErrorSerializer,
        },
    )
    def get(self, request: Request, pk: int) -> Response:
        """Handle GET request for offer details."""
        try:
            offer = _offer_base_queryset().get(pk=pk)
        except Offer.DoesNotExist:
            raise Http404("Offer not found.") from None

        if request.user.pk not in (offer.proposer_id, offer.recipient_id, offer.carrier_id):
            raise Http404("Offer not found.")

        return Response(OfferSerializer(offer).data)


class OfferAcceptView(APIView):
    """Accept a pending offer."""

    permission_classes = [IsAuthenticated, IsVerified]

    @extend_schema(
        tags=["Offers"],
        summary="Accept an offer",
        description=(
            "Accept a pending offer, create the corresponding Order, and update load status. "
            "Only the offer recipient can accept."
        ),
        request=None,
        responses={
            200: OfferSerializer,
            401: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request, pk: int) -> Response:
        """Handle POST request to accept an offer."""
        offer = services.accept_offer(user=request.user, offer_id=pk)
        offer = _offer_base_queryset().get(pk=offer.pk)
        return Response(OfferSerializer(offer).data, status=status.HTTP_200_OK)


class OfferRejectView(APIView):
    """Reject a pending offer."""

    permission_classes = [IsAuthenticated, IsVerified]

    @extend_schema(
        tags=["Offers"],
        summary="Reject an offer",
        description="Reject a pending offer. Only the offer recipient can reject.",
        request=None,
        responses={
            200: OfferSerializer,
            401: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request, pk: int) -> Response:
        """Handle POST request to reject an offer."""
        offer = services.reject_offer(user=request.user, offer_id=pk)
        offer = _offer_base_queryset().get(pk=offer.pk)
        return Response(OfferSerializer(offer).data, status=status.HTTP_200_OK)


class OfferCancelView(APIView):
    """Cancel a pending offer."""

    permission_classes = [IsAuthenticated, IsVerified]

    @extend_schema(
        tags=["Offers"],
        summary="Cancel an offer",
        description="Cancel a pending offer. Only the offer proposer can cancel.",
        request=None,
        responses={
            200: OfferSerializer,
            401: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
    )
    def post(self, request: Request, pk: int) -> Response:
        """Handle POST request to cancel an offer."""
        offer = services.cancel_offer(user=request.user, offer_id=pk)
        offer = _offer_base_queryset().get(pk=offer.pk)
        return Response(OfferSerializer(offer).data, status=status.HTTP_200_OK)


class OfferCounterView(APIView):
    """Counter a pending offer."""

    permission_classes = [IsAuthenticated, IsVerified]

    @extend_schema(
        tags=["Offers"],
        summary="Counter an offer",
        description=(
            "Counter a pending offer by marking the old offer countered and creating a new "
            "pending offer with new amount, currency, and comment. Recipient only."
        ),
        request=CounterOfferSerializer,
        responses={
            201: OfferSerializer,
            400: ErrorSerializer,
            401: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        examples=[
            OpenApiExample(
                "Counter offer example",
                value={
                    "amount": "2600.00",
                    "currency": "USD",
                    "comment": "Fuel and transit fee increase.",
                },
                request_only=True,
            ),
        ],
    )
    def post(self, request: Request, pk: int) -> Response:
        """Handle POST request to counter an offer."""
        serializer = CounterOfferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_offer = services.counter_offer(
            user=request.user,
            offer_id=pk,
            data=serializer.validated_data,
        )
        new_offer = _offer_base_queryset().get(pk=new_offer.pk)
        return Response(OfferSerializer(new_offer).data, status=status.HTTP_201_CREATED)
