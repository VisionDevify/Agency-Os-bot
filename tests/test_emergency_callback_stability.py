from app.bot.navigation import screen_for_page
from app.bot.screens import (
    render_button_health_report_page,
    render_callback_error_page,
    render_callback_failure_review_page,
    render_debug_last_error_page,
)
from app.models.audit import AuditLog
from app.models.ai import AIAuditLog
from app.models.callback_error import CallbackErrorLog
from app.models.event_log import EventLog
from app.models.friction import FrictionItem
from app.models.recommendation import Recommendation
from app.services.auth import setup_owner_if_needed
from app.services.callbacks import latest_callback_error, log_callback_failure, run_callback_health_smoke_test, safe_exception_message
from app.services.permissions import PermissionPrincipal, RoleName
from tests.utils import session_scope
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError


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

        assert "Button Health" in screen.text
        assert "Technical:" in screen.text
        assert "Navigation:" in screen.text
        assert "UX:" in screen.text
        assert "Recommended Action:" in screen.text
        assert "Working:" not in screen.text
        assert "nav:button_health:run" in _callbacks(screen.reply_markup)
        assert "nav:button_health:details" in _callbacks(screen.reply_markup)

        details = screen_for_page("button_health:details", principal, session=session, user=owner)
        assert "Fortuna Self-Test Technical Details" in details.text
        assert "Working:" in details.text
        assert "Failing:" in details.text
        assert "Recent Production Failure Logs:" in details.text
        assert "nav:callback_failure_review" in _callbacks(details.reply_markup)


def test_callback_failure_review_renders_empty_state() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)

        screen = render_callback_failure_review_page(session, owner)

        assert "Callback Failure Review" in screen.text
        assert "No callback failures are currently logged" in screen.text
        assert "nav:button_health:run" in _callbacks(screen.reply_markup)


def test_callback_failure_review_classifies_logged_failures() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        log_callback_failure(
            session,
            actor=owner,
            callback_data="nav:proxy:1:rotate",
            page="proxy:1:rotate",
            exc=RuntimeError("proxy renderer failed"),
            affected_screen="proxy:1:rotate",
        )

        screen = render_callback_failure_review_page(session, owner)

        assert "proxy:1:rotate" in screen.text
        assert "Exception: RuntimeError" in screen.text
        assert "Root cause: Proxy screen or proxy action failed." in screen.text
        assert "proxy renderer failed" not in screen.text


def test_button_health_report_includes_recent_failure_counts() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        log_callback_failure(
            session,
            actor=owner,
            callback_data="nav:reports",
            page="reports",
            exc=ValueError("bad report payload"),
            affected_screen="reports",
        )

        screen = render_button_health_report_page(session, owner, details=True)

        assert "Callback errors: 1" in screen.text
        assert "Callback recommendations: 1" in screen.text
        assert "reports: ValueError" in screen.text


def test_callback_problem_report_route_is_safe() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        principal = PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)

        screen = screen_for_page("callback_error:report:1", principal, session=session, user=owner)

        assert "Problem Reported" in screen.text
        assert "nav:menu" in _callbacks(screen.reply_markup)
        assert session.query(AuditLog).filter_by(action="callback.problem_reported").count() == 1


def test_callback_failure_review_route_renders() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        principal = PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)

        screen = screen_for_page("callback_failure_review", principal, session=session, user=owner)

        assert "Callback Failure Review" in screen.text
        assert "Callback errors:" in screen.text


def _owner_principal(session):
    owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
    principal = PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)
    return owner, principal


def _integrity_error(*, table: str = "decision_memory", constraint: str = "ix_decision_memory_decision_id") -> IntegrityError:
    return IntegrityError(
        f"INSERT INTO {table} (...) VALUES (...)",
        {},
        Exception(f'duplicate key value violates unique constraint "{constraint}"'),
    )


def test_integrity_error_message_is_normalized_without_values() -> None:
    message = safe_exception_message(_integrity_error(table="ai_audit_logs", constraint="ck_ai_audit_logs_status"))

    assert "IntegrityError" in message
    assert "table=ai_audit_logs" in message
    assert "constraint=ck_ai_audit_logs_status" in message
    assert "VALUES" not in message


def test_coo_briefing_renders_when_decision_memory_side_effect_fails(monkeypatch) -> None:
    import app.services.decision_engine as decision_engine

    def fail_memory(*args, **kwargs):
        raise _integrity_error()

    monkeypatch.setattr(decision_engine, "record_decision_memory_event", fail_memory)
    with session_scope() as session:
        owner, principal = _owner_principal(session)

        screen = screen_for_page("coo:briefing", principal, session=session, user=owner)
        count = session.scalar(select(func.count(AuditLog.id)))

        assert "COO Briefing" in screen.text
        assert count is not None


def test_named_ai_and_coo_callbacks_render_without_integrity_error() -> None:
    with session_scope() as session:
        owner, principal = _owner_principal(session)

        for page in ("coo:briefing", "ai_brain:coo", "ai_brain:evidence", "ai_brain:opportunity"):
            screen = screen_for_page(page, principal, session=session, user=owner)
            assert screen.text
            assert "IntegrityError" not in screen.text


def test_ai_audit_logging_failure_does_not_break_ai_routes(monkeypatch) -> None:
    import app.services.ai.brain as ai_brain

    class BrokenAIAuditLog:
        def __init__(self, *args, **kwargs):
            raise _integrity_error(table="ai_audit_logs", constraint="ck_ai_audit_logs_status")

    monkeypatch.setattr(ai_brain, "AIAuditLog", BrokenAIAuditLog)
    with session_scope() as session:
        owner, principal = _owner_principal(session)

        for page in ("ai_brain:coo", "ai_brain:evidence"):
            screen = screen_for_page(page, principal, session=session, user=owner)
            assert screen.text
            assert "AI" in screen.text
        assert session.scalar(select(func.count(AIAuditLog.id))) == 0
