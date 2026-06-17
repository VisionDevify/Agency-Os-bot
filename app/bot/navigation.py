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
from app.services.incidents import (
    archive_incident,
    assign_incident,
    create_default_incident,
    escalate_incident,
    get_incident,
    investigate_incident,
    resolve_incident,
)
from app.services.tasks import (
    archive_task,
    assign_task,
    block_task,
    complete_task,
    create_default_task,
    escalate_task,
    get_task,
    start_task,
)
from app.services.notifications import (
    add_current_chat_as_target,
    create_placeholder_notification_target,
    disable_notification_target,
    get_notification_target,
    set_notification_target_purpose,
    test_notification_target,
)
from app.services.automations import (
    get_simulation_run,
    run_daily_briefing_simulation,
    run_proxy_repair_simulation,
    update_simulation_status,
)
from app.services.recommendations import get_recommendation, update_recommendation_status
from app.services.permissions import PermissionPrincipal, require_permission
from app.services.team_operations import set_availability

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
    "production_status": "manage_roles",
}


def permission_for_page(page: str) -> str | None:
    permissions = permissions_for_page(page)
    if not permissions:
        return None
    return permissions[0]


def permissions_for_page(page: str) -> tuple[str, ...] | None:
    if page.startswith("account:") and ":auth:" in page:
        return None
    if page.startswith("account:") and ":proxy:" in page:
        return ("manage_proxies",)
    if page.startswith("proxies:"):
        return ("manage_proxies",)
    if page.startswith("proxy:"):
        return ("manage_proxies",)
    if page.startswith("tasks:"):
        return ("manage_tasks",)
    if page.startswith("task:"):
        return ("manage_tasks",)
    if page.startswith("incidents:"):
        return ("manage_incidents",)
    if page.startswith("incident:"):
        return ("manage_incidents",)
    if page.startswith("reports:chatter"):
        return ("view_chatter_dashboard", "manage_chatter_team")
    if page.startswith("reports:va"):
        return ("upload_content", "manage_tasks", "view_dashboard")
    if page.startswith("reports:"):
        return ("manage_reports",)
    if page == "availability:team":
        return ("manage_users", "manage_reports")
    if page.startswith("availability"):
        return None
    if page.startswith("onboarding"):
        return None
    if page.startswith("recommendation:"):
        return ("manage_reports", "view_dashboard")
    if page.startswith("automations:") or page.startswith("simulation:"):
        return ("manage_automations",)
    if page.startswith("accounts:"):
        return ("manage_accounts",)
    if page.startswith("account:"):
        return ("manage_accounts",)
    if page.startswith("models"):
        return ("view_dashboard",)
    if page.startswith("model:") and page.endswith(":tasks"):
        return ("manage_tasks",)
    if page.startswith("model:") and page.endswith(":incidents"):
        return ("manage_incidents",)
    if page.startswith("model:"):
        return ("view_dashboard",)
    if page.startswith("users:"):
        return ("manage_users",)
    if page.startswith("user:"):
        return ("manage_users",)
    if page.startswith("role:") or page == "permissions":
        return ("manage_roles",)
    if page.startswith("notification_targets") or page.startswith("notification_target:"):
        return ("manage_reports", "manage_roles")
    if page in {"bot_status", "production_status"}:
        return ("view_dashboard", "manage_reports", "manage_roles")
    permission = PAGE_PERMISSIONS.get(page)
    return (permission,) if permission else None


def _perform_admin_action(
    page: str,
    session: Session,
    actor: User,
    *,
    chat_id: int | None = None,
    chat_title: str | None = None,
) -> str | None:
    parts = page.split(":")
    if len(parts) >= 3 and parts[0] == "availability" and parts[1] == "set":
        try:
            set_availability(session, actor, actor=actor, status=parts[2])
        except ValueError:
            return "availability"
        return "availability"
    if page == "automations:simulate:proxy_repair":
        run = run_proxy_repair_simulation(session, actor=actor)
        return f"simulation:{run.id}"
    if page == "automations:simulate:daily_briefing":
        run = run_daily_briefing_simulation(session, actor=actor)
        return f"simulation:{run.id}"
    if len(parts) >= 3 and parts[0] == "simulation" and parts[1].isdigit():
        run = get_simulation_run(session, int(parts[1]))
        if run is None:
            return "automations:simulations"
        action = parts[2]
        if action == "approve":
            update_simulation_status(session, run, actor=actor, status="approved")
            return f"simulation:{run.id}"
        if action == "reject":
            update_simulation_status(session, run, actor=actor, status="rejected")
            return f"simulation:{run.id}"
    if len(parts) >= 3 and parts[0] == "recommendation" and parts[1].isdigit():
        recommendation = get_recommendation(session, int(parts[1]))
        if recommendation is None:
            return "reports:executive:recommendations"
        action = parts[2]
        if action in {"acknowledge", "dismiss", "resolve"}:
            status = {"acknowledge": "acknowledged", "dismiss": "dismissed", "resolve": "resolved"}[action]
            update_recommendation_status(session, recommendation, actor=actor, status=status)
            return f"recommendation:{recommendation.id}"
        if action == "jump":
            if recommendation.entity_type == "incident" and recommendation.entity_id:
                return f"incident:{recommendation.entity_id}"
            if recommendation.entity_type == "account" and recommendation.entity_id:
                return f"account:{recommendation.entity_id}"
            if recommendation.entity_type == "proxy" and recommendation.entity_id:
                return f"proxy:{recommendation.entity_id}"
            if recommendation.entity_type == "model_brand" and recommendation.entity_id:
                return f"model:{recommendation.entity_id}"
            return "reports:executive:recommendations"
    if page == "tasks:create":
        task = create_default_task(session, actor=actor)
        return f"task:{task.id}"
    if len(parts) >= 3 and parts[0] == "task" and parts[1].isdigit():
        task = get_task(session, int(parts[1]))
        if task is None:
            return "tasks:list"
        action = parts[2]
        if action == "start":
            start_task(session, task, actor=actor)
            return f"task:{task.id}"
        if action == "block":
            block_task(session, task, actor=actor)
            return f"task:{task.id}"
        if action == "complete":
            complete_task(session, task, actor=actor)
            return f"task:{task.id}"
        if action == "archive":
            archive_task(session, task, actor=actor)
            return f"task:{task.id}"
        if action == "escalate":
            escalate_task(session, task, actor=actor)
            return f"task:{task.id}"
        if action == "assign" and len(parts) >= 4 and parts[3].isdigit():
            assignee = get_user_by_id(session, int(parts[3]))
            if assignee is not None:
                assign_task(session, task, assignee, actor=actor)
            return f"task:{task.id}"
    if page == "incidents:create":
        incident = create_default_incident(session, actor=actor)
        return f"incident:{incident.id}"
    if len(parts) >= 3 and parts[0] == "incident" and parts[1].isdigit():
        incident = get_incident(session, int(parts[1]))
        if incident is None:
            return "incidents:list"
        action = parts[2]
        if action == "assign" and len(parts) >= 4 and parts[3].isdigit():
            assignee = get_user_by_id(session, int(parts[3]))
            if assignee is not None:
                assign_incident(session, incident, assignee, actor=actor)
            return f"incident:{incident.id}"
        if action == "escalate":
            escalate_incident(session, incident, actor=actor)
            return f"incident:{incident.id}"
        if action == "investigate":
            investigate_incident(session, incident, actor=actor)
            return f"incident:{incident.id}"
        if action == "resolve":
            resolve_incident(session, incident, actor=actor)
            return f"incident:{incident.id}"
        if action == "archive":
            archive_incident(session, incident, actor=actor)
            return f"incident:{incident.id}"
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
    if page == "notification_targets:add":
        target = create_placeholder_notification_target(session, actor=actor)
        return f"notification_target:{target.id}"
    if page == "notification_targets:add_current" and chat_id is not None:
        target_type = "telegram_group" if chat_title else "telegram_user"
        target = add_current_chat_as_target(
            session,
            actor=actor,
            chat_id=chat_id,
            chat_title=chat_title,
            target_type=target_type,
            purpose="testing",
        )
        return f"notification_target:{target.id}"
    if len(parts) >= 3 and parts[0] == "notification_target" and parts[1].isdigit():
        target = get_notification_target(session, int(parts[1]))
        if target is None:
            return "notification_targets"
        action = parts[2]
        if action == "disable":
            disable_notification_target(session, target, actor=actor)
            return f"notification_target:{target.id}"
        if action == "test":
            test_notification_target(session, target, actor=actor)
            return f"notification_target:{target.id}"
        if action == "send_test":
            test_notification_target(session, target, actor=actor)
            return f"notification_target:{target.id}"
        if action == "purpose" and len(parts) >= 4:
            set_notification_target_purpose(session, target, parts[3], actor=actor)
            return f"notification_target:{target.id}"
    return None


def screen_for_page(
    page: str,
    principal: PermissionPrincipal,
    recorder: AuditRecorder = audit_recorder,
    session: Session | None = None,
    user: User | None = None,
    chat_id: int | None = None,
    chat_title: str | None = None,
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

    permissions = permissions_for_page(normalized)
    if permissions is not None:
        try:
            if user is not None:
                if not any(user_has_permission(user, permission) for permission in permissions):
                    raise PermissionError(f"Missing one of: {', '.join(permissions)}")
            else:
                last_error: PermissionError | None = None
                for permission in permissions:
                    try:
                        require_permission(principal, permission)
                        break
                    except PermissionError as exc:
                        last_error = exc
                else:
                    raise last_error or PermissionError(f"Missing one of: {', '.join(permissions)}")
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
                        "permission": "_or_".join(permissions),
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
                        "permission": "_or_".join(permissions),
                    },
                )
            raise

    if session is not None and user is not None:
        action_target = _perform_admin_action(
            normalized,
            session,
            user,
            chat_id=chat_id,
            chat_title=chat_title,
        )
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
        or normalized.startswith("tasks:")
        or normalized.startswith("task:")
        or normalized.startswith("incidents:")
        or normalized.startswith("incident:")
        or normalized.startswith("reports:")
        or normalized.startswith("recommendation:")
        or normalized.startswith("automations:")
        or normalized.startswith("simulation:")
        or normalized.startswith("models:")
        or normalized.startswith("model:")
        or normalized.startswith("users:")
        or normalized.startswith("user:")
        or normalized.startswith("role:")
        or normalized.startswith("notification_targets")
        or normalized.startswith("notification_target:")
        or normalized == "bot_status"
        or normalized == "production_status"
        or normalized.startswith("availability")
        or normalized.startswith("onboarding")
    ):
        return render_page(normalized, session=session, user=user)
    return render_main_menu()
