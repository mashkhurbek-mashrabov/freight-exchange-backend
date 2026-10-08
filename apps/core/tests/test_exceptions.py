"""Tests for core exception handler and ServiceError."""

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions, status

from apps.core.exceptions import ServiceError, handler


def test_service_error_handling() -> None:
    """Verify ServiceError formats detail, code, and status correctly."""
    exc = ServiceError(
        detail="Account is not verified.",
        code="account_not_verified",
        status_code=status.HTTP_403_FORBIDDEN,
    )
    response = handler(exc, {})
    assert response is not None
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data == {
        "detail": "Account is not verified.",
        "code": "account_not_verified",
    }


def test_service_error_conflict() -> None:
    """Verify ServiceError supports conflict status and custom codes."""
    exc = ServiceError(
        detail="Invalid state transition.",
        code="invalid_transition",
        status_code=status.HTTP_409_CONFLICT,
    )
    response = handler(exc, {})
    assert response is not None
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data == {
        "detail": "Invalid state transition.",
        "code": "invalid_transition",
    }


def test_drf_validation_error() -> None:
    """Verify DRF ValidationError preserves field errors under errors key."""
    exc = exceptions.ValidationError({"phone": ["Invalid phone number."]})
    response = handler(exc, {})
    assert response is not None
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data == {
        "detail": "Validation error.",
        "code": "validation_error",
        "errors": {"phone": ["Invalid phone number."]},
    }


def test_django_validation_error_dict() -> None:
    """Verify Django ValidationError with dict errors is formatted."""
    exc = DjangoValidationError({"field": ["Field error"]})
    response = handler(exc, {})
    assert response is not None
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data == {
        "detail": "Validation error.",
        "code": "validation_error",
        "errors": {"field": ["Field error"]},
    }


def test_django_validation_error_list() -> None:
    """Verify Django ValidationError with list messages is formatted."""
    exc = DjangoValidationError(["General error message"])
    response = handler(exc, {})
    assert response is not None
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data == {
        "detail": "Validation error.",
        "code": "validation_error",
        "errors": ["General error message"],
    }


def test_http404_error() -> None:
    """Verify Http404 produces 404 with not_found code."""
    exc = Http404("Item not found.")
    response = handler(exc, {})
    assert response is not None
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.data == {
        "detail": "Item not found.",
        "code": "not_found",
    }


def test_django_permission_denied() -> None:
    """Verify Django PermissionDenied produces 403 with permission_denied code."""
    exc = DjangoPermissionDenied("No access.")
    response = handler(exc, {})
    assert response is not None
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data == {
        "detail": "No access.",
        "code": "permission_denied",
    }


def test_drf_not_authenticated() -> None:
    """Verify DRF NotAuthenticated produces 401 with not_authenticated code."""
    exc = exceptions.NotAuthenticated()
    response = handler(exc, {})
    assert response is not None
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["code"] == "not_authenticated"
    assert "detail" in response.data


def test_drf_permission_denied() -> None:
    """Verify DRF PermissionDenied produces 403 with permission_denied code."""
    exc = exceptions.PermissionDenied()
    response = handler(exc, {})
    assert response is not None
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "permission_denied"
    assert "detail" in response.data


def test_drf_not_found() -> None:
    """Verify DRF NotFound produces 404 with not_found code."""
    exc = exceptions.NotFound()
    response = handler(exc, {})
    assert response is not None
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.data["code"] == "not_found"
    assert "detail" in response.data


def test_unhandled_exception_returns_none() -> None:
    """Verify unexpected Python exceptions return None for standard 500 handling."""
    exc = RuntimeError("Unexpected crash")
    response = handler(exc, {})
    assert response is None


def test_integrity_error_handled_as_conflict() -> None:
    """Verify Django IntegrityError produces 409 with conflict code without leaking SQL."""
    from django.db import IntegrityError

    exc = IntegrityError("duplicate key value violates unique constraint 'foo_idx'")
    response = handler(exc, {})
    assert response is not None
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data == {
        "detail": "Database integrity constraint violated.",
        "code": "conflict",
    }


def test_database_error_handled_as_database_error() -> None:
    """Verify Django DatabaseError produces 500 with sanitized code and detail."""
    from django.db import DatabaseError

    exc = DatabaseError("syntax error at or near 'SELECT table'")
    response = handler(exc, {})
    assert response is not None
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.data == {
        "detail": "A database error occurred.",
        "code": "database_error",
    }
