"""Views for notifications app."""

from typing import Any

from django.db.models import QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.serializers import ErrorSerializer
from apps.notifications.filters import NotificationFilter
from apps.notifications.models import Notification
from apps.notifications.pagination import NotificationPagination
from apps.notifications.serializers import (
    NotificationSerializer,
    ReadAllResponseSerializer,
)
from apps.notifications.services import mark_all_read, mark_read


class NotificationListView(generics.ListAPIView):
    """List notifications for authenticated user."""

    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer
    pagination_class = NotificationPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = NotificationFilter

    queryset = Notification.objects.none()

    def get_queryset(self) -> QuerySet[Notification]:
        """Return notifications for the current user, newest first."""
        if getattr(self, "swagger_fake_view", False) or not self.request.user.is_authenticated:
            return Notification.objects.none()
        return Notification.objects.filter(user=self.request.user).order_by("-created_at")

    @extend_schema(
        tags=["Notifications"],
        summary="List user notifications",
        description=(
            "Retrieve a paginated list of notifications for the authenticated user, "
            "ordered by newest first. Includes top-level unread_count and supports "
            "filtering by ?unread=true."
        ),
        responses={
            200: NotificationSerializer(many=True),
            401: ErrorSerializer,
        },
        examples=[
            OpenApiExample(
                name="Notification example",
                value={
                    "id": 1,
                    "user": 1,
                    "type": "offer_received",
                    "payload": {"offer_id": 10},
                    "read_at": None,
                    "created_at": "2026-10-07T12:00:00Z",
                },
                response_only=True,
            ),
        ],
    )
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        """Handle GET request to list notifications."""
        return super().get(request, *args, **kwargs)


class NotificationReadView(APIView):
    """Mark a specific notification as read."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Notifications"],
        summary="Mark notification as read",
        description=(
            "Mark a specific notification as read. "
            "Returns 404 if the notification belongs to another user or does not exist."
        ),
        request=None,
        responses={
            200: NotificationSerializer,
            401: ErrorSerializer,
            404: ErrorSerializer,
        },
        examples=[
            OpenApiExample(
                name="Notification read response example",
                value={
                    "id": 1,
                    "user": 1,
                    "type": "offer_received",
                    "payload": {"offer_id": 10},
                    "read_at": "2026-10-07T12:30:00Z",
                    "created_at": "2026-10-07T12:00:00Z",
                },
                response_only=True,
            ),
        ],
    )
    def post(self, request: Request, pk: int) -> Response:
        """Handle POST request to mark notification as read."""
        notification = mark_read(request.user, pk)
        serializer = NotificationSerializer(notification)
        return Response(serializer.data, status=status.HTTP_200_OK)


class NotificationReadAllView(APIView):
    """Mark all notifications as read."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["Notifications"],
        summary="Mark all notifications as read",
        description="Mark all unread notifications for the authenticated user as read.",
        request=None,
        responses={
            200: ReadAllResponseSerializer,
            401: ErrorSerializer,
        },
        examples=[
            OpenApiExample(
                name="Mark all read response example",
                value={"updated": 3},
                response_only=True,
            ),
        ],
    )
    def post(self, request: Request) -> Response:
        """Handle POST request to mark all unread notifications as read."""
        updated = mark_all_read(request.user)
        return Response({"updated": updated}, status=status.HTTP_200_OK)
