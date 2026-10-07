"""Factories for notifications app tests."""

from typing import Any

import factory

from apps.accounts.models import User
from apps.notifications.models import Notification


class UserFactory(factory.django.DjangoModelFactory):
    """Factory for User model using User.objects.create_user."""

    class Meta:
        model = User

    phone = factory.Sequence(lambda n: f"+99890{n:07d}")

    @classmethod
    def _create(cls, model_class: type[User], *args: Any, **kwargs: Any) -> User:
        """Create user via User.objects.create_user."""
        return model_class.objects.create_user(**kwargs)


class NotificationFactory(factory.django.DjangoModelFactory):
    """Factory for Notification model."""

    class Meta:
        model = Notification

    user = factory.SubFactory(UserFactory)
    type = Notification.NotificationType.OFFER_RECEIVED
    payload = factory.LazyFunction(dict)
    read_at = None
