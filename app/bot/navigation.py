from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.bot.screens import PAGE_TITLES, Screen, render_dashboard, render_main_menu, render_page
from app.models.permissions import Role
from app.models.user import User
from app.services.audit import AuditRecorder, audit_recorder
from app.services.auth import (
    add_permission_to_role,
    approve_user,
    assign_role_to_user,
    audit_action,
    deny_user,
    disable_user,
    get_user_by_id,
    reactivate_user,
    remove_permission_from_role,
    remove_role_from_user,
    user_has_permission,
)
from app.services.permissions import PermissionPrincipal, require_permission

PAGE_PERMISSIONS: dict[str, str] = {
    "dashboard": "view_dashboard",
    "users": "manage_users",
    "roles": "manage_roles",
    "accounts": "manage_accounts",
    "proxies": "manage_proxies",
    "tasks": "manage_tasks",
    "incidents": "manage_incidents",
    "reports": "manage_reports",
    "automations": "manage_automations",
    "settings": "manage_roles",
    "audit_logs": "view_audit_logs",
}


def permission_for_page(page: str) -> str | None:
    if page.startswith("user:"):
        return "manage_users"
    if page.startswith("role:") or page == "permissions":
        return "manage_roles"
    return PAGE_PERMISSIONS.get(page)


def _perform_admin_action(page: str, session: Session, actor: User) -> str | None:
    parts = page.split(":")
    if len(parts) >= 3 and parts[0] == "user" and parts[1].isdigit():
        target = get_user_by_id(session, int(parts[1]))
        if target is None:
            return f"user:{parts[1]}"
        action = parts[2]
        if action == "approve":
            approve_user(session, target, actor=actor)
            return f"user:{target.id}"
        if action == "deny":
            deny_user(session, target, actor=actor)
            return f"user:{target.id}"
        if action == "disable":
            disable_user(session, target, actor=actor)
            return f"user:{target.id}"
        if action == "reactivate":
            reactivate_user(session, target, actor=actor)
            return f"user:{target.id}"
        if action == "assign_role" and len(parts) >= 4:
            role_name = ":".join(parts[3:])
            assign_role_to_user(session, target, role_name, actor=actor)
            return f"user:{target.id}"
        if action == "remove_role" and len(parts) >= 4:
            role_name = ":".join(parts[3:])
            remove_role_from_user(session, target, role_name, actor=actor)
            return f"user:{target.id}"
    if len(parts) >= 4 and parts[0] == "role" and parts[1].isdigit():
        role = session.scalar(
            select(Role).where(Role.id == int(parts[1])).options(selectinload(Role.permissions))
        )
        if role is None:
            return "roles"
        action = parts[2]
        permission_key = parts[3]
        if action == "add_permission":
            add_permission_to_role(session, role, permission_key, actor=actor)
            return f"role:{role.id}"
        if action == "remove_permission":
            remove_permission_from_role(session, role, permission_key, actor=actor)
            return f"role:{role.id}"
    return None


def screen_for_page(
    page: str,
    principal: PermissionPrincipal,
    recorder: AuditRecorder = audit_recorder,
    session: Session | None = None,
    user: User | None = None,
) -> Screen:
    normalized = "dashboard" if page == "dashboard:refresh" else page
    if normalized == "menu":
        if session is not None:
            audit_action(
                session,
                actor=user,
                action="admin_area.opened",
                resource_type="telegram_menu",
                details={"telegram_id": principal.telegram_id},
            )
        else:
            recorder.record(
                actor_user_id=None,
                action="admin_area.opened",
                resource_type="telegram_menu",
                details={"telegram_id": principal.telegram_id},
            )
        return render_main_menu()

    permission = permission_for_page(normalized)
    if permission is not None:
        try:
            if user is not None:
                if not user_has_permission(user, permission):
                    raise PermissionError(f"Missing permission: {permission}")
            else:
                require_permission(principal, permission)
        except PermissionError:
            if session is not None:
                audit_action(
                    session,
                    actor=user,
                    action="restricted_page.accessed",
                    resource_type="telegram_page",
                    resource_id=normalized,
                    status="denied",
                    details={"telegram_id": principal.telegram_id, "permission": permission},
                )
            else:
                recorder.record(
                    actor_user_id=None,
                    action="restricted_page.accessed",
                    resource_type="telegram_page",
                    resource_id=normalized,
                    details={"telegram_id": principal.telegram_id, "permission": permission},
                )
            raise

    if session is not None and user is not None:
        action_target = _perform_admin_action(normalized, session, user)
        if action_target is not None:
            normalized = action_target

    if session is not None:
        audit_action(
            session,
            actor=user,
            action="management_action.performed",
            resource_type="telegram_page",
            resource_id=normalized,
            details={"telegram_id": principal.telegram_id},
        )
    else:
        recorder.record(
            actor_user_id=None,
            action="management_action.performed",
            resource_type="telegram_page",
            resource_id=normalized,
            details={"telegram_id": principal.telegram_id},
        )

    if normalized == "dashboard":
        return render_dashboard()
    if (
        normalized in PAGE_TITLES
        or normalized == "audit_logs"
        or normalized == "permissions"
        or normalized.startswith("user:")
        or normalized.startswith("role:")
    ):
        return render_page(normalized, session=session)
    return render_main_menu()
