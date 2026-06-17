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
    mask_telegram_id,
    user_has_permission,
)
from app.services.accounts import (
    archive_account,
    get_account,
    latest_auth_session,
    require_account_auth_permission,
    start_auth_session,
    update_account,
    mark_auth_session_success,
)
from app.services.model_brands import (
    archive_model_brand,
    assign_model_member,
    create_default_model_brand,
    get_model_brand,
    remove_model_member,
    update_model_brand,
)
from app.services.proxies import (
    ProxyTestResult,
    assign_proxy_to_account,
    create_default_proxy,
    get_proxy,
    remove_proxy_from_account,
    repair_proxy,
    rollback_session,
    rotate_session,
    verify_location_with_rotation,
)
from app.services.permissions import PermissionPrincipal, require_permission

PAGE_PERMISSIONS: dict[str, str] = {
    "dashboard": "view_dashboard",
    "models": "view_dashboard",
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
    if page.startswith("account:") and ":auth:" in page:
        return None
    if page.startswith("account:") and ":proxy:" in page:
        return "manage_proxies"
    if page.startswith("proxies:"):
        return "manage_proxies"
    if page.startswith("proxy:"):
        return "manage_proxies"
    if page.startswith("accounts:"):
        return "manage_accounts"
    if page.startswith("account:"):
        return "manage_accounts"
    if page.startswith("models"):
        return "view_dashboard"
    if page.startswith("model:"):
        return "view_dashboard"
    if page.startswith("users:"):
        return "manage_users"
    if page.startswith("user:"):
        return "manage_users"
    if page.startswith("role:") or page == "permissions":
        return "manage_roles"
    return PAGE_PERMISSIONS.get(page)


def _perform_admin_action(page: str, session: Session, actor: User) -> str | None:
    parts = page.split(":")
    if page == "proxies:create":
        proxy = create_default_proxy(session, actor=actor)
        return f"proxy:{proxy.id}"
    if len(parts) >= 3 and parts[0] == "proxy" and parts[1].isdigit():
        proxy = get_proxy(session, int(parts[1]))
        if proxy is None:
            return "proxies:list"
        action = parts[2]
        if action == "rotate":
            rotate_session(session, proxy, actor=actor)
            return f"proxy:{proxy.id}"
        if action == "rollback":
            try:
                rollback_session(session, proxy, actor=actor)
            except ValueError:
                pass
            return f"proxy:{proxy.id}"
        if action == "verify":
            verify_location_with_rotation(
                session,
                proxy,
                actor=actor,
                attempts=[
                    ProxyTestResult(
                        success=True,
                        latency_ms=250,
                        detected_country=proxy.target_country,
                        detected_state=proxy.target_state,
                        detected_city=proxy.target_city,
                    )
                ],
            )
            return f"proxy:{proxy.id}"
        if action == "repair":
            repair_proxy(
                session,
                proxy,
                actor=actor,
                initial_result=ProxyTestResult(success=False, latency_ms=0, failure_reason="telegram_test_failed"),
                repair_result=ProxyTestResult(
                    success=True,
                    latency_ms=240,
                    detected_country=proxy.target_country,
                    detected_state=proxy.target_state,
                    detected_city=proxy.target_city,
                ),
            )
            return f"proxy:{proxy.id}"
        if action == "assign" and len(parts) >= 4 and parts[3].isdigit():
            account = get_account(session, int(parts[3]))
            if account is not None:
                assign_proxy_to_account(session, proxy, account, actor=actor)
            return f"proxy:{proxy.id}"
        if action == "remove" and len(parts) >= 4 and parts[3].isdigit():
            account = get_account(session, int(parts[3]))
            if account is not None:
                remove_proxy_from_account(session, account, actor=actor)
            return f"proxy:{proxy.id}"
    if len(parts) >= 3 and parts[0] == "account" and parts[1].isdigit():
        account = get_account(session, int(parts[1]))
        if account is None:
            return "accounts:list"
        action = parts[2]
        if action == "auth" and len(parts) >= 4:
            auth_action = parts[3]
            if auth_action == "enter":
                require_account_auth_permission(session, actor)
                return None
            if auth_action == "start":
                start_auth_session(session, account, actor=actor)
                return f"account:{account.id}:auth:enter"
            if auth_action == "connected":
                auth_session = latest_auth_session(session, account.id)
                if auth_session is not None:
                    mark_auth_session_success(session, auth_session, actor=actor)
                else:
                    update_account(session, account, actor=actor, auth_status="connected")
                return f"account:{account.id}"
            if auth_action == "needs_login":
                update_account(session, account, actor=actor, auth_status="needs_login")
                return f"account:{account.id}"
        if action == "proxy" and len(parts) >= 4:
            proxy_action = parts[3]
            if proxy_action == "assign" and len(parts) >= 5 and parts[4].isdigit():
                proxy = get_proxy(session, int(parts[4]))
                if proxy is not None:
                    assign_proxy_to_account(session, proxy, account, actor=actor)
                return f"account:{account.id}"
            if proxy_action == "remove":
                remove_proxy_from_account(session, account, actor=actor)
                return f"account:{account.id}"
        if action == "disable":
            update_account(session, account, actor=actor, status="disabled")
            return f"account:{account.id}"
        if action == "archive":
            archive_account(session, account, actor=actor)
            return f"account:{account.id}"
    if page == "models:create":
        model_brand = create_default_model_brand(session, actor=actor)
        return f"model:{model_brand.id}"
    if len(parts) >= 3 and parts[0] == "model" and parts[1].isdigit():
        model_brand = get_model_brand(session, int(parts[1]))
        if model_brand is None:
            return "models:list"
        action = parts[2]
        if action == "archive":
            archive_model_brand(session, model_brand, actor=actor)
            return f"model:{model_brand.id}"
        if action == "status" and len(parts) >= 4:
            status = parts[3]
            if status == "archived":
                archive_model_brand(session, model_brand, actor=actor)
            else:
                update_model_brand(session, model_brand, actor=actor, status=status)
            return f"model:{model_brand.id}"
        if action == "team" and len(parts) >= 6:
            team_action = parts[3]
            relationship_type = parts[4]
            if not parts[5].isdigit():
                return f"model:{model_brand.id}:team"
            target = get_user_by_id(session, int(parts[5]))
            if target is None:
                return f"model:{model_brand.id}:team"
            if team_action == "assign":
                assign_model_member(session, model_brand, target, relationship_type, actor=actor)
                return f"model:{model_brand.id}:team"
            if team_action == "remove":
                remove_model_member(session, model_brand, target, relationship_type, actor=actor)
                return f"model:{model_brand.id}:team"
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
                details={"telegram_id_masked": mask_telegram_id(principal.telegram_id)},
            )
        else:
            recorder.record(
                actor_user_id=None,
                action="admin_area.opened",
                resource_type="telegram_menu",
                details={"telegram_id_masked": mask_telegram_id(principal.telegram_id)},
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
                    action="access.denied",
                    resource_type="telegram_page",
                    resource_id=normalized,
                    status="denied",
                    details={
                        "telegram_id_masked": mask_telegram_id(principal.telegram_id),
                        "permission": permission,
                    },
                )
            else:
                recorder.record(
                    actor_user_id=None,
                    action="access.denied",
                    resource_type="telegram_page",
                    resource_id=normalized,
                    details={
                        "telegram_id_masked": mask_telegram_id(principal.telegram_id),
                        "permission": permission,
                    },
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
            details={"telegram_id_masked": mask_telegram_id(principal.telegram_id)},
        )
    else:
        recorder.record(
            actor_user_id=None,
            action="management_action.performed",
            resource_type="telegram_page",
            resource_id=normalized,
            details={"telegram_id_masked": mask_telegram_id(principal.telegram_id)},
        )

    if normalized == "dashboard":
        return render_dashboard(session=session)
    if (
        normalized in PAGE_TITLES
        or normalized == "audit_logs"
        or normalized == "permissions"
        or normalized.startswith("accounts:")
        or normalized.startswith("account:")
        or normalized.startswith("models:")
        or normalized.startswith("model:")
        or normalized.startswith("users:")
        or normalized.startswith("user:")
        or normalized.startswith("role:")
    ):
        return render_page(normalized, session=session)
    return render_main_menu()
