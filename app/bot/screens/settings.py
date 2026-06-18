from .formatting import *
from app.services.observability import production_observability_summary
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
    created_at = user.created_at.isoformat() if user.created_at else "pending timestamp"
    last_seen = user.last_seen.isoformat() if user.last_seen else "Not seen yet"
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

def render_audit_logs_page(session: Session) -> Screen:
    logs = session.scalars(
        select(AuditLog).order_by(desc(AuditLog.created_at), desc(AuditLog.id)).limit(10)
    ).all()
    lines = ["Audit Logs", ""]
    if not logs:
        lines.append("No audit logs yet.")
    for log in logs:
        actor = log.actor_user_id if log.actor_user_id is not None else "system"
        target = f"{log.resource_type}:{log.resource_id}" if log.resource_id else log.resource_type
        timestamp = log.created_at.isoformat() if log.created_at else "pending timestamp"
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

def render_bot_status_page(session: Session) -> Screen:
    summary = system_status_summary(session)
    heartbeats = list_heartbeats(session)
    last_heartbeat = summary["last_heartbeat_at"].isoformat() if summary["last_heartbeat_at"] else "not seen yet"
    last_delivery_at = (
        summary["last_delivery_attempted_at"].isoformat()
        if summary["last_delivery_attempted_at"]
        else "not attempted"
    )
    deployment_time = summary["last_deployment_time"] or "not available"
    lines = [
        "Bot Status",
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
        seen = heartbeat.last_seen_at.isoformat() if heartbeat.last_seen_at else "not seen yet"
        lines.append(f"- {heartbeat.service_name}: {heartbeat.status} at {seen}")
    return Screen(text="\n".join(lines), reply_markup=bot_status_menu())

def _observability_time(value) -> str:
    return value.isoformat() if value else "Unknown"

def _yes_no(value) -> str:
    return "yes" if value else "no"

def render_production_observability_page(session: Session) -> Screen:
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

    lines = [
        "Production Observability",
        "",
        "Safe build metadata:",
        f"App: {summary['app_display_name']}",
        f"Version: {summary['app_version']}",
        f"Git Commit: {summary['git_commit']}",
        f"Deployed At: {summary['deployed_at']}",
        f"Railway Deployment: {summary['railway_deployment_id']}",
        f"Environment: {summary['environment']}",
        "",
        "Services:",
        f"API: {summary['api_status']}",
        f"Bot Worker: {summary['bot_status']}",
        f"Postgres: {summary['postgres_status']}",
        f"Redis: {summary['redis_status']}",
        f"Railway Service Status: {summary['railway_status']}",
        "",
        "Database Revision:",
        migration_line,
        "",
        "Bot Heartbeat:",
        f"Bot Started: {summary['bot_started_at']}",
        f"Last Polling Loop: {summary['last_polling_loop_at']}",
        f"Last Telegram Update: {summary['last_telegram_update_at']}",
        f"Polling Guard: {summary['polling_guard']}",
        f"Redis Lock: {summary['redis_lock_status']}",
        f"Bot Last Seen: {_observability_time(summary['bot_last_seen_at'])}",
        "",
        "Last Operational Records:",
        f"Audit: {summary['last_audit_action']} at {_observability_time(summary['last_audit_at'])}",
        f"Event: {summary['last_event_type']} at {_observability_time(summary['last_event_at'])}",
        f"Automation Run: {summary['last_automation_run']} at {_observability_time(summary['last_automation_run_at'])}",
        f"Intelligence Run: {summary['last_intelligence_run']} at {_observability_time(summary['last_intelligence_run_at'])}",
        f"Last Delivery: {summary['last_delivery_status']}",
        f"Failed Notifications: {summary['failed_notification_count']}",
        f"Notification Targets Configured: {summary['notification_targets_configured_count']}",
        f"Help Questions Today: {summary['help_questions_today']}",
        f"Confused Help Feedback: {summary['help_confused_count']}",
        "",
        "Proxy Health Reality:",
        f"Real Health Checks: {_yes_no(summary['proxy_real_health_checks_enabled'])}",
        f"Real Location Checks: {_yes_no(summary['proxy_real_location_checks_enabled'])}",
        f"Last Real Proxy Check: {summary['last_real_proxy_check_status']} at {_observability_time(summary['last_real_proxy_check_at'])}",
        f"Recent Proxy Health Failures: {_yes_no(summary['recent_proxy_health_failures'])}",
        f"Proxy Pilot: {summary['proxy_pilot_status']}",
        "",
        "Notification Group Readiness:",
        *notification_lines,
        f"Notification Pilot: {summary['notification_pilot_status']}",
        "",
        "UI Self-Test:",
        f"Last Result: {summary['last_ui_self_test_status']} at {_observability_time(summary['last_ui_self_test_at'])}",
        "",
        "Logs:",
        summary["railway_note"],
    ]
    return Screen(text="\n".join(lines), reply_markup=production_observability_menu())

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
        lines.append("No notification targets yet. Start with Testing Sandbox, then add HQ, Operations, Incidents, and Automation Logs.")
    for target in targets[:15]:
        status = "active" if target.is_active else "disabled"
        lines.append(f"{target.id}. {target.name}")
        lines.append(f"   Type: {target.target_type} | Purpose: {_notification_purpose_label(target.purpose)} | Status: {status}")
        lines.append(f"   Chat: {mask_target_chat_id(target)}")
        lines.append(f"   Last Tested: {target.last_tested_at.isoformat() if target.last_tested_at else 'Never'}")
        buttons.append((f"{target.id}. {target.name} ({status})", f"nav:notification_target:{target.id}"))
    return Screen(text="\n".join(lines), reply_markup=notification_targets_menu(buttons))


def render_notification_group_setup_page(session: Session) -> Screen:
    statuses = notification_group_setup_status(session)
    latest = latest_delivery_attempt(session)
    latest_line = "No delivery attempts yet."
    if latest is not None:
        latest_line = f"{latest.event_type}: {latest.status} at {latest.attempted_at.isoformat()}"
    lines = [
        "Notification Group Setup",
        "",
        "Required Fortuna spaces:",
        "- Fortuna OS - HQ",
        "- Fortuna OS - Operations",
        "- Fortuna OS - Incidents",
        "- Fortuna OS - Automation Logs",
        "- Fortuna OS - Testing Sandbox",
        "",
        "Readiness:",
    ]
    for status in statuses:
        marker = "Configured" if status.configured else "Missing"
        when = status.last_delivery_at.isoformat() if status.last_delivery_at else "never"
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
            "5. Send real test messages only to Testing Sandbox by default.",
            "",
            f"Latest Delivery Attempt: {latest_line}",
        ]
    )
    return Screen(text="\n".join(lines), reply_markup=notification_group_setup_menu())


def render_notification_group_pilot_page(session: Session) -> Screen:
    status = notification_pilot_status(session)
    rows = status["statuses"]
    latest_at = status["latest_at"].isoformat() if status["latest_at"] else "never"
    lines = [
        "Notification Group Pilot",
        "",
        "Pilot goal: register the five Fortuna Telegram spaces without spamming real groups.",
        "Only Testing Sandbox should receive real test messages by default.",
        "",
        f"Configured: {status['configured']}/{status['required']}",
        f"Last Delivery Status: {status['latest_status']} at {latest_at}",
        "",
        "Required Groups:",
    ]
    for item in rows:
        marker = "Configured" if item.configured else "Missing"
        last = item.last_delivery_at.isoformat() if item.last_delivery_at else "never"
        lines.append(f"- Fortuna OS - {item.label}: {marker} | Last test: {item.last_delivery_status} at {last}")
    lines.extend(
        [
            "",
            "Activation Checklist:",
            "1. Create the group/channel.",
            "2. Add @FortunaSolstice_Bot.",
            "3. Open that group/channel.",
            "4. Tap Register This Chat.",
            "5. Choose its purpose.",
            "6. Test only Testing Sandbox first.",
        ]
    )
    return Screen(text="\n".join(lines), reply_markup=notification_group_pilot_menu())


def render_notification_routing_test_page(session: Session) -> Screen:
    statuses = notification_group_setup_status(session)
    configured = [status.label for status in statuses if status.configured]
    missing = [status.label for status in statuses if not status.configured]
    latest = latest_delivery_attempt(session)
    latest_line = "No routing test delivery attempt yet."
    if latest is not None:
        latest_line = f"{latest.event_type}: {latest.status} at {latest.attempted_at.isoformat()}"
    lines = [
        "Notification Routing Test",
        "",
        "Safe behavior:",
        "- Testing Sandbox gets one real test message if configured.",
        "- HQ, Operations, Incidents, and Automation Logs are simulated only.",
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


def render_ui_self_test_page(session: Session, actor: User | None = None, *, run_now: bool = False) -> Screen:
    if run_now and actor is not None:
        run_ui_self_test(session, actor=actor)
    latest = latest_ui_self_test_run(session)
    questions = recent_help_questions(session, limit=3)
    lines = [
        "UI Self-Test",
        "",
        "Owner-only internal renderer check for important Telegram screens.",
        "This verifies screen text/buttons without relying on Telegram Web callback clicks.",
        "",
    ]
    if latest is None:
        lines.append("No self-test has run yet.")
    else:
        when = latest.created_at.isoformat() if latest.created_at else "unknown time"
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
    return Screen(text="\n".join(lines), reply_markup=ui_self_test_menu())

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
        f"Last Tested: {target.last_tested_at.isoformat() if target.last_tested_at else 'Never'}",
        "",
        "Recent Delivery Attempts:",
    ]
    attempts = latest_delivery_attempts_for_target(session, target, limit=5)
    if not attempts:
        lines.append("- None yet")
    for attempt in attempts:
        when = attempt.attempted_at.isoformat() if attempt.attempted_at else "unknown time"
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
        f"Current Purpose: {target.purpose}",
    ]
    return Screen(text="\n".join(lines), reply_markup=notification_target_purpose_menu(target.id))

