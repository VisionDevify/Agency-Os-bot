from dataclasses import dataclass

from aiogram.types import InlineKeyboardMarkup
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.bot.menu import (
    account_detail_menu,
    account_list_menu,
    account_model_choice_menu,
    account_platform_menu,
    account_proxy_choice_menu,
    accounts_menu,
    automations_menu,
    availability_menu,
    briefing_menu,
    bot_status_menu,
    dashboard_menu,
    daily_digest_menu,
    executive_dashboard_menu,
    incident_detail_menu,
    incident_list_menu,
    incident_user_choice_menu,
    incidents_menu,
    intelligence_briefing_menu,
    intelligence_menu,
    intelligence_run_menu,
    main_menu,
    manager_command_menu,
    model_detail_menu,
    model_edit_menu,
    model_list_menu,
    model_member_choice_menu,
    model_team_menu,
    models_menu,
    notification_target_detail_menu,
    notification_target_purpose_menu,
    notification_targets_menu,
    onboarding_country_menu,
    onboarding_language_menu,
    onboarding_pending_menu,
    onboarding_time_format_menu,
    onboarding_timezone_menu,
    operations_dashboard_menu,
    opportunities_menu,
    opportunity_detail_menu,
    page_menu,
    platform_filter_menu,
    permission_choice_menu,
    proxies_menu,
    proxy_account_choice_menu,
    proxy_detail_menu,
    proxy_list_menu,
    reports_menu,
    recommendation_detail_menu,
    recommendations_menu,
    role_choice_menu,
    role_detail_menu,
    roles_menu,
    settings_menu,
    simulation_run_detail_menu,
    simulation_runs_menu,
    task_detail_menu,
    task_list_menu,
    task_user_choice_menu,
    tasks_menu,
    user_detail_menu,
    users_menu,
)
from app.models.account import ACCOUNT_PLATFORMS, Account
from app.models.audit import AuditLog
from app.models.incident import Incident
from app.models.intelligence import ExecutiveInsight, IntelligenceRun, IntelligenceSignal, IssuePattern, TrendSnapshot, WorkloadSnapshot
from app.models.model_brand import MODEL_BRAND_RELATIONSHIP_TYPES, ModelBrand, ModelBrandMember
from app.models.opportunity import Opportunity, OpportunityResult
from app.models.permissions import Permission, Role
from app.models.proxy import Proxy
from app.models.automation import AutomationSimulationRun
from app.models.recommendation import Recommendation
from app.models.reporting import NotificationTarget
from app.models.task import Task
from app.models.user import User
from app.services.auth import DEFAULT_PERMISSION_DESCRIPTIONS
from app.services.automations import list_simulation_runs
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
from app.services.opportunities import (
    get_opportunity,
    list_opportunities,
    opportunity_results,
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


def render_main_menu() -> Screen:
    return Screen(text="Agency OS\nSelect an area.", reply_markup=main_menu())


def render_dashboard(stats: DashboardStats | None = None, session: Session | None = None) -> Screen:
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


def render_models_home() -> Screen:
    return Screen(text="Models\nCommand center.", reply_markup=models_menu())


def render_accounts_home() -> Screen:
    return Screen(text="Accounts\nSecure account management.", reply_markup=accounts_menu())


def render_proxies_home() -> Screen:
    return Screen(text="Proxy Vault\nInfrastructure intelligence.", reply_markup=proxies_menu())


def render_tasks_home() -> Screen:
    return Screen(text="Tasks\nOperational work queue.", reply_markup=tasks_menu())


def render_incidents_home() -> Screen:
    return Screen(text="Incidents\nEscalation and resolution center.", reply_markup=incidents_menu())


def render_reports_home() -> Screen:
    return Screen(text="Reports\nBriefings, dashboards, and accountability.", reply_markup=reports_menu())


def render_intelligence_home(session: Session | None = None) -> Screen:
    lines = ["Intelligence Command Center", ""]
    if session is None:
        lines.append("Signals, patterns, trends, and workload intelligence.")
    else:
        status = command_center_intelligence_status(session)
        lines.extend(
            [
                f"Status: {status['status']}",
                f"Open Signals: {status['open_signals']}",
                f"Critical Signals: {status['critical_signals']}",
                f"Active Patterns: {status['active_patterns']}",
                f"Negative Trends: {status['negative_trends']}",
                f"Overloaded Users: {status['overloaded_users']}",
                f"Open Executive Insights: {status['open_executive_insights']}",
                "",
                "Run analysis or drill into signals, patterns, trends, and workload.",
            ]
        )
    return Screen(text="\n".join(lines), reply_markup=intelligence_menu())


def render_opportunities_home(session: Session | None = None) -> Screen:
    opportunities = list_opportunities(session, limit=5) if session is not None else []
    lines = ["Opportunities", "", "Manual, human-approved opportunity intelligence foundation.", ""]
    buttons: list[tuple[str, str]] = []
    if not opportunities:
        lines.append("No opportunities yet.")
    for opportunity in opportunities:
        lines.append(f"{opportunity.id}. {opportunity.title}")
        lines.append(f"   Platform: {opportunity.platform} | Score: {opportunity.score} | Status: {opportunity.status}")
        buttons.append((f"{opportunity.id}. {opportunity.title[:36]}", f"nav:opportunity:{opportunity.id}"))
    return Screen(text="\n".join(lines), reply_markup=opportunities_menu(buttons))


def render_automations_home() -> Screen:
    lines = [
        "Automations",
        "",
        "Simulation mode is active.",
        "Preview, simulate, approve, then execute.",
    ]
    return Screen(text="\n".join(lines), reply_markup=automations_menu())


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
        lines.append("No accounts yet.")
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
        lines.append("Create a Model/Brand first.")
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
        lines.append("No models yet.")
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
        lines.append("No proxies yet.")
    for proxy in proxies[:15]:
        health = calculate_proxy_health(proxy)
        lines.append(f"{proxy.id}. {proxy.provider} {proxy.host}:{proxy.port}")
        lines.append(f"   Status: {proxy.status} | Health: {health.label} {health.score}/100")
        lines.append(f"   Target: {proxy.target_state or proxy.target_country or 'Not set'}")
        buttons.append(_proxy_button(proxy))
    return Screen(text="\n".join(lines), reply_markup=proxy_list_menu(buttons))


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
        f"Current Session: {proxy.session_suffix}",
        f"Previous Session: {proxy.previous_session_suffix or 'None'}",
        f"Rotation Count: {proxy.rotation_count}",
        f"Generated Username: {proxy.generated_username}",
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
        "Jump opens the closest related Agency OS page when available.",
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
    lines = [
        "Opportunity",
        "",
        f"Title: {opportunity.title}",
        f"Platform: {opportunity.platform}",
        f"Status: {opportunity.status}",
        f"Score: {opportunity.score}/100",
        f"Niche: {opportunity.niche or 'Not set'}",
        f"Model/Brand: {model.display_name if model else 'Unassigned'}",
        f"Assigned To: {_identity(assignee)}",
        f"URL: {opportunity.url or 'Not set'}",
        f"Reason: {opportunity.reason or 'None'}",
        f"Suggested Angle: {opportunity.suggested_angle or 'None'}",
        "",
        "Safety: posting remains manual and human-approved.",
    ]
    return Screen(text="\n".join(lines), reply_markup=opportunity_detail_menu(opportunity.id))


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
            text="Welcome to Agency OS.\n\nStep 1: Select your language.",
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
    return Screen(
        text=(
            "Access pending approval.\n\n"
            f"Language: {user.language or 'Not set'}\n"
            f"Country: {user.country or 'Not set'}\n"
            f"Timezone: {user.timezone}\n"
            f"Time Format: {user.time_format}\n\n"
            "Your profile is saved. An admin can approve access."
        ),
        reply_markup=onboarding_pending_menu(),
    )


def render_notification_targets_page(session: Session) -> Screen:
    targets = list_notification_targets(session)
    lines = ["Notification Targets", ""]
    buttons: list[tuple[str, str]] = []
    if not targets:
        lines.append("No notification targets yet.")
    for target in targets[:15]:
        status = "active" if target.is_active else "disabled"
        lines.append(f"{target.id}. {target.name}")
        lines.append(f"   Type: {target.target_type} | Purpose: {target.purpose} | Status: {status}")
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
        f"Purpose: {target.purpose}",
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
                f"Status: {model_brand.status}",
            ]
        ),
        reply_markup=model_edit_menu(model_brand.id, model_brand.status),
    )


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
    return Screen(text="\n".join(lines), reply_markup=user_detail_menu(user.id, user.status))


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


def render_page(page: str, session: Session | None = None, user: User | None = None) -> Screen:
    if page == "proxies":
        return render_proxies_home()
    if page == "proxies:list" and session is not None:
        return render_proxy_list_page(session)
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
                return render_model_edit_page(session, model_id)
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
    if page == "opportunities" and session is not None:
        return render_opportunities_home(session)
    if page == "opportunities:list" and session is not None:
        return render_opportunity_list_page(session)
    if page == "opportunities:results" and session is not None:
        return render_opportunity_results_page(session)
    if page.startswith("opportunity:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
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
    if page == "automations":
        return render_automations_home()
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
