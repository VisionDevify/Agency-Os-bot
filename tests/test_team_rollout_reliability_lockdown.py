from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.bot.screens.errors import render_button_health_report_page
from app.models.button_issue import ButtonIssue
from app.models.callback_error import CallbackErrorLog
from app.models.recommendation import Recommendation
from app.services.auth import setup_owner_if_needed
from app.services.callbacks import callback_failure_review
from app.services.reliability import (
    CallbackTiming,
    record_callback_latency,
    reliability_summary,
    run_command_verification_harness,
    working_screen_for_page,
)
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)


def _callback_error(page: str) -> CallbackErrorLog:
    return CallbackErrorLog(
        callback_data=f"nav:{page}",
        page=page,
        affected_screen=page,
        exception_type="IntegrityError",
        error_message="IntegrityError table=callback_audit constraint=callback_unique",
        created_at=datetime.now(UTC) - timedelta(hours=2),
    )


def _callback_recommendation(page: str) -> Recommendation:
    return Recommendation(
        recommendation_type="callback_failure",
        title="Button Needs Repair",
        description=f"Callback {page} failed and needs review.",
        severity="warning",
        entity_type="telegram_callback",
        entity_id=page,
        status="open",
        metadata_json={"source": "test"},
    )


def test_verify_navigation_revalidates_historical_ai_callback_debt(monkeypatch) -> None:
    monkeypatch.setenv("AI_ENABLED", "false")
    monkeypatch.setenv("SEARCH_ENABLED", "false")
    with session_scope() as session:
        owner = _owner(session)
        for page in ("coo:briefing", "ai_brain:coo", "ai_brain:evidence", "ai_brain:opportunity"):
            session.add(_callback_error(page))
            session.add(_callback_recommendation(page))
        session.flush()

        result = run_command_verification_harness(session, actor=owner)
        review = callback_failure_review(session, limit=20)

        assert not result.failed
        assert result.callback_issue_count == 0
        assert not review.active_items
        assert not [item for item in review.validating_items if item.page.startswith("ai_brain") or item.page == "coo:briefing"]
        assert {item.page for item in review.historical_items}.issuperset(
            {"coo:briefing", "ai_brain:coo", "ai_brain:evidence", "ai_brain:opportunity"}
        )


def test_successful_command_latency_revalidates_old_callback_failure_without_recommendation(monkeypatch) -> None:
    _non_critical_recovery(monkeypatch)
    with session_scope() as session:
        error = _callback_error("command_center:scores")
        session.add(error)
        session.flush()
        success_at = error.created_at + timedelta(minutes=10)
        record_callback_latency(
            session,
            CallbackTiming(
                callback_route="command:scores",
                received_at=success_at,
                acknowledged_at=success_at,
                render_started_at=success_at,
                render_finished_at=success_at,
                edit_or_send_completed_at=success_at,
            ),
            result="succeeded",
            metadata={"test": True},
        )
        session.flush()

        review = callback_failure_review(session, limit=20)
        summary = reliability_summary(session)

        assert not review.active_items
        assert not review.validating_items
        assert {item.page for item in review.historical_items} == {"command_center:scores"}
        assert summary["active_issue_count"] == 0
        assert summary["status"] == "healthy"


def _non_critical_recovery(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.reliability.recovery_risk_assessment",
        lambda session: SimpleNamespace(risk_level="Moderate", status="needs_review"),
    )


def test_reliability_ignores_non_blocking_button_debt_in_rollout_status(monkeypatch) -> None:
    _non_critical_recovery(monkeypatch)
    with session_scope() as session:
        session.add(
            ButtonIssue(
                screen="scores",
                button_label="Details",
                callback_data="nav:command_center:scores",
                issue_type="raw_internal_label",
                severity="medium",
                status="open",
                evidence_summary="Historical label wording issue.",
                recommended_fix="Rename in the next wording pass.",
            )
        )
        session.flush()

        summary = reliability_summary(session)

        assert summary["status"] == "healthy"
        assert summary["active_issue_count"] == 0
        assert summary["non_blocking_warning_count"] == 1
        assert summary["team_rollout_status"] == "ready"


def test_renderer_issue_still_blocks_team_rollout(monkeypatch) -> None:
    _non_critical_recovery(monkeypatch)
    with session_scope() as session:
        session.add(
            ButtonIssue(
                screen="ai_brain",
                button_label=None,
                callback_data="nav:ai_brain",
                issue_type="renderer_error",
                severity="high",
                status="open",
                evidence_summary="AI Brain renderer failed.",
                recommended_fix="Fix renderer.",
            )
        )
        session.flush()

        summary = reliability_summary(session)

        assert summary["status"] == "needs_review"
        assert summary["active_issue_count"] == 1
        assert summary["team_rollout_status"] == "needs_review"


def test_button_health_simple_view_does_not_run_full_scan(monkeypatch) -> None:
    import app.bot.screens.errors as errors_module

    def fail_scan(*args, **kwargs):
        raise AssertionError("simple Button Health view should not run the full scan")

    monkeypatch.setattr(errors_module, "run_button_issue_scan", fail_scan)
    with session_scope() as session:
        owner = _owner(session)
        screen = render_button_health_report_page(session, owner)

        assert "Button Health" in screen.text
        assert "Run Check" in str(screen.reply_markup.inline_keyboard)
        assert working_screen_for_page("button_health:run") is not None
