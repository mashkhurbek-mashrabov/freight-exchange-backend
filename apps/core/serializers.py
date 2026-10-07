"""Shared core serializers."""

from rest_framework import serializers


class ErrorSerializer(serializers.Serializer):
    """Shared error response serializer."""

    detail = serializers.CharField(help_text="Human-readable error description.")
    code = serializers.CharField(help_text="Machine-readable error code.")


class ValidationErrorSerializer(ErrorSerializer):
    """Validation error response serializer containing field errors."""

    errors = serializers.DictField(
        required=False,
        help_text="Field-level validation error details.",
    )
