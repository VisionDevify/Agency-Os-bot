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
    assistant_next_menu,
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
    help_feedback_menu,
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
    notification_group_pilot_menu,
    notification_target_detail_menu,
    notification_group_setup_menu,
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
    owner_advanced_home_menu,
    owner_simple_home_menu,
    page_menu,
    performance_menu,
    platform_filter_menu,
    post_watch_menu,
    post_watch_detail_menu,
    playbook_detail_menu,
    permission_choice_menu,
    proxies_advanced_menu,
    proxies_menu,
    proxy_account_choice_menu,
    proxy_detail_menu,
    proxy_entry_check_menu,
    proxy_list_menu,
    proxy_real_check_pilot_menu,
    production_observability_menu,
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
    start_here_menu,
    setup_progress_menu,
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
    today_priorities_menu,
    ui_self_test_menu,
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
    latest_delivery_attempt,
    latest_delivery_attempts_for_target,
    list_notification_targets,
    mask_target_chat_id,
    notification_group_setup_status,
)
from app.services.proxies import (
    accounts_for_proxy,
    accounts_missing_proxy,
    affected_models_for_proxy,
    calculate_proxy_health,
    infrastructure_stats,
    latest_proxy_health_check_results,
    list_proxies,
    proxy_check_mode,
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

def _readiness_label(score: int) -> str:
    if score >= 85:
        return "Ready"
    if score >= 60:
        return "Needs Attention"
    return "Blocked"

def _automation_status_line(rule: AutomationRule) -> str:
    approval = "Owner approval" if rule.requires_owner_approval else "Approval"
    return f"{rule.status} | Risk: {rule.risk_level} | {approval if rule_requires_owner_label(rule) else 'Standard review'}"

def rule_requires_owner_label(rule: AutomationRule) -> bool:
    return rule.requires_owner_approval or rule.risk_level in {"high", "critical"}

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

def _proxy_button(proxy: Proxy) -> tuple[str, str]:
    return f"{proxy.id}. {proxy.provider} {proxy.host}:{proxy.port}", f"nav:proxy:{proxy.id}"

def _mask_proxy_value(value: str | None) -> str:
    if not value:
        return "Not set"
    if len(value) <= 6:
        return "hidden"
    return f"{value[:3]}...{value[-3:]}"

def _task_button(task: Task) -> tuple[str, str]:
    return f"{task.id}. {task.title[:36]} ({task.status})", f"nav:task:{task.id}"

def _incident_button(incident: Incident) -> tuple[str, str]:
    return f"{incident.id}. {incident.title[:34]} ({incident.severity})", f"nav:incident:{incident.id}"

def _notification_purpose_label(purpose: str) -> str:
    purpose_labels = {
        "owner": "HQ",
        "operations": "Operations",
        "incidents": "Incidents",
        "automation_logs": "Automation Logs",
        "testing": "Testing Sandbox",
    }
    return purpose_labels.get(purpose, purpose)

def _model_identity(model_brand: ModelBrand) -> str:
    if model_brand.stage_name:
        return f"{model_brand.display_name} ({model_brand.stage_name})"
    return model_brand.display_name

def _member_names(members: list[User]) -> str:
    if not members:
        return "None"
    return ", ".join(user.display_name or user.username or f"User {user.id}" for user in members)

def _masked_telegram_id(value: int) -> str:
    raw = str(value)
    if len(raw) <= 4:
        return "hidden"
    return f"{raw[:2]}...{raw[-2:]}"

def _queue_lines(title: str, items: list[dict], *, empty: str) -> list[str]:
    lines = [title]
    if not items:
        lines.append(f"- {empty}")
    for item in items[:5]:
        label = item.get("title") or item.get("name") or f"Item {item.get('id', '')}"
        extra = item.get("owner") or item.get("priority") or item.get("type")
        lines.append(f"- {label}{f' ({extra})' if extra else ''}")
    return lines

__all__ = [name for name in globals() if not name.startswith("__")]
