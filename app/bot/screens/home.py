from .formatting import *

def render_main_menu(session: Session | None = None, user: User | None = None) -> Screen:
    if session is None or user is None:
        return Screen(text="Fortuna OS\nSelect an area.", reply_markup=main_menu())
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

