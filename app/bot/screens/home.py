from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .formatting import *

def _owner_display_name(user: User) -> str:
    return user.display_name or user.username or "there"


def _owner_greeting(user: User | None) -> str:
    now = datetime.now(UTC)
    try:
        zone = ZoneInfo((user.timezone if user and user.timezone and user.timezone != "UTC" else "America/New_York"))
        hour = now.astimezone(zone).hour
    except ZoneInfoNotFoundError:
        hour = now.hour
    if hour < 12:
        return "Good morning"
    if hour < 18:
        return "Good afternoon"
    return "Good evening"


def _readiness_marker(score: int) -> str:
    if score >= 80:
        return "\U0001f7e2"
    if score >= 45:
        return "\U0001f7e1"
    return "\U0001f534"


def render_main_menu(session: Session | None = None, user: User | None = None) -> Screen:
    if session is None or user is None:
        return Screen(text="Fortuna OS\nSelect an area.", reply_markup=main_menu())
    if primary_role(user) in {"Owner", "Admin"}:
        report = build_activation_report(session)
        blockers = report["blockers"]
        next_move = blockers[0]["title"] if blockers else "Nothing urgent here."
        score = int(report["readiness_score"])
        lines = [
            "\U0001f319 Fortuna OS",
            f"{_owner_greeting(user)}, {_owner_display_name(user)}.",
            "",
            f"Readiness: {score}% {_readiness_marker(score)}",
            f"Today: {len(blockers[:5])} actions waiting",
            "Production: \U0001f7e2 Healthy",
            "",
            "Next best move:",
            next_move,
            "",
            "Ready when you are.",
        ]
        return Screen(text="\n".join(lines), reply_markup=owner_simple_home_menu())
    details = personalized_dashboard(session, user)
    items = role_home_items(user)
    lines = [
        f"Welcome back, {details['display_name']}",
        "",
        f"Role: {details['role']}",
        f"Availability: {_status_marker(details['availability_status'])} {details['availability_status'].replace('_', ' ')}",
        f"Tasks Due Today: {details['tasks_due_today']}",
        f"Overdue Items: {details['overdue_items']}",
        f"Assigned Models: {details['assigned_models']}",
        "",
        "Recommended Action:",
        details["recommended_action"],
        "",
        role_intro(details["role"]),
    ]
    return Screen(text="\n".join(lines), reply_markup=role_home_menu(items))


def render_owner_advanced_page() -> Screen:
    lines = [
        "Fortuna OS Advanced",
        "",
        "The deeper controls live here when you need them.",
        "",
        "Use Simple Mode for the daily flow.",
    ]
    return Screen(text="\n".join(lines), reply_markup=owner_advanced_home_menu())


def render_start_here_page(session: Session, user: User | None = None) -> Screen:
    report = build_activation_report(session)
    blockers = report["blockers"]
    score = int(report["readiness_score"])
    lines = [
        "Start Here",
        "",
        f"Readiness: {score}% {_readiness_marker(score)}",
        "",
    ]
    if score < 70:
        lines.extend(
            [
                "Your agency is not fully set up yet. Finish these first.",
                "",
                "Top Setup Steps:",
                "1. Complete model profile",
                "2. Add accounts",
                "3. Assign team",
                "4. Add creators",
                "5. Register notifications",
                "",
                "Recommended next move:",
                blockers[0]["title"] if blockers else "Open Setup and review progress.",
            ]
        )
    else:
        lines.extend(
            [
                "Nothing urgent here.",
                "",
                "Fortuna noticed the core setup is in good shape. Check Today for the next operating task.",
            ]
        )
    return Screen(text="\n".join(lines), reply_markup=start_here_menu())

def render_dashboard(
    stats: DashboardStats | None = None,
    session: Session | None = None,
    user: User | None = None,
) -> Screen:
    if session is not None and user is not None and primary_role(user) not in {"Owner", "Admin", "Manager"}:
        return render_personalized_dashboard_page(session, user)
    current = stats or (dashboard_stats(session) if session is not None else placeholder_dashboard_stats())
    lines = [
        "Dashboard",
        "",
        f"Total Users: {current.total_users}",
        f"Active Users: {current.active_users}",
        f"Total Accounts: {current.accounts}",
        f"Instagram Accounts: {current.instagram_accounts}",
        f"X Accounts: {current.x_accounts}",
        f"OnlyFans Accounts: {current.onlyfans_accounts}",
        f"Accounts Needing Login: {current.accounts_needing_login}",
        f"Accounts Needing 2FA: {current.accounts_needing_2fa}",
        f"Critical Accounts: {current.critical_accounts}",
        f"Open Tasks: {current.open_tasks}",
        f"Blocked Tasks: {current.blocked_tasks}",
        f"Overdue Tasks: {current.overdue_tasks}",
        f"Completed Today: {current.completed_tasks_today}",
        f"Open Incidents: {current.open_incidents}",
        f"Critical Incidents: {current.critical_incidents}",
        f"Models: {current.models}",
        f"Healthy Models: {current.healthy_models}",
        f"Warning Models: {current.warning_models}",
        f"Critical Models: {current.critical_models}",
        "",
        "Top Models by Activity:",
    ]
    lines.extend(f"- {item}" for item in current.top_model_activity[:5])
    if not current.top_model_activity:
        lines.append("- No model activity yet")
    lines.extend(["", "Recent Model Events:"])
    lines.extend(f"- {item}" for item in current.recent_model_events[:5])
    if not current.recent_model_events:
        lines.append("- No model events yet")
    lines.extend(
        [
            "",
            "Infrastructure:",
            f"Total Proxies: {current.total_proxies}",
            f"Healthy Proxies: {current.healthy_proxies}",
            f"Warning Proxies: {current.warning_proxies}",
            f"Critical Proxies: {current.critical_proxies}",
            f"Accounts Assigned Proxy: {current.accounts_assigned_proxy}",
            f"Accounts Missing Proxy: {current.accounts_missing_proxy}",
            f"Average Health Score: {current.average_proxy_health_score}",
            "",
            "Recent Rotations:",
        ]
    )
    lines.extend(f"- {item}" for item in current.recent_proxy_rotations[:5])
    if not current.recent_proxy_rotations:
        lines.append("- No rotations yet")
    lines.extend(["", "Recent Failures:"])
    lines.extend(f"- {item}" for item in current.recent_proxy_failures[:5])
    if not current.recent_proxy_failures:
        lines.append("- No failures yet")
    lines.extend(["", "Recent Incidents:"])
    lines.extend(f"- {item}" for item in current.recent_proxy_incidents[:5])
    if not current.recent_proxy_incidents:
        lines.append("- No proxy incidents yet")
    text = "\n".join(lines)
    return Screen(text=text, reply_markup=dashboard_menu())

def render_personalized_dashboard_page(session: Session, user: User) -> Screen:
    details = personalized_dashboard(session, user)
    performance = details["performance"]
    lines = [
        f"Welcome Back, {details['display_name']}",
        "",
        f"Role: {details['role']}",
        f"Availability: {_status_marker(details['availability_status'])} {details['availability_status'].replace('_', ' ')}",
        f"Tasks Due Today: {details['tasks_due_today']}",
        f"Overdue Items: {details['overdue_items']}",
        f"Assigned Models: {details['assigned_models']}",
        "",
        "Recommended Action:",
        details["recommended_action"],
        "",
        "Performance Snapshot:",
        f"Tasks Completed Today: {performance['tasks_completed']}",
        f"Overdue Items: {performance['overdue_items']}",
        f"Open Incidents: {performance['open_incidents']}",
        f"Accountability Score: {performance['accountability_score']}",
        "",
        "Recent Activity:",
    ]
    lines.extend(f"- {item}" for item in details["recent_activity"][:3])
    if not details["recent_activity"]:
        lines.append("- No recent activity yet")
    return Screen(text="\n".join(lines), reply_markup=personalized_dashboard_menu())

def render_daily_experience_page(session: Session, user: User) -> Screen:
    details = daily_experience(session, user)
    lines = [
        f"{details['greeting']}, {details['display_name']}",
        "",
        f"Role: {details['role']}",
        f"Today: {details['today']}",
        f"Availability: {_status_marker(details['availability_status'])} {details['availability_status'].replace('_', ' ')}",
        "",
        "Today's Priorities:",
    ]
    lines.extend(f"- {item}" for item in details["priorities"])
    lines.extend(
        [
            "",
            f"Tasks Due: {details['tasks_due_today']}",
            f"Open Incidents: {details['open_incidents']}",
            f"Recommendations: {details['recommended_action']}",
            "",
            "Quick Actions:",
        ]
    )
    lines.extend(f"- {label}" for label, _ in details["quick_actions"])
    return Screen(text="\n".join(lines), reply_markup=daily_experience_menu(details["quick_actions"]))

def render_performance_page(session: Session, user: User) -> Screen:
    role = primary_role(user)
    stats = role_performance_snapshot(session, user)
    lines = ["Performance Snapshot", "", f"Role: {role}", ""]
    if role in {"Senior Chatter", "Chatter"}:
        lines.extend(
            [
                f"Tasks Completed: {stats['tasks_completed']}",
                f"Opportunities Handled: {stats['opportunities_handled']}",
                f"Accountability Score: {stats['accountability_score']}",
            ]
        )
    elif role == "VA":
        lines.extend(
            [
                f"Tasks Completed: {stats['tasks_completed']}",
                f"Accounts Maintained: {stats['accounts_maintained']}",
                f"Overdue Items: {stats['overdue_items']}",
            ]
        )
    elif role in {"Manager", "Chatter Manager", "Owner", "Admin"}:
        metrics = manager_command_metrics(session)
        lines.extend(
            [
                f"Team Health: {_status_marker('healthy' if metrics['overdue_tasks'] == 0 else 'warning')}",
                f"Open Incidents: {metrics['open_incidents']}",
                f"Overdue Tasks: {metrics['overdue_tasks']}",
                f"People On Shift: {len(metrics['on_shift'])}",
            ]
        )
    else:
        lines.extend(
            [
                f"Tasks Completed: {stats['tasks_completed']}",
                f"Overdue Items: {stats['overdue_items']}",
                f"Accountability Score: {stats['accountability_score']}",
            ]
        )
    lines.extend(["", "This is for visibility and support, not punishment."])
    return Screen(text="\n".join(lines), reply_markup=performance_menu())

def render_structure_map_page() -> Screen:
    lines = [
        "How Fortuna OS Is Organized",
        "",
        "Fortuna HQ",
        "↓",
        "Models / Brands",
        "↓",
        "Accounts + Team",
        "↓",
        "Tasks + Incidents + Opportunities",
        "↓",
        "Reports + Intelligence + Automations",
        "",
        "Start with one model/brand. Everything else attaches to that.",
    ]
    return Screen("\n".join(lines), structure_map_menu())

