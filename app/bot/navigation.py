from sqlalchemy.orm import Session

from app.bot.screens import PAGE_TITLES, Screen, render_dashboard, render_main_menu, render_page
from app.models.user import User
from app.services.audit import AuditRecorder, audit_recorder
from app.services.auth import audit_action, user_has_permission
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

    permission = PAGE_PERMISSIONS.get(normalized)
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
    if normalized in PAGE_TITLES or normalized == "audit_logs":
        return render_page(normalized, session=session)
    return render_main_menu()
