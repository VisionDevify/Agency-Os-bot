from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.bot.navigation import screen_for_page
from app.bot.screens import (
    render_category_trends_page,
    render_coo_briefing_page,
    render_decision_quality_trends_page,
    render_prediction_preview_page,
    render_today_priorities_page,
)
from app.core.config import settings
from app.models.decision_memory import DecisionMemory
from app.models.decision_trends import DecisionQualityTrend, PredictiveCOOPrediction
from app.models.recovery import BackupRun, BackupStorageTarget, RestoreTestRun
from app.services.auth import setup_owner_if_needed
from app.services.decision_trends import (
    DecisionTrendEngine,
    PredictiveCOOEngine,
    record_prediction_feedback,
    safe_decision_trend_report,
    safe_predictive_coo_report,
)
from app.services.help_brain import help_brain_answer
from app.services.observability import production_observability_summary
from app.services.permissions import PermissionPrincipal, RoleName
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=61, owner_telegram_id=61, display_name="Rex")


def _principal(user):
    return PermissionPrincipal(telegram_id=user.telegram_id, is_owner=True, role=RoleName.OWNER)


def _buttons(screen) -> list[str]:
    return [button.text for row in screen.reply_markup.inline_keyboard for button in row]


def _memory(
    *,
    decision_id: str,
    category: str,
    outcome: str = "shown",
    usefulness_score: int = 50,
    confidence: str = "medium",
) -> DecisionMemory:
    now = datetime.now(UTC)
    return DecisionMemory(
        decision_id=decision_id,
        category=category,
        severity="needs_review",
        priority_rank=40,
        confidence=confidence,
        shown_at=now,
        opened_at=now if outcome in {"opened", "acted_on", "resolved"} else None,
        acted_on_at=now if outcome in {"acted_on", "resolved"} else None,
        ignored_at=now if outcome in {"ignored", "dismissed"} else None,
        resolved_at=now if outcome == "resolved" else None,
        outcome=outcome,
        lifecycle_status="resolved" if outcome == "resolved" else "dismissed" if outcome == "dismissed" else "active",
        usefulness_score=usefulness_score,
        evidence_summary=f"{category} evidence",
        source_records=["test"],
        metadata_json={"recommendation_quality_score": usefulness_score},
    )


def _verified_backup_and_restore(session) -> None:
    now = datetime.now(UTC)
    session.add(
        BackupStorageTarget(
            name="Backblaze B2",
            target_type="backblaze_b2",
            enabled=True,
            encrypted=True,
            connection_status="active",
            provider_available=True,
            last_success_at=now,
            masked_config_json={"bucket": "fortuna-backups"},
        )
    )
    session.flush()
    backup = BackupRun(
        run_identifier="s61-backup",
        backup_type="manual",
        status="succeeded",
        started_at=now,
        finished_at=now,
        storage_target="backblaze_b2",
        encrypted=True,
        checksum="abc123",
        artifact_uri="s3://fortuna-backups/s61.enc",
        artifact_verified=True,
        external_storage_used=True,
    )
    session.add(backup)
    session.flush()
    session.add(
        RestoreTestRun(
            run_identifier="s61-restore",
            backup_run_id=backup.id,
            status="verified_only",
            started_at=now,
            finished_at=now,
            result_summary="Backup file verified; full restore DB not configured.",
            checksum_verified=True,
            decrypt_verified=True,
            full_restore_performed=False,
        )
    )
    session.flush()


def test_insufficient_data_returns_explicit_insufficient_data() -> None:
    with session_scope() as session:
        session.add(_memory(decision_id="one", category="notification", outcome="opened"))
        session.flush()

        trend = DecisionTrendEngine().calculate_category_trend(session, category="notification")

        assert trend.direction == "insufficient_data"
        assert "Not enough" in trend.reason


def test_recovery_trend_improves_after_acted_and_resolved_memory() -> None:
    with session_scope() as session:
        session.add_all(
            [
                _memory(decision_id="r1", category="recovery", outcome="acted_on", usefulness_score=70, confidence="high"),
                _memory(decision_id="r2", category="recovery", outcome="resolved", usefulness_score=82, confidence="high"),
                _memory(decision_id="r3", category="recovery", outcome="acted_on", usefulness_score=76, confidence="medium"),
            ]
        )
        session.flush()

        report = safe_decision_trend_report(session)
        recovery = next(trend for trend in report.trends if trend.category == "recovery")
        persisted = session.scalar(select(DecisionQualityTrend).where(DecisionQualityTrend.category == "recovery"))

        assert recovery.direction == "improving"
        assert persisted is not None
        assert persisted.trend_direction == "improving"


def test_ignored_platform_setup_does_not_become_failure() -> None:
    with session_scope() as session:
        session.add_all(
            [
                _memory(decision_id="p1", category="platform_connection", outcome="ignored", usefulness_score=55),
                _memory(decision_id="p2", category="platform_connection", outcome="opened", usefulness_score=58),
                _memory(decision_id="p3", category="platform_connection", outcome="ignored", usefulness_score=54),
            ]
        )
        session.flush()

        trend = DecisionTrendEngine().calculate_category_trend(session, category="platform_connection")
        prediction = safe_predictive_coo_report(session)

        assert trend.direction == "stable"
        assert any(item.can_wait for item in prediction.predictions if "Platform" in item.prediction_title)


def test_restore_test_path_prediction_appears_after_verified_backup_and_verified_only_restore() -> None:
    with session_scope() as session:
        _owner(session)
        _verified_backup_and_restore(session)

        report = safe_predictive_coo_report(session)

        assert report.available is True
        assert any("Restore-test path" in item.prediction_title for item in report.predictions)
        restore_prediction = next(item for item in report.predictions if "Restore-test path" in item.prediction_title)
        assert restore_prediction.confidence == "medium"
        assert "verified_only" in restore_prediction.evidence_summary


def test_prediction_cannot_outrank_active_critical_issue() -> None:
    with session_scope() as session:
        _owner(session)

        report = safe_predictive_coo_report(session)

        assert report.current_critical_active is True
        assert report.primary is None
        assert report.next_best_move == "Current verified priorities still come first."


def test_prediction_feedback_records_events_and_quality() -> None:
    with session_scope() as session:
        owner = _owner(session)
        _verified_backup_and_restore(session)

        record = record_prediction_feedback(session, action="helpful", actor=owner)
        report = safe_predictive_coo_report(session, actor=owner)

        assert record is not None
        assert record.status == "helpful"
        assert session.scalar(select(PredictiveCOOPrediction)) is not None
        assert report.quality.prediction_count >= 1
        assert report.quality.helpful_rate > 0


def test_proven_correct_requires_later_evidence() -> None:
    with session_scope() as session:
        owner = _owner(session)
        _verified_backup_and_restore(session)

        record = PredictiveCOOEngine().record_feedback(session, action="proven_correct", actor=owner)

        assert record is not None
        assert record.status != "proven_correct"


def test_feature_flag_disables_prediction_sections(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "predictive_coo_enabled", False)
    with session_scope() as session:
        _owner(session)

        report = safe_predictive_coo_report(session)
        screen = render_prediction_preview_page(session)

        assert report.enabled is False
        assert "Disabled" in screen.text


def test_trend_and_prediction_screens_render_without_raw_ids() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)

        trends = screen_for_page("intelligence:quality:trends", principal, session=session, user=owner)
        categories = render_category_trends_page(session, owner)
        prediction = screen_for_page("prediction:preview", principal, session=session, user=owner)
        details = screen_for_page("prediction:preview:details", principal, session=session, user=owner)

        assert "Decision Quality Trends" in trends.text
        assert "Category Trends" in categories.text
        assert "Prediction Preview" in prediction.text
        assert "Evidence:" in details.text
        assert "decision_id" not in trends.text
        assert "source_records" not in prediction.text
        assert "Back" in _buttons(trends)
        assert "Main Menu" in _buttons(prediction)


def test_coo_and_today_include_prediction_when_useful() -> None:
    with session_scope() as session:
        owner = _owner(session)
        _verified_backup_and_restore(session)

        coo = render_coo_briefing_page(session, owner)
        today = render_today_priorities_page(session, owner)

        assert "Likely Next" in coo.text
        assert "Restore-test path" in coo.text
        assert "Likely next" in today.text


def test_trend_failure_does_not_crash_coo_briefing(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args, **_kwargs):
        raise RuntimeError("trend offline")

    monkeypatch.setattr(DecisionTrendEngine, "calculate_trends", boom)
    with session_scope() as session:
        owner = _owner(session)

        screen = render_coo_briefing_page(session, owner)
        report = safe_decision_trend_report(session)

        assert "COO Briefing" in screen.text
        assert report.available is False


def test_prediction_failure_does_not_crash_today(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args, **_kwargs):
        raise RuntimeError("prediction offline")

    monkeypatch.setattr(PredictiveCOOEngine, "generate_predictions", boom)
    with session_scope() as session:
        owner = _owner(session)

        today = render_today_priorities_page(session, owner)
        report = safe_predictive_coo_report(session)

        assert "What Matters Today" in today.text
        assert report.available is False


def test_observability_and_help_brain_include_predictive_quality_safely() -> None:
    with session_scope() as session:
        owner = _owner(session)

        summary = production_observability_summary(session)
        trends = help_brain_answer(session, owner, question="What are Decision Quality Trends?")
        predictive = help_brain_answer(session, owner, question="What is Predictive COO?")
        facts = help_brain_answer(session, owner, question="Are predictions facts?")

        assert "decision_trends_status" in summary
        assert "prediction_health_status" in summary
        assert "does not invent improvement" in trends.answer
        assert "evidence-backed guesses" in predictive.answer
        assert "not facts" in facts.answer.lower()
