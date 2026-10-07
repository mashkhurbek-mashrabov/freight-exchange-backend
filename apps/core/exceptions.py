"""Exception classes and custom DRF exception handler."""

from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


class ServiceError(Exception):
    """Domain service error with HTTP status code and error code."""

    def __init__(
        self,
        detail: str = "Service error.",
        code: str = "service_error",
        status_code: int = 400,
    ) -> None:
        self.detail = detail
        self.code = code
        self.status_code = status_code
        super().__init__(detail)


def handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    """DRF exception handler returning unified {detail, code} payload."""
    if isinstance(exc, ServiceError):
        return Response(
            {"detail": exc.detail, "code": exc.code},
            status=exc.status_code,
        )

    if isinstance(exc, Http404):
        return Response(
            {"detail": str(exc) if str(exc) else "Not found.", "code": "not_found"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if isinstance(exc, DjangoPermissionDenied):
        return Response(
            {
                "detail": str(exc) if str(exc) else "Permission denied.",
                "code": "permission_denied",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    if isinstance(exc, DjangoValidationError):
        if hasattr(exc, "message_dict"):
            errors: Any = exc.message_dict
        elif hasattr(exc, "messages"):
            errors = exc.messages
        else:
            errors = str(exc)
        return Response(
            {
                "detail": "Validation error.",
                "code": "validation_error",
                "errors": errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    response = drf_exception_handler(exc, context)
    if response is not None:
        if isinstance(exc, exceptions.Throttled):
            detail = (
                str(exc.detail)
                if hasattr(exc, "detail")
                else "Request was throttled."
            )
            response.data = {
                "detail": detail,
                "code": "throttled",
            }
            return response

        if isinstance(exc, exceptions.ValidationError):
            response.data = {
                "detail": "Validation error.",
                "code": "validation_error",
                "errors": response.data,
            }
            return response

        if isinstance(exc, exceptions.NotAuthenticated):
            detail = (
                str(exc.detail)
                if hasattr(exc, "detail")
                else "Authentication credentials were not provided."
            )
            response.data = {"detail": detail, "code": "not_authenticated"}
            return response

        if isinstance(exc, exceptions.PermissionDenied):
            code = getattr(exc.detail, "code", None) or getattr(
                exc, "default_code", "permission_denied"
            )
            detail = (
                str(exc.detail) if hasattr(exc, "detail") else "Permission denied."
            )
            response.data = {"detail": detail, "code": str(code)}
            return response

        code = getattr(getattr(exc, "detail", None), "code", None) or getattr(
            exc, "default_code", "error"
        )
        detail_val = (
            response.data.get("detail", str(response.data))
            if isinstance(response.data, dict)
            else str(response.data)
        )
        response.data = {
            "detail": str(detail_val),
            "code": str(code),
        }
        return response

    return None
