from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.bot.screens import render_page
from app.bot.screens.agency_awareness import (
    render_agency_active_areas_page,
    render_agency_awareness_page,
    render_agency_missing_page,
    render_agency_not_connected_page,
)
from app.bot.screens.coo import render_coo_briefing_page
from app.bot.screens.home import render_today_priorities_page
from app.bot.screens.settings import render_production_observability_page
from app.models.agency_awareness import AgencyAwarenessSnapshot
from app.models.recovery import BackupRun, RestoreTestRun
from app.services.agency_awareness import (
    DOMAIN_REGISTRY,
    AgencyAwarenessEngine,
    agency_awareness_report,
    create_manual_record,
    insufficient_data_report,
    latest_awareness_snapshot,
    report_from_snapshot,
)
from app.services.ai import AIGroundingContextBuilder
from app.services.auth import setup_owner_if_needed
from app.services.help_brain import help_brain_answer
from tests.utils import session_scope


REQUIRED_DOMAINS = {
    "recovery",
    "ai_brain",
    "search_intelligence",
    "notifications",
    "platform_connections",
    "instagram",
    "x",
    "reddit",
    "onlyfans",
    "chaturbate",
    "creators",
    "content",
    "traffic_sources",
    "fans",
    "whales",
    "chatters",
    "opportunities",
    "operations",
    "compliance",
    "finance",
    "knowledge_memory",
}


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=66, owner_telegram_id=66, display_name="Owner")


def _callbacks(screen) -> set[str]:
    return {button.callback_data for row in screen.reply_markup.inline_keyboard for button in row}


def _seed_recovery(session) -> None:
    backup = BackupRun(
        run_identifier="unit-backup-66",
        status="succeeded",
        backup_type="manual",
        storage_target="backblaze_b2",
        artifact_uri="b2://fortuna-backups/test.enc",
        size_bytes=123,
        checksum="abc123",
        encrypted=True,
        artifact_verified=True,
        external_storage_used=True,
        started_at=datetime.now(UTC) - timedelta(minutes=5),
        finished_at=datetime.now(UTC) - timedelta(minutes=4),
    )
    restore = RestoreTestRun(
        run_identifier="unit-restore-66",
        status="verified_only",
        backup_run=backup,
        started_at=datetime.now(UTC) - timedelta(minutes=3),
        finished_at=datetime.now(UTC) - timedelta(minutes=2),
        checksum_verified=True,
        decrypt_verified=True,
        full_restore_performed=False,
    )
    session.add_all([backup, restore])
    session.flush()


def test_domain_registry_contains_required_domains() -> None:
    assert REQUIRED_DOMAINS.issubset({domain.domain_id for domain in DOMAIN_REGISTRY})


def test_awareness_report_tolerates_missing_inputs_and_low_visibility(monkeypatch) -> None:
    monkeypatch.setenv("AI_ENABLED", "false")
    monkeypatch.setenv("SEARCH_ENABLED", "false")
    with session_scope() as session:
        report = AgencyAwarenessEngine(unavailable_inputs=("knowledge_memory",)).safe_generate(session, persist=False)

        assert report.overall_status in {"degraded", "insufficient_data", "needs_review"}
        assert report.degraded_mode is True
        assert "knowledge_memory" in report.missing_inputs
        assert any(domain.status == "insufficient_data" for domain in report.domains)


def test_manual_record_is_evidence_but_not_system_truth() -> None:
    with session_scope() as session:
        create_manual_record(
            session,
            domain_id="creators",
            record_type="activity",
            summary="Creator outreach is active.",
            confidence="medium",
            created_by="owner",
        )
        report = agency_awareness_report(session, persist=False)
        creators = next(domain for domain in report.domains if domain.domain_id == "creators")

        assert creators.status == "active"
        assert creators.confidence == "medium"
        assert creators.source == "manual"
        assert "Manual activity" in creators.evidence_summary


def test_external_platform_outages_degrade_without_marking_active() -> None:
    with session_scope() as session:
        report = AgencyAwarenessEngine(external_outages=("instagram", "x", "reddit")).safe_generate(session, persist=False)
        affected = [domain for domain in report.domains if domain.domain_id in {"instagram", "x", "reddit"}]

        assert report.degraded_mode is True
        assert affected
        assert all(domain.unavailable for domain in affected)
        assert all(domain.status != "active" for domain in affected)
        assert any(domain.connection_state == "temporarily_unavailable" for domain in affected)


def test_snapshot_persists_and_stale_fallback_is_labeled() -> None:
    with session_scope() as session:
        report = agency_awareness_report(session, persist=True)
        snapshot = latest_awareness_snapshot(session)

        assert snapshot is not None
        assert snapshot.visibility_score == report.visibility_score

        snapshot.generated_at = datetime.now(UTC) - timedelta(hours=8)
        stale_report = report_from_snapshot(snapshot)

        assert stale_report.stale is True
        assert stale_report.snapshot_source == "fallback"
        assert stale_report.degraded_mode is True


def test_no_snapshot_available_is_explicit_insufficient_data() -> None:
    report = insufficient_data_report()

    assert report.overall_status == "insufficient_data"
    assert report.visibility_score == 0
    assert report.degraded_mode is True
    assert "agency_awareness_snapshot" in report.missing_inputs


def test_agency_awareness_screens_render_core_paths(monkeypatch) -> None:
    monkeypatch.setenv("AI_ENABLED", "false")
    monkeypatch.setenv("SEARCH_ENABLED", "false")
    with session_scope() as session:
        owner = _owner(session)
        screens = [
            render_agency_awareness_page(session, owner),
            render_agency_active_areas_page(session, owner),
            render_agency_missing_page(session, owner),
            render_agency_not_connected_page(session, owner),
            render_page("agency_awareness:details", session=session, user=owner),
        ]

        assert "Agency Awareness" in screens[0].text
        assert "Active Areas" in screens[1].text
        assert "Missing / Inactive" in screens[2].text
        assert "Not Connected" in screens[3].text
        assert "Agency Awareness Details" in screens[4].text
        assert "nav:agency_awareness:active" in _callbacks(screens[0])
        assert "nav:menu" in _callbacks(screens[0])


def test_navigation_back_home_and_more_routes_work() -> None:
    with session_scope() as session:
        owner = _owner(session)
        active = render_page("agency_awareness:active", session=session, user=owner)
        screen = render_page("owner_advanced", session=session, user=owner)
        callbacks = _callbacks(screen)

        assert active.reply_markup is not None
        assert "nav:agency_awareness" in callbacks


def test_coo_and_today_include_awareness_when_visibility_gap_exists(monkeypatch) -> None:
    monkeypatch.setenv("AI_ENABLED", "false")
    monkeypatch.setenv("SEARCH_ENABLED", "false")
    with session_scope() as session:
        owner = _owner(session)
        create_manual_record(session, domain_id="creators", record_type="activity", summary="Creator outreach active.")

        briefing = render_coo_briefing_page(session, owner)
        today = render_today_priorities_page(session, owner)

        assert "Agency Awareness" in briefing.text
        assert "Visibility Gap" in today.text


def test_observability_shows_agency_awareness_when_meaningful(monkeypatch) -> None:
    monkeypatch.setenv("AI_ENABLED", "false")
    monkeypatch.setenv("SEARCH_ENABLED", "false")
    with session_scope() as session:
        owner = _owner(session)
        screen = render_production_observability_page(session, owner, details=True)

        assert "Agency Awareness:" in screen.text
        assert "Visibility:" in screen.text


def test_help_brain_answers_agency_awareness_questions() -> None:
    with session_scope() as session:
        owner = _owner(session)
        answer = help_brain_answer(session, owner, question="What is Agency Awareness?")
        degraded = help_brain_answer(session, owner, question="What is degraded mode?")

        assert "live map" in answer.answer
        assert answer.next_action == "agency_awareness"
        assert "fallback snapshot" in degraded.answer


def test_recovery_evidence_marks_recovery_active() -> None:
    with session_scope() as session:
        _seed_recovery(session)
        report = agency_awareness_report(session, persist=False)
        recovery = next(domain for domain in report.domains if domain.domain_id == "recovery")

        assert recovery.status in {"active", "needs_review"}
        assert recovery.confidence == "high"
        assert "restore" in recovery.evidence_summary


def test_ai_grounding_context_includes_agency_visibility(monkeypatch) -> None:
    monkeypatch.setenv("AI_ENABLED", "true")
    with session_scope() as session:
        owner = _owner(session)
        context = AIGroundingContextBuilder(session, actor=owner).build(use_case="coo_briefing")

        assert "agency_awareness" in context
        assert context["agency_awareness"]["visibility_level"] in {"low", "medium", "high"}
        assert "active_domains" in context["agency_awareness"]
        assert "not_connected_domains" in context["agency_awareness"]
