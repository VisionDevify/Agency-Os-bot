from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select

from .formatting import *
from app.services.fortuna_personality import dynamic_greeting, screen_lines
from app.services.productization import best_next_action, setup_steps
from app.services.system_truth import reconcile_stale_system_warnings, system_truth
from app.services.button_health import button_health_summary
from app.services.decision_engine import generate_coo_briefing
from app.services.decision_trends import safe_predictive_coo_report
from app.services.reality_calibration import safe_reality_calibration_report
from app.services.agency_awareness import agency_awareness_report

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


def _setup_progress(session: Session, report: dict | None = None) -> dict:
    report = report or build_activation_report(session)
    blockers = report["blockers"]
    codes = {blocker.get("code", "") for blocker in blockers}
    model_count = session.scalar(select(func.count(ModelBrand.id))) or 0
    account_count = session.scalar(select(func.count(Account.id))) or 0
    team_count = session.scalar(select(func.count(ModelBrandMember.user_id))) or 0
    creator_count = session.scalar(select(func.count(CreatorWatch.id)).where(CreatorWatch.is_active.is_(True))) or 0
    opportunity_count = session.scalar(select(func.count(Opportunity.id))) or 0
    proxy_count = session.scalar(select(func.count(Proxy.id))) or 0
    notification_count = session.scalar(select(func.count(NotificationTarget.id)).where(NotificationTarget.is_active.is_(True))) or 0
    sections = [
        {
            "label": "Model Setup",
            "complete": bool(model_count) and not any(code.startswith("model.missing") for code in codes),
            "attention": bool(model_count),
            "fix": "agency_activation:models",
            "view": "models",
            "missing": "Model profile",
        },
        {
            "label": "Accounts",
            "complete": bool(account_count) and int(report["accounts_ready"]) == 100,
            "attention": bool(account_count),
            "fix": "agency_activation:accounts",
            "view": "accounts",
            "missing": "Accounts",
        },
        {
            "label": "Team",
            "complete": bool(team_count) and int(report["teams_ready"]) == 100,
            "attention": bool(team_count),
            "fix": "agency_activation:team",
            "view": "manager_qa",
            "missing": "Team",
        },
        {
            "label": "Creators",
            "complete": bool(creator_count) and int(report["creators_ready"]) == 100,
            "attention": bool(creator_count),
            "fix": "agency_activation:creators",
            "view": "opportunities:creators",
            "missing": "Creators",
        },
        {
            "label": "Notifications",
            "complete": bool(notification_count) and int(report["notifications_ready"]) == 100,
            "attention": bool(notification_count),
            "fix": "notification_group_pilot",
            "view": "notification_group_setup",
            "missing": "Notifications",
        },
        {
            "label": "Proxy",
            "complete": bool(proxy_count),
            "attention": bool(proxy_count),
            "fix": "proxies",
            "view": "proxies:dashboard",
            "missing": "Proxy",
        },
    ]
    # Opportunities are useful context for the home completeness score even though they live under Growth.
    base_checks = [
        bool(model_count),
        sections[0]["complete"],
        bool(account_count),
        sections[1]["complete"],
        sections[2]["complete"],
        sections[3]["complete"],
        bool(opportunity_count),
        sections[4]["complete"],
        sections[5]["complete"],
        int(report["readiness_score"]) >= 70,
    ]
    missing = [section["missing"] for section in sections if not section["complete"]][:3]
    return {
        "complete_count": sum(1 for item in base_checks if item),
        "total": len(base_checks),
        "sections": sections,
        "missing": missing,
        "top_blocker": blockers[0] if blockers else None,
    }


def _estimated_minutes(missing_count: int) -> int:
    if missing_count <= 1:
        return 2
    if missing_count <= 3:
        return 5
    return 10


def render_main_menu(session: Session | None = None, user: User | None = None) -> Screen:
    if session is None or user is None:
        return Screen(text="Fortuna OS\nSelect an area.", reply_markup=main_menu())
    if primary_role(user) in {"Owner", "Admin"}:
        reconcile_stale_system_warnings(session, actor=user)
        report = build_activation_report(session)
        truth = system_truth(session)
        next_action = best_next_action(session, user)
        production_status = "\U0001f7e2 Production Healthy" if truth.production_ready else "\U0001f7e1 Production Needs Attention"
        emergency_warning: list[str] = []
        if truth.database_backend == "sqlite_fallback":
            production_status = "\U0001f7e1 Production Degraded"
            emergency_warning = [
                "",
                "Storage warning:",
                "Fortuna is running in emergency storage mode. Data may not persist.",
            ]
        progress = _setup_progress(session, report)
        missing = progress["missing"] or ["Nothing urgent"]
        focus = progress["top_blocker"]["title"] if progress["top_blocker"] else "Nothing urgent here"
        greeting = dynamic_greeting(user)
        lines = [
            "\U0001f319 Fortuna OS",
            "",
            f"{greeting.emoji} {greeting.text}",
            "",
            "🟢 Status" if production_status.startswith("\U0001f7e2") else "🟡 Status",
            "Everything is running smoothly." if production_status.startswith("\U0001f7e2") else production_status,
            *emergency_warning,
            "",
            "🎯 Today’s Focus",
            "Today’s Focus:",
            focus,
            "",
            "🧩 Missing",
            *[f"• {item}" for item in missing],
            "",
            "✨ Next Best Move",
            next_action.title,
            "",
            f"Estimated Time: {next_action.estimated_time}",
            "",
            "Ready when you are.",
        ]
        return Screen(text="\n".join(lines), reply_markup=owner_simple_home_menu())
    details = personalized_dashboard(session, user)
    items = role_home_items(user)
    next_action = best_next_action(session, user)
    role = details["role"]
    if role in {"Manager", "Chatter Manager"}:
        lines = screen_lines(
            header="Manager Home",
            header_emoji="👥",
            status="No urgent team issues.",
            noticed=["Review assignments and alerts."],
            next_move=f"Next best move: {next_action.title}",
        )
        lines[1:1] = ["", f"Welcome back, {details['display_name']}", f"Role: {details['role']}"]
    elif role in {"Senior Chatter", "Chatter"}:
        lines = screen_lines(
            header="My Work",
            header_emoji="🎯",
            status="Your work queue is ready.",
            noticed=["Assigned opportunities and tasks live here."],
            next_move=f"Next best move: {next_action.title}",
        )
        lines[1:1] = ["", f"Welcome back, {details['display_name']}", f"Role: {details['role']}"]
    elif role == "VA":
        lines = screen_lines(
            header="VA Tasks",
            header_emoji="📝",
            status="Setup work is ready when you are.",
            noticed=["Tasks and assignments are the main focus."],
            next_move=f"Next best move: {next_action.title}",
        )
        lines[1:1] = ["", f"Welcome back, {details['display_name']}", f"Role: {details['role']}"]
    else:
        lines = [
            f"✨ Welcome back, {details['display_name']}",
            "",
            f"Role: {details['role']}",
            f"Availability: {_status_marker(details['availability_status'])} {details['availability_status'].replace('_', ' ')}",
            "",
            "🎯 What matters",
            f"• Tasks due today: {details['tasks_due_today']}",
            f"• Overdue items: {details['overdue_items']}",
            f"• Assigned models: {details['assigned_models']}",
            "",
            "✨ Next Best Move",
            next_action.title,
            "",
            "Why:",
            next_action.reason,
        ]
    return Screen(text="\n".join(lines), reply_markup=role_home_menu(items))


def render_owner_advanced_page() -> Screen:
    lines = [
        "\U0001f319 More",
        "",
        "Advanced tools are here when you need them.",
        "",
        "Most days, Home and Today are enough. These areas are for deeper checks and owner tools.",
    ]
    return Screen(text="\n".join(lines), reply_markup=owner_advanced_home_menu())


def render_start_here_page(session: Session, user: User | None = None) -> Screen:
    report = build_activation_report(session)
    blockers = report["blockers"]
    score = int(report["readiness_score"])
    lines = [
        "Start Here",
        "",
        "Fortuna checked this for you.",
        "",
    ]
    if score < 70:
        lines.extend(
            [
                "Your agency is not fully set up yet. Let\u2019s finish the basics first.",
                "",
                "Top Setup Steps",
                "1. Complete model profile",
                "2. Add accounts",
                "3. Assign team",
                "4. Add creators",
                "5. Register notifications",
                "",
                "Next Best Move",
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


def _workspace_step(label: str, done: bool, page: str, *, waiting: bool = False) -> dict:
    return {
        "label": label,
        "done": done,
        "page": page,
        "waiting": waiting,
        "status": "Done" if done else "Waiting" if waiting else "Needs Attention",
    }


def _first_real_model(models: list[ModelBrand]) -> ModelBrand | None:
    for model in models:
        if not model.is_demo and model.status != "archived":
            return model
    return models[0] if models else None


def render_first_workspace_flow_page(session: Session, user: User | None = None) -> Screen:
    models = list_model_brands(session)
    accounts = list_accounts(session)
    proxies = list_proxies(session)
    creators = list_creator_watches(session, active_only=False, limit=100)
    opportunities = list_opportunities(session, include_archived=True, limit=100)
    first_model = _first_real_model(models)
    report = build_activation_report(session)
    model_ready = bool(
        first_model
        and first_model.display_name
        and first_model.display_name not in {"New Model 1", "Untitled Model", "Default Model"}
        and first_model.country
        and first_model.timezone
        and first_model.primary_platform
        and first_model.status == "active"
    )
    model_page = f"model:{first_model.id}:complete" if first_model else "setup:wizard:model"
    model_accounts = [account for account in accounts if first_model and account.model_brand_id == first_model.id]
    model_creators = [creator for creator in creators if first_model and creator.assigned_model_id == first_model.id]
    model_opportunities = [
        opportunity
        for opportunity in opportunities
        if first_model and opportunity.model_brand_id == first_model.id and opportunity.status != "archived"
    ]
    team_count = (
        session.scalar(
            select(func.count(ModelBrandMember.user_id)).where(ModelBrandMember.model_brand_id == first_model.id)
        )
        if first_model
        else 0
    ) or 0
    team_blockers = [
        blocker
        for blocker in report["blockers"]
        if blocker.get("section") == "team"
        and (
            not first_model
            or blocker.get("entity_id") in {None, first_model.id}
            or blocker.get("code") == "team.no_real_users"
        )
    ]
    team_skipped = bool(first_model and not team_count and not team_blockers)
    accounts_missing = [account for account in accounts_missing_proxy(session) if first_model and account.model_brand_id == first_model.id]
    daily = daily_autopilot_summary(session, user)
    daily_ran = bool(daily["last_run"])
    steps = [
        _workspace_step("Complete model profile", model_ready, model_page),
        _workspace_step("Add first account", bool(model_accounts), "setup:wizard:accounts", waiting=not first_model),
        _workspace_step("Add proxy", bool(proxies), "proxies:add"),
        _workspace_step("Assign proxy to account", bool(model_accounts) and not accounts_missing, "proxies:missing", waiting=not model_accounts),
        _workspace_step("Add team member or skip", bool(team_count or team_skipped), f"model:{first_model.id}:team" if first_model else "setup:wizard:team", waiting=not first_model),
        _workspace_step("Add creator watch", bool(model_creators), "setup:wizard:creators", waiting=not first_model),
        _workspace_step("Create first opportunity", bool(model_opportunities), "setup:wizard:opportunities", waiting=not first_model),
        _workspace_step("Run daily cycle", daily_ran, "automations:daily_autopilot:run", waiting=not model_opportunities),
    ]
    next_step = next((step for step in steps if not step["done"] and not step["waiting"]), None)
    if next_step is None:
        next_step = next((step for step in steps if not step["done"]), None)
    action_buttons = []
    if next_step is not None:
        action_buttons.append((next_step["label"], next_step["page"]))
    if first_model and not team_count and team_blockers:
        action_buttons.append(("Skip Team For Now", "first_workspace:skip_team"))
    lines = [
        "First Workspace Guide",
        "",
        "Fortuna will take you from empty workspace to usable daily operations.",
        "",
        "Current state:",
    ]
    for step in steps:
        marker = "\u2705" if step["done"] else "\u23f3" if step["waiting"] else "\U0001f534"
        lines.append(f"{marker} {step['label']}: {step['status']}")
        if step["label"] == "Add team member or skip" and team_skipped:
            lines.append("   Team setup is marked manual for now.")
    lines.extend(
        [
            "",
            "Why this matters:",
            "Each step connects the first model to the records Fortuna needs for daily operations.",
            "",
            "Next best action:",
            next_step["label"] if next_step else "Run the daily cycle and start operating.",
            "",
            "Safe vs risky:",
            "Setup, simulated checks, and records are safe. Real proxy checks and auth work require owner-controlled confirmation.",
        ]
    )
    return Screen("\n".join(lines), first_workspace_menu(action_buttons))


def render_today_priorities_page(session: Session, user: User | None = None) -> Screen:
    briefing = generate_coo_briefing(session, actor=user)
    prediction_report = safe_predictive_coo_report(session, decisions=briefing.decisions, actor=user)
    reality = safe_reality_calibration_report(session, actor=user)
    prediction = prediction_report.primary
    top = briefing.top_priority
    actions = todays_top_5_actions(session, actor=user)
    recent_actions = recent_operations_activity(session)
    approvals = pending_approvals(session)
    followups = outstanding_blockers(session)
    recommendations = list_recommendations(session, status="open", limit=5)
    button_health = button_health_summary(session)
    awareness = agency_awareness_report(session, persist=False)
    button_needs_review = button_health.open_issue_count > 0 and button_health.overall_status in {"needs_review", "needs_attention", "critical"}
    next_action = (
        top.next_best_move
        if top is not None
        else "Open Button Health."
        if button_needs_review
        else "Nothing urgent here."
    )
    buttons = []
    if top is not None:
        buttons.append(("✨ Do This Next", top.action_page))
    if button_needs_review:
        buttons.append(("🧭 Button Health", "button_health"))
    lines = [
        "🌅 What Matters Today",
        "",
        "Today's Priorities",
        "",
        "Recommended Next Action:",
        next_action,
        "",
        "🎯 First:",
    ]
    if top is not None:
        lines.extend([top.title, "", "Why:", top.risk])
    else:
        lines.append("- Nothing urgent here.")
    lines.extend(["", "✅ Stable:"])
    if any(decision.category == "system_health" for decision in briefing.risks):
        lines.append("- Production health needs review in Observability.")
    else:
        lines.append("- No active production blocker is competing with the top priority.")
    lines.extend(["", "🧘 Can Wait:"])
    if briefing.can_wait:
        lines.extend(f"- {decision.title}" for decision in briefing.can_wait[:3])
    else:
        lines.append("- No optional setup item is competing for attention.")
    if prediction is not None:
        if reality.available and reality.outcome_counts.get("pending", 0):
            lines.extend(["", "Prediction status:", "Still pending evidence."])
        lines.extend(["", "🔮 Likely next:", prediction.prediction_title])
    if awareness.degraded_mode or awareness.visibility_level == "low" or awareness.missing_domains:
        lines.extend(
            [
                "",
                "Visibility Gap:",
                (
                    "Some awareness data is currently unavailable. Review manual updates until access returns."
                    if awareness.degraded_mode
                    else f"Fortuna has {awareness.visibility_level} agency visibility right now."
                ),
                "",
                "Next:",
                awareness.next_best_move,
            ]
        )
    if briefing.learning_summary:
        lines.extend(["", "What Fortuna Learned:"])
        lines.extend(f"- {item}" for item in briefing.learning_summary[:2])
    lines.extend(["", "Top 5 Actions:"])
    if briefing.decisions:
        for index, decision in enumerate(briefing.decisions[:5], start=1):
            lines.append(f"{index}. {decision.title}")
    elif actions:
        for index, action in enumerate(actions[:5], start=1):
            lines.append(f"{index}. {action.title}")
    else:
        lines.append("- Nothing urgent here.")
    if button_needs_review:
        lines.extend(
            [
                "",
                "Needs Review:",
                f"Fortuna found {button_health.open_issue_count} button or navigation issue(s).",
                "",
                "Next Best Move:",
                "Open Button Health.",
            ]
        )
    lines.extend(["", "Urgent Items:"])
    urgent = [rec for rec in recommendations if rec.severity == "critical"]
    lines.extend(f"- {rec.title}" for rec in urgent[:3]) if urgent else lines.append("- None right now.")
    lines.extend(["", "Things Fortuna Did:"])
    lines.extend(f"- {item}" for item in recent_actions[:3]) if recent_actions else lines.append("- No actions recorded today.")
    lines.extend(["", "Pending Approvals:"])
    lines.extend(f"- {approval.rule.name if approval.rule else approval.automation_rule_id}" for approval in approvals[:3]) if approvals else lines.append("- No approvals waiting.")
    lines.extend(["", "Follow-Ups:"])
    lines.extend(f"- {item}" for item in followups[:3]) if followups else lines.append("- No follow-ups due.")
    return Screen("\n".join(lines), today_priorities_menu(buttons))


def render_setup_progress_page(session: Session, user: User | None = None) -> Screen:
    steps = setup_steps(session)
    next_step = next((step for step in steps if not step.complete and not step.optional and step.status != "Waiting"), None)
    if next_step is None:
        next_step = next((step for step in steps if not step.complete and step.status != "Waiting"), None)
    lines = [
        "\U0001f9e9 Setup",
        "",
        "Fortuna checked your setup path.",
        "",
        "Setup Steps:",
    ]
    rows: list[tuple[str, str, str]] = []
    for step in steps:
        if step.complete:
            marker = "\u2705"
        elif step.optional:
            marker = "\U0001f7e1"
        elif step.status == "Waiting":
            marker = "\u23f3"
        else:
            marker = "\U0001f534"
        lines.append(f"Step {step.number}: {step.label}")
        lines.append(f"{marker} {step.status}")
        if not step.complete and step.status != "Waiting":
            rows.append((step.label, step.action_page, step.action_page))
    lines.extend(
        [
            "",
            "Next Best Move:",
            next_step.action_label if next_step else "Run the daily cycle.",
            "",
            "Why:",
            next_step.why if next_step else "Setup looks complete enough for daily operations.",
            "",
            "One step at a time. You\u2019re close.",
        ]
    )
    return Screen("\n".join(lines), setup_progress_menu(rows))


def render_assistant_next_page(session: Session, user: User | None = None) -> Screen:
    next_action = best_next_action(session, user)
    lines = [
        "What Should I Do Next?",
        "",
        "Fortuna recommends:",
        next_action.title,
        "",
        "Why:",
        next_action.reason,
        "",
        "Estimated time:",
        next_action.estimated_time,
        "",
        "Ready when you are.",
    ]
    return Screen("\n".join(lines), assistant_next_menu(next_action.action_page))

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

