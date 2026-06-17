from dataclasses import dataclass, field
from enum import StrEnum


class RoleName(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    VA = "va"
    CHATTER = "chatter"
    VIEWER = "viewer"


ROLE_PERMISSIONS: dict[RoleName, frozenset[str]] = {
    RoleName.OWNER: frozenset({"*"}),
    RoleName.ADMIN: frozenset(
        {
            "dashboard.view",
            "users.manage",
            "roles.manage",
            "accounts.manage",
            "proxies.manage",
            "tasks.manage",
            "incidents.manage",
            "reports.view",
            "automations.manage",
            "settings.manage",
        }
    ),
    RoleName.MANAGER: frozenset(
        {
            "dashboard.view",
            "accounts.manage",
            "proxies.view",
            "tasks.manage",
            "incidents.manage",
            "reports.view",
            "automations.view",
        }
    ),
    RoleName.VA: frozenset(
        {"dashboard.view", "accounts.view", "tasks.manage", "incidents.create", "reports.view"}
    ),
    RoleName.CHATTER: frozenset({"dashboard.view", "accounts.view", "tasks.view"}),
    RoleName.VIEWER: frozenset({"dashboard.view", "reports.view"}),
}


@dataclass(frozen=True)
class PermissionPrincipal:
    telegram_id: int
    is_owner: bool = False
    role: RoleName = RoleName.VIEWER
    permissions: frozenset[str] = field(default_factory=frozenset)


def permissions_for_role(role: RoleName | str) -> frozenset[str]:
    return ROLE_PERMISSIONS[RoleName(role)]


def can(principal: PermissionPrincipal, permission: str) -> bool:
    role_permissions = permissions_for_role(principal.role)
    return (
        principal.is_owner
        or "*" in role_permissions
        or permission in principal.permissions
        or permission in role_permissions
    )


def require_permission(principal: PermissionPrincipal, permission: str) -> None:
    if not can(principal, permission):
        raise PermissionError(f"Missing permission: {permission}")


def require_owner(principal: PermissionPrincipal, owner_telegram_id: int | None) -> None:
    if owner_telegram_id is None or principal.telegram_id != owner_telegram_id:
        raise PermissionError("Owner-only setup is restricted")
