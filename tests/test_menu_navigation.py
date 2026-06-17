import pytest

from app.bot.menu import MENU_ITEMS, dashboard_menu, main_menu
from app.bot.navigation import screen_for_page
from app.bot.screens import render_dashboard
from app.services.audit import AuditRecorder
from app.services.accounts import create_account
from app.models.audit import AuditLog
from app.services.auth import (
    USER_STATUS_ACTIVE,
    USER_STATUS_PENDING,
    assign_role_to_user,
    get_or_create_telegram_user,
    setup_owner_if_needed,
)
from app.services.model_brands import create_model_brand
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.proxies import create_proxy
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
        model = create_model_brand(session, actor=owner, display_name="Callback Model")
        account = create_account(
            session,
            model_brand=model,
            platform="instagram",
            username="callback",
            actor=owner,
        )
        proxy = create_proxy(
            session,
            actor=owner,
            provider="provider",
            host="proxy.local",
            port=8010,
            base_username="base",
            password="secret",
        )
        principal = PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)

        pages = [
            "dashboard:refresh",
            "accounts",
            "accounts:list",
            "accounts:add",
            f"accounts:add:model:{model.id}",
            f"accounts:add:model:{model.id}:platform:instagram",
            "accounts:by_model",
            f"accounts:model:{model.id}",
            "accounts:by_platform",
            "accounts:platform:instagram",
            "accounts:attention",
            f"account:{account.id}",
            f"account:{account.id}:audit",
            f"account:{account.id}:proxy:assign",
            "models",
            "models:list",
            "models:dashboard",
            "proxies",
            "proxies:list",
            "proxies:missing",
            "proxies:simulation",
            "proxies:dashboard",
            f"proxy:{proxy.id}",
            f"proxy:{proxy.id}:accounts",
            f"proxy:{proxy.id}:assign",
            f"proxy:{proxy.id}:remove",
            f"proxy:{proxy.id}:audit",
            "tasks",
            "tasks:list",
            "tasks:create",
            "tasks:my",
            "tasks:assigned",
            "tasks:overdue",
            "tasks:blocked",
            "incidents",
            "incidents:list",
            "incidents:create",
            "incidents:my",
            "incidents:critical",
            "reports",
            "reports:executive",
            "reports:operations",
            "reports:chatter",
            "reports:va",
            "reports:daily",
            "reports:accountability",
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


def test_account_auth_prompt_requires_sensitive_permission() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        model = create_model_brand(session, actor=owner, display_name="Sensitive Callback Model")
        account = create_account(
            session,
            model_brand=model,
            platform="instagram",
            username="sensitive_callback",
            actor=owner,
        )
        viewer = get_or_create_telegram_user(session, telegram_user_id=5, display_name="Viewer")
        viewer.status = USER_STATUS_ACTIVE
        viewer.is_active = True
        assign_role_to_user(session, viewer, RoleName.VIEWER)
        principal = PermissionPrincipal(telegram_id=viewer.telegram_id, role=RoleName.VIEWER)

        with pytest.raises(PermissionError):
            screen_for_page(f"account:{account.id}:auth:enter", principal, session=session, user=viewer)

        denied = session.query(AuditLog).filter_by(action="access.denied").one()
        assert denied.resource_type == "account_auth_session"
        assert denied.details["permission"] == "owner_or_admin_with_manage_accounts_or_view_credentials"
