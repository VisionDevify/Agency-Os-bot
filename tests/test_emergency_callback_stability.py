from app.bot.navigation import screen_for_page
from app.bot.screens import render_callback_error_page, render_debug_last_error_page
from app.models.audit import AuditLog
from app.models.callback_error import CallbackErrorLog
from app.models.event_log import EventLog
from app.models.friction import FrictionItem
from app.models.recommendation import Recommendation
from app.services.auth import setup_owner_if_needed
from app.services.callbacks import latest_callback_error, log_callback_failure, run_callback_health_smoke_test
from app.services.permissions import PermissionPrincipal, RoleName
from tests.utils import session_scope


def _callbacks(markup) -> list[str]:
    return [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data is not None
    ]


def test_callback_error_fallback_screen_has_safe_recovery_buttons() -> None:
    screen = render_callback_error_page("proxies", error_id=12)
    callbacks = _callbacks(screen.reply_markup)

    assert "Fortuna encountered a problem loading this screen." in screen.text
    assert "nav:menu" in callbacks
    assert "nav:proxies" in callbacks
    assert "nav:callback_error:report:12" in callbacks


def test_callback_failure_logging_creates_diagnostics_records() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)

        error = log_callback_failure(
            session,
            actor=owner,
            callback_data="nav:proxy:1:rotate",
            page="proxy:1:rotate",
            exc=RuntimeError("provider error password=hunter2"),
            affected_screen="proxy:1:rotate",
        )

        assert error.id is not None
        assert "hunter2" not in error.error_message
        assert latest_callback_error(session).id == error.id
        assert session.query(CallbackErrorLog).count() == 1
        assert session.query(FrictionItem).count() == 1
        assert session.query(Recommendation).filter_by(recommendation_type="callback_failure").count() == 1
        assert session.query(AuditLog).filter_by(action="callback.failed", status="failed").count() >= 1
        assert session.query(EventLog).filter_by(event_type="callback.failed").count() == 1


def test_debug_last_error_screen_shows_owner_safe_summary() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        log_callback_failure(
            session,
            actor=owner,
            callback_data="nav:reports",
            page="reports",
            exc=ValueError("renderer failed"),
            affected_screen="reports",
        )

        screen = render_debug_last_error_page(session, owner)

        assert "Last Button Error" in screen.text
        assert "Callback: nav:reports" in screen.text
        assert "Exception: ValueError" in screen.text
        assert "renderer failed" not in screen.text
        assert "No secrets" in screen.text


def test_button_health_smoke_test_runs_non_destructive_renderers() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)

        report = run_callback_health_smoke_test(session, actor=owner)

        assert report.total > 0
        assert "menu" in report.working
        assert all("create" not in page for page in report.working)


def test_button_health_report_route_renders() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        principal = PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)

        screen = screen_for_page("button_health", principal, session=session, user=owner)

        assert "Button Health Report" in screen.text
        assert "Working:" in screen.text
        assert "Failing:" in screen.text
        assert "nav:button_health:run" in _callbacks(screen.reply_markup)


def test_callback_problem_report_route_is_safe() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        principal = PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)

        screen = screen_for_page("callback_error:report:1", principal, session=session, user=owner)

        assert "Problem Reported" in screen.text
        assert "nav:menu" in _callbacks(screen.reply_markup)
        assert session.query(AuditLog).filter_by(action="callback.problem_reported").count() == 1
