from dataclasses import dataclass

from aiogram.types import InlineKeyboardMarkup

from app.bot.menu import dashboard_menu, main_menu, page_menu
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


def render_page(page: str) -> Screen:
    title = PAGE_TITLES.get(page, "Unknown")
    return Screen(text=f"{title}\n\nManagement tools will appear here.", reply_markup=page_menu())
