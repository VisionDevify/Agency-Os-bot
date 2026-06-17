from dataclasses import dataclass, field
from enum import StrEnum


class RoleName(StrEnum):
    OWNER = "Owner"
    ADMIN = "Admin"
    MANAGER = "Manager"
    VA = "VA"
    CHATTER_MANAGER = "Chatter Manager"
    SENIOR_CHATTER = "Senior Chatter"
    CHATTER = "Chatter"
    VIEWER = "Viewer"
    MODEL_CLIENT = "Model/Client"


ROLE_PERMISSIONS: dict[RoleName, frozenset[str]] = {
    RoleName.OWNER: frozenset({"*"}),
    RoleName.ADMIN: frozenset(
        {
            "view_dashboard",
            "manage_users",
            "manage_roles",
            "manage_accounts",
            "manage_proxies",
            "manage_tasks",
            "manage_incidents",
            "manage_reports",
            "manage_automations",
            "view_audit_logs",
        }
    ),
    RoleName.MANAGER: frozenset(
        {
            "view_dashboard",
            "manage_accounts",
            "manage_tasks",
            "manage_incidents",
            "manage_reports",
            "manage_automations",
            "resolve_incidents",
        }
    ),
    RoleName.VA: frozenset({"view_dashboard", "manage_tasks", "upload_content"}),
    RoleName.CHATTER_MANAGER: frozenset(
        {"view_dashboard", "view_chatter_dashboard", "manage_chatter_team", "approve_content"}
    ),
    RoleName.SENIOR_CHATTER: frozenset(
        {"view_dashboard", "view_chatter_dashboard", "approve_content", "upload_content"}
    ),
    RoleName.CHATTER: frozenset({"view_dashboard", "view_chatter_dashboard", "upload_content"}),
    RoleName.VIEWER: frozenset({"view_dashboard"}),
    RoleName.MODEL_CLIENT: frozenset({"view_dashboard", "approve_content"}),
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
