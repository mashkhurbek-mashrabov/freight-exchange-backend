import logging

import pytest
from django.conf import settings

if not settings.configured:
    settings.configure(SMS_BACKEND="apps.accounts.sms.ConsoleSmsBackend")

from apps.accounts.sms import BaseSmsBackend, ConsoleSmsBackend, send_sms  # noqa: E402


def test_console_sms_backend_send(caplog: pytest.LogCaptureFixture) -> None:
    """ConsoleSmsBackend logs message at INFO level."""
    backend = ConsoleSmsBackend()
    with caplog.at_level(logging.INFO, logger="apps.accounts.sms"):
        backend.send("+998901234567", "Your verification code is 123456")

    assert "SMS to +998901234567: Your verification code is 123456" in caplog.text


def test_send_sms_default_backend(caplog: pytest.LogCaptureFixture) -> None:
    """send_sms uses configured backend and logs via ConsoleSmsBackend."""
    with caplog.at_level(logging.INFO, logger="apps.accounts.sms"):
        send_sms("+998909876543", "Test message")

    assert "SMS to +998909876543: Test message" in caplog.text


class RecordingSmsBackend(BaseSmsBackend):
    """Test backend recording sent messages in memory."""

    sent_messages: list[tuple[str, str]] = []

    def send(self, phone: str, text: str) -> None:
        self.sent_messages.append((phone, text))


def test_send_sms_custom_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """send_sms dynamically imports and delegates to configured backend class."""
    RecordingSmsBackend.sent_messages.clear()
    monkeypatch.setattr(
        settings,
        "SMS_BACKEND",
        "apps.accounts.tests.test_sms.RecordingSmsBackend",
    )
    send_sms("+998901112233", "Custom backend text")

    assert RecordingSmsBackend.sent_messages == [("+998901112233", "Custom backend text")]


def test_base_sms_backend_not_implemented() -> None:
    """BaseSmsBackend.send raises NotImplementedError."""
    backend = BaseSmsBackend()
    with pytest.raises(NotImplementedError):
        backend.send("+998901234567", "Text")
