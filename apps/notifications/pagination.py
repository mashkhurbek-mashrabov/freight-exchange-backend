"""Pagination classes for notifications."""

from typing import Any

from rest_framework.response import Response

from apps.core.pagination import DefaultPagination
from apps.notifications.services import unread_count


class NotificationPagination(DefaultPagination):
    """Notification pagination subclass returning top-level unread_count."""

    def get_paginated_response(self, data: Any) -> Response:
        """Return standardized pagination dictionary including unread_count."""
        unread_total = 0
        if hasattr(self, "request") and self.request and self.request.user.is_authenticated:
            unread_total = unread_count(self.request.user)

        return Response(
            {
                "count": self.page.paginator.count,
                "unread_count": unread_total,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )

    def get_paginated_response_schema(self, schema: dict[str, Any]) -> dict[str, Any]:
        """Return OpenAPI response schema including unread_count for drf-spectacular."""
        return {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "example": 123,
                },
                "unread_count": {
                    "type": "integer",
                    "example": 5,
                },
                "next": {
                    "type": "string",
                    "nullable": True,
                    "format": "uri",
                    "example": "http://api.example.org/api/v1/notifications?page=4",
                },
                "previous": {
                    "type": "string",
                    "nullable": True,
                    "format": "uri",
                    "example": "http://api.example.org/api/v1/notifications?page=2",
                },
                "results": schema,
            },
        }
