from dataclasses import dataclass, field


@dataclass(frozen=True)
class PermissionPrincipal:
    telegram_id: int
    is_owner: bool = False
    permissions: frozenset[str] = field(default_factory=frozenset)


def can(principal: PermissionPrincipal, permission: str) -> bool:
    return principal.is_owner or permission in principal.permissions


def require_permission(principal: PermissionPrincipal, permission: str) -> None:
    if not can(principal, permission):
        raise PermissionError(f"Missing permission: {permission}")


def require_owner(principal: PermissionPrincipal, owner_telegram_id: int | None) -> None:
    if owner_telegram_id is None or principal.telegram_id != owner_telegram_id:
        raise PermissionError("Owner-only setup is restricted")
