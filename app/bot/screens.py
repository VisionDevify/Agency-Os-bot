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
    dashboard_menu,
    main_menu,
    model_detail_menu,
    model_edit_menu,
    model_list_menu,
    model_member_choice_menu,
    model_team_menu,
    models_menu,
    page_menu,
    platform_filter_menu,
    permission_choice_menu,
    proxies_menu,
    proxy_account_choice_menu,
    proxy_detail_menu,
    proxy_list_menu,
    role_choice_menu,
    role_detail_menu,
    roles_menu,
    settings_menu,
    user_detail_menu,
    users_menu,
)
from app.models.account import ACCOUNT_PLATFORMS, Account
from app.models.audit import AuditLog
from app.models.model_brand import MODEL_BRAND_RELATIONSHIP_TYPES, ModelBrand, ModelBrandMember
from app.models.permissions import Permission, Role
from app.models.proxy import Proxy
from app.models.user import User
from app.services.auth import DEFAULT_PERMISSION_DESCRIPTIONS
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
        f"Open Incidents: {current.open_incidents}",
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
        "Open Tasks: 0",
        "Open Incidents: 0",
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
        text="Access pending approval.",
        reply_markup=main_menu(),
    )


def render_disabled() -> Screen:
    return Screen(text="Account disabled.", reply_markup=main_menu())


def render_denied() -> Screen:
    return Screen(text="Access denied.", reply_markup=main_menu())


def render_page(page: str, session: Session | None = None) -> Screen:
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
            if parts[2] in {"tasks", "incidents"}:
                return render_model_placeholder_page(session, model_id, parts[2].title())
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
    if page == "audit_logs" and session is not None:
        return render_audit_logs_page(session)
    if page == "settings":
        return Screen(text="Settings\n\nAdministrative tools.", reply_markup=settings_menu())
    title = PAGE_TITLES.get(page, "Unknown")
    return Screen(text=f"{title}\n\nManagement tools will appear here.", reply_markup=page_menu())
