"""Views for geo reference data."""

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.serializers import ErrorSerializer
from apps.geo import services
from apps.geo.serializers import (
    CountrySerializer,
    CurrencySerializer,
    ExchangeRateSerializer,
)


class CountryListView(APIView):
    """
    List countries reference endpoint.

    Small reference list: pagination is explicitly disabled (pagination_class = None).
    Results are cached for 1 hour.
    """

    permission_classes = [IsAuthenticated]
    pagination_class = None

    @extend_schema(
        tags=["Reference"],
        summary="List countries",
        description="Retrieve all countries with localized names and flag URLs. Cached for 1 hour.",
        parameters=[
            OpenApiParameter(
                name="search",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Search countries by 2-letter ISO code or localized name (uz/ru/en).",
                required=False,
            )
        ],
        responses={
            200: CountrySerializer(many=True),
            401: ErrorSerializer,
        },
    )
    def get(self, request: Request) -> Response:
        """Handle GET request returning cached list of countries."""
        search = request.query_params.get("search")
        data = services.get_cached_countries(
            query_string=request.META.get("QUERY_STRING", ""),
            search=search,
        )
        return Response(data, status=status.HTTP_200_OK)


class CurrencyListView(APIView):
    """
    List currencies reference endpoint.

    Small reference list: pagination is explicitly disabled (pagination_class = None).
    Results are cached for 1 hour.
    """

    permission_classes = [IsAuthenticated]
    pagination_class = None

    @extend_schema(
        tags=["Reference"],
        summary="List currencies",
        description="Retrieve all supported currencies. Cached for 1 hour.",
        responses={
            200: CurrencySerializer(many=True),
            401: ErrorSerializer,
        },
    )
    def get(self, request: Request) -> Response:
        """Handle GET request returning cached list of currencies."""
        data = services.get_cached_currencies(
            query_string=request.META.get("QUERY_STRING", "")
        )
        return Response(data, status=status.HTTP_200_OK)


class ExchangeRateListView(APIView):
    """
    List exchange rates reference endpoint.

    Small reference list: pagination is explicitly disabled (pagination_class = None).
    Returns the latest rate per base/quote currency pair, cached for 1 hour.
    """

    permission_classes = [IsAuthenticated]
    pagination_class = None

    @extend_schema(
        tags=["Reference"],
        summary="List exchange rates",
        description=(
            "Retrieve the latest exchange rate per base/quote pair. "
            "Filter by base and/or quote currency code. Cached for 1 hour."
        ),
        parameters=[
            OpenApiParameter(
                name="base",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter by base currency code (e.g. USD).",
                required=False,
            ),
            OpenApiParameter(
                name="quote",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Filter by quote currency code (e.g. UZS).",
                required=False,
            ),
        ],
        responses={
            200: ExchangeRateSerializer(many=True),
            401: ErrorSerializer,
        },
    )
    def get(self, request: Request) -> Response:
        """Handle GET request returning cached list of latest exchange rates."""
        base = request.query_params.get("base")
        quote = request.query_params.get("quote")
        data = services.get_cached_exchange_rates(
            query_string=request.META.get("QUERY_STRING", ""),
            base=base,
            quote=quote,
        )
        return Response(data, status=status.HTTP_200_OK)
