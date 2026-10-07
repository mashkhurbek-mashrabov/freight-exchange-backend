"""Serializers for notifications app."""

from rest_framework import serializers

from apps.notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """Serializer representing a Notification."""

    class Meta:
        model = Notification
        fields = [
            "id",
            "user",
            "type",
            "payload",
            "read_at",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "type",
            "payload",
            "read_at",
            "created_at",
        ]


class ReadAllResponseSerializer(serializers.Serializer):
    """Response serializer for marking all notifications read."""

    updated = serializers.IntegerField(
        help_text="Number of notifications marked as read.",
    )
