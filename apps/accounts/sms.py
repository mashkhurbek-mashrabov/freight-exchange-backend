"""SMS backends."""


class BaseSmsBackend:
    """Base class for SMS backends."""

    def send_sms(self, phone: str, text: str) -> bool:
        """Send an SMS message."""
        raise NotImplementedError


class ConsoleSmsBackend(BaseSmsBackend):
    """Console SMS backend printing SMS messages to stdout."""

    def send_sms(self, phone: str, text: str) -> bool:
        """Print the SMS to standard output."""
        print(f"[SMS to {phone}]: {text}")
        return True
