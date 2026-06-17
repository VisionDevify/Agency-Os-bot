import pytest

from app.bot.menu import MENU_ITEMS, dashboard_menu, main_menu
from app.bot.navigation import screen_for_page
from app.bot.screens import render_dashboard
from app.services.audit import AuditRecorder
from app.services.auth import USER_STATUS_PENDING, get_or_create_telegram_user, setup_owner_if_needed
from app.services.permissions import PermissionPrincipal, RoleName
from tests.utils import session_scope


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
    assert "Back" in labels
    assert "Main Menu" in labels
    assert "nav:dashboard:refresh" in callbacks
    assert "nav:tasks" in callbacks
    assert "nav:incidents" in callbacks
    assert "nav:menu" in callbacks


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

    assert recorder.events[-1]["action"] == "access.denied"
    assert recorder.events[-1]["resource_id"] == "users"
    assert "telegram_id" not in recorder.events[-1]["details"]
    assert recorder.events[-1]["details"]["telegram_id_masked"] == "hidden"


def test_dynamic_user_detail_navigation_renders_user_screen() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        pending = get_or_create_telegram_user(
            session,
            telegram_user_id=2,
            display_name="Pending Person",
            username="pending_person",
        )
        assert pending.status == USER_STATUS_PENDING
        principal = PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)

        screen = screen_for_page(f"user:{pending.id}", principal, session=session, user=owner)

        assert "User Detail" in screen.text
        assert "Pending Person" in screen.text


def test_pending_users_navigation_renders_queue() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        pending = get_or_create_telegram_user(
            session,
            telegram_user_id=3,
            display_name="Waiting Person",
            username="waiting_person",
        )
        principal = PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)

        screen = screen_for_page("users:pending", principal, session=session, user=owner)
        callbacks = callback_data(screen.reply_markup)

        assert pending.status == USER_STATUS_PENDING
        assert "Pending Users" in screen.text
        assert "Waiting Person" in screen.text
        assert f"nav:user:{pending.id}" in callbacks


def test_dynamic_admin_callbacks_do_not_crash() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        user = get_or_create_telegram_user(session, telegram_user_id=4, display_name="Callback Person")
        principal = PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)

        pages = [
            "dashboard:refresh",
            "users",
            "users:pending",
            f"user:{user.id}",
            f"user:{user.id}:assign_role",
            "roles",
            "permissions",
            "audit_logs",
        ]

        for page in pages:
            screen = screen_for_page(page, principal, session=session, user=owner)
            assert screen.text
            assert screen.reply_markup is not None
