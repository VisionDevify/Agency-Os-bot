from __future__ import annotations

from datetime import UTC, datetime

from app.bot.navigation import screen_for_page
from app.bot.screens import (
    render_decision_review_page,
    render_decision_timeline_page,
    render_evidence_notes_page,
    render_knowledge_memory_page,
    render_reality_check_page,
)
from app.models.decision_trends import PredictiveCOOPrediction
from app.models.evidence import EvidenceRecord, KnowledgeMemory, OwnerValidation
from app.models.reality_calibration import PredictionOutcome
from app.services.auth import setup_owner_if_needed
from app.services.evidence_capture import (
    create_evidence_record,
    create_knowledge_lesson,
    decision_timeline,
    record_evidence_note,
    record_owner_validation,
    safe_evidence_capture_report,
)
from app.services.help_brain import help_brain_answer
from app.services.observability import production_observability_summary
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.reality_calibration import CalibrationEngine, safe_reality_calibration_report
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=63, owner_telegram_id=63, display_name="Rex")


def _principal(user):
    return PermissionPrincipal(telegram_id=user.telegram_id, is_owner=True, role=RoleName.OWNER)


def _buttons(screen) -> list[str]:
    return [button.text for row in screen.reply_markup.inline_keyboard for button in row]


def _prediction(
    *,
    title: str = "Restore-test path is likely the next recovery blocker",
    evidence_key: str = "recovery_restore_path:s63",
    confidence: str = "medium",
) -> PredictiveCOOPrediction:
    return PredictiveCOOPrediction(
        prediction_title=title,
        prediction_type="likely_blocker",
        confidence=confidence,
        reason="Evidence suggests this may matter next.",
        evidence_summary="Backup is verified; restore validation is verified_only.",
        recommended_next_action="Create restore-test path.",
        can_wait=False,
        status="shown",
        shown_at=datetime.now(UTC),
        evidence_key=evidence_key,
        metadata_json={},
    )


def test_evidence_record_creation_and_links() -> None:
    with session_scope() as session:
        owner = _owner(session)
        prediction = _prediction()
        session.add(prediction)
        session.flush()

        evidence = create_evidence_record(
            session,
            evidence_type="owner_note",
            category="recovery",
            summary="Restore testing became the next task.",
            details="Owner observed this after backup setup.",
            linked_prediction_id=prediction.id,
            linked_decision_id="decision-recovery",
            linked_recommendation_id=None,
            actor=owner,
        )

        assert evidence.evidence_strength == "weak"
        assert evidence.linked_prediction_id == prediction.id
        assert evidence.linked_decision_id == "decision-recovery"
        assert session.query(EvidenceRecord).count() == 1


def test_owner_validation_records_all_outcomes() -> None:
    with session_scope() as session:
        owner = _owner(session)
        prediction = _prediction()
        session.add(prediction)
        session.flush()

        for outcome in ("correct", "incorrect", "partially_correct", "too_early", "add_evidence"):
            validation = record_owner_validation(
                session,
                validation_outcome=outcome,
                actor=owner,
                linked_prediction_id=prediction.id,
                summary=f"Owner marked {outcome}.",
            )
            assert validation.validation_outcome == outcome

        assert session.query(OwnerValidation).count() == 5
        assert session.query(EvidenceRecord).count() == 5


def test_strong_owner_evidence_can_support_calibration_without_fabricating_silence() -> None:
    with session_scope() as session:
        owner = _owner(session)
        prediction = _prediction()
        session.add(prediction)
        session.flush()

        record_owner_validation(
            session,
            validation_outcome="correct",
            actor=owner,
            linked_prediction_id=prediction.id,
            summary="Correct. Restore testing became the next blocker.",
            details="Backup setup finished and restore path was the next operational task.",
            evidence_strength="strong",
        )

        report = safe_reality_calibration_report(session, actor=owner)
        outcome = next(item for item in report.outcomes if item.prediction_id == prediction.id)

        assert outcome.outcome == "proven_correct"
        assert "Owner validation" in outcome.evidence_summary


def test_weak_owner_validation_does_not_prove_prediction() -> None:
    with session_scope() as session:
        owner = _owner(session)
        prediction = _prediction()
        session.add(prediction)
        session.flush()

        record_owner_validation(
            session,
            validation_outcome="correct",
            actor=owner,
            linked_prediction_id=prediction.id,
            summary="Looks right.",
        )

        report = safe_reality_calibration_report(session, actor=owner)
        outcome = next(item for item in report.outcomes if item.prediction_id == prediction.id)

        assert outcome.outcome != "proven_correct"


def test_partial_validation_creates_partially_correct_outcome() -> None:
    with session_scope() as session:
        owner = _owner(session)
        prediction = _prediction()
        session.add(prediction)
        session.flush()

        record_owner_validation(
            session,
            validation_outcome="partially_correct",
            actor=owner,
            linked_prediction_id=prediction.id,
            summary="Restore testing mattered, but another recovery task also appeared.",
        )

        report = safe_reality_calibration_report(session, actor=owner)
        outcome = next(item for item in report.outcomes if item.prediction_id == prediction.id)

        assert outcome.outcome == "partially_correct"


def test_strong_evidence_has_larger_calibration_effect_than_weak_evidence() -> None:
    with session_scope() as session:
        owner = _owner(session)
        for index, strength in enumerate(("weak", "strong"), start=1):
            prediction = _prediction(title=f"Calibration evidence {index}", evidence_key=f"general:s63:{index}")
            session.add(prediction)
            session.flush()
            record_owner_validation(
                session,
                validation_outcome="correct",
                actor=owner,
                linked_prediction_id=prediction.id,
                summary=f"Owner validation {index}.",
                details="Operational evidence attached." if strength == "strong" else None,
                evidence_strength=strength,
            )

        report = safe_reality_calibration_report(session, actor=owner)
        assert report.outcome_counts["proven_correct"] == 1
        assert report.outcome_counts["not_enough_evidence"] + report.outcome_counts["pending"] >= 1


def test_knowledge_lesson_creation_and_retrieval() -> None:
    with session_scope() as session:
        owner = _owner(session)
        evidence = create_evidence_record(
            session,
            evidence_type="operational_outcome",
            category="recovery",
            summary="Backup setup improved recovery faster than expected.",
            evidence_strength="strong",
            actor=owner,
        )
        lesson = create_knowledge_lesson(
            session,
            actor=owner,
            category="recovery",
            lesson="Recovery setup moved faster after external storage was configured.",
            evidence_records=[evidence],
        )

        report = safe_evidence_capture_report(session)

        assert lesson.confidence == "high"
        assert report.knowledge_count == 1
        assert session.query(KnowledgeMemory).count() == 1


def test_decision_timeline_preserves_chain() -> None:
    with session_scope() as session:
        owner = _owner(session)
        prediction = _prediction()
        session.add(prediction)
        session.flush()
        record_evidence_note(
            session,
            actor=owner,
            linked_prediction_id=prediction.id,
            summary="Owner saw restore testing become the next task.",
        )
        record_owner_validation(
            session,
            validation_outcome="partially_correct",
            actor=owner,
            linked_prediction_id=prediction.id,
            summary="Partially correct.",
        )
        safe_reality_calibration_report(session, actor=owner)

        timeline = decision_timeline(session)
        screen = render_decision_timeline_page(session, owner)

        assert timeline.available is True
        assert [step.label for step in timeline.steps] == [
            "Prediction",
            "Recommendation",
            "Evidence",
            "Owner Validation",
            "Outcome",
            "Lesson Learned",
        ]
        assert "Decision Timeline" in screen.text


def test_owner_evidence_screens_render_and_hide_raw_ids() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)
        prediction = _prediction()
        session.add(prediction)
        session.flush()

        screens = [
            render_decision_review_page(session, owner),
            render_evidence_notes_page(session, owner),
            render_knowledge_memory_page(session, owner),
            screen_for_page("owner_validation:correct", principal, session=session, user=owner),
            screen_for_page("evidence:notes:record", principal, session=session, user=owner),
            screen_for_page("knowledge:memory", principal, session=session, user=owner),
        ]

        for screen in screens:
            assert "raw" not in screen.text.casefold()
            assert "prediction_id" not in screen.text
            assert "linked_prediction_id" not in screen.text
            assert any("Back" in label for label in _buttons(screen))
            assert any("Home" in label for label in _buttons(screen))


def test_reality_observability_and_help_use_owner_evidence() -> None:
    with session_scope() as session:
        owner = _owner(session)
        prediction = _prediction()
        session.add(prediction)
        session.flush()
        record_owner_validation(
            session,
            validation_outcome="partially_correct",
            actor=owner,
            linked_prediction_id=prediction.id,
            summary="Partially correct evidence.",
        )

        reality = render_reality_check_page(session, owner)
        summary = production_observability_summary(session)
        evidence_answer = help_brain_answer(session, owner, question="What is Evidence?")
        validation_answer = help_brain_answer(session, owner, question="Can owner feedback override system records?")

        assert "What Fortuna Learned" in reality.text
        assert summary["evidence_capture_meaningful"] is True
        assert summary["owner_validation_count"] == 1
        assert "traceable record" in evidence_answer.answer
        assert "cannot override" in validation_answer.answer


def test_evidence_failure_falls_back_safely(monkeypatch) -> None:
    with session_scope() as session:
        owner = _owner(session)

        def broken(_session):
            raise RuntimeError("evidence unavailable")

        monkeypatch.setattr("app.services.evidence_capture.evidence_capture_report", broken)

        report = safe_evidence_capture_report(session)
        screen = render_decision_review_page(session, owner)

        assert report.available is False
        assert "Evidence:" in screen.text


def test_prediction_outcome_accepts_partially_correct_state() -> None:
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
            outcome="partially_correct",
        )
        session.add(outcome)
        session.flush()

        assert outcome.outcome == "partially_correct"
        assert CalibrationEngine().build_report(session).outcome_counts["partially_correct"] == 1
