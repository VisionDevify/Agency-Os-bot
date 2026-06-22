from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.bot.navigation import screen_for_page
from app.bot.screens.command_center import render_command_center_home
from app.bot.screens.drift import render_active_drift_page, render_drift_page, render_drift_plans_page
from app.models.agency_awareness import AgencyManualRecord
from app.models.button_issue import ButtonIssue
from app.models.recovery import BackupRun
from app.models.reliability import CallbackLatencyRecord
from app.services.agency_drift import (
    AgencyDriftEngine,
    agency_drift_report,
    create_manual_plan_from_template,
    drift_score_pressure,
    set_plan_status,
)
from app.services.auth import setup_owner_if_needed
from app.services.live_scores import build_command_center_report
from app.services.permissions import PermissionPrincipal, RoleName
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)


def _principal():
    return PermissionPrincipal(telegram_id=1, is_owner=True, role=RoleName.OWNER)


def test_drift_requires_expectation() -> None:
    with session_scope() as session:
        session.add(
            AgencyManualRecord(
                domain_id="content",
                record_type="activity",
                summary="IG posting happened.",
                confidence="medium",
                created_by="owner",
            )
        )
        session.flush()

        report = AgencyDriftEngine(include_starter_expectations=False).generate(session)

        assert report.active_findings == ()
        assert report.next_best_move == "No active drift. Keep plans updated as reality changes."


def test_missing_data_becomes_visibility_gap_not_failure() -> None:
    with session_scope() as session:
        create_manual_plan_from_template(session, "creator_outreach")

        report = AgencyDriftEngine(include_starter_expectations=False).generate(session)

        assert len(report.active_findings) == 1
        finding = report.active_findings[0]
        assert finding.status == "needs_review"
        assert finding.severity == "low"
        assert finding.confidence == "low"
        assert "visibility_gap" in finding.gap


def test_paused_plan_does_not_create_drift() -> None:
    with session_scope() as session:
        plan = create_manual_plan_from_template(session, "posting")
        set_plan_status(session, plan.id, "paused")

        report = AgencyDriftEngine(include_starter_expectations=False).generate(session)

        assert report.active_findings == ()


def test_backup_freshness_drift_detected_without_verified_backup() -> None:
    with session_scope() as session:
        report = AgencyDriftEngine().generate(session)

        recovery_findings = [item for item in report.active_findings if item.domain == "recovery"]
        assert recovery_findings
        assert recovery_findings[0].status == "active"
        assert recovery_findings[0].severity == "high"


def test_reliability_drift_detected_from_active_issue() -> None:
    with session_scope() as session:
        session.add(
            ButtonIssue(
                screen="scores",
                button_label=None,
                callback_data="nav:command_center:scores",
                issue_type="renderer_error",
                severity="high",
                status="open",
                evidence_summary="Scores renderer failed.",
                recommended_fix="Fix scores route.",
            )
        )
        session.flush()

        report = AgencyDriftEngine().generate(session)

        assert any(item.domain == "reliability" and item.gap == "reliability_active_issue" for item in report.active_findings)


def test_command_verification_drift_resolves_after_success_record() -> None:
    with session_scope() as session:
        session.add(
            CallbackLatencyRecord(
                callback_route="command:verify_navigation",
                received_at=datetime.now(UTC),
                result="succeeded",
                latency_label="excellent",
            )
        )
        session.flush()

        report = AgencyDriftEngine().generate(session)

        assert not any(item.gap == "command_verification_missing" for item in report.active_findings)


def test_manual_drift_resolves_when_evidence_appears() -> None:
    with session_scope() as session:
        plan = create_manual_plan_from_template(session, "creator_outreach")
        first = AgencyDriftEngine(include_starter_expectations=False).generate(session)
        assert first.active_findings

        session.add(
            AgencyManualRecord(
                domain_id=plan.domain,
                record_type="activity",
                summary="Creator outreach happened.",
                confidence="medium",
                created_by="owner",
            )
        )
        session.flush()
        second = AgencyDriftEngine(include_starter_expectations=False).generate(session)

        assert not second.active_findings
        assert second.resolved_findings


def test_drift_reappears_if_same_gap_returns() -> None:
    with session_scope() as session:
        plan = create_manual_plan_from_template(session, "creator_outreach")
        old = AgencyManualRecord(
            domain_id=plan.domain,
            record_type="activity",
            summary="Old creator outreach.",
            confidence="medium",
            created_by="owner",
            created_at=datetime.now(UTC) - timedelta(days=20),
        )
        session.add(old)
        session.flush()
        first = AgencyDriftEngine(include_starter_expectations=False).generate(session)
        assert first.active_findings[0].gap == "expected_activity_stale"

        old.created_at = datetime.now(UTC)
        session.flush()
        resolved = AgencyDriftEngine(include_starter_expectations=False).generate(session)
        assert not resolved.active_findings

        old.created_at = datetime.now(UTC) - timedelta(days=20)
        session.flush()
        reappeared = AgencyDriftEngine(include_starter_expectations=False).generate(session)

        assert reappeared.active_findings[0].status == "reappeared"


def test_score_impact_is_bounded_and_command_center_limits_attention() -> None:
    with session_scope() as session:
        create_manual_plan_from_template(session, "creator_outreach")
        AgencyDriftEngine(include_starter_expectations=False).generate(session)

        pressure = drift_score_pressure(session)
        report = build_command_center_report(session)

        assert all(value <= 10 for value in pressure.values())
        assert len(report.attention_items) <= 3


def test_drift_screens_render_without_raw_ids() -> None:
    with session_scope() as session:
        owner = _owner(session)
        create_manual_plan_from_template(session, "creator_outreach")

        screens = [
            render_drift_page(session, owner),
            render_active_drift_page(session, owner),
            render_drift_plans_page(session, owner),
            screen_for_page("drift", _principal(), session=session, user=owner),
            screen_for_page("drift:active", _principal(), session=session, user=owner),
            screen_for_page("drift:plans", _principal(), session=session, user=owner),
            screen_for_page("drift:add", _principal(), session=session, user=owner),
        ]

        for screen in screens:
            assert "metadata_json" not in screen.text
            assert "AgencyPlan:" not in screen.text
            assert "plan_id" not in screen.text
            assert "Drift" in screen.text or "Plans" in screen.text or "Add Plan" in screen.text


def test_command_center_can_show_one_drift_attention_item() -> None:
    with session_scope() as session:
        _owner(session)
        session.add(
            BackupRun(
                run_identifier="old-backup",
                backup_type="manual",
                status="succeeded",
                started_at=datetime.now(UTC) - timedelta(days=3),
                finished_at=datetime.now(UTC) - timedelta(days=3),
                encrypted=True,
                checksum="abc",
                artifact_uri="s3://bucket/backup.enc",
                artifact_verified=True,
                external_storage_used=True,
            )
        )
        session.flush()

        screen = render_command_center_home(session)

        assert "Attention Needed" in screen.text
        assert screen.text.count("Run a fresh backup.") <= 1
