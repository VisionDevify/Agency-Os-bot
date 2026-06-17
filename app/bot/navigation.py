from app.bot.screens import PAGE_TITLES, Screen, render_dashboard, render_main_menu, render_page
from app.services.audit import AuditRecorder, audit_recorder
from app.services.permissions import PermissionPrincipal, require_permission

PAGE_PERMISSIONS: dict[str, str] = {
    "dashboard": "dashboard.view",
    "users": "users.manage",
    "roles": "roles.manage",
    "accounts": "accounts.manage",
    "proxies": "proxies.manage",
    "tasks": "tasks.manage",
    "incidents": "incidents.manage",
    "reports": "reports.view",
    "automations": "automations.manage",
    "settings": "settings.manage",
}


def screen_for_page(
    page: str,
    principal: PermissionPrincipal,
    recorder: AuditRecorder = audit_recorder,
) -> Screen:
    normalized = "dashboard" if page == "dashboard:refresh" else page
    if normalized == "menu":
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
            require_permission(principal, permission)
        except PermissionError:
            recorder.record(
                actor_user_id=None,
                action="restricted_page.accessed",
                resource_type="telegram_page",
                resource_id=normalized,
                details={"telegram_id": principal.telegram_id, "permission": permission},
            )
            raise

    recorder.record(
        actor_user_id=None,
        action="management_action.performed",
        resource_type="telegram_page",
        resource_id=normalized,
        details={"telegram_id": principal.telegram_id},
    )

    if normalized == "dashboard":
        return render_dashboard()
    if normalized in PAGE_TITLES:
        return render_page(normalized)
    return render_main_menu()
