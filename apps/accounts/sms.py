import logging
from typing import Any

from django.conf import settings
from django.utils.module_loading import import_string

logger = logging.getLogger("apps.accounts.sms")


class BaseSmsBackend:
    """Base interface for SMS backends."""

    def send(self, phone: str, text: str) -> None:
        """Send an SMS message to the given phone number."""
        raise NotImplementedError("Subclasses must implement send().")


class ConsoleSmsBackend(BaseSmsBackend):
    """Console SMS backend logging messages at INFO level."""

    def send(self, phone: str, text: str) -> None:
        """Log the outgoing SMS message."""
        logger.info("SMS to %s: %s", phone, text)


def send_sms(phone: str, text: str) -> None:
    """Send an SMS message using the backend configured in Django settings."""
    backend_path = getattr(settings, "SMS_BACKEND", "apps.accounts.sms.ConsoleSmsBackend")
    backend_cls: Any = import_string(backend_path)
    backend = backend_cls()
    backend.send(phone, text)
