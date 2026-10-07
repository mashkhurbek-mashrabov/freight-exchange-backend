"""Permission classes."""

from typing import Any

from rest_framework import exceptions
from rest_framework.permissions import BasePermission


class IsVerified(BasePermission):
    """Permission check ensuring the user has status='verified'."""

    message = "Account is not verified."
    code = "account_not_verified"

    def has_permission(self, request: Any, view: Any) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(request.user, "status", None) == "verified":
            return True
        raise exceptions.PermissionDenied(
            detail=self.message,
            code=self.code,
        )


class HasRole(BasePermission):
    """Permission check ensuring the user has one of the allowed roles."""

    message = "Role not allowed for this action."
    code = "role_not_allowed"
    allowed_roles: set[str] = set()

    def __init__(self, allowed_roles: set[str] | list[str] | tuple[str, ...] | None = None) -> None:
        if allowed_roles is not None:
            self.allowed_roles = set(allowed_roles)

    def has_permission(self, request: Any, view: Any) -> bool:
        if not request.user or not request.user.is_authenticated:
            return False
        if not self.allowed_roles or getattr(request.user, "role", None) in self.allowed_roles:
            return True
        raise exceptions.PermissionDenied(
            detail=self.message,
            code=self.code,
        )

    @classmethod
    def of(cls, *roles: str) -> type["HasRole"]:
        """Return a permission class restricted to the specified roles."""
        role_set = set(roles)
        name_suffix = "_".join(sorted(roles))
        return type(
            f"HasRole_{name_suffix}",
            (cls,),
            {
                "allowed_roles": role_set,
                "message": cls.message,
                "code": cls.code,
            },
        )
