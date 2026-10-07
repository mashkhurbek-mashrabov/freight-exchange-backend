"""Core service views."""

from django.db import connection
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    """Health check endpoint verifying database connectivity."""

    permission_classes = [AllowAny]

    @extend_schema(
        tags=["Service"],
        summary="Service health check",
        description="Verifies database connectivity with SELECT 1 and returns status ok.",
        responses={
            200: inline_serializer(
                name="HealthResponse",
                fields={"status": serializers.CharField()},
            ),
            503: inline_serializer(
                name="HealthErrorResponse",
                fields={
                    "status": serializers.CharField(),
                    "detail": serializers.CharField(),
                },
            ),
        },
    )
    def get(self, request: Request) -> Response:
        """Handle GET health check request."""
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                cursor.fetchone()
            return Response({"status": "ok"}, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response(
                {"status": "error", "detail": str(exc)},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
