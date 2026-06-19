from datetime import UTC, datetime

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .formatting import *
from app.bot.menu import callback_for, page_controls
from app.services.integrity import run_integrity_check
from app.services.bot_instances import bot_instance_diagnostics
from app.services.observability import production_observability_summary
from app.services.system_truth import reconcile_stale_system_warnings
from app.services.help_brain import (
    latest_ui_self_test_run,
    notification_pilot_status,
    recent_help_questions,
    run_ui_self_test,
)

def render_users_page(session: Session, status_filter: str | None = None) -> Screen:
    users = session.scalars(
        select(User).options(selectinload(User.roles)).order_by(User.id).limit(10)
    ).all()
    all_pending_count = sum(1 for user in users if user.status == "pending")
    if status_filter is not None:
        users = [user for user in users if user.status == status_filter]
    title = "Pending Users" if status_filter == "pending" else "Users"
    lines = [title, "", f"Pending: {all_pending_count}", ""]
    if not users:
        lines.append("No users yet.")
    buttons: list[tuple[str, str]] = []
    for user in users:
        role_names = ", ".join(role.name for role in user.roles) or "No roles"
        if user.display_name and user.username:
            identity = f"{user.display_name} (@{user.username})"
        elif user.username:
            identity = f"@{user.username}"
        else:
            identity = user.display_name or f"User {user.id}"
        lines.append(f"{user.id}. {identity}")
        lines.append(f"   Status: {user.status} | Roles: {role_names}")
        buttons.append((f"{user.id}. {identity} ({user.status})", f"nav:user:{user.id}"))
    return Screen(text="\n".join(lines), reply_markup=users_menu(buttons))

def render_user_detail_page(session: Session, user_id: int) -> Screen:
    user = session.scalar(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles), selectinload(User.roles).selectinload(Role.permissions))
    )
    if user is None:
        return Screen(text="User not found.", reply_markup=page_menu(back_to="users"))

    role_names = ", ".join(role.name for role in user.roles) or "No roles"
    logs = session.scalars(
        select(AuditLog)
        .where(AuditLog.resource_type == "user", AuditLog.resource_id == str(user.id))
        .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
        .limit(5)
    ).all()
    recent = [f"- {log.action} ({log.status})" for log in logs] or ["- No recent user actions"]
    username = f"@{user.username}" if user.username else "Not set"
    created_at = format_user_datetime(user, user.created_at) if user.created_at else "pending timestamp"
    last_seen = format_user_datetime(user, user.last_seen) if user.last_seen else "Not seen yet"
    lines = [
        "User Detail",
        "",
        f"Display Name: {user.display_name or 'Unknown'}",
        f"Username: {username}",
        f"Telegram ID: {_masked_telegram_id(user.telegram_id)}",
        f"Status: {user.status}",
        f"Roles: {role_names}",
        f"Language: {user.language or 'Not set'}",
        f"Country: {user.country or 'Not set'}",
        f"Timezone: {user.timezone}",
        f"Time Format: {user.time_format}",
        f"Created: {created_at}",
        f"Last Seen: {last_seen}",
        "",
        "Recent Audit Actions:",
        *recent,
    ]
    return Screen(text="\n".join(lines), reply_markup=user_detail_menu(user.id, user.status, user.is_owner))

def render_role_assignment_page(session: Session, user_id: int, action: str) -> Screen:
    user = session.scalar(select(User).where(User.id == user_id).options(selectinload(User.roles)))
    if user is None:
        return Screen(text="User not found.", reply_markup=page_menu(back_to="users"))
    title = "Assign Role" if action == "assign_role" else "Remove Role"
    if action == "remove_role":
        role_names = sorted(role.name for role in user.roles)
    else:
        assigned = {role.name for role in user.roles}
        role_names = [
            role_name
            for role_name in session.scalars(select(Role.name).order_by(Role.name)).all()
            if role_name not in assigned
        ]
    if not role_names:
        return Screen(
            text=f"{title}\n\nNo roles available.",
            reply_markup=page_menu(back_to=f"user:{user_id}"),
        )
    return Screen(
        text=f"{title}\n\nUser: {user.display_name or user.username or user.id}",
        reply_markup=role_choice_menu(user_id, action, list(role_names)),
    )

def render_roles_page(session: Session) -> Screen:
    roles = session.scalars(
        select(Role).options(selectinload(Role.permissions)).order_by(Role.name)
    ).all()
    lines = ["Roles", ""]
    buttons: list[tuple[str, str]] = []
    for role in roles:
        lines.append(f"{role.id}. {role.name} ({len(role.permissions)} permissions)")
        buttons.append((role.name, f"nav:role:{role.id}"))
    return Screen(text="\n".join(lines), reply_markup=roles_menu(buttons))

def render_role_detail_page(session: Session, role_id: int) -> Screen:
    role = session.scalar(
        select(Role).where(Role.id == role_id).options(selectinload(Role.permissions))
    )
    if role is None:
        return Screen(text="Role not found.", reply_markup=page_menu(back_to="roles"))
    permissions = "\n".join(f"- {permission.key}" for permission in sorted(role.permissions, key=lambda p: p.key))
    if not permissions:
        permissions = "- No permissions"
    return Screen(
        text=f"Role\n\nName: {role.name}\nPermissions:\n{permissions}",
        reply_markup=role_detail_menu(role.id),
    )

def render_permission_list_page(session: Session, role_id: int, action: str) -> Screen:
    role = session.scalar(
        select(Role).where(Role.id == role_id).options(selectinload(Role.permissions))
    )
    if role is None:
        return Screen(text="Role not found.", reply_markup=page_menu(back_to="roles"))
    role_keys = {permission.key for permission in role.permissions}
    if action == "add_permission":
        permission_keys = [key for key in DEFAULT_PERMISSION_DESCRIPTIONS if key not in role_keys]
        title = "Add Permission"
    else:
        permission_keys = sorted(role_keys)
        title = "Remove Permission"
    if not permission_keys:
        return Screen(text=f"{title}\n\nNo permissions available.", reply_markup=page_menu(back_to=f"role:{role.id}"))
    return Screen(
        text=f"{title}\n\nRole: {role.name}",
        reply_markup=permission_choice_menu(role.id, action, permission_keys),
    )

def render_default_permissions_page() -> Screen:
    lines = ["Default Permissions", ""]
    lines.extend(f"- {key}" for key in DEFAULT_PERMISSION_DESCRIPTIONS)
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="roles"))

def render_audit_logs_page(session: Session, user: User | None = None) -> Screen:
    logs = session.scalars(
        select(AuditLog).order_by(desc(AuditLog.created_at), desc(AuditLog.id)).limit(10)
    ).all()
    lines = ["Audit Logs", ""]
    if not logs:
        lines.append("No audit logs yet.")
    for log in logs:
        actor = log.actor_user_id if log.actor_user_id is not None else "system"
        target = f"{log.resource_type}:{log.resource_id}" if log.resource_id else log.resource_type
        timestamp = format_user_datetime(user, log.created_at) if log.created_at else "pending timestamp"
        lines.append(f"{timestamp}")
        lines.append(f"Actor: {actor} | Action: {log.action}")
        lines.append(f"Target: {target} | Status: {log.status}")
        lines.append("")
    return Screen(text="\n".join(lines).strip(), reply_markup=page_menu(back_to="settings"))

def render_access_pending() -> Screen:
    return Screen(
        text="Access pending approval.\n\nComplete or update your profile while an admin reviews access.",
        reply_markup=onboarding_pending_menu(),
    )

def render_disabled() -> Screen:
    return Screen(text="Account disabled.", reply_markup=main_menu())

def render_denied() -> Screen:
    return Screen(text="Access denied.", reply_markup=main_menu())

def render_bot_status_page(session: Session, user: User | None = None, *, details: bool = False) -> Screen:
    summary = system_status_summary(session)
    heartbeats = list_heartbeats(session)
    last_heartbeat = format_user_datetime(user, summary["last_heartbeat_at"]) if summary["last_heartbeat_at"] else "not seen yet"
    last_delivery_at = format_user_datetime(user, summary["last_delivery_attempted_at"]) if summary["last_delivery_attempted_at"] else "not attempted"
    deployment_time = summary["last_deployment_time"] or "not available"
    issues: list[str] = []
    for label, key in [("API", "api_status"), ("Bot", "bot_status"), ("DB", "db_status"), ("Redis", "redis_status")]:
        if str(summary[key]).lower() not in {"healthy", "ok"}:
            issues.append(f"{label} is {summary[key]}.")
    if summary["failed_notification_count"]:
        issues.append("Notification deliveries have failures.")
    if not details:
        return Screen(
            text="\n".join(
                [
                    "🟢 Bot Status" if not issues else "🟡 Bot Status",
                    "",
                    "Status:",
                    "Healthy" if not issues else "Needs Attention",
                    "",
                    f"Issues Found: {len(issues)}",
                    f"Last Heartbeat: {last_heartbeat}",
                    "",
                    "Summary:",
                    "Fortuna checked the API, bot worker, database, Redis, deployments, and notifications.",
                    "",
                    "Recommended Action:",
                    "No action needed." if not issues else issues[0],
                ]
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Refresh", callback_data=callback_for("bot_status"))],
                    [InlineKeyboardButton(text="Technical Details", callback_data=callback_for("bot_status:details"))],
                    *page_controls(back_to="settings"),
                ]
            ),
        )
    lines = [
        "Bot Status Technical Details",
        "",
        f"Environment: {summary['environment']}",
        f"Production Status: {summary['production_status']}",
        f"Last Deployment: {summary['last_deployment_status']}",
        f"Last Deployment Time: {deployment_time}",
        f"API: {summary['api_status']}",
        f"Bot: {summary['bot_status']}",
        f"DB: {summary['db_status']}",
        f"Redis: {summary['redis_status']}",
        f"Last Heartbeat: {last_heartbeat}",
        f"Railway Deployment: {summary['railway_deployment_status']}",
        f"Last Delivery Attempt: {summary['last_delivery_event_type']} / {summary['last_delivery_status']} at {last_delivery_at}",
        f"Failed Notification Count: {summary['failed_notification_count']}",
        f"Last Event: {summary['latest_event_type']}",
        "",
        "Services:",
    ]
    for heartbeat in heartbeats:
        seen = format_user_datetime(user, heartbeat.last_seen_at) if heartbeat.last_seen_at else "not seen yet"
        lines.append(f"- {heartbeat.service_name}: {heartbeat.status} at {seen}")
    return Screen(
        text="\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Executive Summary", callback_data=callback_for("bot_status"))],
                [InlineKeyboardButton(text="Production Observability", callback_data=callback_for("production_observability"))],
                *page_controls(back_to="settings"),
            ]
        ),
    )

def _observability_time(value, user: User | None = None) -> str:
    return format_user_datetime(user, value) if value else "Unknown"

def _yes_no(value) -> str:
    return "yes" if value else "no"

def _observability_summary_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Refresh", callback_data=callback_for("production_observability"))],
            [InlineKeyboardButton(text="Technical Details", callback_data=callback_for("production_observability:details"))],
            [InlineKeyboardButton(text="Run Integrity Check", callback_data=callback_for("integrity"))],
            *page_controls(back_to="owner_advanced"),
        ]
    )


def _observability_details_markup(back_to: str = "production_observability") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Executive Summary", callback_data=callback_for(back_to))],
            [InlineKeyboardButton(text="Run Integrity Check", callback_data=callback_for("integrity"))],
            [InlineKeyboardButton(text="Bot Instance Diagnostics", callback_data=callback_for("bot_instance_status"))],
            *page_controls(back_to=back_to),
        ]
    )


def _integrity_summary_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Refresh", callback_data=callback_for("integrity"))],
            [InlineKeyboardButton(text="Technical Details", callback_data=callback_for("integrity:details"))],
            *page_controls(back_to="production_observability"),
        ]
    )


def _integrity_details_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Executive Summary", callback_data=callback_for("integrity"))],
            [InlineKeyboardButton(text="Production Observability", callback_data=callback_for("production_observability"))],
            *page_controls(back_to="production_observability"),
        ]
    )


def render_production_observability_page(
    session: Session,
    user: User | None = None,
    *,
    details: bool = False,
) -> Screen:
    reconcile_stale_system_warnings(session, actor=user)
    summary = production_observability_summary(session)
    migration_status = summary["alembic_status"]
    migration_line = (
        f"Alembic: {summary['alembic_current']} / expected {summary['alembic_expected']} ({migration_status})"
    )
    if migration_status == "Mismatch":
        migration_line += "\nWarning: DB revision does not match expected head. Do not run destructive commands."
    notification_lines = []
    for item in summary["notification_readiness"]:
        marker = "Configured" if item["configured"] else "Missing"
        notification_lines.append(f"- {item['label']}: {marker} ({item['active_count']} active)")

    issues = list(summary["system_truth_current_issues"])
    status = "Healthy" if not issues else "Needs Attention"
    recommended_action = "Continue setup." if not issues else issues[0]
    if not details:
        checked_lines = (
            [
                "- PostgreSQL is durable",
                "- Redis is healthy",
                "- One bot instance is active",
                "- Migrations are current",
            ]
            if not issues
            else [f"- {issue}" for issue in issues[:4]]
        )
        summary_line = (
            "Fortuna checked this. Everything is running."
            if not issues
            else "Fortuna found one thing that needs attention."
            if len(issues) == 1
            else "Fortuna found a few things that need attention."
        )
        return Screen(
            text="\n".join(
                [
                    "🟢 Production Observability" if not issues else "🟡 Production Observability",
                    "",
                    "Status:",
                    status,
                    "",
                    f"Issues Found: {len(issues)}",
                    f"Last Check: {format_user_datetime(user, datetime.now(UTC))}",
                    "",
                    "Fortuna checked:",
                    *checked_lines,
                    "",
                    "Summary:",
                    summary_line,
                    "",
                    "Recommended Action:",
                    recommended_action,
                ]
            ),
            reply_markup=_observability_summary_markup(),
        )

    lines = [
        "Production Observability Technical Details",
        "",
        "Safe build metadata:",
        f"App: {summary['app_display_name']}",
        f"Version: {summary['app_version']}",
        f"Git Commit: {summary['git_commit']}",
        f"Deployed At: {summary['deployed_at']}",
        f"Railway Deployment: {summary['railway_deployment_id']}",
        f"Environment: {summary['environment']}",
        "",
        "Storage:",
        f"Backend: {summary['storage_backend']}",
        f"Driver: {summary['storage_driver']}",
        f"Durable: {_yes_no(summary['storage_durable']) if summary['storage_durable'] is not None else 'unknown'}",
        f"Risk: {summary['storage_risk_label']}",
        f"Warning: {summary['storage_warning']}",
        f"SQLite Fallback Allowed: {_yes_no(summary['sqlite_fallback_allowed'])}",
        f"SQLite Location: {summary['sqlite_file_location']}",
        f"Last DB Write: {_observability_time(summary['last_db_write_at'], user)}",
        f"Owners: {summary['owner_count']} | Roles: {summary['role_count']}",
        f"Audit Rows: {summary['audit_count']} | Event Rows: {summary['event_count']}",
        "",
        "Services:",
        f"API: {summary['api_status']}",
        f"Bot Worker: {summary['bot_status']}",
        f"DB Heartbeat: {summary['postgres_status']}",
        f"Redis: {summary['redis_status']}",
        f"Redis Connected: {_yes_no(summary['redis_connected'])}",
        f"Polling Guard Active: {_yes_no(summary['polling_guard_active'])}",
        f"Last Redis Ping: {_observability_time(summary['last_redis_ping_at'], user)}",
        f"Railway Service Status: {summary['railway_status']}",
        "",
        "Database Revision:",
        migration_line,
        "",
        "Bot Heartbeat:",
        f"Instance: {summary['bot_instance_id']}",
        f"Primary Polling: {_yes_no(summary['bot_primary_polling_enabled'])}",
        f"Polling Allowed: {_yes_no(summary['bot_polling_allowed'])}",
        f"Active Bot Instances: {summary['active_bot_instance_count']}",
        f"Duplicate Bot Instances: {summary['duplicate_bot_instance_count']}",
        f"Current Truth Issues: {', '.join(summary['system_truth_current_issue_codes']) or 'None'}",
        f"Polling Warning: {summary['bot_polling_warning']}",
        f"Bot Started: {summary['bot_started_at']}",
        f"Last Polling Loop: {summary['last_polling_loop_at']}",
        f"Last Telegram Update: {summary['last_telegram_update_at']}",
        f"Polling Guard: {summary['polling_guard']}",
        f"Redis Lock: {summary['redis_lock_status']}",
        f"Bot Last Seen: {_observability_time(summary['bot_last_seen_at'], user)}",
        "",
        "Last Operational Records:",
        f"Audit: {summary['last_audit_action']} at {_observability_time(summary['last_audit_at'], user)}",
        f"Event: {summary['last_event_type']} at {_observability_time(summary['last_event_at'], user)}",
        f"Automation Run: {summary['last_automation_run']} at {_observability_time(summary['last_automation_run_at'], user)}",
        f"Intelligence Run: {summary['last_intelligence_run']} at {_observability_time(summary['last_intelligence_run_at'], user)}",
        f"Last Delivery: {summary['last_delivery_status']}",
        f"Failed Notifications: {summary['failed_notification_count']}",
        f"Notification Targets Configured: {summary['notification_targets_configured_count']}",
        f"Help Questions Today: {summary['help_questions_today']}",
        f"Confused Help Feedback: {summary['help_confused_count']}",
        "",
        "Proxy Health Reality:",
        f"Real Health Checks: {_yes_no(summary['proxy_real_health_checks_enabled'])}",
        f"Real Location Checks: {_yes_no(summary['proxy_real_location_checks_enabled'])}",
        f"Last Real Proxy Check: {summary['last_real_proxy_check_status']} at {_observability_time(summary['last_real_proxy_check_at'], user)}",
        f"Recent Proxy Health Failures: {_yes_no(summary['recent_proxy_health_failures'])}",
        f"Proxy Pilot: {summary['proxy_pilot_status']}",
        "",
        "Notification Group Readiness:",
        f"Routing Mode: {summary['notification_routing_label']}",
        f"HQ Configured: {_yes_no(summary['notification_hq_configured'])}",
        f"Ops Configured: {_yes_no(summary['notification_ops_configured'])}",
        f"Alerts Configured: {_yes_no(summary['notification_alerts_configured'])}",
        f"Ops/Alerts Combined: {_yes_no(summary['notification_ops_alerts_combined'])}",
        *notification_lines,
        f"Notification Pilot: {summary['notification_pilot_status']}",
        "",
        "UI Self-Test:",
        f"Last Result: {summary['last_ui_self_test_status']} at {_observability_time(summary['last_ui_self_test_at'], user)}",
        "",
        "Logs:",
        summary["railway_note"],
    ]
    return Screen(text="\n".join(lines), reply_markup=_observability_details_markup())

def render_integrity_page(session: Session, user: User | None = None, *, details: bool = False) -> Screen:
    reconcile_stale_system_warnings(session, actor=user)
    result = run_integrity_check(session, actor=user)
    marker = "PASS" if result["overall"] == "pass" else "WARNING" if result["overall"] == "warning" else "FAIL"
    issues = [check for check in result["checks"] if check.status != "pass"]
    if not details:
        if result["overall"] == "pass":
            title = "\U0001f7e2 Production Check"
            status = "Everything looks healthy."
            summary = "Fortuna checked production storage, Redis, the bot instance, migrations, and core tables."
            recommended = "Continue setup."
        elif result["overall"] == "warning":
            title = "\U0001f7e1 Production Check"
            status = "One or more checks need attention."
            summary = "Fortuna found a warning. The details are available if you want to inspect it."
            recommended = issues[0].detail if issues else "Review Technical Details."
        else:
            title = "\U0001f534 Production Check"
            status = "Fortuna found a production problem."
            summary = "A core safety check failed. Review details before entering real data."
            recommended = issues[0].detail if issues else "Review Technical Details."
        issue_lines = [f"- {check.detail}" for check in issues[:4]]
        return Screen(
            text="\n".join(
                [
                    title,
                    "Production Integrity Check",
                    "",
                    status,
                    "",
                    "Fortuna checked:",
                    "- Database",
                    "- Redis",
                    "- Bot instances",
                    "- Migrations",
                    "- Learning",
                    "- Automation",
                    "- Proxies",
                    "",
                    "Summary:",
                    summary,
                    *(["", "Needs attention:", *issue_lines] if issue_lines else []),
                    "",
                    "Recommended action:",
                    recommended,
                    "",
                    "No secrets or connection strings are shown here.",
                ]
            ),
            reply_markup=_integrity_summary_markup(),
        )
    lines = [
        "Production Check Technical Details",
        "",
        f"Overall: {marker}",
        f"Storage: {result['storage_display_backend']}",
        f"Durable: {_yes_no(result['storage_durable']) if result['storage_durable'] is not None else 'unknown'}",
    ]
    if result.get("storage_warning"):
        lines.append(f"Warning: {result['storage_warning']}")
    lines.extend(
        [
            "",
            "Checks:",
        ]
    )
    for check in result["checks"]:
        status = "PASS" if check.status == "pass" else "WARN" if check.status == "warning" else "FAIL"
        lines.append(f"- {status}: {check.name}")
        lines.append(f"  {check.detail}")
    lines.extend(
        [
            "",
            "No secrets, tokens, proxy passwords, or raw connection strings are shown here.",
        ]
    )
    return Screen(text="\n".join(lines), reply_markup=_integrity_details_markup())


def render_botstatus_page(
    session: Session,
    user: User | None = None,
    *,
    current_instance_id: str | None = None,
    details: bool = False,
) -> Screen:
    diagnostics = bot_instance_diagnostics(session, current_instance_id=current_instance_id)
    warning = "None"
    if not diagnostics["preflight_allowed"]:
        warning = str(diagnostics["preflight_reason"])
    elif diagnostics["multiple_active_instances"]:
        warning = "Multiple active bot instance heartbeats detected."
    elif diagnostics["risk"] != "ready":
        warning = str(diagnostics["risk"])

    issue_count = 0 if warning == "None" else 1
    if not details:
        status = "Healthy" if issue_count == 0 else "Needs Attention"
        recommended_action = "No action needed." if issue_count == 0 else warning
        return Screen(
            text="\n".join(
                [
                    "🟢 Fortuna Bot Status" if issue_count == 0 else "🟡 Fortuna Bot Status",
                    "",
                    "Status:",
                    status,
                    "",
                    f"Issues Found: {issue_count}",
                    f"Last Check: {format_user_datetime(user, datetime.now(UTC))}",
                    "",
                    "Summary:",
                    "Fortuna checked polling, Redis guardrails, database durability, and duplicate bot instances.",
                    "",
                    "Recommended Action:",
                    recommended_action,
                ]
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Refresh", callback_data=callback_for("bot_instance_status"))],
                    [InlineKeyboardButton(text="Technical Details", callback_data=callback_for("bot_instance_status:details"))],
                    *page_controls(back_to="production_observability"),
                ]
            ),
        )

    lines = [
        "Fortuna Bot Status Technical Details",
        "",
        f"Instance: {diagnostics['instance_id_masked']}",
        f"Primary Polling: {_yes_no(diagnostics['primary_polling_enabled'])}",
        f"Polling Allowed: {_yes_no(diagnostics['preflight_allowed'])}",
        f"Redis Configured: {_yes_no(diagnostics['redis_configured'])}",
        f"Polling Guard: {diagnostics['polling_guard']}",
        f"Redis Lock: {diagnostics['redis_lock_status']}",
        f"DB Backend: {diagnostics['db_backend']}",
        f"Durable DB: {_yes_no(diagnostics['db_durable']) if diagnostics['db_durable'] is not None else 'unknown'}",
        f"Environment: {diagnostics['environment']}",
        f"Active Instances: {diagnostics['active_instance_count']}",
        f"Duplicate Instances: {diagnostics['duplicate_instance_count']}",
        f"Last Telegram Update: {diagnostics['last_update_at']}",
        f"Last Polling Loop: {diagnostics['last_polling_loop_at']}",
        f"Warning: {warning}",
        "",
        "No tokens, raw URLs, proxy passwords, or chat IDs are shown here.",
    ]
    return Screen(text="\n".join(lines), reply_markup=_observability_details_markup("bot_instance_status"))


def render_availability_page(session: Session, user: User) -> Screen:
    availability = get_or_create_availability(session, user)
    shift = (
        f"{availability.shift_start_local} - {availability.shift_end_local}"
        if availability.shift_start_local and availability.shift_end_local
        else "Not set"
    )
    quiet_hours = (
        f"{availability.quiet_hours_start_local} - {availability.quiet_hours_end_local}"
        if availability.quiet_hours_start_local and availability.quiet_hours_end_local
        else "Not set"
    )
    lines = [
        "My Availability",
        "",
        f"Status: {availability.status}",
        f"Language: {user.language or 'Not set'}",
        f"Country: {user.country or 'Not set'}",
        f"Timezone: {user.timezone}",
        f"Time Format: {user.time_format}",
        f"Shift: {shift}",
        f"Quiet Hours: {quiet_hours}",
        f"Last Seen: {format_user_datetime(user, user.last_seen)}",
    ]
    return Screen(text="\n".join(lines), reply_markup=availability_menu())

def render_team_availability_page(session: Session) -> Screen:
    users = session.scalars(
        select(User)
        .options(selectinload(User.availability), selectinload(User.roles))
        .order_by(User.status, User.display_name, User.id)
        .limit(30)
    ).all()
    lines = ["Team Availability", ""]
    if not users:
        lines.append("No users yet.")
    for user in users:
        availability = user.availability
        status = availability.status if availability else "off_shift"
        timezone = (availability.timezone if availability else user.timezone) or "UTC"
        roles = ", ".join(role.name for role in user.roles) or "No roles"
        lines.append(f"{_identity(user)}")
        lines.append(f"   Status: {status} | Timezone: {timezone} | Roles: {roles}")
        lines.append(f"   Last Seen: {format_user_datetime(user, user.last_seen)}")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="settings"))

def render_onboarding_page(session: Session, user: User, *, step: str | None = None) -> Screen:
    current_step = step or onboarding_next_step(user)
    if current_step == "language":
        return Screen(
            text="Welcome to Fortuna OS.\n\nStep 1: Select your language.",
            reply_markup=onboarding_language_menu(),
        )
    if current_step == "country":
        return Screen(
            text=f"Language: {user.language or 'Not set'}\n\nStep 2: Select your country.",
            reply_markup=onboarding_country_menu(),
        )
    if current_step == "timezone":
        timezones = timezone_suggestions_for_country(user.country)
        return Screen(
            text=f"Country: {user.country or 'Not set'}\n\nStep 3: Confirm your timezone.",
            reply_markup=onboarding_timezone_menu(timezones),
        )
    if current_step == "time_format":
        return Screen(
            text=f"Timezone: {user.timezone}\n\nStep 4: Select your time format.",
            reply_markup=onboarding_time_format_menu(),
        )
    role = primary_role(user)
    intro = role_intro(role)
    return Screen(
        text=(
            "Access pending approval.\n\n"
            f"Language: {user.language or 'Not set'}\n"
            f"Country: {user.country or 'Not set'}\n"
            f"Timezone: {user.timezone}\n"
            f"Time Format: {user.time_format}\n\n"
            f"Role Intro: {intro}\n\n"
            "Your profile is saved. An admin can approve access."
        ),
        reply_markup=onboarding_pending_menu(),
    )

def render_notification_targets_page(session: Session) -> Screen:
    targets = list_notification_targets(session)
    lines = [
        "Notification Targets",
        "",
        "To register a group or channel, open that Telegram space first, then tap Register Current Chat as Fortuna Target.",
        "Chat IDs stay masked in the UI.",
        "",
    ]
    buttons: list[tuple[str, str]] = []
    if not targets:
        lines.append("No notification targets yet. Start with Fortuna HQ, then add Fortuna Ops and Fortuna Alerts when the groups are ready.")
    for target in targets[:15]:
        status = "active" if target.is_active else "disabled"
        lines.append(f"{target.id}. {target.name}")
        lines.append(f"   Type: {target.target_type} | Purpose: {_notification_purpose_label(target.purpose)} | Status: {status}")
        lines.append(f"   Chat: {mask_target_chat_id(target)}")
        lines.append(f"   Last Tested: {format_user_datetime(None, target.last_tested_at) if target.last_tested_at else 'Never'}")
        buttons.append((f"{target.id}. {target.name} ({status})", f"nav:notification_target:{target.id}"))
    return Screen(text="\n".join(lines), reply_markup=notification_targets_menu(buttons))


def render_notification_group_setup_page(session: Session) -> Screen:
    statuses = notification_group_setup_status(session)
    latest = latest_delivery_attempt(session)
    latest_line = "No delivery attempts yet."
    if latest is not None:
        latest_line = f"{latest.event_type}: {latest.status} at {format_user_datetime(None, latest.attempted_at)}"
    lines = [
        "Notification Group Setup",
        "",
        "Required Fortuna spaces:",
        "- Fortuna HQ",
        "- Fortuna Ops",
        "- Fortuna Alerts",
        "",
        "Readiness:",
    ]
    for status in statuses:
        marker = "Configured" if status.configured else "Missing"
        when = format_user_datetime(None, status.last_delivery_at) if status.last_delivery_at else "never"
        lines.append(
            f"- {status.label}: {marker} ({status.active_count} active) | Last delivery: {status.last_delivery_status} at {when}"
        )
    lines.extend(
        [
            "",
            "How to register:",
            "1. Open the Fortuna Telegram group or channel.",
            "2. Add @FortunaSolstice_Bot if it is not already there.",
            "3. Tap Register Current Chat as Fortuna Target.",
            "4. Choose the matching purpose.",
            "5. Use Preview Routing before sending real group alerts.",
            "",
            f"Latest Delivery Attempt: {latest_line}",
        ]
    )
    return Screen(text="\n".join(lines), reply_markup=notification_group_setup_menu())


def render_notification_group_pilot_page(session: Session) -> Screen:
    status = notification_pilot_status(session)
    rows = status["statuses"]
    latest_at = format_user_datetime(None, status["latest_at"]) if status["latest_at"] else "never"
    lines = [
        "Notification Group Pilot",
        "",
        "Pilot goal: register the three Fortuna Telegram spaces without spamming real groups.",
        "Routing tests preview where alerts would go unless the owner explicitly sends a real test.",
        "",
        f"Configured: {status['configured']}/{status['required']}",
        f"Last Delivery Status: {status['latest_status']} at {latest_at}",
        "",
        "Required Groups:",
    ]
    for item in rows:
        marker = "Configured" if item.configured else "Missing"
        last = format_user_datetime(None, item.last_delivery_at) if item.last_delivery_at else "never"
        lines.append(f"- {item.label}: {marker} | Last test: {item.last_delivery_status} at {last}")
    lines.extend(
        [
            "",
            "Activation Checklist:",
            "1. Create the group/channel.",
            "2. Add @FortunaSolstice_Bot.",
            "3. Open that group/channel.",
            "4. Tap Register This Chat.",
            "5. Choose its purpose.",
            "6. Preview routing before sending real alerts.",
        ]
    )
    return Screen(text="\n".join(lines), reply_markup=notification_group_pilot_menu())


def render_notification_routing_page(session: Session) -> Screen:
    summary = notification_routing_mode_summary(session)
    latest_at = format_user_datetime(None, summary.last_delivery_at) if summary.last_delivery_at else "never"
    mode_note = (
        "HQ stays private. Ops and Alerts are combined into one team/action channel."
        if summary.combined_ops_alerts
        else "HQ, Ops, and Alerts are routed as separate Fortuna spaces."
    )
    lines = [
        "Notification Routing",
        "",
        f"Mode: {summary.label}",
        mode_note,
        "",
        "Current Targets:",
        f"- HQ: {'Configured' if summary.hq_configured else 'Not registered yet'}",
        f"- Ops: {'Configured' if summary.ops_configured else 'Not registered yet'}",
        f"- Alerts: {'Configured' if summary.alerts_configured else 'Not registered yet'}",
        "",
    ]
    if summary.combined_ops_alerts:
        lines.append(
            "Combined Ops/Alerts: Fortuna will route team operations and fast-action alerts to the Alerts target when Ops is not separate."
        )
    else:
        lines.append("Combined Ops/Alerts: Off")
    lines.extend(
        [
            "",
            f"Last Delivery: {summary.last_delivery_status} at {latest_at}",
            "",
            "Next step:",
            "When the owner creates a Telegram group/chat, open it and tap Register Current Chat.",
            "Test buttons preview safely if a target is missing.",
        ]
    )
    return Screen(text="\n".join(lines), reply_markup=notification_routing_menu())


def render_notification_routing_test_page(session: Session) -> Screen:
    statuses = notification_group_setup_status(session)
    configured = [status.label for status in statuses if status.configured]
    missing = [status.label for status in statuses if not status.configured]
    latest = latest_delivery_attempt(session)
    latest_line = "No routing test delivery attempt yet."
    if latest is not None:
        latest_line = f"{latest.event_type}: {latest.status} at {format_user_datetime(None, latest.attempted_at)}"
    lines = [
        "Notification Routing Test",
        "",
        "Safe behavior:",
        "- HQ, Ops, and Alerts are previewed by default.",
        "- Real sends require an explicit owner-approved target action.",
        "- Raw chat IDs are never shown.",
        "",
        "Would Send To:",
        *(f"- {label}" for label in (configured or ["No active targets configured"])),
        "",
        "Skipped or Missing:",
        *(f"- {label}" for label in (missing or ["None"])),
        "",
        f"Latest Attempt: {latest_line}",
    ]
    return Screen(text="\n".join(lines), reply_markup=notification_group_setup_menu())


def render_ui_self_test_page(
    session: Session,
    actor: User | None = None,
    *,
    run_now: bool = False,
    details: bool = False,
) -> Screen:
    if run_now and actor is not None:
        run_ui_self_test(session, actor=actor)
    latest = latest_ui_self_test_run(session)
    questions = recent_help_questions(session, limit=3)
    if latest is None:
        status = "Not Run Yet"
        issues_found = 0
        last_check = "Not run yet"
        summary = "Fortuna has not checked the Telegram screen renderers yet."
        recommended_action = "Run the self-test now."
        systems_checked = 0
    else:
        failures = len(latest.failures_json or [])
        warnings = len(latest.warnings_json or [])
        issues_found = failures + warnings
        systems_checked = latest.screens_checked
        last_check = format_user_datetime(actor, latest.created_at) if latest.created_at else "unknown time"
        if failures:
            status = "Needs Attention"
            summary = f"Fortuna found {failures} screen failure{'s' if failures != 1 else ''}."
            recommended_action = "Open Technical Details and fix the first failed screen."
        elif warnings:
            status = "Watch"
            summary = f"Fortuna found {warnings} warning{'s' if warnings != 1 else ''}, but no critical screen failures."
            recommended_action = "Review Technical Details when convenient."
        else:
            status = "Healthy"
            summary = "Fortuna did not find any critical issues."
            recommended_action = "No action needed."

    if not details:
        marker = "🟢" if status == "Healthy" else "🟡" if status in {"Watch", "Not Run Yet"} else "🔴"
        return Screen(
            text="\n".join(
                [
                    f"{marker} Fortuna Self-Test",
                    "",
                    "Status:",
                    status,
                    "",
                    f"Systems Checked: {systems_checked}",
                    f"Issues Found: {issues_found}",
                    f"Last Check: {last_check}",
                    "",
                    "Summary:",
                    summary,
                    "",
                    "Recommended Action:",
                    recommended_action,
                ]
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="Run Again", callback_data=callback_for("ui_self_test:run"))],
                    [InlineKeyboardButton(text="Technical Details", callback_data=callback_for("ui_self_test:details"))],
                    *page_controls(back_to="settings"),
                ]
            ),
        )

    lines = [
        "UI Self-Test Technical Details",
        "",
        "Owner-only internal renderer check for important Telegram screens.",
        "This verifies screen text/buttons without relying on Telegram Web callback clicks.",
        "",
    ]
    if latest is None:
        lines.append("No self-test has run yet.")
    else:
        when = format_user_datetime(actor, latest.created_at) if latest.created_at else "unknown time"
        lines.extend(
            [
                f"Last Result: {latest.status}",
                f"Screens Checked: {latest.screens_checked}",
                f"Failures: {len(latest.failures_json or [])}",
                f"Warnings: {len(latest.warnings_json or [])}",
                f"Timestamp: {when}",
            ]
        )
        if latest.failures_json:
            lines.append("")
            lines.append("Failures:")
            lines.extend(f"- {item}" for item in latest.failures_json[:5])
        if latest.warnings_json:
            lines.append("")
            lines.append("Warnings:")
            lines.extend(f"- {item}" for item in latest.warnings_json[:5])
    lines.extend(["", "Recent Help Questions:"])
    if not questions:
        lines.append("- None yet")
    for question in questions:
        lines.append(f"- {question.detected_intent}: {question.feedback or 'no feedback'}")
    return Screen(
        text="\n".join(lines),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Run Again", callback_data=callback_for("ui_self_test:run"))],
                [InlineKeyboardButton(text="Executive Summary", callback_data=callback_for("ui_self_test"))],
                [InlineKeyboardButton(text="Button Health Report", callback_data=callback_for("button_health"))],
                *page_controls(back_to="settings"),
            ]
        ),
    )

def render_notification_target_detail_page(session: Session, target_id: int) -> Screen:
    target = session.get(NotificationTarget, target_id)
    if target is None:
        return Screen(text="Notification target not found.", reply_markup=page_menu(back_to="notification_targets"))
    status = "active" if target.is_active else "disabled"
    lines = [
        "Notification Target",
        "",
        f"Name: {target.name}",
        f"Type: {target.target_type}",
        f"Purpose: {_notification_purpose_label(target.purpose)}",
        f"Status: {status}",
        f"Telegram Chat ID: {mask_target_chat_id(target)}",
        f"Last Tested: {format_user_datetime(None, target.last_tested_at) if target.last_tested_at else 'Never'}",
        "",
        "Recent Delivery Attempts:",
    ]
    attempts = latest_delivery_attempts_for_target(session, target, limit=5)
    if not attempts:
        lines.append("- None yet")
    for attempt in attempts:
        when = format_user_datetime(None, attempt.attempted_at) if attempt.attempted_at else "unknown time"
        suffix = f" ({attempt.error_message})" if attempt.error_message else ""
        lines.append(f"- {attempt.event_type}: {attempt.status} at {when}{suffix}")
    lines.extend([
        "",
        "Test messages are allowed only for explicitly configured safe targets.",
    ])
    return Screen(text="\n".join(lines), reply_markup=notification_target_detail_menu(target.id))

def render_notification_target_purpose_page(session: Session, target_id: int) -> Screen:
    target = session.get(NotificationTarget, target_id)
    if target is None:
        return Screen(text="Notification target not found.", reply_markup=page_menu(back_to="notification_targets"))
    lines = [
        "Set Notification Purpose",
        "",
        f"Target: {target.name}",
        f"Current Purpose: {_notification_purpose_label(target.purpose)}",
    ]
    return Screen(text="\n".join(lines), reply_markup=notification_target_purpose_menu(target.id))

