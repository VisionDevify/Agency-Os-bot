from dataclasses import dataclass

from aiogram.types import InlineKeyboardMarkup
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.bot.menu import dashboard_menu, main_menu, page_menu, settings_menu
from app.models.audit import AuditLog
from app.models.permissions import Role
from app.models.user import User
from app.services.dashboard import DashboardStats, placeholder_dashboard_stats


@dataclass(frozen=True)
class Screen:
    text: str
    reply_markup: InlineKeyboardMarkup


PAGE_TITLES: dict[str, str] = {
    "users": "Users",
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


def render_dashboard(stats: DashboardStats | None = None) -> Screen:
    current = stats or placeholder_dashboard_stats()
    text = "\n".join(
        [
            "Dashboard",
            "",
            f"Total Users: {current.total_users}",
            f"Active Users: {current.active_users}",
            f"Accounts: {current.accounts}",
            f"Healthy Proxies: {current.healthy_proxies}",
            f"Open Tasks: {current.open_tasks}",
            f"Open Incidents: {current.open_incidents}",
        ]
    )
    return Screen(text=text, reply_markup=dashboard_menu())


def render_users_page(session: Session) -> Screen:
    users = session.scalars(
        select(User).options(selectinload(User.roles)).order_by(User.id).limit(10)
    ).all()
    lines = ["Users", ""]
    if not users:
        lines.append("No users yet.")
    for user in users:
        role_names = ", ".join(role.name for role in user.roles) or "No roles"
        username = f"@{user.username}" if user.username else f"telegram:{user.telegram_id}"
        lines.append(f"{user.id}. {username}")
        lines.append(f"   Status: {user.status} | Roles: {role_names}")
    lines.extend(["", "Disable user and assign role flows are ready for Sprint 3 actions."])
    return Screen(text="\n".join(lines), reply_markup=page_menu())


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
        text="Access pending. Contact an admin to activate your account.",
        reply_markup=main_menu(),
    )


def render_disabled() -> Screen:
    return Screen(text="Your access is disabled. Contact an admin.", reply_markup=main_menu())


def render_page(page: str, session: Session | None = None) -> Screen:
    if page == "users" and session is not None:
        return render_users_page(session)
    if page == "audit_logs" and session is not None:
        return render_audit_logs_page(session)
    if page == "settings":
        return Screen(text="Settings\n\nAdministrative tools.", reply_markup=settings_menu())
    title = PAGE_TITLES.get(page, "Unknown")
    return Screen(text=f"{title}\n\nManagement tools will appear here.", reply_markup=page_menu())
