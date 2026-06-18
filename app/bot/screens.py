from dataclasses import dataclass

from aiogram.types import InlineKeyboardMarkup
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.bot.menu import (
    account_setup_state_menu,
    account_detail_menu,
    account_list_menu,
    account_model_choice_menu,
    account_platform_menu,
    account_proxy_choice_menu,
    accounts_menu,
    activation_blocker_detail_menu,
    activation_section_menu,
    agency_activation_menu,
    automation_approval_detail_menu,
    automation_approvals_menu,
    automation_rule_detail_menu,
    automation_rules_menu,
    automation_run_detail_menu,
    automation_runs_menu,
    automation_templates_menu,
    automations_menu,
    availability_menu,
    briefing_menu,
    bot_status_menu,
    chatter_workspace_menu,
    choice_menu,
    coo_briefing_menu,
    coo_dashboard_menu,
    creator_watch_detail_menu,
    creator_watch_menu,
    dashboard_menu,
    daily_experience_menu,
    daily_digest_menu,
    daily_autopilot_menu,
    demo_seed_menu,
    executive_mode_menu,
    executive_dashboard_menu,
    first_day_plan_menu,
    help_center_menu,
    help_copilot_menu,
    incident_detail_menu,
    incident_list_menu,
    incident_user_choice_menu,
    incidents_menu,
    intelligence_briefing_menu,
    intelligence_menu,
    intelligence_run_menu,
    learning_center_menu,
    learning_playbooks_menu,
    main_menu,
    manager_command_menu,
    manager_queue_menu,
    manager_setup_qa_menu,
    model_completion_menu,
    model_detail_menu,
    model_edit_menu,
    model_list_menu,
    model_member_choice_menu,
    model_team_menu,
    models_menu,
    notification_target_detail_menu,
    notification_target_purpose_menu,
    notification_digest_mode_menu,
    notification_targets_menu,
    onboarding_country_menu,
    onboarding_language_menu,
    onboarding_pending_menu,
    onboarding_time_format_menu,
    onboarding_timezone_menu,
    operations_dashboard_menu,
    opportunities_menu,
    opportunity_command_menu,
    opportunity_detail_menu,
    page_menu,
    performance_menu,
    platform_filter_menu,
    post_watch_menu,
    post_watch_detail_menu,
    playbook_detail_menu,
    permission_choice_menu,
    proxies_menu,
    proxy_account_choice_menu,
    proxy_detail_menu,
    proxy_entry_check_menu,
    proxy_list_menu,
    reports_menu,
    recommendation_detail_menu,
    recommendations_menu,
    readiness_v2_menu,
    role_choice_menu,
    role_detail_menu,
    role_home_menu,
    roles_menu,
    scheduled_automations_menu,
    settings_menu,
    simulation_run_detail_menu,
    simulation_runs_menu,
    setup_finish_menu,
    setup_wizard_menu,
    task_detail_menu,
    task_list_menu,
    task_user_choice_menu,
    team_qa_detail_menu,
    team_onboarding_activation_menu,
    team_activation_menu,
    team_qa_menu,
    tasks_menu,
    user_detail_menu,
    users_menu,
    structure_map_menu,
    owner_daily_checklist_menu,
    fortuna_action_log_menu,
    my_work_menu,
    top5_actions_menu,
)
from app.models.account import ACCOUNT_PLATFORMS, Account
from app.models.audit import AuditLog
from app.models.incident import Incident
from app.models.intelligence import ExecutiveInsight, IntelligenceRun, IntelligenceSignal, IssuePattern, TrendSnapshot, WorkloadSnapshot
from app.models.model_brand import MODEL_BRAND_RELATIONSHIP_TYPES, ModelBrand, ModelBrandMember
from app.models.opportunity import (
    CREATOR_WATCH_PLATFORMS,
    CREATOR_WATCH_PRIORITIES,
    OPPORTUNITY_PLATFORMS,
    OPPORTUNITY_PRIORITIES,
    OPPORTUNITY_STATUSES,
    POST_WATCH_ATTENTION_LEVELS,
    POST_WATCH_PLATFORMS,
    POST_WATCH_TYPES,
    CreatorWatch,
    Opportunity,
    OpportunityResult,
    PostWatch,
)
from app.models.permissions import Permission, Role
from app.models.proxy import Proxy
from app.models.automation import AutomationApproval, AutomationRule, AutomationRun, AutomationRunStep, AutomationSimulationRun
from app.models.recommendation import Recommendation
from app.models.reporting import NotificationTarget
from app.models.task import Task
from app.models.user import User
from app.services.auth import DEFAULT_PERMISSION_DESCRIPTIONS
from app.services.automations import (
    BUILTIN_AUTOMATION_TEMPLATES,
    automation_metrics,
    get_automation_rule,
    get_automation_run,
    get_automation_step,
    latest_automation_runs,
    latest_rule_approval,
    list_automation_rules,
    list_simulation_runs,
    pending_approvals,
    rollback_plan_for_rule,
    seed_builtin_automation_templates,
)
from app.services.heartbeats import list_heartbeats, system_status_summary
from app.services.dashboard import DashboardStats, dashboard_stats, placeholder_dashboard_stats
from app.services.accounts import (
    account_audit_logs,
    account_health,
    accounts_for_model,
    accounts_needing_attention,
    latest_waiting_auth_session,
    list_accounts,
    platform_label,
)
from app.services.agency_activation import (
    account_setup_states,
    build_activation_report,
)
from app.services.autonomous_operations import outstanding_blockers, recent_operations_activity
from app.services.coo import (
    coo_briefing,
    chatter_work_queue,
    executive_mode_summary,
    fortuna_messages,
    manager_work_queue,
    readiness_score_v2,
    team_load_balancer,
    todays_top_5_actions,
    top_priorities,
)
from app.services.model_brands import (
    RELATIONSHIP_LABELS,
    active_users_for_assignment,
    list_model_brands,
    model_audit_logs,
    summarize_members,
)
from app.services.model_health import calculate_model_health
from app.services.incidents import (
    critical_incidents,
    escalation_target_for,
    get_incident,
    incident_audit_logs,
    incident_timeline,
    incidents_for_model,
    list_incidents,
    my_incidents,
    open_incidents,
    severity_label,
)
from app.services.operations import (
    chatter_dashboard,
    executive_dashboard,
    generate_accountability_report,
    generate_daily_briefing,
    generate_daily_digest,
    daily_digest_delivery_history,
    record_dashboard_view,
    record_report_view,
    operations_dashboard,
    preview_daily_digest,
    request_briefing_send,
    request_digest_send,
    va_dashboard,
    view_accountability_report,
    view_latest_daily_briefing,
)
from app.services.team_operations import (
    format_user_datetime,
    get_or_create_availability,
    manager_command_metrics,
    onboarding_next_step,
    timezone_suggestions_for_country,
)
from app.services.team_experience import (
    create_notification_digest,
    daily_experience,
    help_text,
    help_topics_for_role,
    human_term,
    list_notification_digests,
    list_onboarding_checklists,
    personalized_dashboard,
    primary_role,
    role_home_items,
    role_intro,
    role_performance_snapshot,
    run_due_scheduled_automations,
    scheduled_automation_summary,
)
from app.services.notifications import (
    latest_delivery_attempts_for_target,
    list_notification_targets,
    mask_target_chat_id,
)
from app.services.proxies import (
    accounts_for_proxy,
    accounts_missing_proxy,
    affected_models_for_proxy,
    calculate_proxy_health,
    infrastructure_stats,
    list_proxies,
    recent_proxy_audit_logs,
    simulation_mode_summary,
)
from app.services.production_activation import (
    autonomous_action_log,
    daily_autopilot_summary,
    find_activation_blocker,
    owner_daily_checklist,
    proxy_entry_status,
    team_onboarding_activation,
)
from app.services.tasks import (
    assigned_tasks,
    blocked_tasks,
    get_task,
    list_tasks,
    my_tasks,
    overdue_tasks,
    task_audit_logs,
    tasks_for_model,
)
from app.services.recommendations import generate_recommendations, list_recommendations
from app.services.intelligence import (
    command_center_intelligence_status,
    generate_executive_intelligence_briefing,
    list_executive_insights,
    list_intelligence_runs,
    list_patterns,
    list_signals,
    list_trends,
    list_workload_snapshots,
    recommendation_why,
)
from app.services.learning import (
    automation_learning_summary,
    executive_memory_briefing,
    get_playbook,
    learning_center_metrics,
    list_confidence_records,
    list_learning_events,
    list_outcome_memories,
    list_playbooks,
    opportunity_learning_summary,
    recommend_playbooks,
)
from app.services.opportunities import (
    active_users_for_opportunity_assignment,
    chatter_workspace,
    comment_strategies_for_opportunity,
    get_creator_watch,
    get_opportunity,
    get_post_watch,
    help_copilot_answer,
    list_opportunities,
    list_creator_watches,
    list_models_for_opportunity_assignment,
    list_post_watches,
    manager_opportunity_view,
    opportunity_learning_overview,
    opportunity_queue_summary,
    opportunity_results,
    team_activation_qa,
    team_activation_summary,
)
from app.services.setup_wizard import (
    first_day_plan,
    latest_setup_state,
    manager_setup_qa,
    summarize_setup_state,
)


@dataclass(frozen=True)
class Screen:
    text: str
    reply_markup: InlineKeyboardMarkup


PAGE_TITLES: dict[str, str] = {
    "users": "Users",
    "models": "Models",
    "roles": "Roles",
    "accounts": "Accounts",
    "proxies": "Proxies",
    "tasks": "Tasks",
    "incidents": "Incidents",
    "reports": "Reports",
    "intelligence": "Intelligence",
    "opportunities": "Opportunities",
    "automations": "Automations",
    "settings": "Settings",
}


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


def render_help_center_page(user: User | None = None) -> Screen:
    buttons = [(label, f"nav:help:{topic}") for topic, label in help_topics_for_role(user)]
    lines = [
        "Help Center",
        "",
        "Quick answers for day-to-day work.",
        "Pick a topic when you need a reminder or a clean next step.",
    ]
    return Screen(text="\n".join(lines), reply_markup=help_center_menu(buttons))


def render_help_topic_page(topic: str, user: User | None = None) -> Screen:
    title = dict(help_topics_for_role(user)).get(topic, topic.replace("_", " ").title())
    return Screen(
        text=f"{title}\n\n{help_text(topic, user)}",
        reply_markup=page_menu(back_to="help"),
    )


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


def render_setup_wizard_page(session: Session, user: User | None = None) -> Screen:
    state = latest_setup_state(session, user) if user is not None else None
    summary = summarize_setup_state(session, state)
    model = summary["model"]
    lines = [
        "Fortuna Setup Wizard",
        "",
        "Use this to make Fortuna OS usable for the team without guessing where to start.",
        "",
        "Steps:",
        "1. Create Model/Brand",
        "2. Add Accounts",
        "3. Assign Team",
        "4. Add Creator Watchlist Starters",
        "5. Create Starter Opportunities",
        "6. Review Setup Summary",
        "",
        f"Current Model: {model.display_name if model else 'None yet'}",
        f"Accounts Added: {summary['accounts']}",
        f"Team Assigned: {summary['team']}",
        f"Creators Added: {summary['creators']}",
        f"Opportunities Created: {summary['opportunities']}",
    ]
    if summary["missing"]:
        lines.extend(["", "Still Missing:", *[f"- {item.title()}" for item in summary["missing"]]])
    else:
        lines.extend(["", "Setup has the basics. Review and finish when ready."])
    return Screen("\n".join(lines), setup_wizard_menu())


def _readiness_label(score: int) -> str:
    if score >= 85:
        return "Ready"
    if score >= 60:
        return "Needs Attention"
    return "Blocked"


def render_agency_activation_page(session: Session) -> Screen:
    report = build_activation_report(session)
    blockers = report["blockers"]
    recent_actions = recent_operations_activity(session)
    open_blockers = outstanding_blockers(session)
    lines = [
        "Fortuna Activation",
        "",
        f"Fortuna Readiness: {_status_marker('healthy' if report['readiness_score'] >= 85 else 'warning' if report['readiness_score'] >= 60 else 'critical')} {report['readiness_score']}% ({_readiness_label(report['readiness_score'])})",
        "",
        f"Models Ready: {report['models_ready']}%",
        f"Accounts Ready: {report['accounts_ready']}%",
        f"Teams Ready: {report['teams_ready']}%",
        f"Creators Ready: {report['creators_ready']}%",
        f"Opportunities Ready: {report['opportunities_ready']}%",
        f"Notifications Ready: {report['notifications_ready']}%",
        "",
        "Top Blockers:",
    ]
    if not blockers:
        lines.append("- None. Setup is ready for daily operations.")
    for blocker in blockers[:6]:
        lines.append(f"- {blocker['title']}")
    lines.extend(["", "What Fortuna OS Did Today:"])
    lines.extend(f"- {item}" for item in recent_actions[:4])
    if not recent_actions:
        lines.append("- No autonomous actions recorded yet.")
    lines.extend(["", "Outstanding Blockers:"])
    lines.extend(f"- {item}" for item in open_blockers[:4])
    if not open_blockers:
        lines.append("- No autonomous blockers currently open.")
    lines.extend(
        [
            "",
            "Run Activation Scan to save this readiness snapshot, refresh recommendations, and create setup tasks without duplicates.",
        ]
    )
    return Screen("\n".join(lines), agency_activation_menu())


def render_activation_section_page(session: Session, section: str) -> Screen:
    report = build_activation_report(session)
    blockers = [blocker for blocker in report["blockers"] if blocker.get("section") == section]
    title = {
        "models": "Fix Models",
        "accounts": "Fix Accounts",
        "team": "Fix Team",
        "creators": "Fix Creators",
        "opportunities": "Fix Opportunities",
        "notifications": "Fix Notifications",
    }.get(section, "Fix Setup")
    lines = [title, ""]
    if not blockers:
        lines.append("Nothing blocking this area right now.")
    for blocker in blockers[:10]:
        lines.append(f"- {blocker['title']}")
        lines.append(f"  Next: {blocker['description']}")
    choices: list[tuple[str, str]] = []
    for index, blocker in enumerate(blockers[:8]):
        choices.append((blocker["title"][:40], f"nav:agency_activation:blocker:{section}:{index}"))
        if blocker.get("action_page"):
            choices.append((f"Fix Now: {blocker['title'][:31]}", f"nav:{blocker['action_page']}"))
    choices.append(("Run Activation Scan", "nav:agency_activation:scan"))
    if not choices:
        return Screen("\n".join(lines), activation_section_menu(section))
    return Screen("\n".join(lines), choice_menu(choices, back_to="agency_activation"))


def render_activation_blocker_detail_page(session: Session, section: str, index: int, *, explain: bool = False) -> Screen:
    blocker = find_activation_blocker(session, section, index)
    if blocker is None:
        return Screen("This blocker is no longer active.", activation_section_menu(section))
    lines = [
        "Setup Blocker",
        "",
        blocker["title"],
        "",
        f"Status: {_status_marker(blocker.get('severity', 'warning'))} {blocker.get('severity', 'warning').title()}",
        f"Area: {section.title()}",
        "",
        "What is happening:",
        blocker["description"],
        "",
        "What to do next:",
        "Use Fix Now to open the exact setup screen. Use Skip for Later if this is real but not today's priority. Use Mark Not Needed only when this blocker does not apply to your agency.",
    ]
    if explain:
        lines.extend(
            [
                "",
                "Why this matters:",
                "Fortuna OS uses this signal to decide readiness, create setup tasks, and route work to the right person. Closing irrelevant blockers keeps the owner checklist focused.",
            ]
        )
    return Screen(
        "\n".join(lines),
        activation_blocker_detail_menu(section, index, blocker.get("action_page")),
    )


def render_model_completion_page(session: Session, model_id: int) -> Screen:
    model_brand = session.scalar(
        select(ModelBrand)
        .where(ModelBrand.id == model_id)
        .options(selectinload(ModelBrand.members).selectinload(ModelBrandMember.user))
    )
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="agency_activation:models"))
    accounts = accounts_for_model(session, model_id)
    creators = [creator for creator in list_creator_watches(session) if creator.assigned_model_id == model_id]
    opportunities = [opportunity for opportunity in list_opportunities(session) if opportunity.model_brand_id == model_id]
    relationship_types = {member.relationship_type for member in model_brand.members}
    checks = [
        ("Country", model_brand.country),
        ("Timezone", model_brand.timezone),
        ("Primary Platform", model_brand.primary_platform),
        ("Team", "assigned" if relationship_types else None),
        ("Accounts", str(len(accounts)) if accounts else None),
        ("Creators", str(len(creators)) if creators else None),
        ("Opportunities", str(len(opportunities)) if opportunities else None),
    ]
    lines = [
        "Model Completion Wizard",
        "",
        f"Model: {model_brand.display_name}",
        f"Status: {model_brand.status}",
        "",
        "Setup Checklist:",
    ]
    for label, value in checks:
        marker = "Done" if value else "Needs setup"
        lines.append(f"- {label}: {marker}{f' ({value})' if value else ''}")
    lines.extend(
        [
            "",
            "Use the buttons below to fill the missing pieces. You can come back here anytime from Fortuna Activation.",
        ]
    )
    return Screen("\n".join(lines), model_completion_menu(model_id))


def render_account_setup_state_page(session: Session) -> Screen:
    states = account_setup_states(session)
    lines = ["Account Setup State", ""]
    buttons: list[tuple[str, str]] = []
    if not states:
        lines.append("No accounts yet. Create a model first, then add IG/X/OF/Email account records without passwords.")
    for state in states[:12]:
        lines.append(f"{state.platform.title()} @{state.username}")
        lines.append(f"   Model: {state.model_name} | Status: {state.status}")
        lines.append(f"   Checklist: {', '.join(state.checklist)}")
        if state.recommended_actions:
            lines.append(f"   Next: {state.recommended_actions[0]}")
        buttons.append((f"{state.platform.title()} @{state.username}", f"nav:account:{state.account_id}"))
    return Screen("\n".join(lines), account_setup_state_menu(buttons))


def render_setup_model_prompt_page() -> Screen:
    lines = [
        "Create First Model",
        "",
        "Send the model/brand details in this format:",
        "",
        "Display Name | Stage Name | Country | Timezone | Notes",
        "",
        "Example:",
        "Fortuna Solstice | Fortuna | United States | America/New_York | Launch profile",
        "",
        "You can type skip for optional notes.",
    ]
    return Screen("\n".join(lines), page_menu(back_to="setup:wizard"))


def render_setup_accounts_page(session: Session, user: User | None = None) -> Screen:
    state = latest_setup_state(session, user) if user is not None else None
    summary = summarize_setup_state(session, state)
    model = summary["model"]
    if model is None:
        return Screen(
            "Add Accounts\n\nNo model exists yet. Create your first model/brand before adding IG/X/OF accounts.",
            choice_menu([("Create First Model", "nav:setup:wizard:model")], back_to="setup:wizard"),
        )
    choices = [
        ("Instagram", "nav:setup:wizard:accounts:platform:instagram"),
        ("X", "nav:setup:wizard:accounts:platform:x"),
        ("OnlyFans", "nav:setup:wizard:accounts:platform:onlyfans"),
        ("Email", "nav:setup:wizard:accounts:platform:email"),
        ("Other", "nav:setup:wizard:accounts:platform:other"),
    ]
    return Screen(
        "\n".join(
            [
                "Add Accounts",
                "",
                f"Model: {model.display_name}",
                "Choose a platform, then send username/display/reference details.",
                "Credential values stay out of Telegram.",
            ]
        ),
        choice_menu(choices, back_to="setup:wizard"),
    )


def render_setup_account_input_page(session: Session, user: User | None, platform: str) -> Screen:
    state = latest_setup_state(session, user) if user is not None else None
    summary = summarize_setup_state(session, state)
    model = summary["model"]
    if model is None:
        return render_setup_accounts_page(session, user)
    return Screen(
        "\n".join(
            [
                "Add Account",
                "",
                f"Model: {model.display_name}",
                f"Platform: {platform_label(platform)}",
                "",
                "Send:",
                "username | display name | URL/reference | notes",
                "",
                "Never send passwords or 2FA codes here.",
            ]
        ),
        page_menu(back_to="setup:wizard:accounts"),
    )


def render_setup_team_page(session: Session, user: User | None = None, relationship_type: str | None = None) -> Screen:
    state = latest_setup_state(session, user) if user is not None else None
    summary = summarize_setup_state(session, state)
    model = summary["model"]
    if model is None:
        return Screen(
            "Assign Team\n\nCreate a model/brand first, then assign managers, chatters, and VAs.",
            choice_menu([("Create First Model", "nav:setup:wizard:model")], back_to="setup:wizard"),
        )
    if relationship_type is None:
        choices = [
            ("Assign Manager", "nav:setup:wizard:team:assign:manager"),
            ("Assign Chatter Manager", "nav:setup:wizard:team:assign:chatter_manager"),
            ("Assign Senior Chatter", "nav:setup:wizard:team:assign:senior_chatter"),
            ("Assign Chatter", "nav:setup:wizard:team:assign:chatter"),
            ("Assign VA", "nav:setup:wizard:team:assign:va"),
            ("Skip For Later", "nav:setup:wizard:creators"),
        ]
        return Screen(
            f"Assign Team\n\nModel: {model.display_name}\nChoose the role you want to assign.",
            choice_menu(choices, back_to="setup:wizard"),
        )
    users = active_users_for_assignment(session)
    choices = [
        (_identity(user)[:40], f"nav:setup:wizard:team:assign:{relationship_type}:{user.id}")
        for user in users
    ]
    if not choices:
        return Screen(
            "Assign Team\n\nNo active users available yet. Approve users first, then come back.",
            choice_menu([("Pending Users", "nav:users:pending")], back_to="setup:wizard:team"),
        )
    label = RELATIONSHIP_LABELS.get(relationship_type, relationship_type)
    return Screen(
        f"Assign {label}\n\nModel: {model.display_name}\nPick a team member.",
        choice_menu(choices, back_to="setup:wizard:team"),
    )


def render_setup_creators_page(session: Session, user: User | None = None) -> Screen:
    state = latest_setup_state(session, user) if user is not None else None
    summary = summarize_setup_state(session, state)
    model = summary["model"]
    if model is None:
        return Screen(
            "Add Creator Starters\n\nCreate a model/brand first, then add creators worth watching.",
            choice_menu([("Create First Model", "nav:setup:wizard:model")], back_to="setup:wizard"),
        )
    return Screen(
        "\n".join(
            [
                "Add Creator Starters",
                "",
                f"Model: {model.display_name}",
                "Send one creator in this format:",
                "",
                "platform | username | display name | niche | priority",
                "",
                "Example: x | creatorname | Creator Name | fitness | high",
            ]
        ),
        choice_menu([("Use Full Creator Flow", "nav:opportunities:creators:add")], back_to="setup:wizard"),
    )


def render_setup_opportunities_page(session: Session, user: User | None = None) -> Screen:
    state = latest_setup_state(session, user) if user is not None else None
    summary = summarize_setup_state(session, state)
    model = summary["model"]
    if model is None:
        return Screen(
            "Create Starter Opportunities\n\nCreate a model/brand first, then create manual opportunities.",
            choice_menu([("Create First Model", "nav:setup:wizard:model")], back_to="setup:wizard"),
        )
    return Screen(
        "\n".join(
            [
                "Create Starter Opportunities",
                "",
                f"Model: {model.display_name}",
                "Send one opportunity in this format:",
                "",
                "title | platform | niche | assigned user id",
                "",
                "Use skip for assigned user id if you want to assign later.",
            ]
        ),
        choice_menu([("Use Full Opportunity Flow", "nav:opportunities:add")], back_to="setup:wizard"),
    )


def render_setup_summary_page(session: Session, user: User | None = None) -> Screen:
    state = latest_setup_state(session, user) if user is not None else None
    summary = summarize_setup_state(session, state)
    model = summary["model"]
    lines = [
        "Setup Summary",
        "",
        f"Model Created: {model.display_name if model else 'No'}",
        f"Accounts Added: {summary['accounts']}",
        f"Team Assigned: {summary['team']}",
        f"Creators Added: {summary['creators']}",
        f"Opportunities Created: {summary['opportunities']}",
        "",
        "Missing Items:",
    ]
    lines.extend(f"- {item.title()}" for item in summary["missing"]) if summary["missing"] else lines.append("- None")
    return Screen("\n".join(lines), setup_finish_menu(model.id if model else None))


def render_first_day_plan_page(session: Session, user: User) -> Screen:
    plan = first_day_plan(session, user)
    lines = [
        "First Day Plan",
        "",
        f"Progress: {plan['completion_score']}%",
        "",
        "Use this checklist to activate the agency cleanly.",
        "",
    ]
    for item in plan["items"]:
        marker = "Done" if item["done"] else "Next"
        lines.append(f"{marker}: {item['label']}")
    return Screen("\n".join(lines), first_day_plan_menu(plan["items"]))


def render_manager_setup_qa_page(session: Session) -> Screen:
    qa = manager_setup_qa(session)
    lines = [
        "Manager Setup / QA",
        "",
        "This shows what still needs a human owner. Use it to clean up setup gaps.",
        "",
        f"Models Without Manager: {len(qa['models_without_manager'])}",
        f"Models Without Chatters: {len(qa['models_without_chatters'])}",
        f"Accounts Without Model: {len(qa['accounts_without_model'])}",
        f"Opportunities Without Assignee: {len(qa['opportunities_without_assignee'])}",
        f"Tasks Without Owner: {len(qa['tasks_without_owner'])}",
        f"Users Pending Approval: {len(qa['users_pending'])}",
        f"Users Without Timezone: {len(qa['users_without_timezone'])}",
        f"Users Without Role: {len(qa['users_without_role'])}",
        f"Users Not Onboarded: {len(qa['users_not_onboarded'])}",
    ]
    return Screen("\n".join(lines), manager_setup_qa_menu())


def render_demo_seed_page() -> Screen:
    return Screen(
        "\n".join(
            [
                "Demo Seed Mode",
                "",
                "Owner-only test data for learning the UI.",
                "Demo records are marked and can be cleared without touching real records.",
                "",
                "Only create demo data when you intentionally want sample screens.",
            ]
        ),
        demo_seed_menu(),
    )


def render_models_home() -> Screen:
    return Screen(
        text="Models / Brands\n\nEverything in Fortuna OS starts with a model or brand.",
        reply_markup=models_menu(),
    )


def render_accounts_home() -> Screen:
    return Screen(
        text="Accounts\n\nCreate a model first, then attach Instagram, X, OnlyFans, Email, or Other accounts.",
        reply_markup=accounts_menu(),
    )


def render_proxies_home() -> Screen:
    return Screen(
        text="\n".join(
            [
                "Proxy Vault",
                "",
                "Manage encrypted proxy records, account assignments, and health checks.",
                "Use the Olympix wizard for Mobile SOCKS5 proxies. Passwords are encrypted and never shown back in Telegram.",
            ]
        ),
        reply_markup=proxies_menu(),
    )


def render_tasks_home() -> Screen:
    return Screen(text="Tasks\nOperational work queue.", reply_markup=tasks_menu())


def render_incidents_home() -> Screen:
    return Screen(text="Incidents\nEscalation and resolution center.", reply_markup=incidents_menu())


def render_reports_home() -> Screen:
    return Screen(text="Reports\nBriefings, dashboards, and accountability.", reply_markup=reports_menu())


def render_intelligence_home(session: Session | None = None) -> Screen:
    lines = ["Intelligence Command Center", ""]
    if session is None:
        lines.append("Things to watch, recurring problems, trends, and workload intelligence.")
    else:
        status = command_center_intelligence_status(session)
        learning = learning_center_metrics(session)
        lines.extend(
            [
                f"Status: {status['status']}",
                f"Things To Watch: {status['open_signals']}",
                f"Critical Watch Items: {status['critical_signals']}",
                f"Recurring Problems: {status['active_patterns']}",
                f"Negative Trends: {status['negative_trends']}",
                f"Overloaded Users: {status['overloaded_users']}",
                f"Management Insights: {status['open_executive_insights']}",
                f"Learning Events: {learning['total_learning_events']}",
                f"Active Playbooks: {learning['active_playbooks']}",
                "",
                "Run analysis or drill into watch items, recurring problems, trends, and workload.",
            ]
        )
    return Screen(text="\n".join(lines), reply_markup=intelligence_menu())


def render_opportunities_home(session: Session | None = None) -> Screen:
    opportunities = list_opportunities(session, limit=5) if session is not None else []
    lines = [
        "Opportunities",
        "",
        "Manual, human-approved opportunity command center.",
        "Use it to decide what deserves attention next. No posting is automated.",
        "",
    ]
    buttons: list[tuple[str, str]] = []
    if not opportunities:
        lines.append("No opportunities yet. Add a creator, watch one of your own posts, or create a manual opportunity.")
    for opportunity in opportunities:
        lines.append(f"{opportunity.id}. {opportunity.title}")
        lines.append(f"   Platform: {opportunity.platform} | Score: {opportunity.score} | Status: {opportunity.status}")
        buttons.append((f"{opportunity.id}. {opportunity.title[:36]}", f"nav:opportunity:{opportunity.id}"))
    return Screen(text="\n".join(lines), reply_markup=opportunities_menu(buttons))


def render_creator_intake_page(session: Session, page: str) -> Screen:
    parts = page.split(":")
    if page == "opportunities:creators:add":
        choices = [(platform.upper() if platform == "x" else platform.title(), f"nav:opportunities:creators:add:platform:{platform}") for platform in CREATOR_WATCH_PLATFORMS]
        return Screen(
            text="Add Creator\n\nStep 1 of 9\nChoose platform.",
            reply_markup=choice_menu(choices, back_to="opportunities:creators"),
        )
    if len(parts) >= 5 and parts[3] == "platform":
        return Screen(
            text="Add Creator\n\nStep 2 of 9\nSend the creator username in chat. Do not include passwords or private data.",
            reply_markup=page_menu(back_to="opportunities:creators:add"),
        )
    if len(parts) >= 5 and parts[3] == "priority":
        models = list_models_for_opportunity_assignment(session)
        choices = [("Skip Model", "nav:opportunities:creators:add:model:skip")]
        choices.extend((model.display_name[:40], f"nav:opportunities:creators:add:model:{model.id}") for model in models)
        return Screen("Add Creator\n\nStep 6 of 9\nAssign a model/brand or skip.", choice_menu(choices, back_to="opportunities:creators:add"))
    if len(parts) >= 5 and parts[3] == "model":
        users = active_users_for_opportunity_assignment(session)
        choices = [("Skip Chatter", "nav:opportunities:creators:add:chatter:skip")]
        choices.extend((_identity(user)[:40], f"nav:opportunities:creators:add:chatter:{user.id}") for user in users)
        return Screen("Add Creator\n\nStep 7 of 9\nAssign a chatter/team member or skip.", choice_menu(choices, back_to="opportunities:creators:add"))
    if len(parts) >= 5 and parts[3] == "chatter":
        return Screen(
            text="Add Creator\n\nStep 8 of 9\nSend optional notes, or type skip to create the creator watch item.",
            reply_markup=page_menu(back_to="opportunities:creators:add"),
        )
    return Screen("Add Creator\n\nContinue the guided creator intake.", page_menu(back_to="opportunities:creators"))


def render_opportunity_intake_page(session: Session, page: str) -> Screen:
    parts = page.split(":")
    if page == "opportunities:add":
        choices = [
            ("Creator Watch", "nav:opportunities:add:source:creator_watch"),
            ("Own Post", "nav:opportunities:add:source:own_post"),
            ("Manual", "nav:opportunities:add:source:manual"),
        ]
        return Screen("Add Opportunity\n\nStep 1 of 10\nChoose the source.", choice_menu(choices, back_to="opportunities:command"))
    if page == "opportunities:add:source:creator_watch":
        creators = list_creator_watches(session, active_only=True, limit=20)
        choices = [(f"{creator.creator_name[:32]}", f"nav:opportunities:add:source:creator_watch:{creator.id}") for creator in creators]
        if not choices:
            choices = [("No creators yet", "nav:opportunities:creators")]
        return Screen("Add Opportunity\n\nChoose the creator source.", choice_menu(choices, back_to="opportunities:add"))
    if page == "opportunities:add:source:own_post":
        posts = list_post_watches(session, limit=20)
        choices = [(f"{post.post_reference[:32]}", f"nav:opportunities:add:source:own_post:{post.id}") for post in posts]
        if not choices:
            choices = [("No watched posts yet", "nav:opportunities:posts")]
        return Screen("Add Opportunity\n\nChoose the own post source.", choice_menu(choices, back_to="opportunities:add"))
    if "platform" in parts:
        return Screen(
            text="Add Opportunity\n\nStep 3 of 10\nSend the title or short description in chat.",
            reply_markup=page_menu(back_to="opportunities:add"),
        )
    if len(parts) >= 4 and parts[2] == "source":
        choices = [(platform.upper() if platform == "x" else platform.title(), f"nav:{page}:platform:{platform}") for platform in OPPORTUNITY_PLATFORMS if platform != "reddit"]
        return Screen("Add Opportunity\n\nStep 2 of 10\nChoose platform.", choice_menu(choices, back_to="opportunities:add"))
    if len(parts) >= 4 and parts[2] == "priority":
        models = list_models_for_opportunity_assignment(session)
        choices = [("Skip Model", "nav:opportunities:add:model:skip")]
        choices.extend((model.display_name[:40], f"nav:opportunities:add:model:{model.id}") for model in models)
        return Screen("Add Opportunity\n\nStep 6 of 10\nAssign a model/brand or skip.", choice_menu(choices, back_to="opportunities:add"))
    if len(parts) >= 4 and parts[2] == "model":
        users = active_users_for_opportunity_assignment(session)
        choices = [("Skip Chatter", "nav:opportunities:add:chatter:skip")]
        choices.extend((_identity(user)[:40], f"nav:opportunities:add:chatter:{user.id}") for user in users)
        return Screen("Add Opportunity\n\nStep 8 of 10\nAssign a chatter or skip.", choice_menu(choices, back_to="opportunities:add"))
    if len(parts) >= 4 and parts[2] == "chatter":
        return Screen(
            text="Add Opportunity\n\nStep 9 of 10\nSend optional notes, or type skip to confirm and create.",
            reply_markup=page_menu(back_to="opportunities:add"),
        )
    return Screen("Add Opportunity\n\nContinue the guided intake.", page_menu(back_to="opportunities"))


def render_post_intake_page(session: Session, page: str) -> Screen:
    parts = page.split(":")
    if page == "opportunities:posts:add":
        models = list_models_for_opportunity_assignment(session)
        choices = [(model.display_name[:40], f"nav:opportunities:posts:add:model:{model.id}") for model in models]
        if not choices:
            choices = [("Create a Model First", "nav:models:create")]
        return Screen("Add Own Post\n\nStep 1 of 8\nChoose model/brand.", choice_menu(choices, back_to="opportunities:posts"))
    if "platform" in parts:
        return Screen(
            text="Add Own Post\n\nStep 4 of 8\nSend the post reference or URL in chat.",
            reply_markup=page_menu(back_to="opportunities:posts:add"),
        )
    if len(parts) >= 5 and parts[3] == "model":
        choices = [(platform.upper() if platform == "x" else platform.title(), f"nav:{page}:platform:{platform}") for platform in POST_WATCH_PLATFORMS]
        return Screen("Add Own Post\n\nStep 2 of 8\nChoose platform.", choice_menu(choices, back_to="opportunities:posts:add"))
    if len(parts) >= 5 and parts[3] == "type":
        choices = [(level.title(), f"nav:opportunities:posts:add:attention:{level}") for level in POST_WATCH_ATTENTION_LEVELS]
        return Screen("Add Own Post\n\nStep 6 of 8\nChoose attention level.", choice_menu(choices, back_to="opportunities:posts:add"))
    if len(parts) >= 5 and parts[3] == "attention":
        users = active_users_for_opportunity_assignment(session)
        choices = [("Skip Chatter", "nav:opportunities:posts:add:chatter:skip")]
        choices.extend((_identity(user)[:40], f"nav:opportunities:posts:add:chatter:{user.id}") for user in users)
        return Screen("Add Own Post\n\nStep 7 of 8\nAssign chatter/team member or skip.", choice_menu(choices, back_to="opportunities:posts:add"))
    if len(parts) >= 5 and parts[3] == "chatter":
        return Screen(
            text="Add Own Post\n\nStep 8 of 8\nSend optional notes, or type skip to confirm and create.",
            reply_markup=page_menu(back_to="opportunities:posts:add"),
        )
    return Screen("Add Own Post\n\nContinue the guided post intake.", page_menu(back_to="opportunities:posts"))


def render_opportunity_command_center_page(session: Session, user: User | None = None) -> Screen:
    summary = opportunity_queue_summary(session, user=user)
    counts = summary["counts"]
    lines = [
        "Opportunity Command Center",
        "",
        f"New: {counts['discovered']}",
        f"Reviewing: {counts['reviewing']}",
        f"Assigned: {counts['assigned']}",
        f"Completed: {counts['completed']}",
        f"Rejected: {counts['rejected']}",
        f"Archived: {counts['archived']}",
        "",
        "Top Opportunities:",
    ]
    buttons: list[tuple[str, str]] = []
    if not summary["top"]:
        lines.append("- None yet")
    for opportunity in summary["top"][:5]:
        lines.append(f"- {opportunity.title} | {opportunity.score}/100 | {opportunity.status}")
        buttons.append((f"{opportunity.id}. {opportunity.title[:32]}", f"nav:opportunity:{opportunity.id}"))
    lines.append("")
    lines.append("High Priority:")
    if not summary["high_priority"]:
        lines.append("- None")
    for opportunity in summary["high_priority"][:5]:
        lines.append(f"- {_status_marker('warning')} {opportunity.title} | {opportunity.score}/100")
    lines.append("")
    lines.append("Recent Results:")
    if not summary["recent_results"]:
        lines.append("- No results recorded yet")
    for result in summary["recent_results"][:5]:
        opportunity = session.get(Opportunity, result.opportunity_id)
        lines.append(f"- {opportunity.title if opportunity else 'Opportunity'}: {result.status}")
    return Screen(text="\n".join(lines), reply_markup=opportunity_command_menu())


def render_creator_watchlist_page(session: Session) -> Screen:
    creators = list_creator_watches(session, active_only=True, limit=20)
    lines = ["Creator Watchlist", "", "Creators worth watching. Human review only.", ""]
    buttons: list[tuple[str, str]] = []
    if not creators:
        lines.append("No creators watched yet.")
    for creator in creators:
        chatter = creator.assigned_chatter
        model = creator.assigned_model
        lines.append(f"{creator.id}. {creator.creator_name} (@{creator.creator_username})")
        lines.append(f"   Platform: {creator.platform} | Priority: {creator.priority} | Niche: {creator.niche or 'not set'}")
        lines.append(f"   Model: {model.display_name if model else 'Unassigned'} | Chatter: {_identity(chatter)}")
        buttons.append((f"{creator.id}. {creator.creator_name[:34]}", f"nav:creator:{creator.id}"))
    return Screen(text="\n".join(lines), reply_markup=creator_watch_menu(buttons))


def render_creator_watch_detail_page(session: Session, creator_id: int) -> Screen:
    creator = get_creator_watch(session, creator_id)
    if creator is None:
        return Screen(text="Creator watch item not found.", reply_markup=page_menu(back_to="opportunities:creators"))
    lines = [
        "Creator Watch",
        "",
        f"Name: {creator.creator_name}",
        f"Display Name: {creator.display_name or creator.creator_name}",
        f"Username: @{creator.creator_username}",
        f"Platform: {creator.platform}",
        f"Priority: {creator.priority}",
        f"Niche: {creator.niche or 'Not set'}",
        f"Profile: {creator.profile_url or 'Not set'}",
        f"Assigned Model: {creator.assigned_model.display_name if creator.assigned_model else 'Unassigned'}",
        f"Assigned Chatter: {_identity(creator.assigned_chatter)}",
        f"Team ID: {creator.assigned_team_id or 'Unassigned'}",
        f"Status: {creator.status}",
        f"Active: {creator.is_active}",
        f"Created: {creator.created_at.isoformat() if creator.created_at else 'Not set'}",
        f"Updated: {creator.updated_at.isoformat() if creator.updated_at else 'Not set'}",
        f"Notes: {creator.notes or 'None'}",
        "",
        "Use this to focus human attention. No platform actions are automated.",
    ]
    return Screen(text="\n".join(lines), reply_markup=creator_watch_detail_menu(creator.id))


def render_post_watch_page(session: Session, *, status: str | None = None) -> Screen:
    posts = list_post_watches(session, status=status, limit=20)
    title = "Own Post Watch" if status is None else "Own Post Watch - Attention Needed"
    lines = [title, "", "Track important posts that may need human attention.", ""]
    buttons: list[tuple[str, str]] = []
    if not posts:
        lines.append("No watched posts yet.")
    for post in posts:
        model = post.model_brand
        lines.append(f"{post.id}. {post.post_reference}")
        lines.append(f"   Platform: {post.platform} | Type: {post.post_type} | Status: {post.status}")
        lines.append(f"   Model: {model.display_name if model else 'Unknown'} | Notes: {post.notes or 'None'}")
        buttons.append((f"{post.id}. {post.post_reference[:34]}", f"nav:post:{post.id}"))
    return Screen(text="\n".join(lines), reply_markup=post_watch_menu(buttons))


def render_post_watch_detail_page(session: Session, post_id: int) -> Screen:
    post = get_post_watch(session, post_id)
    if post is None:
        return Screen(text="Post watch item not found.", reply_markup=page_menu(back_to="opportunities:posts"))
    lines = [
        "Own Post Watch",
        "",
        f"Post: {post.post_reference}",
        f"Platform: {post.platform}",
        f"Type: {post.post_type}",
        f"Status: {post.status}",
        f"Attention: {post.attention_level}",
        f"Model/Brand: {post.model_brand.display_name if post.model_brand else 'Unknown'}",
        f"Account ID: {post.account_id or 'None'}",
        f"Assigned Chatter: {_identity(post.assigned_chatter)}",
        f"Team ID: {post.assigned_team_id or 'Unassigned'}",
        f"Notes: {post.notes or 'None'}",
    ]
    return Screen(text="\n".join(lines), reply_markup=post_watch_detail_menu(post.id))


def render_automations_home(session: Session | None = None, user: User | None = None) -> Screen:
    lines = ["Automation Dashboard", "", "Lifecycle: Draft -> Simulate -> Approve -> Activate -> Run"]
    if session is not None:
        seed_builtin_automation_templates(session, actor=user)
        metrics = automation_metrics(session)
        lines.extend(
            [
                "",
                f"Active Automations: {metrics['active_automations']}",
                f"Failed Automations: {metrics['failed_automations']}",
                f"Pending Approvals: {metrics['pending_approvals']}",
                f"Last Automation Run: {metrics['last_automation_run']} ({metrics['last_run_status']})",
                f"Automation Success Rate: {metrics['automation_success_rate']}%",
                "",
                "Simulation mode is the default safety layer.",
            ]
        )
    else:
        lines.extend(["", "Simulation mode is active.", "Preview, simulate, approve, then execute."])
    return Screen(text="\n".join(lines), reply_markup=automations_menu())


def _automation_status_line(rule: AutomationRule) -> str:
    approval = "Owner approval" if rule.requires_owner_approval else "Approval"
    return f"{rule.status} | Risk: {rule.risk_level} | {approval if rule_requires_owner_label(rule) else 'Standard review'}"


def rule_requires_owner_label(rule: AutomationRule) -> bool:
    return rule.requires_owner_approval or rule.risk_level in {"high", "critical"}


def render_automation_rules_page(session: Session, user: User | None = None) -> Screen:
    seed_builtin_automation_templates(session, actor=user)
    rules = list_automation_rules(session)
    lines = ["Automation Rules", ""]
    buttons: list[tuple[str, str]] = []
    if not rules:
        lines.append("No automation rules yet.")
    for rule in rules[:20]:
        lines.append(f"{rule.id}. {rule.name}")
        lines.append(f"   {_automation_status_line(rule)}")
        buttons.append((f"{rule.id}. {rule.name[:36]}", f"nav:automation:{rule.id}"))
    return Screen(text="\n".join(lines), reply_markup=automation_rules_menu(buttons))


def render_automation_templates_page(session: Session, user: User | None = None) -> Screen:
    rules = seed_builtin_automation_templates(session, actor=user)
    by_type = {rule.automation_type: rule for rule in rules}
    lines = ["Built-In Automation Templates", ""]
    buttons: list[tuple[str, str]] = []
    for template in BUILTIN_AUTOMATION_TEMPLATES:
        rule = by_type.get(template.automation_type)
        status = rule.status if rule else "not seeded"
        lines.append(f"- {template.name}")
        lines.append(f"  Risk: {template.risk_level} | Status: {status}")
        lines.append(f"  What starts it: {template.trigger_type}")
        if rule:
            buttons.append((template.name[:40], f"nav:automation:{rule.id}"))
    return Screen(text="\n".join(lines), reply_markup=automation_templates_menu(buttons))


def _json_lines(title: str, value: object, *, limit: int = 8) -> list[str]:
    lines = [title]
    if isinstance(value, dict):
        items = list(value.items())[:limit]
        if not items:
            return lines + ["- None"]
        return lines + [f"- {key}: {item}" for key, item in items]
    if isinstance(value, list):
        if not value:
            return lines + ["- None"]
        rendered: list[str] = []
        for item in value[:limit]:
            if isinstance(item, dict):
                rendered.append("- " + ", ".join(f"{key}: {val}" for key, val in item.items()))
            else:
                rendered.append(f"- {item}")
        return lines + rendered
    return lines + [f"- {value or 'None'}"]


def render_automation_rule_detail_page(session: Session, rule_id: int) -> Screen:
    rule = get_automation_rule(session, rule_id)
    if rule is None:
        return Screen(text="Automation rule not found.", reply_markup=page_menu(back_to="automations:rules"))
    latest_approval = latest_rule_approval(session, rule)
    rollback = rollback_plan_for_rule(rule)
    lines = [
        "Automation Rule",
        "",
        f"Name: {rule.name}",
        f"Status: {rule.status}",
        f"Category: {rule.category}",
        f"Risk: {_status_marker(rule.risk_level)} {rule.risk_level}",
        f"Owner Approval Required: {'yes' if rule.requires_owner_approval else 'no'}",
        f"Latest Approval: {latest_approval.status if latest_approval else 'none'}",
        f"Last Simulated: {rule.last_simulated_at.isoformat() if rule.last_simulated_at else 'never'}",
        f"Last Run: {rule.last_run_at.isoformat() if rule.last_run_at else 'never'}",
        "",
        "What starts it:",
        f"- {rule.trigger_type}",
    ]
    lines.extend(_json_lines("Checks before running:", rule.conditions_json))
    lines.extend(_json_lines("What it will do:", rule.actions_json))
    lines.extend(_json_lines("How to undo it:", rollback.get("steps", [])))
    if rollback.get("limitations"):
        lines.extend(_json_lines("Rollback limitations:", rollback["limitations"], limit=4))
    return Screen(text="\n".join(lines), reply_markup=automation_rule_detail_menu(rule.id, rule.status))


def render_automation_rule_simulations_page(session: Session, rule_id: int) -> Screen:
    rule = get_automation_rule(session, rule_id)
    if rule is None:
        return Screen(text="Automation rule not found.", reply_markup=page_menu(back_to="automations:rules"))
    runs = [
        run
        for run in list_simulation_runs(session, limit=50)
        if run.automation_rule_id == rule.id
    ]
    lines = ["Simulation Results", "", f"Rule: {rule.name}", ""]
    buttons: list[tuple[str, str]] = []
    if not runs:
        lines.append("No simulations for this rule yet.")
    for run in runs[:10]:
        lines.append(f"{run.id}. {run.status} | Risk: {run.risk_level}")
        lines.append(f"   Would trigger: {run.would_trigger_count} | Fail: {run.would_fail_count}")
        buttons.append((f"{run.id}. {run.status}", f"nav:simulation:{run.id}"))
    return Screen(text="\n".join(lines), reply_markup=simulation_runs_menu(buttons))


def render_automation_rollback_page(session: Session, rule_id: int) -> Screen:
    rule = get_automation_rule(session, rule_id)
    if rule is None:
        return Screen(text="Automation rule not found.", reply_markup=page_menu(back_to="automations:rules"))
    plan = rollback_plan_for_rule(rule)
    lines = ["Rollback Plan", "", f"Rule: {rule.name}", f"Rollback Available: {'yes' if plan.get('available') else 'no'}", ""]
    lines.extend(_json_lines("Rollback steps:", plan.get("steps", [])))
    lines.extend(_json_lines("Limitations:", plan.get("limitations", [])))
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to=f"automation:{rule.id}"))


def render_automation_approvals_page(session: Session) -> Screen:
    approvals = pending_approvals(session)
    lines = ["Pending Automation Approvals", ""]
    buttons: list[tuple[str, str]] = []
    if not approvals:
        lines.append("No pending approvals.")
    for approval in approvals:
        rule_name = approval.rule.name if approval.rule else f"Rule {approval.automation_rule_id}"
        lines.append(f"{approval.id}. {rule_name}")
        lines.append(f"   Status: {approval.status} | Expires: {approval.expires_at.isoformat() if approval.expires_at else 'not set'}")
        buttons.append((f"{approval.id}. {rule_name[:34]}", f"nav:approval:{approval.id}"))
    return Screen(text="\n".join(lines), reply_markup=automation_approvals_menu(buttons))


def render_automation_approval_detail_page(session: Session, approval_id: int) -> Screen:
    approval = session.get(AutomationApproval, approval_id)
    if approval is None:
        return Screen(text="Approval not found.", reply_markup=page_menu(back_to="automations:approvals"))
    rule = approval.rule
    lines = [
        "Automation Approval",
        "",
        f"Rule: {rule.name if rule else approval.automation_rule_id}",
        f"Status: {approval.status}",
        f"Risk: {rule.risk_level if rule else 'unknown'}",
        f"Requested By: {approval.requested_by_user_id}",
        f"Approved By: {approval.approved_by_user_id or 'pending'}",
        f"Expires: {approval.expires_at.isoformat() if approval.expires_at else 'not set'}",
        f"Reason: {approval.approval_reason or 'None'}",
    ]
    return Screen(text="\n".join(lines), reply_markup=automation_approval_detail_menu(approval.id, approval.automation_rule_id))


def render_automation_runs_page(session: Session, *, rule_id: int | None = None) -> Screen:
    runs = latest_automation_runs(session, limit=30)
    if rule_id is not None:
        runs = [run for run in runs if run.automation_rule_id == rule_id]
    lines = ["Automation Run History", ""]
    buttons: list[tuple[str, str]] = []
    if not runs:
        lines.append("No automation runs yet.")
    for run in runs[:15]:
        rule_name = run.rule.name if run.rule else f"Rule {run.automation_rule_id}"
        lines.append(f"{run.id}. {rule_name}")
        lines.append(f"   Status: {run.status} | Rollback: {run.rollback_status}")
        lines.append(f"   Started: {run.started_at.isoformat() if run.started_at else 'not started'}")
        buttons.append((f"{run.id}. {rule_name[:34]}", f"nav:automation_run:{run.id}"))
    return Screen(text="\n".join(lines), reply_markup=automation_runs_menu(buttons))


def render_automation_run_detail_page(session: Session, run_id: int) -> Screen:
    run = get_automation_run(session, run_id)
    if run is None:
        return Screen(text="Automation run not found.", reply_markup=page_menu(back_to="automations:runs"))
    lines = [
        "Automation Run",
        "",
        f"Rule: {run.rule.name if run.rule else run.automation_rule_id}",
        f"Status: {run.status}",
        f"Rollback Available: {'yes' if run.rollback_available else 'no'}",
        f"Rollback Status: {run.rollback_status}",
        f"Started: {run.started_at.isoformat() if run.started_at else 'not started'}",
        f"Finished: {run.finished_at.isoformat() if run.finished_at else 'not finished'}",
        f"Error: {run.error_message or 'None'}",
        "",
        "Steps:",
    ]
    buttons: list[tuple[str, str]] = []
    if not run.steps:
        lines.append("- No step records yet.")
    for step in sorted(run.steps, key=lambda item: item.step_order):
        lines.append(f"- {step.step_order}. {step.action_type}: {step.status}")
        buttons.append((f"{step.step_order}. {step.action_type[:32]}", f"nav:automation_step:{step.id}"))
    return Screen(text="\n".join(lines), reply_markup=automation_run_detail_menu(run.id, buttons))


def render_automation_step_detail_page(session: Session, step_id: int) -> Screen:
    step = get_automation_step(session, step_id)
    if step is None:
        return Screen(text="Automation step not found.", reply_markup=page_menu(back_to="automations:runs"))
    lines = [
        "Automation Step",
        "",
        f"Action: {step.action_type}",
        f"Status: {step.status}",
        f"Entity: {step.entity_type or 'n/a'}:{step.entity_id or 'n/a'}",
        f"Started: {step.started_at.isoformat() if step.started_at else 'not started'}",
        f"Finished: {step.finished_at.isoformat() if step.finished_at else 'not finished'}",
        f"Error: {step.error_message or 'None'}",
    ]
    lines.extend(_json_lines("Input:", step.input_json, limit=6))
    lines.extend(_json_lines("Output:", step.output_json, limit=6))
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to=f"automation_run:{step.automation_run_id}"))


def render_automation_health_page(session: Session) -> Screen:
    metrics = automation_metrics(session)
    lines = [
        "Automation Health",
        "",
        f"Total Rules: {metrics['total_rules']}",
        f"Active: {metrics['active_automations']}",
        f"Failed: {metrics['failed_automations']}",
        f"Pending Approvals: {metrics['pending_approvals']}",
        f"Total Simulations: {metrics['total_simulations']}",
        f"Total Runs: {metrics['total_runs']}",
        f"Success Count: {metrics['success_count']}",
        f"Failure Count: {metrics['failure_count']}",
        f"Skipped Count: {metrics['skipped_count']}",
        f"Rollback Count: {metrics['rollback_count']}",
        f"Last Run: {metrics['last_automation_run']} ({metrics['last_run_status']})",
        f"Average Duration: {metrics['average_duration_seconds']}s",
        f"Affected Entities: {metrics['affected_entities_count']}",
        f"Success Rate: {metrics['automation_success_rate']}%",
    ]
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="automations"))


def _identity(user: User | None) -> str:
    if user is None:
        return "Unassigned"
    return user.display_name or user.username or f"User {user.id}"


def _status_marker(status: str) -> str:
    return {
        "healthy": "\U0001f7e2",
        "active": "\U0001f7e2",
        "open": "\U0001f7e1",
        "in_progress": "\U0001f7e1",
        "investigating": "\U0001f7e1",
        "warning": "\U0001f7e1",
        "blocked": "\U0001f534",
        "critical": "\U0001f534",
        "disabled": "\u26ab",
        "archived": "\u26ab",
        "complete": "\U0001f7e2",
        "resolved": "\U0001f7e2",
    }.get(status, "\u26aa")


def _account_button(account: Account) -> tuple[str, str]:
    label = f"{account.id}. {platform_label(account.platform)} @{account.username}"
    return label, f"nav:account:{account.id}"


def render_account_list_page(
    session: Session,
    *,
    accounts: list[Account] | None = None,
    title: str = "Accounts",
    back_to: str = "accounts",
) -> Screen:
    current_accounts = accounts if accounts is not None else list_accounts(session)
    lines = [title, ""]
    buttons: list[tuple[str, str]] = []
    if not current_accounts:
        if back_to.startswith("model:") or title.startswith("Accounts for "):
            lines.append("No accounts yet. Add an account to this model from Setup Fortuna or Accounts -> Add Account.")
        else:
            lines.append("No accounts yet. Create a model first, then attach IG/X/OF/Email accounts.")
    for account in current_accounts[:15]:
        health = account_health(account)
        model_name = account.model_brand.display_name if account.model_brand else "Unassigned"
        lines.append(f"{account.id}. {platform_label(account.platform)} @{account.username}")
        lines.append(f"   Model: {model_name} | Status: {account.status}")
        lines.append(f"   Auth: {account.auth_status} | Health: {health.label} {health.score}/100")
        buttons.append(_account_button(account))
    return Screen(text="\n".join(lines), reply_markup=account_list_menu(buttons, back_to=back_to))


def render_account_model_choice_page(session: Session) -> Screen:
    models = list_model_brands(session)
    lines = ["Choose Model/Brand", ""]
    buttons: list[tuple[str, str]] = []
    if not models:
        lines.append("No models yet. Start by creating your first model/brand.")
        buttons.append(("Create First Model", "nav:setup:wizard:model"))
    for model_brand in models:
        buttons.append((model_brand.display_name, f"nav:accounts:add:model:{model_brand.id}"))
    return Screen(text="\n".join(lines), reply_markup=account_model_choice_menu(buttons))


def render_account_platform_choice_page(session: Session, model_id: int) -> Screen:
    model_brand = session.get(ModelBrand, model_id)
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="accounts:add"))
    return Screen(
        text=f"Choose Platform\n\nModel: {model_brand.display_name}",
        reply_markup=account_platform_menu(model_brand.id),
    )


def render_account_input_page(session: Session, model_id: int, platform: str) -> Screen:
    model_brand = session.get(ModelBrand, model_id)
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="accounts:add"))
    return Screen(
        text="\n".join(
            [
                "Add Account",
                "",
                f"Model: {model_brand.display_name}",
                f"Platform: {platform_label(platform)}",
                "",
                "Send username or username | display name.",
            ]
        ),
        reply_markup=page_menu(back_to=f"accounts:add:model:{model_id}"),
    )


def render_accounts_by_model_page(session: Session) -> Screen:
    models = list_model_brands(session)
    lines = ["Accounts by Model", ""]
    buttons: list[tuple[str, str]] = []
    if not models:
        lines.append("No models yet. Start by creating your first model/brand.")
        buttons.append(("Create First Model", "nav:setup:wizard:model"))
    for model_brand in models:
        count = len(accounts_for_model(session, model_brand.id))
        lines.append(f"{model_brand.display_name}: {count}")
        buttons.append((f"{model_brand.display_name} ({count})", f"nav:accounts:model:{model_brand.id}"))
    return Screen(text="\n".join(lines), reply_markup=account_list_menu(buttons, back_to="accounts"))


def render_accounts_by_platform_page() -> Screen:
    return Screen(text="Accounts by Platform", reply_markup=platform_filter_menu())


def render_account_detail_page(session: Session, account_id: int) -> Screen:
    account = session.scalar(
        select(Account)
        .where(Account.id == account_id)
        .options(
            selectinload(Account.model_brand),
            selectinload(Account.auth_sessions),
            selectinload(Account.assigned_proxy),
        )
    )
    if account is None:
        return Screen(text="Account not found.", reply_markup=page_menu(back_to="accounts:list"))
    model_name = account.model_brand.display_name if account.model_brand else "Unassigned"
    health = account_health(account)
    last_checked = account.last_checked_at.isoformat() if account.last_checked_at else "Not checked yet"
    proxy_assignment = (
        f"{account.assigned_proxy.provider} {account.assigned_proxy.host}:{account.assigned_proxy.port}"
        if account.assigned_proxy
        else "Not assigned"
    )
    lines = [
        "Account Detail",
        "",
        f"Platform: {platform_label(account.platform)}",
        f"Username: @{account.username}",
        f"Display Name: {account.display_name}",
        f"Model/Brand: {model_name}",
        f"Status: {account.status}",
        f"Auth Status: {account.auth_status}",
        f"Health: {health.label} {health.score}/100",
        f"Proxy Assignment: {proxy_assignment}",
        f"Last Checked: {last_checked}",
        f"Notes: {account.notes or 'None'}",
    ]
    return Screen(text="\n".join(lines), reply_markup=account_detail_menu(account.id))


def render_account_proxy_assignment_page(session: Session, account_id: int) -> Screen:
    account = session.get(Account, account_id)
    if account is None:
        return Screen(text="Account not found.", reply_markup=page_menu(back_to="accounts:list"))
    proxies = list_proxies(session, include_disabled=False)
    buttons = [
        (
            f"{proxy.id}. {proxy.provider} {proxy.host}:{proxy.port}",
            f"nav:account:{account.id}:proxy:assign:{proxy.id}",
        )
        for proxy in proxies
    ]
    lines = ["Assign Proxy", "", f"Account: @{account.username}", ""]
    if not buttons:
        lines.append("No active proxies available.")
    return Screen(text="\n".join(lines), reply_markup=account_proxy_choice_menu(account.id, buttons))


def render_account_auth_prompt_page(session: Session, account_id: int) -> Screen:
    account = session.get(Account, account_id)
    if account is None:
        return Screen(text="Account not found.", reply_markup=page_menu(back_to="accounts:list"))
    auth_session = latest_waiting_auth_session(session, account.id)
    if auth_session is None:
        return Screen(
            text="Enter 2FA Code\n\nNo waiting auth session. Start Login/Auth Session first.",
            reply_markup=page_menu(back_to=f"account:{account.id}"),
        )
    return Screen(
        text="\n".join(
            [
                "Enter 2FA Code",
                "",
                f"Account: {platform_label(account.platform)} @{account.username}",
                "Send the verification code in the next message.",
                "The bot will store only a hash and will try to delete your code message.",
            ]
        ),
        reply_markup=page_menu(back_to=f"account:{account.id}"),
    )


def render_account_audit_page(session: Session, account_id: int) -> Screen:
    account = session.get(Account, account_id)
    if account is None:
        return Screen(text="Account not found.", reply_markup=page_menu(back_to="accounts:list"))
    logs = account_audit_logs(session, account)
    lines = ["Account Audit History", "", f"Account: {platform_label(account.platform)} @{account.username}", ""]
    if not logs:
        lines.append("No account audit events yet.")
    for log in logs:
        timestamp = log.created_at.isoformat() if log.created_at else "pending timestamp"
        lines.append(f"{timestamp}")
        lines.append(f"Action: {log.action} | Status: {log.status}")
        lines.append("")
    return Screen(text="\n".join(lines).strip(), reply_markup=page_menu(back_to=f"account:{account.id}"))


def _proxy_button(proxy: Proxy) -> tuple[str, str]:
    return f"{proxy.id}. {proxy.provider} {proxy.host}:{proxy.port}", f"nav:proxy:{proxy.id}"


def render_proxy_list_page(session: Session) -> Screen:
    proxies = list_proxies(session)
    lines = ["Proxy Vault", ""]
    buttons: list[tuple[str, str]] = []
    if not proxies:
        lines.append("No proxies yet. Add an encrypted proxy with the Olympix wizard or create a placeholder for testing.")
    for proxy in proxies[:15]:
        health = calculate_proxy_health(proxy)
        lines.append(f"{proxy.id}. {proxy.provider} {proxy.host}:{proxy.port}")
        lines.append(f"   Status: {proxy.status} | Health: {health.label} {health.score}/100")
        lines.append(f"   Target: {proxy.target_state or proxy.target_country or 'Not set'}")
        buttons.append(_proxy_button(proxy))
    return Screen(text="\n".join(lines), reply_markup=proxy_list_menu(buttons))


def render_olympix_proxy_wizard_page() -> Screen:
    lines = [
        "Olympix Mobile SOCKS5 Wizard",
        "",
        "This creates an encrypted proxy record. The password is never shown back in Telegram.",
        "",
        "Fixed provider details:",
        "Host: host.olympix.io",
        "Port: 1080",
        "",
        "Send the setup values in this format:",
        "base username | password | target country | target state | target city",
        "",
        "Example:",
        "customer-user | password | United States | Florida | Miami",
        "",
        "Target city is optional. Do not paste this into any unrelated chat.",
    ]
    return Screen("\n".join(lines), page_menu(back_to="proxies"))


def _mask_proxy_value(value: str | None) -> str:
    if not value:
        return "Not set"
    if len(value) <= 6:
        return "hidden"
    return f"{value[:3]}...{value[-3:]}"


def render_proxy_entry_check_page(session: Session) -> Screen:
    status = proxy_entry_status(session)
    lines = [
        "Proxy Setup Check",
        "",
        f"Saved Proxies: {status.total_proxies}",
        f"Encrypted Ready Proxies: {status.real_proxies}",
        f"Accounts Missing Proxy: {status.accounts_missing_proxy}",
        "",
        status.guidance,
        "",
        "Secrets stay hidden. Passwords are stored encrypted and are never displayed back in Telegram.",
    ]
    return Screen("\n".join(lines), proxy_entry_check_menu(status.needs_setup))


def render_proxy_detail_page(session: Session, proxy_id: int) -> Screen:
    proxy = session.scalar(
        select(Proxy)
        .where(Proxy.id == proxy_id)
        .options(selectinload(Proxy.accounts).selectinload(Account.model_brand))
    )
    if proxy is None:
        return Screen(text="Proxy not found.", reply_markup=page_menu(back_to="proxies:list"))
    health = calculate_proxy_health(proxy)
    assigned_accounts = accounts_for_proxy(session, proxy)
    affected_models = affected_models_for_proxy(session, proxy)
    target_location = ", ".join(
        item for item in [proxy.target_city, proxy.target_state, proxy.target_country] if item
    ) or "Not set"
    detected_location = ", ".join(
        item for item in [proxy.detected_city, proxy.detected_state, proxy.detected_country] if item
    ) or "Not checked yet"
    lines = [
        "Proxy Detail",
        "",
        f"Provider: {proxy.provider}",
        f"Host: {proxy.host}:{proxy.port}",
        f"Status: {proxy.status}",
        f"Health: {health.label} {health.score}/100",
        f"Current Session: {_mask_proxy_value(proxy.session_suffix)}",
        f"Previous Session: {_mask_proxy_value(proxy.previous_session_suffix)}",
        f"Rotation Count: {proxy.rotation_count}",
        f"Generated Username: {_mask_proxy_value(proxy.generated_username)}",
        "Password: encrypted and hidden",
        f"Target Location: {target_location}",
        f"Detected Location: {detected_location}",
        f"Last Health Check: {proxy.last_health_check.isoformat() if proxy.last_health_check else 'Not checked yet'}",
        f"Last Rotation: {proxy.last_rotation.isoformat() if proxy.last_rotation else 'Never'}",
        f"Last Successful Rotation: {proxy.last_successful_rotation.isoformat() if proxy.last_successful_rotation else 'Never'}",
        f"Accounts Using Proxy: {len(assigned_accounts)}",
        f"Accounts Missing Proxy: {len(accounts_missing_proxy(session))}",
        f"Models Affected: {len(affected_models)}",
    ]
    if health.reasons:
        lines.extend(["", "Health Reasons:"])
        lines.extend(f"- {reason}" for reason in health.reasons)
    return Screen(text="\n".join(lines), reply_markup=proxy_detail_menu(proxy.id))


def render_proxy_assigned_accounts_page(session: Session, proxy_id: int) -> Screen:
    proxy = session.get(Proxy, proxy_id)
    if proxy is None:
        return Screen(text="Proxy not found.", reply_markup=page_menu(back_to="proxies:list"))
    accounts = accounts_for_proxy(session, proxy)
    return render_account_list_page(
        session,
        accounts=accounts,
        title=f"Accounts Using Proxy {proxy.id}",
        back_to=f"proxy:{proxy.id}",
    )


def render_proxy_assign_account_page(session: Session, proxy_id: int) -> Screen:
    proxy = session.get(Proxy, proxy_id)
    if proxy is None:
        return Screen(text="Proxy not found.", reply_markup=page_menu(back_to="proxies:list"))
    buttons = [
        (
            f"{account.id}. @{account.username}",
            f"nav:proxy:{proxy.id}:assign:{account.id}",
        )
        for account in accounts_missing_proxy(session)
    ]
    lines = ["Assign Account to Proxy", "", f"Proxy: {proxy.provider} {proxy.host}:{proxy.port}", ""]
    if not buttons:
        lines.append("No accounts are missing proxies.")
    return Screen(text="\n".join(lines), reply_markup=proxy_account_choice_menu(proxy.id, buttons, "assign"))


def render_proxy_remove_account_page(session: Session, proxy_id: int) -> Screen:
    proxy = session.get(Proxy, proxy_id)
    if proxy is None:
        return Screen(text="Proxy not found.", reply_markup=page_menu(back_to="proxies:list"))
    buttons = [
        (
            f"{account.id}. @{account.username}",
            f"nav:proxy:{proxy.id}:remove:{account.id}",
        )
        for account in accounts_for_proxy(session, proxy)
    ]
    lines = ["Remove Account from Proxy", "", f"Proxy: {proxy.provider} {proxy.host}:{proxy.port}", ""]
    if not buttons:
        lines.append("No accounts are assigned to this proxy.")
    return Screen(text="\n".join(lines), reply_markup=proxy_account_choice_menu(proxy.id, buttons, "remove"))


def render_accounts_missing_proxy_page(session: Session) -> Screen:
    return render_account_list_page(
        session,
        accounts=accounts_missing_proxy(session),
        title="Accounts Missing Proxy",
        back_to="proxies",
    )


def render_proxy_simulation_page(session: Session) -> Screen:
    summary = simulation_mode_summary(session)
    lines = [
        "Simulation Mode",
        "",
        "Yesterday:",
        f"Would Rotate: {summary.would_rotate} Proxies",
        f"Would Repair: {summary.would_repair} Proxies",
        f"Would Fail: {summary.would_fail} Proxies",
        "",
        "No changes applied.",
        "Owner approval is required before automatic repair activation.",
    ]
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="proxies"))


def render_infrastructure_dashboard_page(session: Session) -> Screen:
    stats = infrastructure_stats(session)
    lines = [
        "Infrastructure Dashboard",
        "",
        f"Total Proxies: {stats.total_proxies}",
        f"Healthy: {stats.healthy_proxies}",
        f"Warning: {stats.warning_proxies}",
        f"Critical: {stats.critical_proxies}",
        f"Disabled: {stats.disabled_proxies}",
        f"Accounts Assigned: {stats.accounts_assigned_proxy}",
        f"Accounts Missing Proxy: {stats.accounts_missing_proxy}",
        f"Average Health Score: {stats.average_health_score}",
        "",
        "Recent Rotations:",
    ]
    lines.extend(f"- {item}" for item in stats.recent_rotations[:5])
    if not stats.recent_rotations:
        lines.append("- No rotations yet")
    lines.extend(["", "Recent Failures:"])
    lines.extend(f"- {item}" for item in stats.recent_failures[:5])
    if not stats.recent_failures:
        lines.append("- No failures yet")
    lines.extend(["", "Recent Incidents:"])
    lines.extend(f"- {item}" for item in stats.recent_incidents[:5])
    if not stats.recent_incidents:
        lines.append("- No proxy incidents yet")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="proxies"))


def render_proxy_audit_page(session: Session, proxy_id: int) -> Screen:
    proxy = session.get(Proxy, proxy_id)
    if proxy is None:
        return Screen(text="Proxy not found.", reply_markup=page_menu(back_to="proxies:list"))
    logs = recent_proxy_audit_logs(session, proxy)
    lines = ["Proxy Audit History", "", f"Proxy: {proxy.provider} {proxy.host}:{proxy.port}", ""]
    if not logs:
        lines.append("No proxy audit events yet.")
    for log in logs:
        timestamp = log.created_at.isoformat() if log.created_at else "pending timestamp"
        lines.append(f"{timestamp}")
        lines.append(f"Action: {log.action} | Status: {log.status}")
        lines.append("")
    return Screen(text="\n".join(lines).strip(), reply_markup=page_menu(back_to=f"proxy:{proxy.id}"))


def _task_button(task: Task) -> tuple[str, str]:
    return f"{task.id}. {task.title[:36]} ({task.status})", f"nav:task:{task.id}"


def render_task_list_page(
    session: Session,
    *,
    tasks: list[Task] | None = None,
    title: str = "Tasks",
    back_to: str = "tasks",
) -> Screen:
    current_tasks = tasks if tasks is not None else list_tasks(session)
    lines = [title, ""]
    buttons: list[tuple[str, str]] = []
    if not current_tasks:
        lines.append("No tasks yet.")
    for task in current_tasks[:15]:
        due = task.due_at.isoformat() if task.due_at else "No due date"
        model = task.model_brand.display_name if task.model_brand else "No model"
        assignee = _identity(task.assigned_to)
        lines.append(f"{task.id}. {_status_marker(task.status)} {task.title}")
        lines.append(f"   Status: {task.status} | Priority: {task.priority}")
        lines.append(f"   Model: {model} | Assigned: {assignee}")
        lines.append(f"   Due: {due}")
        buttons.append(_task_button(task))
    return Screen(text="\n".join(lines), reply_markup=task_list_menu(buttons, back_to=back_to))


def render_task_detail_page(session: Session, task_id: int) -> Screen:
    task = get_task(session, task_id)
    if task is None:
        return Screen(text="Task not found.", reply_markup=page_menu(back_to="tasks:list"))
    model = task.model_brand.display_name if task.model_brand else "No model"
    account = f"{task.account.platform} @{task.account.username}" if task.account else "No account"
    due = task.due_at.isoformat() if task.due_at else "No due date"
    completed = task.completed_at.isoformat() if task.completed_at else "Not completed"
    logs = task_audit_logs(session, task, limit=3)
    recent = [f"- {log.action} ({log.status})" for log in logs] or ["- No recent task events"]
    lines = [
        "Task Detail",
        "",
        f"Title: {task.title}",
        f"Description: {task.description or 'None'}",
        f"Status: {_status_marker(task.status)} {task.status}",
        f"Priority: {task.priority}",
        f"Model/Brand: {model}",
        f"Account: {account}",
        f"Assigned To: {_identity(task.assigned_to)}",
        f"Created By: {_identity(task.created_by)}",
        f"Due: {due}",
        f"Completed: {completed}",
        "",
        "Recent Events:",
        *recent,
    ]
    return Screen(text="\n".join(lines), reply_markup=task_detail_menu(task.id))


def render_task_assignment_page(session: Session, task_id: int) -> Screen:
    task = get_task(session, task_id)
    if task is None:
        return Screen(text="Task not found.", reply_markup=page_menu(back_to="tasks:list"))
    buttons = [
        (_identity(user), f"nav:task:{task.id}:assign:{user.id}")
        for user in active_users_for_assignment(session)
        if user.id != task.assigned_to_user_id
    ]
    lines = ["Reassign Task", "", f"Task: {task.title}", ""]
    if not buttons:
        lines.append("No active users available.")
    return Screen(text="\n".join(lines), reply_markup=task_user_choice_menu(task.id, buttons))


def _incident_button(incident: Incident) -> tuple[str, str]:
    return f"{incident.id}. {incident.title[:34]} ({incident.severity})", f"nav:incident:{incident.id}"


def render_incident_list_page(
    session: Session,
    *,
    incidents: list[Incident] | None = None,
    title: str = "Incidents",
    back_to: str = "incidents",
) -> Screen:
    current_incidents = incidents if incidents is not None else list_incidents(session)
    lines = [title, ""]
    buttons: list[tuple[str, str]] = []
    if not current_incidents:
        lines.append("No incidents yet.")
    for incident in current_incidents[:15]:
        assignee = _identity(incident.assigned_to)
        source = incident.source_type or "manual"
        lines.append(f"{incident.id}. {_status_marker(incident.severity)} {incident.title}")
        lines.append(f"   Severity: {severity_label(incident.severity)} | Status: {incident.status}")
        lines.append(f"   Source: {source} | Assigned: {assignee}")
        buttons.append(_incident_button(incident))
    return Screen(text="\n".join(lines), reply_markup=incident_list_menu(buttons, back_to=back_to))


def render_incident_detail_page(session: Session, incident_id: int) -> Screen:
    incident = get_incident(session, incident_id)
    if incident is None:
        return Screen(text="Incident not found.", reply_markup=page_menu(back_to="incidents:list"))
    model = incident.model_brand.display_name if incident.model_brand else "No model"
    account = f"{incident.account.platform} @{incident.account.username}" if incident.account else "No account"
    proxy = f"{incident.proxy.provider} {incident.proxy.host}:{incident.proxy.port}" if incident.proxy else "No proxy"
    resolved = incident.resolved_at.isoformat() if incident.resolved_at else "Not resolved"
    logs = incident_audit_logs(session, incident, limit=3)
    recent = [f"- {log.action} ({log.status})" for log in logs] or ["- No recent incident events"]
    lines = [
        "Incident Detail",
        "",
        f"Title: {incident.title}",
        f"Description: {incident.description or 'None'}",
        f"Severity: {_status_marker(incident.severity)} {severity_label(incident.severity)}",
        f"Status: {incident.status}",
        f"Source: {incident.source_type or 'manual'}",
        f"Model/Brand: {model}",
        f"Account: {account}",
        f"Proxy: {proxy}",
        f"Assigned To: {_identity(incident.assigned_to)}",
        f"Escalation Target: {escalation_target_for(incident)}",
        f"Resolved: {resolved}",
        f"Resolution Notes: {incident.resolution_notes or 'None'}",
        "",
        "Recent Events:",
        *recent,
    ]
    return Screen(text="\n".join(lines), reply_markup=incident_detail_menu(incident.id))


def render_incident_assignment_page(session: Session, incident_id: int) -> Screen:
    incident = get_incident(session, incident_id)
    if incident is None:
        return Screen(text="Incident not found.", reply_markup=page_menu(back_to="incidents:list"))
    buttons = [
        (_identity(user), f"nav:incident:{incident.id}:assign:{user.id}")
        for user in active_users_for_assignment(session)
        if user.id != incident.assigned_to_user_id
    ]
    lines = ["Assign Incident", "", f"Incident: {incident.title}", ""]
    if not buttons:
        lines.append("No active users available.")
    return Screen(text="\n".join(lines), reply_markup=incident_user_choice_menu(incident.id, buttons))


def render_incident_timeline_page(session: Session, incident_id: int) -> Screen:
    incident = get_incident(session, incident_id)
    if incident is None:
        return Screen(text="Incident not found.", reply_markup=page_menu(back_to="incidents:list"))
    entries = incident_timeline(session, incident)
    lines = ["Incident Timeline", "", f"Incident: {incident.title}", ""]
    if not entries:
        lines.append("No timeline entries yet.")
    for entry in entries[:15]:
        actor = _identity(entry.actor)
        when = entry.created_at.isoformat() if entry.created_at else "pending timestamp"
        lines.append(f"{when}")
        lines.append(f"{entry.event_type} by {actor}")
        lines.append(entry.message)
        lines.append("")
    return Screen(text="\n".join(lines).strip(), reply_markup=page_menu(back_to=f"incident:{incident.id}"))


def render_executive_dashboard_page(session: Session, user: User | None = None) -> Screen:
    record_dashboard_view(session, actor=user, dashboard_name="executive")
    generate_recommendations(session, actor=user)
    stats = executive_dashboard(session)
    lines = [
        "Executive Command Center",
        "",
        f"Status: {stats['operational_status_banner']}",
        f"Agency Health Score: {stats['agency_health_score']}/100",
        f"Models: {stats['total_models']} "
        f"({stats['healthy_models']} healthy / {stats['warning_models']} warning / {stats['critical_models']} critical)",
        f"Accounts: {stats['total_accounts']} "
        f"({stats['healthy_accounts']} healthy / {stats['warning_accounts']} warning / {stats['critical_accounts']} critical)",
        f"Auth Attention: login {stats['accounts_needing_login']} / 2FA {stats['accounts_needing_2fa']}",
        f"Proxies: {stats['total_proxies']} "
        f"({stats['healthy_proxies']} healthy / {stats['warning_proxies']} warning / {stats['critical_proxies']} critical)",
        f"Accounts Missing Proxy: {stats['accounts_missing_proxy']}",
        f"Tasks: {stats['open_tasks']} open / {stats['overdue_tasks']} overdue / {stats['completed_tasks_today']} done today",
        f"Incidents: {stats['open_incidents']} open / {stats['critical_incidents']} critical",
        "",
        "Critical Alerts:",
    ]
    lines.extend(f"- {item}" for item in stats["critical_alerts"][:5])
    if not stats["critical_alerts"]:
        lines.append("- No active critical alerts")
    lines.extend(["", "Top Recommendations:"])
    if stats["top_recommendations"]:
        for recommendation in stats["top_recommendations"]:
            marker = _status_marker(recommendation["severity"])
            lines.append(f"- {marker} {recommendation['title']}")
    else:
        lines.append("- No open recommendations")
    lines.extend(
        [
            "",
            "Production Status:",
            f"Railway: {stats['production_status']}",
            f"Last Deployment: {stats['last_deployment_status']}",
            f"Bot Heartbeat: {stats['last_bot_heartbeat']}",
            f"Last Event: {stats['last_event_logged']} at {stats['last_event_at']}",
            "",
            "Automation Status:",
            f"Active Automations: {stats['active_automations']}",
            f"Failed Automations: {stats['failed_automations']}",
            f"Pending Approvals: {stats['pending_automation_approvals']}",
            f"Last Automation Run: {stats['last_automation_run']} at {stats['last_automation_run_at']}",
            f"Automation Success Rate: {stats['automation_success_rate']}%",
            "",
            "Recent High-Risk Events:",
        ]
    )
    lines.extend(f"- {item}" for item in stats["recent_high_risk_events"][:5])
    if not stats["recent_high_risk_events"]:
        lines.append("- No high-risk events found")
    return Screen(text="\n".join(lines), reply_markup=executive_dashboard_menu())


def render_operations_dashboard_page(session: Session, user: User | None = None) -> Screen:
    record_dashboard_view(session, actor=user, dashboard_name="operations")
    stats = operations_dashboard(session)
    lines = [
        "Operations Dashboard",
        "",
        f"Pending Tasks: {stats['pending_tasks']}",
        f"Blocked Tasks: {stats['blocked_tasks']}",
        f"Accounts Needing Attention: {stats['accounts_needing_attention']}",
        f"Proxies Needing Attention: {stats['proxies_needing_attention']}",
        f"Models Needing Attention: {stats['models_needing_attention']}",
        "",
        "Tasks by Status:",
    ]
    for status, count in stats["tasks_by_status"].items():
        lines.append(f"- {status}: {count}")
    lines.extend(
        [
            "",
            "Incidents by Severity:",
        ]
    )
    for severity, count in stats["incidents_by_severity"].items():
        lines.append(f"- {severity.title()}: {count}")
    lines.extend(["", "Recent Escalations:"])
    lines.extend(f"- {item}" for item in stats["recent_escalations"][:5])
    if not stats["recent_escalations"]:
        lines.append("- No recent escalations")
    lines.extend(["", "Recent Failed Repairs:"])
    lines.extend(f"- {item}" for item in stats["recent_failed_repairs"][:5])
    if not stats["recent_failed_repairs"]:
        lines.append("- No recent failed repairs")
    return Screen(text="\n".join(lines), reply_markup=operations_dashboard_menu())


def render_manager_command_page(session: Session, user: User | None = None) -> Screen:
    record_dashboard_view(session, actor=user, dashboard_name="manager_command")
    metrics = manager_command_metrics(session)
    lines = [
        "Manager Command View",
        "",
        f"People On Shift: {len(metrics['on_shift'])}",
        f"People Off Shift: {len(metrics['off_shift'])}",
        f"Open Tasks: {metrics['open_tasks']}",
        f"Overdue Tasks: {metrics['overdue_tasks']}",
        f"Open Incidents: {metrics['open_incidents']}",
        f"Unresolved Critical Incidents: {metrics['unresolved_critical_incidents']}",
        f"Owner/Admin Recommendations: {metrics['owner_admin_recommendations']}",
        f"Notification Delivery Failures: {metrics['notification_delivery_failures']}",
        "",
        "On Shift:",
    ]
    if metrics["on_shift"]:
        lines.extend(f"- {_identity(person)}" for person in metrics["on_shift"][:10])
    else:
        lines.append("- Nobody marked on shift")
    lines.extend(["", "Open Tasks by Assignee:"])
    if metrics["open_tasks_by_assignee"]:
        for user_id, count in sorted(metrics["open_tasks_by_assignee"].items(), key=lambda item: str(item[0])):
            assignee = session.get(User, user_id) if user_id is not None else None
            lines.append(f"- {_identity(assignee)}: {count}")
    else:
        lines.append("- None")
    lines.extend(["", "Open Incidents by Assignee:"])
    if metrics["open_incidents_by_assignee"]:
        for user_id, count in sorted(metrics["open_incidents_by_assignee"].items(), key=lambda item: str(item[0])):
            assignee = session.get(User, user_id) if user_id is not None else None
            lines.append(f"- {_identity(assignee)}: {count}")
    else:
        lines.append("- None")
    return Screen(text="\n".join(lines), reply_markup=manager_command_menu())


def render_chatter_dashboard_page(session: Session, user: User | None = None) -> Screen:
    record_dashboard_view(session, actor=user, dashboard_name="chatter")
    stats = chatter_dashboard(session, user=user)
    lines = [
        "Chatter Dashboard",
        "",
        f"Assigned Models: {stats['assigned_models']}",
        f"Open Tasks: {stats['open_tasks']}",
        f"Escalations: {stats['escalations']}",
        f"Notes: {stats['notes']}",
        "",
        "Future Metrics:",
    ]
    lines.extend(f"- {item}" for item in stats["future_metrics"])
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="reports"))


def render_va_dashboard_page(session: Session, user: User | None = None) -> Screen:
    record_dashboard_view(session, actor=user, dashboard_name="va")
    stats = va_dashboard(session, user=user)
    lines = [
        "VA Dashboard",
        "",
        f"Assigned Models: {stats['assigned_models']}",
        f"Assigned Accounts: {stats['assigned_accounts']}",
        f"Open Tasks: {stats['open_tasks']}",
        f"Overdue Tasks: {stats['overdue_items']}",
        f"Content/Upload: {stats['uploads']}",
        f"Approvals: {stats['approvals']}",
    ]
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="reports"))


def render_daily_briefing_page(
    session: Session,
    user: User | None = None,
    *,
    mode: str = "generate",
) -> Screen:
    if mode == "latest":
        summary = view_latest_daily_briefing(session, actor=user)
        if summary is None:
            return Screen(
                text="Daily Company Briefing\n\nNo briefing has been generated yet.",
                reply_markup=briefing_menu(),
            )
    else:
        summary = generate_daily_briefing(session, actor=user)
    record_report_view(session, actor=user, report_name="daily_briefing")
    lines = [
        "Daily Company Briefing",
        "",
        f"Briefing ID: {summary.get('briefing_id', 'pending')}",
        f"Summary: {summary['summary_text']}",
        f"Overall Status: {summary['overall_status']}",
        f"Agency Health Score: {summary['agency_health_score']}",
        f"Active Models: {summary['models_active']}",
        f"Models Healthy/Warning/Critical: "
        f"{summary['models_healthy']}/{summary['models_warning']}/{summary['models_critical']}",
        f"Accounts Healthy/Warning/Critical: "
        f"{summary['accounts_healthy']}/{summary['accounts_warning']}/{summary['accounts_critical']}",
        f"Accounts Needing Login/2FA: {summary['accounts_needing_login']}/{summary['accounts_needing_2fa']}",
        f"Proxies Healthy/Warning/Critical: "
        f"{summary['proxies_healthy']}/{summary['proxies_warning']}/{summary['proxies_critical']}",
        f"Open Incidents: {summary['open_incidents']}",
        f"Critical Incidents: {summary['critical_incidents']}",
        f"Tasks Completed Today: {summary['tasks_completed_today']}",
        f"Overdue Tasks: {summary['overdue_tasks']}",
        "",
        "Top Active Users:",
    ]
    if summary["top_active_users"]:
        for row in summary["top_active_users"]:
            lines.append(f"- {row['display_name']}: {row['completed_tasks']}")
    else:
        lines.append("- No completed tasks yet today")
    lines.extend(["", "Recent Audit Highlights:"])
    lines.extend(f"- {item}" for item in summary["recent_audit_highlights"])
    lines.extend(["", "Recommended Actions:"])
    lines.extend(f"- {item}" for item in summary["recommended_actions"])
    return Screen(text="\n".join(lines), reply_markup=briefing_menu())


def render_daily_digest_page(
    session: Session,
    user: User | None = None,
    *,
    mode: str = "home",
    purpose: str | None = None,
) -> Screen:
    if mode == "generate":
        summary = generate_daily_digest(session, actor=user)
        title = "Daily Digest Generated"
    elif mode == "preview":
        summary = preview_daily_digest(session, actor=user)
        title = "Daily Digest Preview"
        if summary is None:
            return Screen(
                text="Daily Digest\n\nNo digest has been generated yet.",
                reply_markup=daily_digest_menu(),
            )
    elif mode == "send":
        target_purpose = purpose or "operations"
        attempts = request_digest_send(session, actor=user, purpose=target_purpose)
        latest = preview_daily_digest(session, actor=user) or generate_daily_digest(session, actor=user)
        lines = [
            "Daily Digest Send Requested",
            "",
            f"Purpose: {target_purpose}",
            f"Delivery Attempts Created: {attempts}",
            "",
            latest["summary_text"],
        ]
        return Screen(text="\n".join(lines), reply_markup=daily_digest_menu())
    elif mode == "history":
        attempts = daily_digest_delivery_history(session)
        lines = ["Daily Digest Delivery History", ""]
        if not attempts:
            lines.append("No delivery attempts yet.")
        for attempt in attempts:
            when = attempt.attempted_at.isoformat() if attempt.attempted_at else "unknown time"
            lines.append(f"{when} | {attempt.event_type} | {attempt.status}")
        return Screen(text="\n".join(lines), reply_markup=daily_digest_menu())
    elif mode == "schedule":
        return Screen(
            text="Daily Digest Schedule\n\nScheduling is prepared as a placeholder. Use Generate/Preview/Send today.",
            reply_markup=daily_digest_menu(),
        )
    else:
        summary = preview_daily_digest(session, actor=user)
        if summary is None:
            lines = [
                "Daily Digest",
                "",
                "No digest generated yet.",
                "Use Generate Digest to create today's operational summary.",
            ]
            return Screen(text="\n".join(lines), reply_markup=daily_digest_menu())
        title = "Daily Digest"
    record_report_view(session, actor=user, report_name="daily_digest")
    lines = [
        title,
        "",
        f"Summary: {summary['summary_text']}",
        f"Agency Health Score: {summary['agency_health_score']}",
        f"Critical Incidents: {summary['critical_incidents']}",
        f"Overdue Tasks: {summary['overdue_tasks']}",
        f"Accounts Needing Login/2FA: {summary['accounts_needing_login']}/{summary['accounts_needing_2fa']}",
        f"Proxies Warning/Critical: {summary['proxies_warning']}/{summary['proxies_critical']}",
        "",
        "Top Recommendations:",
    ]
    for item in summary["recommended_actions"][:5]:
        lines.append(f"- {item}")
    if not summary["recommended_actions"]:
        lines.append("- No recommendations right now")
    return Screen(text="\n".join(lines), reply_markup=daily_digest_menu())


def render_accountability_page(session: Session, user: User | None = None) -> Screen:
    view_accountability_report(session, actor=user)
    report = generate_accountability_report(session, actor=user)
    record_report_view(session, actor=user, report_name="team_accountability")
    lines = ["Team Accountability", "", f"Generated: {report['generated_at']}", ""]
    if not report["users"]:
        lines.append("No users yet.")
    for row in report["users"][:15]:
        roles = ", ".join(row["roles"]) or "No roles"
        lines.append(f"{row['display_name']}")
        lines.append(f"   Open Tasks: {row['assigned_open_tasks']} | Completed Today: {row['completed_today']}")
        lines.append(
            f"   Overdue: {row['overdue_tasks']} | Open Incidents: {row['open_incidents_assigned']}"
        )
        lines.append(f"   Resolved Today: {row['resolved_incidents_today']} | Score: {row['score']}")
        lines.append(f"   Last Seen: {row['last_seen']} | Roles: {roles}")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="reports"))


def render_recommendations_page(session: Session, user: User | None = None) -> Screen:
    generate_recommendations(session, actor=user)
    recommendations = list_recommendations(session, status="open", limit=20)
    record_report_view(session, actor=user, report_name="recommendations")
    lines = ["Recommendations", ""]
    buttons: list[tuple[str, str]] = []
    if not recommendations:
        lines.append("No open recommendations.")
    for recommendation in recommendations:
        marker = _status_marker(recommendation.severity)
        lines.append(f"{recommendation.id}. {marker} {recommendation.title}")
        lines.append(f"   Status: {recommendation.status} | Type: {recommendation.recommendation_type}")
        buttons.append(
            (
                f"{recommendation.id}. {recommendation.title}",
                f"nav:recommendation:{recommendation.id}",
            )
        )
    return Screen(text="\n".join(lines), reply_markup=recommendations_menu(buttons))


def render_recommendation_detail_page(session: Session, recommendation_id: int) -> Screen:
    recommendation = session.get(Recommendation, recommendation_id)
    if recommendation is None:
        return Screen(
            text="Recommendation not found.",
            reply_markup=page_menu(back_to="reports:executive:recommendations"),
        )
    target = (
        f"{recommendation.entity_type}:{recommendation.entity_id}"
        if recommendation.entity_type and recommendation.entity_id
        else "General"
    )
    lines = [
        "Recommendation",
        "",
        f"Title: {recommendation.title}",
        f"Severity: {_status_marker(recommendation.severity)} {recommendation.severity}",
        f"Status: {recommendation.status}",
        f"Type: {recommendation.recommendation_type}",
        f"Target: {target}",
        f"Description: {recommendation.description}",
        "",
        "Jump opens the closest related Fortuna OS page when available.",
    ]
    return Screen(text="\n".join(lines), reply_markup=recommendation_detail_menu(recommendation.id))


def render_recommendation_why_page(session: Session, recommendation_id: int) -> Screen:
    recommendation = session.get(Recommendation, recommendation_id)
    if recommendation is None:
        return Screen(text="Recommendation not found.", reply_markup=page_menu(back_to="reports:executive:recommendations"))
    why = recommendation_why(recommendation)
    source_signals = ", ".join(str(signal_id) for signal_id in why["source_signal_ids"]) or "None"
    lines = [
        "Why This Recommendation",
        "",
        f"Title: {recommendation.title}",
        f"Reason: {why['reason']}",
        f"Confidence: {why['confidence_score'] if why['confidence_score'] is not None else 'Not scored'}",
        f"Related Entity: {why['related_entity']}",
        f"Source Signals: {source_signals}",
        f"Source Pattern: {why['source_pattern_id'] or 'None'}",
        "",
        "Suggested Next Action:",
        why["suggested_action"],
    ]
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to=f"recommendation:{recommendation.id}"))


def render_intelligence_briefing_page(
    session: Session,
    user: User | None = None,
    *,
    mode: str = "generate",
) -> Screen:
    if mode == "latest":
        latest = list_executive_insights(session, limit=1)
        if not latest:
            return Screen(
                text="Executive Intelligence Briefing\n\nNo intelligence briefing has been generated yet.",
                reply_markup=intelligence_briefing_menu(),
            )
        insight = latest[0]
        lines = [
            "Executive Intelligence Briefing",
            "",
            f"Insight ID: {insight.id}",
            f"Severity: {_status_marker(insight.severity)} {insight.severity}",
            f"Confidence: {insight.confidence_score}",
            f"Summary: {insight.body}",
            "",
            "Recommended Action:",
            insight.recommended_action,
        ]
        return Screen(text="\n".join(lines), reply_markup=intelligence_briefing_menu())
    if mode == "send_hq":
        lines = [
            "Executive Intelligence Briefing",
            "",
            "Send to HQ is a safe placeholder until notification targets are explicitly approved.",
        ]
        return Screen(text="\n".join(lines), reply_markup=intelligence_briefing_menu())
    briefing = generate_executive_intelligence_briefing(session, actor=user)
    lines = [
        "Executive Intelligence Briefing",
        "",
        f"Insight ID: {briefing['insight_id']}",
        f"Agency Health Score: {briefing['agency_health_score']}/100",
        f"Summary: {briefing['summary_text']}",
        "",
        "Top Risks:",
    ]
    lines.extend(f"- {item}" for item in briefing["top_risks"][:3])
    if not briefing["top_risks"]:
        lines.append("- No top risks detected")
    lines.extend(["", "Top Improvements:"])
    lines.extend(f"- {item}" for item in briefing["top_improvements"][:3])
    if not briefing["top_improvements"]:
        lines.append("- No improvement recommendations yet")
    lines.extend(["", "Patterns Detected:"])
    lines.extend(f"- {item}" for item in briefing["patterns_detected"][:5])
    if not briefing["patterns_detected"]:
        lines.append("- No active patterns")
    lines.extend(["", "Negative Trends:"])
    lines.extend(f"- {item}" for item in briefing["negative_trends"][:5])
    if not briefing["negative_trends"]:
        lines.append("- No significant negative trends")
    lines.extend(["", "Overloaded Users:"])
    lines.extend(f"- {item}" for item in briefing["overloaded_users"][:5])
    if not briefing["overloaded_users"]:
        lines.append("- None")
    lines.extend(
        [
            "",
            "What the system is learning:",
            briefing.get("learning_summary", "Learning memory is still warming up."),
            f"Top Recurring Problem: {briefing.get('top_recurring_problem', 'Not enough data')}",
            f"Best Playbook: {briefing.get('best_playbook') or 'Not enough data'}",
            f"Lowest Confidence Playbook: {briefing.get('lowest_confidence_playbook') or 'Not enough data'}",
        ]
    )
    lines.extend(["", "Confidence Notes:", briefing["confidence_notes"]])
    return Screen(text="\n".join(lines), reply_markup=intelligence_briefing_menu())


def render_intelligence_runs_page(session: Session) -> Screen:
    runs = list_intelligence_runs(session, limit=10)
    lines = ["Intelligence Runs", ""]
    buttons: list[tuple[str, str]] = []
    if not runs:
        lines.append("No intelligence runs yet.")
    for run in runs:
        finished = run.finished_at.isoformat() if run.finished_at else "running"
        lines.append(f"{run.id}. {run.run_type}")
        lines.append(f"   Status: {run.status} | Finished: {finished}")
        buttons.append((f"{run.id}. {run.run_type}", f"nav:intelligence:run_detail:{run.id}"))
    return Screen(text="\n".join(lines), reply_markup=intelligence_run_menu(buttons))


def render_intelligence_run_detail_page(session: Session, run_id: int) -> Screen:
    run = session.get(IntelligenceRun, run_id)
    if run is None:
        return Screen(text="Intelligence run not found.", reply_markup=page_menu(back_to="intelligence:runs"))
    lines = [
        "Intelligence Run",
        "",
        f"ID: {run.id}",
        f"Type: {run.run_type}",
        f"Status: {run.status}",
        f"Started: {run.started_at.isoformat() if run.started_at else 'unknown'}",
        f"Finished: {run.finished_at.isoformat() if run.finished_at else 'not finished'}",
        f"Error: {run.error_message or 'None'}",
        "",
        "Summary:",
    ]
    for key, value in sorted((run.summary_json or {}).items()):
        lines.append(f"- {key}: {value}")
    if not run.summary_json:
        lines.append("- Empty")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="intelligence:runs"))


def render_intelligence_signals_page(session: Session) -> Screen:
    signals = list_signals(session, status="open", limit=20)
    lines = ["Intelligence Signals", ""]
    if not signals:
        lines.append("No open intelligence signals.")
    for signal in signals:
        lines.append(f"{signal.id}. {_status_marker(signal.severity)} {signal.title}")
        lines.append(f"   Type: {signal.signal_type} | Confidence: {signal.confidence_score}")
        lines.append(f"   Entity: {signal.entity_type or 'general'}:{signal.entity_id or 'n/a'}")
        lines.append(f"   Seen: {signal.occurrence_count} | Last: {signal.last_seen_at.isoformat() if signal.last_seen_at else 'unknown'}")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="intelligence"))


def render_intelligence_patterns_page(session: Session) -> Screen:
    patterns = list_patterns(session, status="active", limit=20)
    lines = ["Issue Patterns", ""]
    if not patterns:
        lines.append("No active issue patterns.")
    for pattern in patterns:
        lines.append(f"{pattern.id}. {_status_marker(pattern.severity)} {pattern.title}")
        lines.append(f"   Type: {pattern.pattern_type} | Confidence: {pattern.confidence_score}")
        lines.append(f"   Entity: {pattern.entity_type or 'general'}:{pattern.entity_id or 'n/a'}")
        lines.append(f"   Occurrences: {pattern.occurrence_count}")
        lines.append(f"   Action: {pattern.suggested_action}")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="intelligence"))


def render_intelligence_trends_page(session: Session) -> Screen:
    trends = list_trends(session, limit=20)
    lines = ["Trend Analysis", ""]
    if not trends:
        lines.append("No trend snapshots yet.")
    for trend in trends:
        change = f"{trend.percent_change}%" if trend.percent_change is not None else "baseline"
        lines.append(f"{trend.id}. {trend.metric_name}: {trend.value_numeric}")
        lines.append(f"   Direction: {trend.trend_direction} | Change: {change}")
        lines.append(f"   Window: {trend.comparison_window} | Date: {trend.snapshot_date.isoformat()}")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="intelligence"))


def render_workload_intelligence_page(session: Session, user: User | None = None) -> Screen:
    snapshots = list_workload_snapshots(session, limit=30)
    if not snapshots:
        from app.services.intelligence import analyze_workload

        snapshots = analyze_workload(session, actor=user)
    lines = ["Workload Intelligence", ""]
    overloaded = [snapshot for snapshot in snapshots if snapshot.overload_status in {"overloaded", "critical"}]
    off_shift = [snapshot for snapshot in snapshots if snapshot.availability_status != "on_shift"]
    overdue = [snapshot for snapshot in snapshots if snapshot.overdue_tasks > 0]
    critical = [snapshot for snapshot in snapshots if snapshot.critical_incidents > 0]
    lines.extend(
        [
            f"Overloaded Users: {len(overloaded)}",
            f"Users Off Shift: {len(off_shift)}",
            f"Users With Overdue Tasks: {len(overdue)}",
            f"Users With Critical Incidents: {len(critical)}",
            "",
            "Suggested Reassignments:",
        ]
    )
    if not overloaded and not overdue:
        lines.append("- None right now")
    for snapshot in (overloaded + overdue)[:10]:
        user_obj = session.get(User, snapshot.user_id)
        lines.append(
            f"- {_identity(user_obj)}: {snapshot.overload_status}, score {snapshot.workload_score}, "
            f"overdue {snapshot.overdue_tasks}"
        )
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="reports"))


def render_learning_center_page(session: Session) -> Screen:
    metrics = learning_center_metrics(session)
    lines = [
        "Learning Center",
        "",
        f"Total Learning Events: {metrics['total_learning_events']}",
        f"Active Playbooks: {metrics['active_playbooks']}",
        f"Outcome Memories: {metrics['outcome_memories']}",
        "",
        "Highest Confidence Playbooks:",
    ]
    for playbook in metrics["highest_confidence_playbooks"][:3]:
        lines.append(f"- {playbook.name}: {playbook.confidence_score}%")
    if not metrics["highest_confidence_playbooks"]:
        lines.append("- None yet")
    lines.extend(["", "Repeated Failures:"])
    for memory in metrics["repeated_failures"][:3]:
        lines.append(f"- {memory.summary}")
    if not metrics["repeated_failures"]:
        lines.append("- None recorded")
    lines.extend(["", "Recent Learning Events:"])
    for event in metrics["recent_events"][:5]:
        lines.append(f"- {event.event_type}: {event.outcome}")
    if not metrics["recent_events"]:
        lines.append("- Learning events will appear as operations complete.")
    return Screen(text="\n".join(lines), reply_markup=learning_center_menu())


def render_playbooks_page(session: Session, *, recommended: bool = False) -> Screen:
    if recommended:
        pairs = recommend_playbooks(session, source_type="system", event_type="current_operations", limit=7)
        playbooks = [playbook for playbook, _reason in pairs]
        reasons = {playbook.id: reason for playbook, reason in pairs}
        title = "Recommended Playbooks"
    else:
        playbooks = list_playbooks(session)
        reasons = {}
        title = "Playbooks"
    lines = [title, ""]
    buttons: list[tuple[str, str]] = []
    if not playbooks:
        lines.append("No playbooks yet.")
    for playbook in playbooks:
        reason = reasons.get(playbook.id)
        lines.append(f"{playbook.id}. {playbook.name}")
        lines.append(
            f"   Category: {playbook.category} | Risk: {playbook.risk_level} | Confidence: {playbook.confidence_score}%"
        )
        if reason:
            lines.append(f"   Why: {reason}")
        buttons.append((f"{playbook.id}. {playbook.name[:34]}", f"nav:playbook:{playbook.id}"))
    back_to = "intelligence:learning" if not recommended else "intelligence:learning"
    return Screen(text="\n".join(lines), reply_markup=learning_playbooks_menu(buttons, back_to=back_to))


def render_playbook_detail_page(session: Session, playbook_id: int) -> Screen:
    playbook = get_playbook(session, playbook_id)
    if playbook is None:
        return Screen(text="Playbook not found.", reply_markup=page_menu(back_to="intelligence:learning:playbooks"))
    lines = [
        "Playbook",
        "",
        f"Name: {playbook.name}",
        f"Category: {playbook.category}",
        f"Status: {playbook.status}",
        f"Risk: {_status_marker(playbook.risk_level)} {playbook.risk_level}",
        f"Confidence: {playbook.confidence_score}%",
        f"Successes: {playbook.success_count}",
        f"Failures: {playbook.failure_count}",
        "",
        "Trigger:",
        playbook.trigger_summary,
        "",
        "Diagnosis Steps:",
    ]
    lines.extend(f"- {step}" for step in (playbook.diagnosis_steps_json or [])[:6])
    lines.extend(["", "Resolution Steps:"])
    lines.extend(f"- {step}" for step in (playbook.resolution_steps_json or [])[:6])
    lines.extend(["", "Verification Steps:"])
    lines.extend(f"- {step}" for step in (playbook.verification_steps_json or [])[:6])
    if playbook.rollback_steps_json:
        lines.extend(["", "Rollback Limitations / Steps:"])
        lines.extend(f"- {step}" for step in playbook.rollback_steps_json[:5])
    return Screen(text="\n".join(lines), reply_markup=playbook_detail_menu(playbook.id))


def render_playbook_history_page(session: Session, playbook_id: int) -> Screen:
    playbook = get_playbook(session, playbook_id)
    if playbook is None:
        return Screen(text="Playbook not found.", reply_markup=page_menu(back_to="intelligence:learning:playbooks"))
    runs = sorted(playbook.runs or [], key=lambda run: run.created_at, reverse=True)[:15]
    lines = ["Playbook History", "", playbook.name, ""]
    if not runs:
        lines.append("No runs or suggestions recorded yet.")
    for run in runs:
        lines.append(f"{run.id}. {run.status}")
        lines.append(f"   Source: {run.source_type or 'general'}:{run.source_id or 'n/a'}")
        lines.append(f"   Result: {run.result_summary or 'pending'}")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to=f"playbook:{playbook.id}"))


def render_outcome_memory_page(session: Session) -> Screen:
    memories = list_outcome_memories(session, limit=25)
    lines = ["Outcome Memory", ""]
    if not memories:
        lines.append("No outcome memories yet.")
    for memory in memories:
        lines.append(f"{memory.id}. {memory.memory_type}")
        lines.append(
            f"   Seen: {memory.occurrences} | Success Rate: {memory.success_rate}% | Last: {memory.last_outcome}"
        )
        lines.append(f"   {memory.summary}")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="intelligence:learning"))


def render_confidence_changes_page(session: Session) -> Screen:
    records = list_confidence_records(session, limit=25)
    lines = ["Confidence Changes", ""]
    if not records:
        lines.append("No confidence changes yet.")
    for record in records:
        previous = record.previous_score if record.previous_score is not None else "baseline"
        lines.append(f"{record.id}. {record.subject_type}:{record.subject_id}")
        lines.append(f"   {previous} -> {record.new_score} | {record.reason}")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="intelligence:learning"))


def render_automation_learning_page(session: Session) -> Screen:
    summary = automation_learning_summary(session)
    lines = [
        "Automation Learning",
        "",
        f"Success Rate: {summary['success_rate']}%",
        f"Succeeded Runs: {summary['succeeded_runs']}",
        f"Failed Runs: {summary['failed_runs']}",
        f"Skipped Runs: {summary['skipped_runs']}",
        "",
        "Automation Memories:",
    ]
    for memory in summary["memories"][:10]:
        lines.append(f"- {memory.summary}")
    if not summary["memories"]:
        lines.append("- No automation outcome memory yet.")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="intelligence:learning"))


def render_opportunity_learning_page(session: Session) -> Screen:
    summary = opportunity_learning_summary(session)
    lines = ["Opportunity Learning", "", "Best Niches:"]
    for niche, stats in summary["best_niches"][:5]:
        lines.append(f"- {niche}: {stats['success']}/{stats['total']} positive")
    if not summary["best_niches"]:
        lines.append("- No opportunity outcomes yet.")
    lines.extend(["", "Best Angles:"])
    for angle, stats in summary["best_angles"][:5]:
        lines.append(f"- {angle}: {stats['success']}/{stats['total']} positive")
    if not summary["best_angles"]:
        lines.append("- No angle memory yet.")
    lines.extend(["", "Weak Sources:"])
    for source, stats in summary["weak_sources"][:5]:
        lines.append(f"- {source}: {stats['success']}/{stats['total']} positive")
    if not summary["weak_sources"]:
        lines.append("- No weak sources identified.")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="intelligence:learning"))


def render_executive_memory_briefing_page(session: Session) -> Screen:
    briefing = executive_memory_briefing(session)
    best = briefing["best_playbook"]
    lowest = briefing["lowest_confidence_playbook"]
    weakest_source = briefing["weakest_opportunity_source"]
    lines = [
        "Executive Memory Briefing",
        "",
        "What the system is learning:",
        briefing["summary"],
        "",
        f"Top Recurring Problem: {briefing['top_recurring_problem']}",
        f"Best Playbook: {best.name if best else 'Not enough data'}",
        f"Lowest Confidence Playbook: {lowest.name if lowest else 'Not enough data'}",
        f"Automation Success Rate: {briefing['automation_success_rate']}%",
        f"Weakest Opportunity Source: {weakest_source[0] if weakest_source else 'Not enough data'}",
        "",
        "Recent Confidence Changes:",
    ]
    for record in briefing["recent_confidence_changes"][:5]:
        lines.append(f"- {record.subject_type}:{record.subject_id} -> {record.new_score} ({record.reason})")
    if not briefing["recent_confidence_changes"]:
        lines.append("- None yet")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="intelligence:learning"))


def render_opportunity_list_page(session: Session) -> Screen:
    opportunities = list_opportunities(session, limit=20)
    lines = ["Opportunities", ""]
    buttons: list[tuple[str, str]] = []
    if not opportunities:
        lines.append("No opportunities yet.")
    for opportunity in opportunities:
        lines.append(f"{opportunity.id}. {opportunity.title}")
        lines.append(f"   Platform: {opportunity.platform} | Score: {opportunity.score} | Status: {opportunity.status}")
        lines.append(f"   Niche: {opportunity.niche or 'not set'}")
        buttons.append((f"{opportunity.id}. {opportunity.title[:36]}", f"nav:opportunity:{opportunity.id}"))
    return Screen(text="\n".join(lines), reply_markup=opportunities_menu(buttons))


def render_opportunity_detail_page(session: Session, opportunity_id: int) -> Screen:
    opportunity = get_opportunity(session, opportunity_id)
    if opportunity is None:
        return Screen(text="Opportunity not found.", reply_markup=page_menu(back_to="opportunities:list"))
    assignee = session.get(User, opportunity.assigned_to_user_id) if opportunity.assigned_to_user_id else None
    model = session.get(ModelBrand, opportunity.model_brand_id) if opportunity.model_brand_id else None
    strategies = comment_strategies_for_opportunity(session, opportunity)[:2]
    latest_result = opportunity_results(session, opportunity, limit=1)
    lines = [
        "Opportunity",
        "",
        f"Title: {opportunity.title}",
        f"Platform: {opportunity.platform}",
        f"Source: {opportunity.source_type or 'manual'}",
        f"Status: {opportunity.status}",
        f"Score: {opportunity.score}/100",
        f"Priority: {opportunity.priority}",
        f"Niche: {opportunity.niche or 'Not set'}",
        f"Model/Brand: {model.display_name if model else 'Unassigned'}",
        f"Assigned To: {_identity(assignee)}",
        f"Assigned At: {opportunity.assigned_at.isoformat() if opportunity.assigned_at else 'Not set'}",
        f"Due: {opportunity.due_at.isoformat() if opportunity.due_at else 'Not set'}",
        f"Completed: {opportunity.completed_at.isoformat() if opportunity.completed_at else 'Not set'}",
        f"URL: {opportunity.url or 'Not set'}",
        f"Reason: {opportunity.reason or 'None'}",
        f"Suggested Angle: {opportunity.suggested_angle or 'None'}",
        f"Latest Result: {latest_result[0].status if latest_result else 'None'}",
        "",
        "Suggested Strategies:",
    ]
    if not strategies:
        lines.append("- No strategy suggestions yet.")
    for strategy in strategies:
        lines.append(f"- {strategy.angle.replace('_', ' ').title()} | Risk: {strategy.risk_score}/100 | Engagement: {strategy.engagement_score}/100")
        if strategy.sample_comment:
            lines.append(f"  Draft: {strategy.sample_comment}")
    lines.extend(
        [
            "",
            "Safety: posting remains manual and human-approved.",
        ]
    )
    return Screen(text="\n".join(lines), reply_markup=opportunity_detail_menu(opportunity.id))


def render_opportunity_strategies_page(session: Session, opportunity_id: int) -> Screen:
    opportunity = get_opportunity(session, opportunity_id)
    if opportunity is None:
        return Screen(text="Opportunity not found.", reply_markup=page_menu(back_to="opportunities:list"))
    strategies = comment_strategies_for_opportunity(session, opportunity)
    lines = [
        "Suggested Strategies",
        "",
        f"Opportunity: {opportunity.title}",
        "These are human review prompts, not automated comments.",
        "",
    ]
    if not strategies:
        lines.append("No strategies generated yet.")
    for strategy in strategies:
        lines.append(f"{strategy.angle.replace('_', ' ').title()} ({strategy.tone})")
        lines.append(
            f"   Curiosity: {strategy.curiosity_score}/100 | Engagement: {strategy.engagement_score}/100 | Risk: {strategy.risk_score}/100"
        )
        lines.append(f"   Draft: {strategy.sample_comment or 'Write a short human-approved comment.'}")
        lines.append(f"   Why: {strategy.reasoning or 'Suggested for human review.'}")
        lines.append(f"   Might Work Because: {strategy.why_it_might_work or 'It gives the chatter a safe angle.'}")
        lines.append(f"   Use Case: {strategy.suggested_use_case or 'Use only when context fits.'}")
    return Screen(
        text="\n".join(lines),
        reply_markup=choice_menu(
            [("Regenerate Strategies", f"nav:opportunity:{opportunity.id}:strategies:regenerate")],
            back_to=f"opportunity:{opportunity.id}",
        ),
    )


def render_opportunity_assignment_page(session: Session, opportunity_id: int) -> Screen:
    opportunity = get_opportunity(session, opportunity_id)
    if opportunity is None:
        return Screen("Opportunity not found.", page_menu(back_to="opportunities:list"))
    users = active_users_for_opportunity_assignment(session)
    choices = [(_identity(user)[:40], f"nav:opportunity:{opportunity.id}:assign:{user.id}") for user in users]
    if not choices:
        choices = [("No active users", f"nav:opportunity:{opportunity.id}")]
    return Screen(
        text=f"Assign Chatter\n\nOpportunity: {opportunity.title}\nChoose who should own this.",
        reply_markup=choice_menu(choices, back_to=f"opportunity:{opportunity.id}"),
    )


def render_opportunity_status_page(session: Session, opportunity_id: int) -> Screen:
    opportunity = get_opportunity(session, opportunity_id)
    if opportunity is None:
        return Screen("Opportunity not found.", page_menu(back_to="opportunities:list"))
    statuses = [status for status in OPPORTUNITY_STATUSES if status != "archived"]
    choices = [(status.replace("_", " ").title(), f"nav:opportunity:{opportunity.id}:status:{status}") for status in statuses]
    return Screen(
        text=f"Change Opportunity Status\n\nCurrent: {opportunity.status}",
        reply_markup=choice_menu(choices, back_to=f"opportunity:{opportunity.id}"),
    )


def render_opportunity_result_status_page(session: Session, opportunity_id: int) -> Screen:
    opportunity = get_opportunity(session, opportunity_id)
    if opportunity is None:
        return Screen("Opportunity not found.", page_menu(back_to="opportunities:list"))
    choices = [
        ("Posted", f"nav:opportunity:{opportunity.id}:result:posted"),
        ("Skipped", f"nav:opportunity:{opportunity.id}:result:skipped"),
        ("Rejected", f"nav:opportunity:{opportunity.id}:result:rejected"),
        ("Failed", f"nav:opportunity:{opportunity.id}:result:failed"),
    ]
    return Screen(
        text="Record Result\n\nChoose the human-recorded result. Fortuna OS will ask for notes next.",
        reply_markup=choice_menu(choices, back_to=f"opportunity:{opportunity.id}"),
    )


def render_creator_model_assignment_page(session: Session, creator_id: int) -> Screen:
    creator = get_creator_watch(session, creator_id)
    if creator is None:
        return Screen("Creator not found.", page_menu(back_to="opportunities:creators"))
    models = list_models_for_opportunity_assignment(session)
    choices = [(model.display_name[:40], f"nav:creator:{creator.id}:assign_model:{model.id}") for model in models]
    if not choices:
        choices = [("No models yet", "nav:models:create")]
    return Screen(
        text=f"Assign Model\n\nCreator: {creator.creator_name}",
        reply_markup=choice_menu(choices, back_to=f"creator:{creator.id}"),
    )


def render_creator_chatter_assignment_page(session: Session, creator_id: int) -> Screen:
    creator = get_creator_watch(session, creator_id)
    if creator is None:
        return Screen("Creator not found.", page_menu(back_to="opportunities:creators"))
    users = active_users_for_opportunity_assignment(session)
    choices = [(_identity(user)[:40], f"nav:creator:{creator.id}:assign_chatter:{user.id}") for user in users]
    if not choices:
        choices = [("No active users", f"nav:creator:{creator.id}")]
    return Screen(
        text=f"Assign Chatter\n\nCreator: {creator.creator_name}",
        reply_markup=choice_menu(choices, back_to=f"creator:{creator.id}"),
    )


def render_creator_priority_page(session: Session, creator_id: int) -> Screen:
    creator = get_creator_watch(session, creator_id)
    if creator is None:
        return Screen("Creator not found.", page_menu(back_to="opportunities:creators"))
    choices = [(priority.title(), f"nav:creator:{creator.id}:priority:{priority}") for priority in CREATOR_WATCH_PRIORITIES]
    return Screen(
        text=f"Edit Priority\n\nCreator: {creator.creator_name}\nCurrent: {creator.priority}",
        reply_markup=choice_menu(choices, back_to=f"creator:{creator.id}"),
    )


def render_post_chatter_assignment_page(session: Session, post_id: int) -> Screen:
    post = get_post_watch(session, post_id)
    if post is None:
        return Screen("Post watch item not found.", page_menu(back_to="opportunities:posts"))
    users = active_users_for_opportunity_assignment(session)
    choices = [(_identity(user)[:40], f"nav:post:{post.id}:assign_chatter:{user.id}") for user in users]
    if not choices:
        choices = [("No active users", f"nav:post:{post.id}")]
    return Screen(
        text=f"Assign Chatter\n\nPost: {post.post_reference}",
        reply_markup=choice_menu(choices, back_to=f"post:{post.id}"),
    )


def render_manager_opportunity_page(session: Session) -> Screen:
    view = manager_opportunity_view(session)
    counts = view["counts"]
    lines = [
        "Manager Opportunity View",
        "",
        f"Team Opportunities: {counts['assigned']}",
        f"Unassigned Opportunities: {len(view['unassigned'])}",
        f"Overdue: {len(view['overdue'])}",
        f"Completed Today: {len(view['completed_today'])}",
        f"High Priority: {len(view['high_priority'])}",
        "",
        "Top Performing Angles:",
    ]
    if not view["top_angles"]:
        lines.append("- Not enough results yet")
    for angle, count in view["top_angles"]:
        lines.append(f"- {angle}: {count} win(s)")
    lines.append("")
    lines.append("By Chatter:")
    if not view["most_active_chatters"]:
        lines.append("- Not enough chatter activity yet")
    for chatter, count in view["most_active_chatters"]:
        lines.append(f"- {chatter}: {count} result(s)")
    lines.append("")
    lines.append("By Model:")
    if not view["by_model"]:
        lines.append("- No model distribution yet")
    for model, count in view["by_model"]:
        lines.append(f"- {model}: {count}")
    lines.append("")
    lines.append("By Niche:")
    if not view["by_niche"]:
        lines.append("- No niche distribution yet")
    for niche, count in view["by_niche"]:
        lines.append(f"- {niche}: {count}")
    lines.append("")
    lines.append("Unassigned Opportunities:")
    if not view["unassigned"]:
        lines.append("- None")
    for opportunity in view["unassigned"][:5]:
        lines.append(f"- {opportunity.title} | {opportunity.score}/100")
    return Screen(text="\n".join(lines), reply_markup=opportunities_menu())


def render_opportunity_learning_v2_page(session: Session) -> Screen:
    summary = opportunity_learning_overview(session)
    lines = ["Opportunity Learning", "", "What Fortuna OS is learning from human-recorded outcomes.", ""]
    lines.append("Best Niches:")
    if not summary["best_niches"]:
        lines.append("- No opportunity outcomes yet.")
    for niche, stats in summary["best_niches"][:5]:
        lines.append(f"- {niche}: {stats['success']}/{stats['total']} positive")
    lines.append("")
    lines.append("Best Angles:")
    if not summary["best_angles"]:
        lines.append("- No angles recorded yet.")
    for angle, stats in summary["best_angles"][:5]:
        lines.append(f"- {angle}: {stats['success']}/{stats['total']} positive")
    lines.append("")
    lines.append("Most Successful Teams:")
    if not summary["most_successful_teams"]:
        lines.append("- Not enough team results yet.")
    for team, count in summary["most_successful_teams"][:5]:
        lines.append(f"- {team}: {count} win(s)")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="opportunities"))


def render_chatter_workspace_page(session: Session, user: User) -> Screen:
    workspace = chatter_workspace(session, user)
    lines = [
        "Chatter Workspace",
        "",
        f"New: {len(workspace['opportunity_tabs']['new'])}",
        f"In Progress: {len(workspace['opportunity_tabs']['in_progress'])}",
        f"Needs Result: {len(workspace['opportunity_tabs']['needs_result'])}",
        f"Completed: {len(workspace['opportunity_tabs']['completed'])}",
        "",
        "Today's Opportunities:",
    ]
    if not workspace["today_opportunities"]:
        lines.append("- No opportunities assigned today.")
    for opportunity in workspace["today_opportunities"]:
        lines.append(f"- {opportunity.title} | {opportunity.priority} | {opportunity.status}")
    lines.append("")
    lines.append("Assigned Models:")
    if not workspace["assigned_models"]:
        lines.append("- No models assigned yet.")
    for model in workspace["assigned_models"]:
        lines.append(f"- {_model_identity(model)}")
    lines.append("")
    lines.append("Assigned Tasks:")
    if not workspace["assigned_tasks"]:
        lines.append("- No open tasks assigned.")
    for task in workspace["assigned_tasks"]:
        lines.append(f"- {task.title} | {task.status} | {task.priority}")
    lines.append("")
    lines.append("Recent Results:")
    if not workspace["recent_results"]:
        lines.append("- No results recorded yet.")
    for result in workspace["recent_results"]:
        lines.append(f"- Opportunity {result.opportunity_id}: {result.status}")
    lines.extend(["", "Recommended Next Action:", workspace["recommended_next_action"]])
    return Screen(text="\n".join(lines), reply_markup=chatter_workspace_menu())


def render_help_copilot_page(session: Session, user: User | None = None, *, question: str | None = None) -> Screen:
    prompts = {
        "where_start": "Where do I start?",
        "create_first_model": "How do I create the first model?",
        "edit_model": "How do I edit a model?",
        "add_accounts": "How do I add accounts?",
        "assign_chatter": "How do I assign a chatter?",
        "create_opportunity": "How do I create an opportunity?",
        "add_creator": "How do I add a creator?",
        "assign_opportunity": "How do I assign an opportunity?",
        "my_opportunities": "Where do I see my opportunities?",
        "access": "Why can't I access this?",
        "next": "What should I do next?",
        "activation": "What's stopping my agency from being ready?",
        "readiness_low": "Why is readiness low?",
        "finish_setup": "How do I finish setup?",
        "model_unhealthy": "Why is this model unhealthy?",
        "record_results": "How do I record results?",
        "opportunity": "How do I complete an opportunity?",
        "where": "Where do I go?",
        "availability": "How does Availability work?",
        "screen:creator_detail": "Explain this Creator Detail screen.",
        "screen:opportunity_detail": "Explain this Opportunity Detail screen.",
        "screen:chatter_workspace": "Explain this Chatter Workspace screen.",
        "screen:manager_opportunity": "Explain this Manager Opportunity View screen.",
        "screen:post_watch": "Explain this Own Post Watch screen.",
    }
    if question:
        result = help_copilot_answer(session, user, question=prompts.get(question, question), current_page="help")
        lines = [
            "Help Copilot",
            "",
            f"Role Context: {result['role']}",
            "",
            result["answer"],
            "",
            f"Next Action: {result['next_action']}",
        ]
    else:
        lines = [
            "Help Copilot",
            "",
            "Ask simple workflow questions like:",
            "- Where do I start?",
            "- How do I create the first model?",
            "- What does this mean?",
            "- How do I complete an opportunity?",
            "- Where do I go?",
            "",
            "Choose a prompt below for a role-aware answer.",
        ]
    return Screen(text="\n".join(lines), reply_markup=help_copilot_menu())


def render_team_activation_page(session: Session) -> Screen:
    summaries = team_activation_qa(session)
    lines = ["Team Activation QA", "", "Friendly rollout readiness. Not punitive.", ""]
    buttons: list[tuple[str, str]] = []
    if not summaries:
        lines.append("No active users yet.")
    for item in summaries[:20]:
        user = item["user"]
        lines.append(f"{user.id}. {_identity(user)}")
        lines.append(f"   Status: {user.status}")
        lines.append(f"   Activation Score: {item['score']}%")
        lines.append(f"   Needs: {', '.join(item['flags'][:4]) if item['flags'] else 'ready'}")
        lines.append(
            f"   Work: {item['assigned_tasks']} task(s), {item['assigned_opportunities']} opportunit(y/ies), {item['assigned_models']} model(s)"
        )
        buttons.append((f"{user.id}. {_identity(user)[:32]}", f"nav:user:{user.id}"))
    return Screen(text="\n".join(lines), reply_markup=team_activation_menu(buttons))


def render_opportunity_results_page(session: Session) -> Screen:
    results = opportunity_results(session, limit=20)
    lines = ["Opportunity Results", ""]
    if not results:
        lines.append("No opportunity results yet.")
    for result in results:
        opportunity = session.get(Opportunity, result.opportunity_id)
        posted_by = session.get(User, result.posted_by_user_id) if result.posted_by_user_id else None
        lines.append(f"{result.id}. {opportunity.title if opportunity else 'Opportunity'}")
        lines.append(f"   Status: {result.status} | Posted By: {_identity(posted_by)}")
        lines.append(f"   Clicks: {result.clicks or 0} | Conversions: {result.conversions or 0}")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="opportunities"))


def render_simulation_runs_page(session: Session) -> Screen:
    runs = list_simulation_runs(session)
    lines = ["Automation Simulation Runs", ""]
    buttons: list[tuple[str, str]] = []
    if not runs:
        lines.append("No simulation runs yet.")
    for run in runs[:15]:
        created = run.created_at.isoformat() if run.created_at else "pending timestamp"
        lines.append(f"{run.id}. {run.automation_name}")
        lines.append(
            f"   Status: {run.status} | Risk: {run.risk_level} | Would Trigger: {run.would_trigger_count}"
        )
        lines.append(f"   Created: {created}")
        buttons.append((f"{run.id}. {run.automation_name}", f"nav:simulation:{run.id}"))
    return Screen(text="\n".join(lines), reply_markup=simulation_runs_menu(buttons))


def render_simulation_run_detail_page(session: Session, run_id: int) -> Screen:
    run = session.get(AutomationSimulationRun, run_id)
    if run is None:
        return Screen(text="Simulation run not found.", reply_markup=page_menu(back_to="automations:simulations"))
    expires = run.expires_at.isoformat() if run.expires_at else "not set"
    impact = run.impact_summary_json or {}
    lines = [
        "Simulation Impact Preview",
        "",
        f"Automation: {run.automation_name}",
        f"Type: {run.automation_type}",
        f"Rule: {run.automation_rule_id or 'legacy/manual'}",
        f"Status: {run.status}",
        f"Risk: {_status_marker(run.risk_level)} {run.risk_level}",
        f"Target Scope: {run.target_scope}",
        f"Would Trigger: {run.would_trigger_count}",
        f"Would Succeed: {run.would_succeed_count}",
        f"Would Fail: {run.would_fail_count}",
        f"Expires: {expires}",
        "",
        "Impact Summary:",
    ]
    for key, value in sorted(impact.items()):
        lines.append(f"- {key}: {value}")
    if not impact:
        lines.append("- No impact details recorded")
    if run.affected_entities_json:
        lines.extend(["", "What could be affected:"])
        for item in run.affected_entities_json[:8]:
            if isinstance(item, dict):
                lines.append("- " + ", ".join(f"{key}: {value}" for key, value in item.items()))
            else:
                lines.append(f"- {item}")
    if run.warnings_json:
        lines.extend(["", "Warnings:"])
        lines.extend(f"- {warning}" for warning in run.warnings_json[:6])
    lines.extend(["", "No production changes are applied by simulation runs."])
    return Screen(text="\n".join(lines), reply_markup=simulation_run_detail_menu(run.id))


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


def _notification_purpose_label(purpose: str) -> str:
    purpose_labels = {
        "owner": "HQ",
        "operations": "Operations",
        "incidents": "Incidents",
        "automation_logs": "Automation Logs",
        "testing": "Testing Sandbox",
    }
    return purpose_labels.get(purpose, purpose)


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


def _model_identity(model_brand: ModelBrand) -> str:
    if model_brand.stage_name:
        return f"{model_brand.display_name} ({model_brand.stage_name})"
    return model_brand.display_name


def render_model_list_page(session: Session) -> Screen:
    models = list_model_brands(session)
    lines = ["Models", ""]
    buttons: list[tuple[str, str]] = []
    if not models:
        lines.append("No models yet. Start by creating your first model/brand to unlock accounts, creators, and opportunities.")
    for model_brand in models[:10]:
        accounts = accounts_for_model(session, model_brand.id)
        health = calculate_model_health(
            model_brand,
            disabled_accounts=sum(1 for account in accounts if account.status == "disabled"),
            warning_accounts=sum(
                1
                for account in accounts
                if account.status == "warning" or account.auth_status in {"needs_login", "needs_2fa"}
            ),
        )
        identity = _model_identity(model_brand)
        lines.append(f"{model_brand.id}. {identity}")
        lines.append(f"   Status: {model_brand.status} | Health: {health.label} {health.score}/100")
        buttons.append((f"{model_brand.id}. {model_brand.display_name}", f"nav:model:{model_brand.id}"))
    return Screen(text="\n".join(lines), reply_markup=model_list_menu(buttons))


def render_model_dashboard_page(session: Session) -> Screen:
    models = list_model_brands(session)
    lines = ["Model Dashboard", ""]
    if not models:
        lines.append("No models yet.")
    for model_brand in models[:10]:
        accounts = accounts_for_model(session, model_brand.id)
        health = calculate_model_health(
            model_brand,
            disabled_accounts=sum(1 for account in accounts if account.status == "disabled"),
            warning_accounts=sum(
                1
                for account in accounts
                if account.status == "warning" or account.auth_status in {"needs_login", "needs_2fa"}
            ),
        )
        lines.append(f"{model_brand.display_name}: {health.label} {health.score}/100")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="models"))


def _member_names(members: list[User]) -> str:
    if not members:
        return "None"
    return ", ".join(user.display_name or user.username or f"User {user.id}" for user in members)


def render_model_detail_page(session: Session, model_id: int) -> Screen:
    model_brand = session.scalar(
        select(ModelBrand)
        .where(ModelBrand.id == model_id)
        .options(selectinload(ModelBrand.members).selectinload(ModelBrandMember.user))
    )
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="models:list"))
    members = summarize_members(model_brand)
    managers = members["manager"]
    chatters = members["chatter_manager"] + members["senior_chatter"] + members["chatter"]
    vas = members["va"]
    accounts = accounts_for_model(session, model_brand.id)
    health = calculate_model_health(
        model_brand,
        disabled_accounts=sum(1 for account in accounts if account.status == "disabled"),
        warning_accounts=sum(
            1
            for account in accounts
            if account.status == "warning" or account.auth_status in {"needs_login", "needs_2fa"}
        ),
    )
    platform_counts = {platform: sum(1 for account in accounts if account.platform == platform) for platform in ACCOUNT_PLATFORMS}
    attention_count = sum(
        1
        for account in accounts
        if account.status in {"warning", "critical", "disabled"}
        or account.auth_status in {"needs_login", "needs_2fa", "expired", "locked"}
    )
    model_tasks = tasks_for_model(session, model_brand.id)
    model_incidents = incidents_for_model(session, model_brand.id)
    open_task_count = sum(1 for task in model_tasks if task.status in {"open", "in_progress", "blocked"})
    open_incident_count = sum(1 for incident in model_incidents if incident.status in {"open", "investigating"})
    lines = [
        "Model Detail",
        "",
        f"Name: {model_brand.display_name}",
        f"Stage Name: {model_brand.stage_name or 'Not set'}",
        f"Country: {model_brand.country or 'Not set'}",
        f"Timezone: {model_brand.timezone or 'Not set'}",
        f"Primary Platform: {model_brand.primary_platform or 'Not set'}",
        f"Status: {model_brand.status}",
        f"Health: {health.label} {health.score}/100",
        f"Managers Assigned: {_member_names(managers)}",
        f"Chatters Assigned: {_member_names(chatters)}",
        f"VAs Assigned: {_member_names(vas)}",
        f"Accounts Count: {len(accounts)}",
        f"Instagram Count: {platform_counts['instagram']}",
        f"X Count: {platform_counts['x']}",
        f"OnlyFans Count: {platform_counts['onlyfans']}",
        f"Email Count: {platform_counts['email']}",
        f"Accounts Needing Attention: {attention_count}",
        f"Open Tasks: {open_task_count}",
        f"Open Incidents: {open_incident_count}",
        f"Notes: {model_brand.notes or 'None'}",
    ]
    return Screen(text="\n".join(lines), reply_markup=model_detail_menu(model_brand.id))


def render_model_edit_page(session: Session, model_id: int) -> Screen:
    model_brand = session.get(ModelBrand, model_id)
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="models:list"))
    return Screen(
        text="\n".join(
            [
                "Edit Model",
                "",
                f"Name: {model_brand.display_name}",
                f"Stage Name: {model_brand.stage_name or 'Not set'}",
                f"Country: {model_brand.country or 'Not set'}",
                f"Timezone: {model_brand.timezone or 'Not set'}",
                f"Primary Platform: {model_brand.primary_platform or 'Not set'}",
                f"Status: {model_brand.status}",
                f"Notes: {model_brand.notes or 'None'}",
                "",
                "Choose a field to edit. Changes are saved, audited, and reflected across dashboards.",
            ]
        ),
        reply_markup=model_edit_menu(model_brand.id, model_brand.status),
    )


def render_model_field_edit_page(session: Session, model_id: int, field: str) -> Screen:
    model_brand = session.get(ModelBrand, model_id)
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="models:list"))
    labels = {
        "display_name": "Name",
        "stage_name": "Stage Name",
        "country": "Country",
        "timezone": "Timezone",
        "primary_platform": "Primary Platform",
        "notes": "Notes",
        "internal_notes": "Internal Notes",
    }
    current = getattr(model_brand, field, None)
    label = labels.get(field, field.replace("_", " ").title())
    lines = [
        f"Edit {label}",
        "",
        f"Model: {model_brand.display_name}",
        f"Current: {current or 'Not set'}",
        "",
        "Send the new value in chat.",
        "Type skip to leave it unchanged.",
    ]
    return Screen("\n".join(lines), page_menu(back_to=f"model:{model_id}:edit"))


def render_model_team_page(session: Session, model_id: int) -> Screen:
    model_brand = session.scalar(
        select(ModelBrand)
        .where(ModelBrand.id == model_id)
        .options(selectinload(ModelBrand.members).selectinload(ModelBrandMember.user))
    )
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="models:list"))
    members = summarize_members(model_brand)
    lines = ["Manage Team", "", f"Model: {model_brand.display_name}", ""]
    for relationship_type in MODEL_BRAND_RELATIONSHIP_TYPES:
        lines.append(f"{RELATIONSHIP_LABELS[relationship_type]}: {_member_names(members[relationship_type])}")
    return Screen(text="\n".join(lines), reply_markup=model_team_menu(model_brand.id))


def render_model_assignment_page(
    session: Session,
    model_id: int,
    relationship_type: str,
) -> Screen:
    model_brand = session.scalar(
        select(ModelBrand)
        .where(ModelBrand.id == model_id)
        .options(selectinload(ModelBrand.members).selectinload(ModelBrandMember.user))
    )
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="models:list"))
    assigned_ids = {
        member.user_id
        for member in model_brand.members
        if member.relationship_type == relationship_type
    }
    user_buttons: list[tuple[str, str]] = []
    for user in active_users_for_assignment(session):
        if user.id in assigned_ids:
            continue
        identity = user.display_name or user.username or f"User {user.id}"
        user_buttons.append(
            (
                identity,
                f"nav:model:{model_brand.id}:team:assign:{relationship_type}:{user.id}",
            )
        )
    lines = [
        f"Assign {RELATIONSHIP_LABELS.get(relationship_type, relationship_type)}",
        "",
        f"Model: {model_brand.display_name}",
    ]
    if not user_buttons:
        lines.extend(["", "No active users available."])
    return Screen(
        text="\n".join(lines),
        reply_markup=model_member_choice_menu(model_brand.id, relationship_type, user_buttons),
    )


def render_model_remove_assignment_page(session: Session, model_id: int) -> Screen:
    model_brand = session.scalar(
        select(ModelBrand)
        .where(ModelBrand.id == model_id)
        .options(selectinload(ModelBrand.members).selectinload(ModelBrandMember.user))
    )
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="models:list"))
    user_buttons: list[tuple[str, str]] = []
    for member in model_brand.members:
        identity = member.user.display_name or member.user.username or f"User {member.user_id}"
        relationship = RELATIONSHIP_LABELS.get(member.relationship_type, member.relationship_type)
        user_buttons.append(
            (
                f"{relationship}: {identity}",
                f"nav:model:{model_brand.id}:team:remove:{member.relationship_type}:{member.user_id}",
            )
        )
    lines = ["Remove Assignment", "", f"Model: {model_brand.display_name}"]
    if not user_buttons:
        lines.extend(["", "No assignments yet."])
    return Screen(
        text="\n".join(lines),
        reply_markup=model_member_choice_menu(model_brand.id, "member", user_buttons),
    )


def render_model_audit_page(session: Session, model_id: int) -> Screen:
    model_brand = session.get(ModelBrand, model_id)
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="models:list"))
    logs = model_audit_logs(session, model_brand)
    lines = ["Model Audit History", "", f"Model: {model_brand.display_name}", ""]
    if not logs:
        lines.append("No model audit events yet.")
    for log in logs:
        timestamp = log.created_at.isoformat() if log.created_at else "pending timestamp"
        lines.append(f"{timestamp}")
        lines.append(f"Action: {log.action} | Status: {log.status}")
        lines.append("")
    return Screen(text="\n".join(lines).strip(), reply_markup=page_menu(back_to=f"model:{model_id}"))


def render_model_placeholder_page(session: Session, model_id: int, title: str) -> Screen:
    model_brand = session.get(ModelBrand, model_id)
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="models:list"))
    return Screen(
        text=f"{title}\n\nModel: {model_brand.display_name}\nCount: 0",
        reply_markup=page_menu(back_to=f"model:{model_id}"),
    )


def render_model_creators_page(session: Session, model_id: int) -> Screen:
    model_brand = session.get(ModelBrand, model_id)
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="models:list"))
    creators = [creator for creator in list_creator_watches(session, active_only=False, limit=100) if creator.assigned_model_id == model_id]
    lines = ["Model Creators", "", f"Model: {model_brand.display_name}", ""]
    buttons: list[tuple[str, str]] = []
    if not creators:
        lines.append("No creators assigned yet. Add a creator from the setup wizard or Creator Watchlist.")
        buttons.append(("Add Creator Starter", "nav:setup:wizard:creators"))
    for creator in creators[:15]:
        lines.append(f"{creator.id}. {creator.display_name or creator.creator_name} (@{creator.creator_username})")
        lines.append(f"   Platform: {creator.platform} | Niche: {creator.niche or 'Not set'} | Priority: {creator.priority}")
        buttons.append((f"{creator.id}. {creator.display_name or creator.creator_name}", f"nav:creator:{creator.id}"))
    return Screen("\n".join(lines), account_list_menu(buttons, back_to=f"model:{model_id}"))


def render_model_opportunities_page(session: Session, model_id: int) -> Screen:
    model_brand = session.get(ModelBrand, model_id)
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="models:list"))
    opportunities = [
        opportunity
        for opportunity in list_opportunities(session, include_archived=True, limit=100)
        if opportunity.model_brand_id == model_id
    ]
    lines = ["Model Opportunities", "", f"Model: {model_brand.display_name}", ""]
    buttons: list[tuple[str, str]] = []
    if not opportunities:
        lines.append("No opportunities yet. Create a starter opportunity from setup or add one manually.")
        buttons.append(("Create Starter Opportunity", "nav:setup:wizard:opportunities"))
    for opportunity in opportunities[:15]:
        lines.append(f"{opportunity.id}. {opportunity.title}")
        lines.append(f"   Status: {opportunity.status} | Priority: {opportunity.priority} | Score: {opportunity.score}")
        buttons.append((f"{opportunity.id}. {opportunity.title[:34]}", f"nav:opportunity:{opportunity.id}"))
    return Screen("\n".join(lines), account_list_menu(buttons, back_to=f"model:{model_id}"))


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


def _masked_telegram_id(value: int) -> str:
    raw = str(value)
    if len(raw) <= 4:
        return "hidden"
    return f"{raw[:2]}...{raw[-2:]}"


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


def render_my_models_page(session: Session, user: User) -> Screen:
    model_ids = select(ModelBrandMember.model_brand_id).where(ModelBrandMember.user_id == user.id)
    models = list(session.scalars(select(ModelBrand).where(ModelBrand.id.in_(model_ids)).order_by(ModelBrand.display_name)).all())
    lines = ["My Models", ""]
    buttons: list[tuple[str, str]] = []
    if not models:
        lines.append("No models are assigned yet.")
    for model_brand in models[:15]:
        lines.append(f"{model_brand.id}. {_model_identity(model_brand)}")
        lines.append(f"   Status: {model_brand.status}")
        buttons.append((model_brand.display_name[:40], f"nav:model:{model_brand.id}"))
    return Screen(text="\n".join(lines), reply_markup=model_list_menu(buttons))


def render_my_accounts_page(session: Session, user: User) -> Screen:
    model_ids = select(ModelBrandMember.model_brand_id).where(ModelBrandMember.user_id == user.id)
    accounts = list(
        session.scalars(
            select(Account)
            .where(Account.model_brand_id.in_(model_ids))
            .options(selectinload(Account.model_brand))
            .order_by(Account.platform, Account.username)
        ).all()
    )
    return render_account_list_page(session, accounts=accounts, title="My Accounts", back_to="menu")


def render_my_opportunities_page(session: Session, user: User) -> Screen:
    opportunities = list(
        session.scalars(
            select(Opportunity)
            .where(Opportunity.assigned_to_user_id == user.id)
            .order_by(desc(Opportunity.updated_at), desc(Opportunity.id))
            .limit(20)
        ).all()
    )
    lines = ["My Opportunities", ""]
    tab_counts = {
        "New": sum(1 for opportunity in opportunities if opportunity.status == "assigned"),
        "In Progress": sum(1 for opportunity in opportunities if opportunity.status == "reviewing"),
        "Posted": sum(1 for opportunity in opportunities if opportunity.status == "completed"),
        "Needs Result": sum(1 for opportunity in opportunities if opportunity.status in {"assigned", "reviewing"}),
        "Completed": sum(1 for opportunity in opportunities if opportunity.status == "completed"),
    }
    lines.extend(f"{label}: {count}" for label, count in tab_counts.items())
    lines.append("")
    buttons: list[tuple[str, str]] = []
    if not opportunities:
        lines.append("No opportunities assigned yet.")
    for opportunity in opportunities:
        lines.append(f"{opportunity.id}. {opportunity.title}")
        lines.append(f"   Priority: {opportunity.priority} | Score: {opportunity.score}/100 | Status: {opportunity.status}")
        buttons.append((f"{opportunity.id}. {opportunity.title[:36]}", f"nav:opportunity:{opportunity.id}"))
    return Screen(text="\n".join(lines), reply_markup=opportunities_menu(buttons))


def render_client_dashboard_page(session: Session, user: User) -> Screen:
    details = personalized_dashboard(session, user)
    lines = [
        "My Dashboard",
        "",
        f"Assigned Models: {details['assigned_models']}",
        f"Tasks Due Today: {details['tasks_due_today']}",
        f"Open Incidents: {details['open_incidents']}",
        "",
        "Reports and team visibility are kept simple here.",
    ]
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="menu"))


def render_my_reports_page(session: Session, user: User) -> Screen:
    details = personalized_dashboard(session, user)
    lines = [
        "My Reports",
        "",
        f"Role: {details['role']}",
        f"Assigned Models: {details['assigned_models']}",
        f"Performance Score: {details['performance']['accountability_score']}",
        "",
        "Full agency reports stay with managers and owners.",
    ]
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="menu"))


def render_my_team_page(session: Session, user: User) -> Screen:
    members = list(
        session.scalars(
            select(User)
            .join(ModelBrandMember, ModelBrandMember.user_id == User.id)
            .where(
                ModelBrandMember.model_brand_id.in_(
                    select(ModelBrandMember.model_brand_id).where(ModelBrandMember.user_id == user.id)
                )
            )
            .options(selectinload(User.roles))
            .distinct()
            .order_by(User.display_name)
        ).all()
    )
    lines = ["My Team", ""]
    if not members:
        lines.append("No team members are visible yet.")
    for member in members[:15]:
        roles = ", ".join(role.name for role in member.roles) or "No role"
        lines.append(f"- {_identity(member)} | {roles}")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="menu"))


def render_uploads_placeholder_page() -> Screen:
    lines = [
        "Uploads",
        "",
        "Upload workflows are prepared as a placeholder.",
        "For now, use Tasks and Availability to coordinate upload work.",
    ]
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="menu"))


def render_team_qa_page(session: Session) -> Screen:
    checklists = list_onboarding_checklists(session)
    lines = ["Team QA", "", "Rollout readiness checklist.", ""]
    buttons: list[tuple[str, str]] = []
    if not checklists:
        lines.append("No users yet.")
    for checklist in checklists[:20]:
        user = checklist.user
        lines.append(f"{user.id}. {_identity(user)}")
        lines.append(f"   Readiness: {checklist.readiness_score}% | Onboarded: {checklist.onboarded}")
        buttons.append((f"{user.id}. {_identity(user)[:32]}", f"nav:team_qa:{user.id}"))
    return Screen(text="\n".join(lines), reply_markup=team_qa_menu(buttons))


def render_team_qa_detail_page(session: Session, user_id: int) -> Screen:
    target = session.scalar(
        select(User).where(User.id == user_id).options(selectinload(User.roles), selectinload(User.availability))
    )
    if target is None:
        return Screen(text="User not found.", reply_markup=page_menu(back_to="team_qa"))
    checklist = list_onboarding_checklists(session)
    current = next(item for item in checklist if item.user_id == target.id)
    lines = [
        "Team QA Detail",
        "",
        f"User: {_identity(target)}",
        f"Roles: {', '.join(role.name for role in target.roles) or 'No roles'}",
        f"Readiness Score: {current.readiness_score}%",
        "",
        f"Role Assigned: {current.role_assigned}",
        f"Timezone Confirmed: {current.timezone_confirmed}",
        f"Availability Configured: {current.availability_configured}",
        f"Help Center Viewed: {current.help_center_viewed}",
        f"Onboarded: {current.onboarded}",
    ]
    return Screen(text="\n".join(lines), reply_markup=team_qa_detail_menu(target.id))


def render_notification_digest_mode_page(session: Session, user: User | None = None, *, generate: bool = False) -> Screen:
    if generate:
        create_notification_digest(session, actor=user, user=user, purpose="operations")
    digests = list_notification_digests(session)
    lines = [
        "Notification Digest Mode",
        "",
        "Low-priority updates are bundled here so the team is not flooded with alerts.",
        "Critical alerts still route immediately.",
        "",
    ]
    if not digests:
        lines.append("No digests yet.")
    for digest in digests[:10]:
        lines.append(f"{digest.id}. {digest.title} | {digest.status} | {digest.item_count} update(s)")
        lines.append(f"   {digest.summary}")
    return Screen(text="\n".join(lines), reply_markup=notification_digest_mode_menu())


def render_scheduled_automations_page(session: Session, user: User | None = None, *, run_due: bool = False) -> Screen:
    results = run_due_scheduled_automations(session, actor=user) if run_due else []
    summary = scheduled_automation_summary(session)
    lines = [
        "Scheduled Automations",
        "",
        "Only low-risk automations auto-run initially.",
        "High-risk work still requires review and approval.",
        "",
        f"Schedules: {summary['total']}",
        f"Active Schedules: {summary['active']}",
        f"Successful Runs: {summary['successful']}",
        f"Failed Runs: {summary['failed']}",
        f"Skipped Runs: {summary['skipped']}",
    ]
    if run_due:
        lines.extend(["", "Run Results:"])
        if not results:
            lines.append("- No due safe automations.")
        for result in results:
            lines.append(f"- {result.rule_name}: {result.status} ({result.reason})")
    return Screen(text="\n".join(lines), reply_markup=scheduled_automations_menu())


def render_daily_autopilot_page(session: Session, user: User | None = None) -> Screen:
    summary = daily_autopilot_summary(session, user)
    next_run = summary["next_run"].isoformat() if summary["next_run"] else "Disabled"
    last_run = summary["last_run"].isoformat() if summary["last_run"] else "Not run yet"
    lines = [
        "Daily Autopilot",
        "",
        f"Status: {'Enabled' if summary['enabled'] else 'Disabled'}",
        f"Owner Timezone: {summary['timezone']}",
        f"Run Time: {summary['run_time_local']}",
        f"Next Run: {next_run}",
        f"Last Run: {last_run}",
        f"Last Result: {summary['last_result']}",
        "",
        "Included Actions:",
    ]
    lines.extend(f"- {action}" for action in summary["included_actions"])
    lines.extend(
        [
            "",
            "Only safe daily checks are enabled here. High-risk automations still require explicit owner approval.",
        ]
    )
    return Screen("\n".join(lines), daily_autopilot_menu(summary["enabled"]))


def render_owner_daily_checklist_page(session: Session, user: User) -> Screen:
    checklist = owner_daily_checklist(session, user)
    next_run = checklist["daily_autopilot_next_run"]
    lines = [
        "Owner Daily Checklist",
        "",
        f"Readiness Score: {checklist['readiness_score']}%",
        f"Owner Approvals Needed: {checklist['approvals_needed']}",
        f"Critical Incidents: {checklist['critical_incidents']}",
        f"Accounts Needing Setup: {checklist['accounts_needing_setup']}",
        f"Opportunities Needing Assignment: {checklist['opportunities_needing_assignment']}",
        f"Follow-Ups Due: {checklist['followups_due']}",
        f"Daily Autopilot: {'Enabled' if checklist['daily_autopilot_enabled'] else 'Disabled'}",
        f"Next Daily Run: {next_run.isoformat() if next_run else 'Disabled'}",
        f"Last Daily Result: {checklist['daily_autopilot_last_result']}",
        "",
        "Top Blockers:",
    ]
    if not checklist["top_blockers"]:
        lines.append("- None right now.")
    for blocker in checklist["top_blockers"]:
        lines.append(f"- {blocker['title']}")
    return Screen("\n".join(lines), owner_daily_checklist_menu())


def render_team_onboarding_activation_page(session: Session) -> Screen:
    data = team_onboarding_activation(session)
    pending = data["pending_users"]
    lines = [
        "Team Onboarding Activation",
        "",
        f"Active Team Members: {data['active_team_count']}",
        f"Pending Users: {len(pending)}",
        f"Users Missing Timezone/Country: {data['missing_localization']}",
        "",
    ]
    if data["active_team_count"] == 0:
        lines.extend(
            [
                "No real team users are active yet.",
                "",
                "Invite packet:",
            ]
        )
        for role, message in data["invite_packet"].items():
            first_line = message.splitlines()[0]
            lines.append(f"- {role.title()}: {first_line}")
        lines.extend(
            [
                "",
                "Owner copy path: send the role-specific invite text from docs/team_invite_packet.md or Help Center. Team members press /start, finish language/timezone, then wait for approval.",
            ]
        )
    elif pending:
        lines.append("Pending users are waiting for approval. Approve only known team members, then assign a role immediately.")
        for user_item in pending[:8]:
            lines.append(f"- {user_item.display_name or user_item.username or 'Telegram user'}")
    else:
        lines.append("Team activation is started. Keep checking timezone, availability, and assigned work.")
    return Screen("\n".join(lines), team_onboarding_activation_menu(bool(pending)))


def render_fortuna_action_log_page(session: Session, window: str = "today") -> Screen:
    log = autonomous_action_log(session, window=window)
    lines = [
        "What Fortuna Did",
        "",
        f"Window: {log['window']}",
        f"Actions Created: {log['actions_created']}",
        f"Tasks Created: {log['tasks_created']}",
        f"Recommendations Created: {log['recommendations_created']}",
        f"Follow-Ups Created: {log['followups_created']}",
        f"Automations Run: {log['automations_run']}",
        f"Errors Detected: {log['errors_detected']}",
        "",
        "Recent Actions:",
    ]
    if not log["recent_actions"]:
        lines.append("- No autonomous actions in this window.")
    for action in log["recent_actions"][:8]:
        lines.append(f"- {action['status']}: {action['type']}")
        if action.get("summary"):
            lines.append(f"  {action['summary']}")
    return Screen("\n".join(lines), fortuna_action_log_menu(window))


def render_coo_dashboard_page(session: Session, user: User | None = None) -> Screen:
    priorities = top_priorities(session, actor=user, limit=5)
    messages = fortuna_messages(session, actor=user)
    lines = [
        "Fortuna COO Layer",
        "",
        "Fortuna is watching readiness, assignments, risks, and follow-ups so work gets routed instead of discovered late.",
        "",
        "What Fortuna Noticed:",
    ]
    lines.extend(f"- {message}" for message in messages)
    lines.append("")
    lines.append("Top Priorities:")
    if priorities:
        for item in priorities[:5]:
            lines.append(f"- {item.score}/100: {item.explanation.split('.')[0]} -> {item.recommended_owner}")
    else:
        lines.append("- No open priorities right now.")
    return Screen("\n".join(lines), coo_dashboard_menu())


def render_today_top5_page(session: Session, user: User | None = None) -> Screen:
    actions = todays_top_5_actions(session, actor=user)
    lines = [
        "Today's Top 5 Actions",
        "",
        "These are the highest-impact actions Fortuna recommends right now.",
        "",
    ]
    buttons: list[tuple[str, str]] = []
    if not actions:
        lines.append("No priority actions right now. Run a COO scan after new setup or team changes.")
    for index, action in enumerate(actions, start=1):
        lines.append(f"{index}. {action.title}")
        lines.append(f"   Owner: {action.owner} | Score: {action.score}/100")
        lines.append(f"   Why: {action.explanation}")
        buttons.append((f"Fix {index}: {action.title[:28]}", action.action_page))
    return Screen("\n".join(lines), top5_actions_menu(buttons))


def render_readiness_v2_page(session: Session) -> Screen:
    readiness = readiness_score_v2(session)
    lines = [
        "Readiness Score V2",
        "",
        f"Agency Readiness: {readiness['readiness_score']}%",
        "",
        "Why the score is low:",
    ]
    if readiness["why_low"]:
        lines.extend(f"- {reason}" for reason in readiness["why_low"])
    else:
        lines.append("- Every readiness section is complete.")
    lines.append("")
    lines.append("Fastest path to improve:")
    buttons: list[tuple[str, str]] = []
    if readiness["fastest_path"]:
        for item in readiness["fastest_path"]:
            lines.append(f"- +{item['estimated_gain']}: {item['title']}")
            if item.get("action_page"):
                buttons.append((f"+{item['estimated_gain']} {item['title'][:24]}", item["action_page"]))
    else:
        lines.append("- Nothing urgent. Keep running the daily cycle.")
    lines.append("")
    lines.append("Biggest blockers:")
    for item in readiness["biggest_blockers"][:5]:
        lines.append(f"- {item['title']} ({item['severity']})")
    return Screen("\n".join(lines), readiness_v2_menu(buttons))


def _queue_lines(title: str, items: list[dict], *, empty: str) -> list[str]:
    lines = [title]
    if not items:
        lines.append(f"- {empty}")
    for item in items[:5]:
        label = item.get("title") or item.get("name") or f"Item {item.get('id', '')}"
        extra = item.get("owner") or item.get("priority") or item.get("type")
        lines.append(f"- {label}{f' ({extra})' if extra else ''}")
    return lines


def render_manager_queue_page(session: Session, user: User | None = None) -> Screen:
    queue = manager_work_queue(session, actor=user)
    lines = [
        "Manager Queue",
        "",
        "This is the work that needs assignment, approval, attention, or escalation.",
        "",
    ]
    lines.extend(_queue_lines("Needs Assignment:", queue["needs_assignment"], empty="Nothing unassigned."))
    lines.append("")
    lines.extend(_queue_lines("Needs Approval:", queue["needs_approval"], empty="No approvals waiting."))
    lines.append("")
    lines.extend(_queue_lines("Needs Attention:", queue["needs_attention"], empty="No manager/admin priorities."))
    lines.append("")
    lines.extend(_queue_lines("Overdue:", queue["overdue"], empty="No overdue work."))
    return Screen("\n".join(lines), manager_queue_menu())


def render_my_work_page(session: Session, user: User) -> Screen:
    queue = chatter_work_queue(session, user)
    lines = [
        "My Work",
        "",
        "No clutter. These are the items waiting on you.",
        "",
        f"Due Today: {len(queue['today'])}",
        f"Priority Tasks: {len(queue['priority'])}",
        f"Due Soon: {len(queue['due_soon'])}",
        f"Waiting On Me: {len(queue['waiting_on_me'])}",
        f"Opportunities: {len(queue['opportunities'])}",
        "",
        "Next Items:",
    ]
    next_items = [task.title for task in queue["today"][:3]] + [opportunity.title for opportunity in queue["opportunities"][:3]]
    if next_items:
        lines.extend(f"- {item}" for item in next_items[:5])
    else:
        lines.append("- Nothing assigned right now. Check with your manager if you expected work.")
    return Screen("\n".join(lines), my_work_menu())


def render_coo_briefing_page(session: Session, user: User | None = None) -> Screen:
    briefing = coo_briefing(session, actor=user)
    lines = [
        "Fortuna COO Briefing",
        "",
        f"Readiness: {briefing['readiness_score']}%",
        "",
        "What changed?",
    ]
    lines.extend(f"- {item}" for item in briefing["what_changed"][:5])
    lines.append("")
    lines.append("What needs attention?")
    lines.extend(f"- {item}" for item in briefing["needs_attention"][:5]) if briefing["needs_attention"] else lines.append("- No urgent attention items.")
    lines.append("")
    lines.append("What is blocked?")
    lines.extend(f"- {item}" for item in briefing["blocked"][:5]) if briefing["blocked"] else lines.append("- No setup blockers.")
    lines.append("")
    lines.append("What should happen next?")
    lines.extend(f"- {item}" for item in briefing["next_actions"][:5]) if briefing["next_actions"] else lines.append("- Run a COO scan after new changes.")
    lines.append("")
    lines.append("Delegation:")
    lines.extend(f"- {item}" for item in briefing["delegate"][:3]) if briefing["delegate"] else lines.append("- Team load looks balanced enough for now.")
    return Screen("\n".join(lines), coo_briefing_menu())


def render_load_balancer_page(session: Session) -> Screen:
    load = team_load_balancer(session)
    lines = [
        "Team Load Balancer",
        "",
        "Fortuna only recommends reassignment here. It does not move work automatically.",
        "",
        "Overloaded:",
    ]
    if load["overloaded"]:
        for row in load["overloaded"][:5]:
            lines.append(f"- {row['name']}: score {row['workload_score']} ({row['status']})")
    else:
        lines.append("- No overloaded users detected.")
    lines.append("")
    lines.append("Idle / Available:")
    if load["idle"]:
        for row in load["idle"][:5]:
            lines.append(f"- {row['name']}: availability {row['availability']}")
    else:
        lines.append("- No idle on-shift users detected.")
    lines.append("")
    lines.append("Recommendations:")
    lines.extend(f"- {item}" for item in load["recommendations"]) if load["recommendations"] else lines.append("- No reassignment recommendation.")
    return Screen("\n".join(lines), page_menu(back_to="coo"))


def render_executive_mode_page(session: Session, user: User | None = None) -> Screen:
    summary = executive_mode_summary(session, actor=user)
    lines = [
        "Fortuna HQ",
        "",
        f"Agency Health: {summary['agency_health']}",
        f"Readiness: {summary['readiness_score']}%",
        f"Critical Issues: {summary['critical_issues']}",
        f"Open Recommendations: {summary['open_recommendations']}",
        f"Failed Automations: {summary['failed_automations']}",
        "",
        "Top Priorities:",
    ]
    if summary["top_priorities"]:
        for item in summary["top_priorities"][:5]:
            lines.append(f"- {item.score}/100: {item.explanation.split('.')[0]}")
    else:
        lines.append("- No open priorities.")
    lines.append("")
    lines.append("What Fortuna Recommends:")
    lines.extend(f"- {message}" for message in summary["messages"][:5])
    return Screen("\n".join(lines), executive_mode_menu())


def render_page(page: str, session: Session | None = None, user: User | None = None) -> Screen:
    if page == "structure":
        return render_structure_map_page()
    if page == "coo" and session is not None:
        return render_coo_dashboard_page(session, user)
    if page == "coo:top5" and session is not None:
        return render_today_top5_page(session, user)
    if page == "coo:readiness" and session is not None:
        return render_readiness_v2_page(session)
    if page == "coo:briefing" and session is not None:
        return render_coo_briefing_page(session, user)
    if page == "coo:load" and session is not None:
        return render_load_balancer_page(session)
    if page == "executive_mode" and session is not None:
        return render_executive_mode_page(session, user)
    if page == "manager_queue" and session is not None:
        return render_manager_queue_page(session, user)
    if page == "my_work" and session is not None and user is not None:
        return render_my_work_page(session, user)
    if page == "owner_daily_checklist" and session is not None and user is not None:
        return render_owner_daily_checklist_page(session, user)
    if page == "team_onboarding_activation" and session is not None:
        return render_team_onboarding_activation_page(session)
    if page.startswith("fortuna_action_log") and session is not None:
        parts = page.split(":")
        window = parts[1] if len(parts) > 1 else "today"
        return render_fortuna_action_log_page(session, window)
    if page == "agency_activation" and session is not None:
        return render_agency_activation_page(session)
    if page.startswith("agency_activation:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 4 and parts[1] == "blocker":
            section = parts[2]
            index = int(parts[3]) if parts[3].isdigit() else 0
            explain = len(parts) >= 5 and parts[4] == "explain"
            return render_activation_blocker_detail_page(session, section, index, explain=explain)
        if len(parts) >= 2 and parts[1] == "accounts":
            return render_account_setup_state_page(session)
        section = parts[1] if len(parts) >= 2 else "models"
        return render_activation_section_page(session, section)
    if page == "setup:wizard" and session is not None:
        return render_setup_wizard_page(session, user)
    if page == "setup:wizard:model":
        return render_setup_model_prompt_page()
    if page == "setup:wizard:accounts" and session is not None:
        return render_setup_accounts_page(session, user)
    if page.startswith("setup:wizard:accounts:platform:") and session is not None:
        return render_setup_account_input_page(session, user, page.split(":")[-1])
    if page == "setup:wizard:team" and session is not None:
        return render_setup_team_page(session, user)
    if page.startswith("setup:wizard:team:assign:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 5:
            return render_setup_team_page(session, user, parts[4])
    if page == "setup:wizard:creators" and session is not None:
        return render_setup_creators_page(session, user)
    if page == "setup:wizard:opportunities" and session is not None:
        return render_setup_opportunities_page(session, user)
    if page in {"setup:wizard:summary", "setup:wizard:finish"} and session is not None:
        return render_setup_summary_page(session, user)
    if page == "first_day_plan" and session is not None and user is not None:
        return render_first_day_plan_page(session, user)
    if page == "manager_qa" and session is not None:
        return render_manager_setup_qa_page(session)
    if page.startswith("demo"):
        return render_demo_seed_page()
    if page == "daily_experience" and session is not None and user is not None:
        return render_daily_experience_page(session, user)
    if page == "performance" and session is not None and user is not None:
        return render_performance_page(session, user)
    if page == "help":
        return render_help_center_page(user)
    if page.startswith("help:"):
        return render_help_topic_page(page.split(":", 1)[1], user)
    if page == "help_copilot" and session is not None:
        return render_help_copilot_page(session, user)
    if page.startswith("help_copilot:") and session is not None:
        return render_help_copilot_page(session, user, question=page.split(":", 1)[1])
    if page == "chatter_workspace" and session is not None and user is not None:
        return render_chatter_workspace_page(session, user)
    if page == "my_models" and session is not None and user is not None:
        return render_my_models_page(session, user)
    if page == "my_accounts" and session is not None and user is not None:
        return render_my_accounts_page(session, user)
    if page == "my_opportunities" and session is not None and user is not None:
        return render_my_opportunities_page(session, user)
    if page == "uploads":
        return render_uploads_placeholder_page()
    if page == "client_dashboard" and session is not None and user is not None:
        return render_client_dashboard_page(session, user)
    if page == "my_reports" and session is not None and user is not None:
        return render_my_reports_page(session, user)
    if page == "my_team" and session is not None and user is not None:
        return render_my_team_page(session, user)
    if page == "team_qa" and session is not None:
        return render_team_qa_page(session)
    if page == "team_activation" and session is not None:
        return render_team_activation_page(session)
    if page.startswith("team_qa:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            return render_team_qa_detail_page(session, int(parts[1]))
    if page == "notification_digest" and session is not None:
        return render_notification_digest_mode_page(session, user=user)
    if page == "notification_digest:generate" and session is not None:
        return render_notification_digest_mode_page(session, user=user, generate=True)
    if page == "automations:scheduled" and session is not None:
        return render_scheduled_automations_page(session, user=user)
    if page == "automations:scheduled:run_due" and session is not None:
        return render_scheduled_automations_page(session, user=user, run_due=True)
    if page == "automations:daily_autopilot" and session is not None:
        return render_daily_autopilot_page(session, user=user)
    if page == "proxies":
        return render_proxies_home()
    if page == "proxies:list" and session is not None:
        return render_proxy_list_page(session)
    if page == "proxies:entry_check" and session is not None:
        return render_proxy_entry_check_page(session)
    if page == "proxies:olympix":
        return render_olympix_proxy_wizard_page()
    if page == "proxies:missing" and session is not None:
        return render_accounts_missing_proxy_page(session)
    if page == "proxies:simulation" and session is not None:
        return render_proxy_simulation_page(session)
    if page == "proxies:dashboard" and session is not None:
        return render_infrastructure_dashboard_page(session)
    if page.startswith("proxy:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            proxy_id = int(parts[1])
            if len(parts) == 2:
                return render_proxy_detail_page(session, proxy_id)
            if parts[2] == "assign":
                return render_proxy_assign_account_page(session, proxy_id)
            if parts[2] == "remove":
                return render_proxy_remove_account_page(session, proxy_id)
            if parts[2] == "accounts":
                return render_proxy_assigned_accounts_page(session, proxy_id)
            if parts[2] == "audit":
                return render_proxy_audit_page(session, proxy_id)
            return render_proxy_detail_page(session, proxy_id)
    if page == "accounts":
        return render_accounts_home()
    if page == "accounts:list" and session is not None:
        return render_account_list_page(session)
    if page == "accounts:add" and session is not None:
        return render_account_model_choice_page(session)
    if page.startswith("accounts:add:model:") and session is not None:
        parts = page.split(":")
        if len(parts) == 4 and parts[3].isdigit():
            return render_account_platform_choice_page(session, int(parts[3]))
        if len(parts) >= 6 and parts[3].isdigit() and parts[4] == "platform":
            return render_account_input_page(session, int(parts[3]), parts[5])
    if page == "accounts:by_model" and session is not None:
        return render_accounts_by_model_page(session)
    if page.startswith("accounts:model:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 3 and parts[2].isdigit():
            model_brand = session.get(ModelBrand, int(parts[2]))
            title = f"Accounts for {model_brand.display_name}" if model_brand else "Accounts"
            return render_account_list_page(
                session,
                accounts=accounts_for_model(session, int(parts[2])),
                title=title,
                back_to="accounts:by_model",
            )
    if page == "accounts:by_platform":
        return render_accounts_by_platform_page()
    if page.startswith("accounts:platform:") and session is not None:
        platform = page.split(":")[2]
        filtered = [account for account in list_accounts(session) if account.platform == platform]
        return render_account_list_page(
            session,
            accounts=filtered,
            title=f"{platform_label(platform)} Accounts",
            back_to="accounts:by_platform",
        )
    if page == "accounts:attention" and session is not None:
        return render_account_list_page(
            session,
            accounts=accounts_needing_attention(session),
            title="Accounts Needing Attention",
            back_to="accounts",
        )
    if page.startswith("account:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            account_id = int(parts[1])
            if len(parts) == 2:
                return render_account_detail_page(session, account_id)
            if parts[2] == "audit":
                return render_account_audit_page(session, account_id)
            if parts[2] == "auth" and len(parts) >= 4 and parts[3] == "enter":
                return render_account_auth_prompt_page(session, account_id)
            if parts[2] == "proxy" and len(parts) >= 4 and parts[3] == "assign":
                return render_account_proxy_assignment_page(session, account_id)
            return render_account_detail_page(session, account_id)
    if page == "models":
        return render_models_home()
    if page in {"models:list", "models:search"} and session is not None:
        return render_model_list_page(session)
    if page == "models:dashboard" and session is not None:
        return render_model_dashboard_page(session)
    if page.startswith("model:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            model_id = int(parts[1])
            if len(parts) == 2:
                return render_model_detail_page(session, model_id)
            if parts[2] == "edit":
                if len(parts) >= 4:
                    return render_model_field_edit_page(session, model_id, parts[3])
                return render_model_edit_page(session, model_id)
            if parts[2] == "complete":
                return render_model_completion_page(session, model_id)
            if parts[2] == "team":
                if len(parts) >= 5 and parts[3] == "assign":
                    return render_model_assignment_page(session, model_id, parts[4])
                if len(parts) >= 4 and parts[3] == "remove":
                    return render_model_remove_assignment_page(session, model_id)
                return render_model_team_page(session, model_id)
            if parts[2] == "audit":
                return render_model_audit_page(session, model_id)
            if parts[2] == "accounts":
                model_brand = session.get(ModelBrand, model_id)
                title = f"Accounts for {model_brand.display_name}" if model_brand else "Accounts"
                return render_account_list_page(
                    session,
                    accounts=accounts_for_model(session, model_id),
                    title=title,
                    back_to=f"model:{model_id}",
                )
            if parts[2] == "creators":
                return render_model_creators_page(session, model_id)
            if parts[2] == "opportunities":
                return render_model_opportunities_page(session, model_id)
            if parts[2] == "tasks":
                model_brand = session.get(ModelBrand, model_id)
                title = f"Tasks for {model_brand.display_name}" if model_brand else "Tasks"
                return render_task_list_page(
                    session,
                    tasks=tasks_for_model(session, model_id),
                    title=title,
                    back_to=f"model:{model_id}",
                )
            if parts[2] == "incidents":
                model_brand = session.get(ModelBrand, model_id)
                title = f"Incidents for {model_brand.display_name}" if model_brand else "Incidents"
                return render_incident_list_page(
                    session,
                    incidents=incidents_for_model(session, model_id),
                    title=title,
                    back_to=f"model:{model_id}",
                )
    if page == "tasks":
        return render_tasks_home()
    if page == "tasks:list" and session is not None:
        return render_task_list_page(session)
    if page == "tasks:my" and session is not None and user is not None:
        return render_task_list_page(session, tasks=my_tasks(session, user), title="My Tasks", back_to="tasks")
    if page == "tasks:assigned" and session is not None:
        return render_task_list_page(
            session,
            tasks=assigned_tasks(session),
            title="Assigned Tasks",
            back_to="tasks",
        )
    if page == "tasks:team" and session is not None:
        return render_task_list_page(
            session,
            tasks=assigned_tasks(session),
            title="Team Tasks",
            back_to="tasks",
        )
    if page == "tasks:overdue" and session is not None:
        return render_task_list_page(session, tasks=overdue_tasks(session), title="Overdue Tasks", back_to="tasks")
    if page == "tasks:blocked" and session is not None:
        return render_task_list_page(session, tasks=blocked_tasks(session), title="Blocked Tasks", back_to="tasks")
    if page == "tasks:escalated" and session is not None:
        escalated = [task for task in list_tasks(session) if task.escalation_level > 0]
        return render_task_list_page(session, tasks=escalated, title="Escalated Tasks", back_to="tasks")
    if page.startswith("task:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            task_id = int(parts[1])
            if len(parts) >= 3 and parts[2] == "assign":
                return render_task_assignment_page(session, task_id)
            return render_task_detail_page(session, task_id)
    if page == "incidents":
        return render_incidents_home()
    if page == "incidents:list" and session is not None:
        return render_incident_list_page(session)
    if page == "incidents:open" and session is not None:
        return render_incident_list_page(
            session,
            incidents=open_incidents(session),
            title="Open Incidents",
            back_to="incidents",
        )
    if page == "incidents:my" and session is not None and user is not None:
        return render_incident_list_page(
            session,
            incidents=my_incidents(session, user),
            title="My Incidents",
            back_to="incidents",
        )
    if page == "incidents:critical" and session is not None:
        return render_incident_list_page(
            session,
            incidents=critical_incidents(session),
            title="Critical Incidents",
            back_to="incidents",
        )
    if page.startswith("incident:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            incident_id = int(parts[1])
            if len(parts) >= 3 and parts[2] == "assign":
                return render_incident_assignment_page(session, incident_id)
            if len(parts) >= 3 and parts[2] == "timeline":
                return render_incident_timeline_page(session, incident_id)
            return render_incident_detail_page(session, incident_id)
    if page == "reports":
        return render_reports_home()
    if page in {"reports:daily", "reports:daily:generate"} and session is not None:
        return render_daily_briefing_page(session, user=user)
    if page == "reports:daily:latest" and session is not None:
        return render_daily_briefing_page(session, user=user, mode="latest")
    if page in {"reports:daily:send_owner", "reports:daily:send_ops"} and session is not None:
        target = "owner" if page.endswith("send_owner") else "operations"
        request_briefing_send(session, actor=user, target=target)
        return render_daily_briefing_page(session, user=user, mode="latest")
    if page == "reports:accountability" and session is not None:
        return render_accountability_page(session, user=user)
    if page in {"reports:intelligence", "reports:intelligence:generate"} and session is not None:
        return render_intelligence_briefing_page(session, user=user)
    if page == "reports:intelligence:latest" and session is not None:
        return render_intelligence_briefing_page(session, user=user, mode="latest")
    if page == "reports:intelligence:send_hq" and session is not None:
        return render_intelligence_briefing_page(session, user=user, mode="send_hq")
    if page == "reports:workload" and session is not None:
        return render_workload_intelligence_page(session, user=user)
    if page == "reports:digest" and session is not None:
        return render_daily_digest_page(session, user=user)
    if page == "reports:digest:generate" and session is not None:
        return render_daily_digest_page(session, user=user, mode="generate")
    if page == "reports:digest:preview" and session is not None:
        return render_daily_digest_page(session, user=user, mode="preview")
    if page == "reports:digest:send_hq" and session is not None:
        return render_daily_digest_page(session, user=user, mode="send", purpose="owner")
    if page == "reports:digest:send_ops" and session is not None:
        return render_daily_digest_page(session, user=user, mode="send", purpose="operations")
    if page == "reports:digest:schedule" and session is not None:
        return render_daily_digest_page(session, user=user, mode="schedule")
    if page == "reports:digest:history" and session is not None:
        return render_daily_digest_page(session, user=user, mode="history")
    if page == "reports:executive" and session is not None:
        return render_executive_dashboard_page(session, user=user)
    if page == "reports:executive:recommendations" and session is not None:
        return render_recommendations_page(session, user=user)
    if page.startswith("recommendation:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            if len(parts) >= 3 and parts[2] == "why":
                return render_recommendation_why_page(session, int(parts[1]))
            return render_recommendation_detail_page(session, int(parts[1]))
    if page == "reports:operations" and session is not None:
        return render_operations_dashboard_page(session, user=user)
    if page == "reports:manager" and session is not None:
        return render_manager_command_page(session, user=user)
    if page == "reports:chatter" and session is not None:
        return render_chatter_dashboard_page(session, user=user)
    if page == "reports:va" and session is not None:
        return render_va_dashboard_page(session, user=user)
    if page == "intelligence" and session is not None:
        return render_intelligence_home(session)
    if page == "intelligence:runs" and session is not None:
        return render_intelligence_runs_page(session)
    if page.startswith("intelligence:run_detail:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 3 and parts[2].isdigit():
            return render_intelligence_run_detail_page(session, int(parts[2]))
    if page == "intelligence:signals" and session is not None:
        return render_intelligence_signals_page(session)
    if page == "intelligence:patterns" and session is not None:
        return render_intelligence_patterns_page(session)
    if page == "intelligence:trends" and session is not None:
        return render_intelligence_trends_page(session)
    if page == "intelligence:learning" and session is not None:
        return render_learning_center_page(session)
    if page == "intelligence:learning:playbooks" and session is not None:
        return render_playbooks_page(session)
    if page == "intelligence:learning:recommended" and session is not None:
        return render_playbooks_page(session, recommended=True)
    if page == "intelligence:learning:outcome_memory" and session is not None:
        return render_outcome_memory_page(session)
    if page == "intelligence:learning:confidence" and session is not None:
        return render_confidence_changes_page(session)
    if page == "intelligence:learning:automation" and session is not None:
        return render_automation_learning_page(session)
    if page == "intelligence:learning:opportunity" and session is not None:
        return render_opportunity_learning_page(session)
    if page == "intelligence:learning:briefing" and session is not None:
        return render_executive_memory_briefing_page(session)
    if page.startswith("playbook:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            if len(parts) >= 3 and parts[2] == "history":
                return render_playbook_history_page(session, int(parts[1]))
            return render_playbook_detail_page(session, int(parts[1]))
    if page == "opportunities" and session is not None:
        return render_opportunities_home(session)
    if page.startswith("opportunities:creators:add") and session is not None:
        return render_creator_intake_page(session, page)
    if page.startswith("opportunities:posts:add") and session is not None:
        return render_post_intake_page(session, page)
    if page.startswith("opportunities:add") and session is not None:
        return render_opportunity_intake_page(session, page)
    if page == "opportunities:command" and session is not None:
        return render_opportunity_command_center_page(session, user=user)
    if page == "opportunities:list" and session is not None:
        return render_opportunity_list_page(session)
    if page == "opportunities:creators" and session is not None:
        return render_creator_watchlist_page(session)
    if page == "opportunities:posts" and session is not None:
        return render_post_watch_page(session)
    if page == "opportunities:posts:attention" and session is not None:
        return render_post_watch_page(session, status="attention_needed")
    if page == "opportunities:manager" and session is not None:
        return render_manager_opportunity_page(session)
    if page == "opportunities:learning" and session is not None:
        return render_opportunity_learning_v2_page(session)
    if page == "opportunities:results" and session is not None:
        return render_opportunity_results_page(session)
    if page.startswith("creator:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            if len(parts) >= 3 and parts[2] == "assign_model":
                return render_creator_model_assignment_page(session, int(parts[1]))
            if len(parts) >= 3 and parts[2] == "assign_chatter":
                return render_creator_chatter_assignment_page(session, int(parts[1]))
            if len(parts) >= 3 and parts[2] == "priority":
                return render_creator_priority_page(session, int(parts[1]))
            if len(parts) >= 3 and parts[2] == "niche":
                return Screen("Edit Niche\n\nSend the new niche in chat.", page_menu(back_to=f"creator:{parts[1]}"))
            return render_creator_watch_detail_page(session, int(parts[1]))
    if page.startswith("post:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            if len(parts) >= 3 and parts[2] == "assign_chatter":
                return render_post_chatter_assignment_page(session, int(parts[1]))
            return render_post_watch_detail_page(session, int(parts[1]))
    if page.startswith("opportunity:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            if len(parts) >= 3 and parts[2] == "assign":
                return render_opportunity_assignment_page(session, int(parts[1]))
            if len(parts) >= 3 and parts[2] == "status":
                return render_opportunity_status_page(session, int(parts[1]))
            if len(parts) >= 3 and parts[2] == "record_result":
                return render_opportunity_result_status_page(session, int(parts[1]))
            if len(parts) >= 4 and parts[2] == "result":
                return Screen(
                    f"Record Result\n\nStatus: {parts[3]}\nSend safe notes or type skip.",
                    page_menu(back_to=f"opportunity:{parts[1]}"),
                )
            if len(parts) >= 3 and parts[2] == "strategies":
                return render_opportunity_strategies_page(session, int(parts[1]))
            return render_opportunity_detail_page(session, int(parts[1]))
    if page == "users" and session is not None:
        return render_users_page(session)
    if page == "users:pending" and session is not None:
        return render_users_page(session, status_filter="pending")
    if page.startswith("user:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            if len(parts) >= 3 and parts[2] in {"assign_role", "remove_role"}:
                return render_role_assignment_page(session, int(parts[1]), parts[2])
            return render_user_detail_page(session, int(parts[1]))
    if page == "roles" and session is not None:
        return render_roles_page(session)
    if page.startswith("role:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            if len(parts) >= 3 and parts[2] in {"add_permission", "remove_permission"}:
                return render_permission_list_page(session, int(parts[1]), parts[2])
            return render_role_detail_page(session, int(parts[1]))
    if page == "permissions":
        return render_default_permissions_page()
    if page == "automations" and session is not None:
        return render_automations_home(session, user=user)
    if page == "automations":
        return render_automations_home()
    if page == "automations:rules" and session is not None:
        return render_automation_rules_page(session, user=user)
    if page == "automations:templates" and session is not None:
        return render_automation_templates_page(session, user=user)
    if page == "automations:approvals" and session is not None:
        return render_automation_approvals_page(session)
    if page == "automations:runs" and session is not None:
        return render_automation_runs_page(session)
    if page == "automations:health" and session is not None:
        return render_automation_health_page(session)
    if page.startswith("automation:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            rule_id = int(parts[1])
            if len(parts) == 2:
                return render_automation_rule_detail_page(session, rule_id)
            if parts[2] == "simulations":
                return render_automation_rule_simulations_page(session, rule_id)
            if parts[2] == "rollback":
                return render_automation_rollback_page(session, rule_id)
            if parts[2] == "runs":
                return render_automation_runs_page(session, rule_id=rule_id)
            return render_automation_rule_detail_page(session, rule_id)
    if page.startswith("approval:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            return render_automation_approval_detail_page(session, int(parts[1]))
    if page.startswith("automation_run:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            return render_automation_run_detail_page(session, int(parts[1]))
    if page.startswith("automation_step:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            return render_automation_step_detail_page(session, int(parts[1]))
    if page == "automations:simulations" and session is not None:
        return render_simulation_runs_page(session)
    if page.startswith("simulation:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            return render_simulation_run_detail_page(session, int(parts[1]))
    if page == "audit_logs" and session is not None:
        return render_audit_logs_page(session)
    if page in {"bot_status", "production_status"} and session is not None:
        return render_bot_status_page(session)
    if page == "availability" and session is not None and user is not None:
        return render_availability_page(session, user)
    if page == "availability:team" and session is not None:
        return render_team_availability_page(session)
    if page.startswith("onboarding") and session is not None and user is not None:
        parts = page.split(":")
        step = parts[2] if len(parts) >= 3 and parts[1] == "reset" else None
        return render_onboarding_page(session, user, step=step)
    if page == "notification_targets" and session is not None:
        return render_notification_targets_page(session)
    if page.startswith("notification_target:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            if len(parts) >= 3 and parts[2] == "purpose":
                return render_notification_target_purpose_page(session, int(parts[1]))
            return render_notification_target_detail_page(session, int(parts[1]))
    if page == "settings":
        return Screen(text="Settings\n\nAdministrative tools.", reply_markup=settings_menu())
    title = PAGE_TITLES.get(page, "Unknown")
    return Screen(text=f"{title}\n\nManagement tools will appear here.", reply_markup=page_menu())
