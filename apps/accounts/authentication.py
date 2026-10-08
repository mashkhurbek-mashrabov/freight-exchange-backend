"""Custom authentication classes and rules for accounts."""

from typing import Any

from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import Token


def user_authentication_rule(user: Any) -> bool:
    """Ensure user is active and account status is not blocked."""
    return (
        user is not None
        and getattr(user, "is_active", False)
        and getattr(user, "status", None) != "blocked"
    )


class CustomJWTAuthentication(JWTAuthentication):
    """JWT authentication ensuring the user is active and account is not blocked."""

    def get_user(self, validated_token: Token) -> Any:
        user = super().get_user(validated_token)
        if getattr(user, "status", None) == "blocked":
            raise AuthenticationFailed(
                detail="User account is blocked.",
                code="account_blocked",
            )
        return user


try:
    from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme

    class CustomJWTScheme(SimpleJWTScheme):
        target_class = "apps.accounts.authentication.CustomJWTAuthentication"
except ImportError:
    pass

