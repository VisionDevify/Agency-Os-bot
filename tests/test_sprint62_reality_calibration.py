from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.bot.navigation import screen_for_page
from app.bot.screens import (
    render_accuracy_by_category_page,
    render_calibration_page,
    render_coo_briefing_page,
    render_prediction_outcomes_page,
    render_reality_check_page,
    render_today_priorities_page,
)
from app.core.config import settings
from app.models.button_issue import ButtonIssue
from app.models.decision_trends import PredictiveCOOPrediction
from app.models.reality_calibration import PredictionOutcome
from app.models.recovery import BackupRun, RestoreTestRun
from app.services.auth import setup_owner_if_needed
from app.services.decision_trends import safe_predictive_coo_report
from app.services.help_brain import help_brain_answer
from app.services.observability import production_observability_summary
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.reality_calibration import (
    CalibrationEngine,
    PredictionEvaluationEngine,
    record_prediction_outcome_feedback,
    safe_reality_calibration_report,
)
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=62, owner_telegram_id=62, display_name="Rex")


def _principal(user):
    return PermissionPrincipal(telegram_id=user.telegram_id, is_owner=True, role=RoleName.OWNER)


def _buttons(screen) -> list[str]:
    return [button.text for row in screen.reply_markup.inline_keyboard for button in row]


def _prediction(
    *,
    title: str = "Restore-test path is likely the next recovery blocker",
    prediction_type: str = "likely_blocker",
    confidence: str = "medium",
    evidence_key: str = "recovery_restore_path:test",
    shown_at: datetime | None = None,
) -> PredictiveCOOPrediction:
    shown = shown_at or datetime.now(UTC)
    return PredictiveCOOPrediction(
        prediction_title=title,
        prediction_type=prediction_type,
        confidence=confidence,
        reason="Evidence suggests this may matter next.",
        evidence_summary="Backup is verified; restore validation is verified_only.",
        recommended_next_action="Create restore-test path.",
        can_wait=False,
        status="shown",
        shown_at=shown,
        evidence_key=evidence_key,
        metadata_json={},
    )


def _backup(session, *, finished_at: datetime) -> BackupRun:
    backup = BackupRun(
        run_identifier=f"s62-backup-{finished_at.timestamp()}",
        backup_type="manual",
        status="succeeded",
        started_at=finished_at,
        finished_at=finished_at,
        storage_target="backblaze_b2",
        encrypted=True,
        checksum="abc123",
        artifact_uri="s3://fortuna-backups/s62.enc",
        artifact_verified=True,
        external_storage_used=True,
    )
    session.add(backup)
    session.flush()
    return backup


def _restore(session, backup: BackupRun, *, status: str, finished_at: datetime, full_restore: bool = False) -> RestoreTestRun:
    restore = RestoreTestRun(
        run_identifier=f"s62-restore-{finished_at.timestamp()}",
        backup_run_id=backup.id,
        status=status,
        started_at=finished_at,
        finished_at=finished_at,
        result_summary="Restore evidence for Sprint 62.",
        checksum_verified=True,
        decrypt_verified=True,
        full_restore_performed=full_restore,
    )
    session.add(restore)
    session.flush()
    return restore


def test_prediction_outcome_defaults_to_pending() -> None:
    with session_scope() as session:
        prediction = _prediction()
        session.add(prediction)
        session.flush()
        outcome = PredictionOutcome(
            prediction_id=prediction.id,
            prediction_type=prediction.prediction_type,
            category="recovery",
            confidence_at_prediction=prediction.confidence,
            predicted_at=datetime.now(UTC),
        )
        session.add(outcome)
        session.flush()

        assert outcome.outcome == "pending"
        assert outcome.evidence_summary == "Waiting for evidence."


def test_restore_prediction_stays_pending_until_later_restore_evidence() -> None:
    with session_scope() as session:
        prediction = _prediction(shown_at=datetime.now(UTC))
        session.add(prediction)
        session.flush()

        report = safe_reality_calibration_report(session)
        outcome = next(item for item in report.outcomes if item.prediction_id == prediction.id)

        assert outcome.outcome == "pending"
        assert "Waiting for later restore-test evidence" in outcome.evidence_summary


def test_restore_prediction_proven_correct_requires_later_evidence() -> None:
    with session_scope() as session:
        shown_at = datetime.now(UTC) - timedelta(hours=2)
        prediction = _prediction(shown_at=shown_at)
        session.add(prediction)
        session.flush()
        backup = _backup(session, finished_at=shown_at + timedelta(hours=1))
        _restore(session, backup, status="verified_only", finished_at=shown_at + timedelta(hours=1), full_restore=False)

        report = safe_reality_calibration_report(session)
        outcome = next(item for item in report.outcomes if item.prediction_id == prediction.id)

        assert outcome.outcome == "proven_correct"
        assert "full restore testing was still the recovery blocker" in outcome.evidence_summary


def test_restore_prediction_proven_wrong_requires_contradicting_evidence() -> None:
    with session_scope() as session:
        shown_at = datetime.now(UTC)
        backup = _backup(session, finished_at=shown_at - timedelta(hours=2))
        _restore(session, backup, status="passed", finished_at=shown_at - timedelta(hours=1), full_restore=True)
        prediction = _prediction(shown_at=shown_at)
        session.add(prediction)
        session.flush()

        report = safe_reality_calibration_report(session)
        outcome = next(item for item in report.outcomes if item.prediction_id == prediction.id)

        assert outcome.outcome == "proven_wrong"
        assert "already existed" in outcome.evidence_summary


def test_owner_feedback_alone_does_not_prove_correctness() -> None:
    with session_scope() as session:
        owner = _owner(session)
        prediction = _prediction()
        session.add(prediction)
        session.flush()

        outcome = record_prediction_outcome_feedback(session, action="right", actor=owner)

        assert outcome is not None
        assert outcome.outcome != "proven_correct"
        assert "no evidence" in (outcome.correction_summary or "").lower()


def test_platform_can_wait_prediction_is_correct_when_activation_not_started() -> None:
    with session_scope() as session:
        prediction = _prediction(
            title="Platform logins can stay in final activation",
            prediction_type="upcoming_setup_need",
            confidence="medium",
            evidence_key="platform_waiting:3",
        )
        session.add(prediction)
        session.flush()

        report = safe_reality_calibration_report(session)
        outcome = next(item for item in report.outcomes if item.prediction_id == prediction.id)

        assert outcome.outcome == "proven_correct"
        assert outcome.category == "platform_connection"


def test_friction_prediction_correct_when_button_issue_continues() -> None:
    with session_scope() as session:
        session.add(
            ButtonIssue(
                screen="notification_center",
                button_label="Back",
                callback_data="nav:bad",
                issue_type="bad_back_target",
                severity="medium",
                status="open",
                evidence_summary="Repeated Back usage found.",
                recommended_fix="Fix Back target.",
            )
        )
        prediction = _prediction(
            title="Notification Center may keep creating friction",
            prediction_type="repeated_friction_warning",
            confidence="medium",
            evidence_key="friction:notification_center",
        )
        session.add(prediction)
        session.flush()

        report = safe_reality_calibration_report(session)
        outcome = next(item for item in report.outcomes if item.prediction_id == prediction.id)

        assert outcome.outcome == "proven_correct"
        assert outcome.category == "friction"


def test_general_supported_prediction_without_evaluator_is_not_enough_evidence() -> None:
    with session_scope() as session:
        prediction = _prediction(
            title="A future setup item may matter later",
            prediction_type="stale_decision_warning",
            confidence="low",
            evidence_key="general:stale",
        )
        session.add(prediction)
        session.flush()

        report = safe_reality_calibration_report(session)
        outcome = next(item for item in report.outcomes if item.prediction_id == prediction.id)

        assert outcome.outcome == "not_enough_evidence"


def test_calibration_detects_insufficient_over_under_and_calibrated_states() -> None:
    now = datetime.now(UTC)
    with session_scope() as session:
        predictions = [
            _prediction(title="High wrong one", confidence="high", evidence_key="high_wrong_1", shown_at=now),
            _prediction(title="High wrong two", confidence="high", evidence_key="high_wrong_2", shown_at=now),
            _prediction(title="Low right one", confidence="low", evidence_key="low_right_1", shown_at=now),
            _prediction(title="Low right two", confidence="low", evidence_key="low_right_2", shown_at=now),
            _prediction(title="Medium right one", confidence="medium", evidence_key="medium_right_1", shown_at=now),
            _prediction(title="Medium wrong two", confidence="medium", evidence_key="medium_wrong_2", shown_at=now),
        ]
        session.add_all(predictions)
        session.flush()
        outcomes = [
            PredictionOutcome(
                prediction_id=prediction.id,
                prediction_type=prediction.prediction_type,
                category="recovery",
                confidence_at_prediction=prediction.confidence,
                predicted_at=now,
                evaluated_at=now,
                outcome=outcome,
                evidence_summary="Calibration fixture.",
                evidence_records=["test"],
            )
            for prediction, outcome in zip(
                predictions,
                ("proven_wrong", "proven_wrong", "proven_correct", "proven_correct", "proven_correct", "proven_wrong"),
                strict=True,
            )
        ]
        session.add_all(outcomes)
        session.flush()

        report = CalibrationEngine().build_report(session)
        buckets = {bucket.scope_value: bucket for bucket in report.confidence_buckets}

        assert buckets["high"].calibration_status == "overconfident"
        assert buckets["low"].calibration_status == "underconfident"
        assert buckets["medium"].calibration_status == "calibrated"


def test_confidence_adjustment_does_not_hide_active_critical_issue() -> None:
    with session_scope() as session:
        _owner(session)

        report = safe_predictive_coo_report(session)

        assert report.current_critical_active is True
        assert report.primary is None


def test_reality_screens_render_and_hide_raw_ids() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)
        prediction = _prediction()
        session.add(prediction)
        session.flush()

        reality = screen_for_page("reality:check", principal, session=session, user=owner)
        outcomes = render_prediction_outcomes_page(session, owner)
        calibration = render_calibration_page(session, owner)
        accuracy = render_accuracy_by_category_page(session, owner)
        feedback = screen_for_page("prediction:outcome:still_pending", principal, session=session, user=owner)

        assert "Reality Check" in reality.text
        assert "Prediction Outcomes" in outcomes.text
        assert "Confidence Calibration" in calibration.text
        assert "Accuracy by Category" in accuracy.text
        assert "Prediction Reality Feedback" in feedback.text
        assert "prediction_id" not in reality.text
        assert "PredictiveCOOPrediction" not in outcomes.text
        assert "Back" in _buttons(reality)
        assert "Main Menu" in _buttons(calibration)


def test_reality_calibration_integrates_with_coo_today_observability_and_help() -> None:
    with session_scope() as session:
        owner = _owner(session)
        prediction = _prediction()
        session.add(prediction)
        session.flush()

        coo = render_coo_briefing_page(session, owner)
        today = render_today_priorities_page(session, owner)
        summary = production_observability_summary(session)
        help_answer = help_brain_answer(session, owner, question="What is Reality Check?")
        calibration_help = help_brain_answer(session, owner, question="Can owner feedback prove a prediction?")

        assert "COO Briefing" in coo.text
        assert "Still pending evidence" in today.text or "What Matters Today" in today.text
        assert "reality_calibration_status" in summary
        assert "Fortuna can be wrong" in help_answer.answer
        assert "feedback alone does not prove" in calibration_help.answer


def test_evaluation_failure_does_not_crash_coo_and_feature_flag_hides_reality(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(*_args, **_kwargs):
        raise RuntimeError("calibration offline")

    monkeypatch.setattr(PredictionEvaluationEngine, "evaluate_predictions", boom)
    with session_scope() as session:
        owner = _owner(session)

        coo = render_coo_briefing_page(session, owner)
        report = safe_reality_calibration_report(session, actor=owner)

        assert "COO Briefing" in coo.text
        assert report.available is False

    monkeypatch.setattr(settings, "reality_calibration_enabled", False)
    with session_scope() as session:
        owner = _owner(session)

        report = safe_reality_calibration_report(session, actor=owner)
        screen = render_reality_check_page(session, owner)

        assert report.enabled is False
        assert "Disabled" in screen.text
