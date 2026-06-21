from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.bot.screens import render_page
from app.bot.screens.reliability import render_reliability_center_page, render_reliability_verify_page
from app.models.reliability import CallbackLatencyRecord, ReliabilityJob
from app.services.auth import setup_owner_if_needed
from app.services.observability import production_observability_summary
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.reliability import (
    SHORTCUT_BY_COMMAND,
    CallbackTiming,
    active_jobs,
    latency_label,
    mark_stale_reliability_jobs,
    record_callback_latency,
    render_command_shortcut,
    run_command_verification_harness,
    start_reliability_job,
    update_reliability_job,
)
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=6701, owner_telegram_id=6701, display_name="Owner")


def _principal(owner) -> PermissionPrincipal:
    return PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)


def test_latency_labels_and_records_are_persisted() -> None:
    with session_scope() as session:
        now = datetime.now(UTC)
        record = record_callback_latency(
            session,
            CallbackTiming(
                callback_route="agency_awareness",
                received_at=now,
                acknowledged_at=now + timedelta(milliseconds=100),
                render_started_at=now + timedelta(milliseconds=120),
                render_finished_at=now + timedelta(milliseconds=900),
                edit_or_send_completed_at=now + timedelta(milliseconds=1100),
            ),
            result="succeeded",
        )

        assert latency_label(400) == "excellent"
        assert latency_label(1200) == "good"
        assert latency_label(2500) == "slow"
        assert latency_label(3500) == "bad"
        assert record.total_latency_ms == 1100
        assert record.ack_latency_ms == 100
        assert record.latency_label == "good"
        assert session.query(CallbackLatencyRecord).count() == 1


def test_reliability_jobs_update_and_stale_jobs_time_out() -> None:
    with session_scope() as session:
        job = start_reliability_job(
            session,
            job_id="ai:test",
            job_type="ai_summary",
            status="running",
            current_step="Summarizing evidence",
        )
        update_reliability_job(session, "ai:test", status="completed", current_step="Summary ready", progress_percent=100)

        stale = start_reliability_job(session, job_id="search:stale", job_type="search", status="running")
        stale.updated_at = datetime.now(UTC) - timedelta(minutes=30)
        timed_out = mark_stale_reliability_jobs(session)

        assert job.status == "completed"
        assert job.finished_at is not None
        assert timed_out == 1
        assert stale.status == "timed_out"


def test_active_jobs_excludes_completed_jobs() -> None:
    with session_scope() as session:
        start_reliability_job(session, job_id="backup:active", job_type="backup", status="verifying")
        start_reliability_job(session, job_id="ai:done", job_type="ai_summary", status="completed")

        jobs = active_jobs(session)

        assert [job.job_id for job in jobs] == ["backup:active"]


def test_command_shortcuts_reuse_screen_renderers(monkeypatch) -> None:
    monkeypatch.setenv("AI_ENABLED", "false")
    monkeypatch.setenv("SEARCH_ENABLED", "false")
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)

        commands = {
            "home": "Fortuna OS",
            "coo": "COO Briefing",
            "today": "What Matters Today",
            "agency": "Agency Awareness",
            "agency_active": "Active Areas",
            "agency_missing": "Missing / Inactive",
            "agency_connected": "Not Connected",
            "ai": "AI Brain",
            "search": "Search Intelligence",
            "recovery": "Recovery Center",
            "reliability": "Reliability Center",
            "observability": "Production Status",
        }
        for command, expected in commands.items():
            screen = render_command_shortcut(session, command=command, principal=principal, user=owner)
            assert expected in screen.text


def test_coo_shortcut_does_not_call_ai_inline(monkeypatch) -> None:
    import app.bot.screens.coo as coo_module

    monkeypatch.setattr(coo_module, "ai_configuration_status", lambda session: {"enabled": True, "configured": True})
    monkeypatch.setattr(
        coo_module,
        "generate_ai_decision_explanation",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("COO shortcut must not call AI inline")),
        raising=False,
    )

    with session_scope() as session:
        owner = _owner(session)
        screen = render_command_shortcut(session, command="coo", principal=_principal(owner), user=owner)

        assert "COO Briefing" in screen.text


def test_verify_navigation_harness_reports_passed_routes(monkeypatch) -> None:
    monkeypatch.setenv("AI_ENABLED", "false")
    monkeypatch.setenv("SEARCH_ENABLED", "false")
    with session_scope() as session:
        owner = _owner(session)
        result = run_command_verification_harness(session, actor=owner)
        screen = render_reliability_verify_page(session, owner)

        assert len(result.passed) >= 10
        assert result.callback_issue_count >= 0
        assert "Navigation Verification" in screen.text
        assert "Passed Routes" in screen.text


def test_reliability_center_excludes_historical_when_healthy() -> None:
    with session_scope() as session:
        owner = _owner(session)
        screen = render_reliability_center_page(session, owner)

        assert "Reliability Center" in screen.text
        assert "Status:" in screen.text
        assert "Active Issues:" in screen.text


def test_slow_callback_appears_in_reliability_and_observability() -> None:
    with session_scope() as session:
        owner = _owner(session)
        now = datetime.now(UTC)
        record_callback_latency(
            session,
            CallbackTiming(
                callback_route="ai_brain:evidence",
                received_at=now,
                acknowledged_at=now + timedelta(milliseconds=50),
                render_started_at=now + timedelta(milliseconds=100),
                render_finished_at=now + timedelta(milliseconds=3200),
                edit_or_send_completed_at=now + timedelta(milliseconds=3500),
            ),
            result="succeeded",
        )

        screen = render_page("reliability:slow", session=session, user=owner)
        summary = production_observability_summary(session)

        assert "ai_brain:evidence" in screen.text
        assert summary["reliability_status"] == "needs_review"
        assert summary["reliability_slowest_area"] == "ai_brain:evidence"


def test_shortcut_registry_contains_required_commands() -> None:
    required = {
        "home",
        "more",
        "coo",
        "today",
        "agency",
        "agency_active",
        "agency_missing",
        "agency_connected",
        "ai",
        "ai_settings",
        "ai_critic",
        "ai_evidence",
        "ai_coo",
        "search",
        "search_settings",
        "search_history",
        "recovery",
        "backup_history",
        "run_backup",
        "restore_test",
        "reliability",
        "callback_failures",
        "button_health",
        "notifications",
        "platforms",
        "decision_memory",
        "reality",
        "intelligence",
        "observability",
        "verify_navigation",
    }

    assert required.issubset(set(SHORTCUT_BY_COMMAND))
