import pytest

from app.bot.menu import MENU_ITEMS, dashboard_menu, main_menu
from app.bot.navigation import screen_for_page
from app.bot.screens import render_dashboard
from app.services.audit import AuditRecorder
from app.services.permissions import PermissionPrincipal, RoleName


def callback_data(markup) -> list[str]:
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data is not None
    ]


def test_main_menu_has_required_inline_buttons() -> None:
    labels = [button.text for row in main_menu().inline_keyboard for button in row]

    assert labels == [label for label, _page in MENU_ITEMS]


def test_dashboard_has_refresh_tasks_and_incidents_buttons() -> None:
    screen = render_dashboard()
    callbacks = callback_data(screen.reply_markup)
    labels = [button.text for row in dashboard_menu().inline_keyboard for button in row]

    assert "Refresh" in labels
    assert "View Tasks" in labels
    assert "View Incidents" in labels
    assert "nav:dashboard:refresh" in callbacks
    assert "nav:tasks" in callbacks
    assert "nav:incidents" in callbacks


def test_page_navigation_includes_back_and_main_menu() -> None:
    recorder = AuditRecorder()
    principal = PermissionPrincipal(telegram_id=1, role=RoleName.ADMIN)

    screen = screen_for_page("users", principal, recorder)
    callbacks = callback_data(screen.reply_markup)

    assert "Users" in screen.text
    assert "nav:menu" in callbacks


def test_restricted_navigation_records_audit_event() -> None:
    recorder = AuditRecorder()
    principal = PermissionPrincipal(telegram_id=2, role=RoleName.VIEWER)

    with pytest.raises(PermissionError):
        screen_for_page("users", principal, recorder)

    assert recorder.events[-1]["action"] == "restricted_page.accessed"
    assert recorder.events[-1]["resource_id"] == "users"
