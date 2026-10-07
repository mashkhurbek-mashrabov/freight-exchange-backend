"""Rate throttles for freight exchange API."""


from rest_framework.request import Request
from rest_framework.settings import api_settings
from rest_framework.throttling import (
    AnonRateThrottle as DRFAnonRateThrottle,
)
from rest_framework.throttling import (
    ScopedRateThrottle as DRFScopedRateThrottle,
)
from rest_framework.throttling import (
    UserRateThrottle as DRFUserRateThrottle,
)
from rest_framework.views import APIView


class AnonRateThrottle(DRFAnonRateThrottle):
    """Rate throttle for unauthenticated requests (scope: anon)."""

    scope = "anon"

    def get_rate(self) -> str | None:
        """Resolve rate supporting class-level patches and dynamic settings."""
        rates = getattr(self, "THROTTLE_RATES", None) or getattr(
            api_settings, "DEFAULT_THROTTLE_RATES", {}
        )
        if isinstance(rates, dict) and self.scope in rates:
            return rates[self.scope]
        return super().get_rate()


class UserRateThrottle(DRFUserRateThrottle):
    """Rate throttle for authenticated requests (scope: user)."""

    scope = "user"

    def get_rate(self) -> str | None:
        """Resolve rate supporting class-level patches and dynamic settings."""
        rates = getattr(self, "THROTTLE_RATES", None) or getattr(
            api_settings, "DEFAULT_THROTTLE_RATES", {}
        )
        if isinstance(rates, dict) and self.scope in rates:
            return rates[self.scope]
        return super().get_rate()


class ScopedRateThrottle(DRFScopedRateThrottle):
    """Scoped rate throttle resolving rate dynamically and keying OTP by IP."""

    def get_rate(self) -> str | None:
        """Resolve rate from class THROTTLE_RATES or api_settings."""
        if not getattr(self, "scope", None):
            return super().get_rate()
        rates = getattr(self, "THROTTLE_RATES", None) or getattr(
            api_settings, "DEFAULT_THROTTLE_RATES", {}
        )
        if isinstance(rates, dict) and self.scope in rates:
            return rates[self.scope]
        return super().get_rate()

    def get_cache_key(self, request: Request, view: APIView) -> str | None:
        """Key OTP scopes strictly by client IP address."""
        self.scope = getattr(view, self.scope_attr, None)
        if not self.scope:
            return None

        # OTP scopes are always tracked per IP regardless of auth
        if self.scope in ("otp", "otp_verify"):
            ident = self.get_ident(request)
            return self.cache_format % {
                "scope": self.scope,
                "ident": ident,
            }

        return super().get_cache_key(request, view)


class IpScopedRateThrottle(ScopedRateThrottle):
    """Scoped rate throttle that keys strictly per client IP for all scopes."""

    def get_cache_key(self, request: Request, view: APIView) -> str | None:
        self.scope = getattr(view, self.scope_attr, None)
        if not self.scope:
            return None
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class OtpRequestThrottle(IpScopedRateThrottle):
    """Throttle for OTP requests (10/min per IP by default)."""

    scope = "otp"


class OtpVerifyThrottle(IpScopedRateThrottle):
    """Throttle for OTP verification (20/min per IP by default)."""

    scope = "otp_verify"
