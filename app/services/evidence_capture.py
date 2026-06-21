from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.decision_memory import DecisionMemory
from app.models.decision_trends import PredictiveCOOPrediction
from app.models.evidence import EvidenceRecord, KnowledgeMemory, OwnerValidation
from app.models.reality_calibration import PredictionOutcome
from app.models.user import User
from app.services.audit import sanitize_details
from app.services.events import emit_event


VALIDATION_LABELS = {
    "correct": "Correct",
    "incorrect": "Incorrect",
    "partially_correct": "Partially correct",
    "too_early": "Too early to tell",
    "add_evidence": "Evidence added",
}


@dataclass(frozen=True)
class EvidenceCaptureReport:
    available: bool
    evidence_count: int
    validation_count: int
    knowledge_count: int
    latest_evidence: EvidenceRecord | None
    latest_validation: OwnerValidation | None
    lessons: tuple[KnowledgeMemory, ...]
    learned_lines: tuple[str, ...]
    next_best_move: str
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class DecisionTimelineStep:
    label: str
    status: str
    summary: str


@dataclass(frozen=True)
class DecisionTimeline:
    available: bool
    steps: tuple[DecisionTimelineStep, ...]
    next_best_move: str
    unavailable_reason: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _actor_label(actor: User | None) -> str | None:
    if actor is None:
        return None
    return str(actor.telegram_id or actor.id)


def _default_strength(evidence_type: str, *, details: str | None = None, linked_system_record: bool = False) -> str:
    if evidence_type == "system_record":
        return "strong"
    if evidence_type == "operational_outcome":
        return "strong" if linked_system_record else "medium"
    if evidence_type == "uploaded_reference":
        return "medium"
    if evidence_type == "owner_validation":
        return "medium" if details else "weak"
    return "weak"


def _latest_prediction(session: Session) -> PredictiveCOOPrediction | None:
    return session.scalar(
        select(PredictiveCOOPrediction).order_by(desc(PredictiveCOOPrediction.created_at), desc(PredictiveCOOPrediction.id)).limit(1)
    )


def _prediction_category(prediction: PredictiveCOOPrediction | None) -> str:
    if prediction is None:
        return "general"
    key = str(prediction.evidence_key or "").casefold()
    if key.startswith("platform"):
        return "platform_connection"
    if key.startswith("friction") or key.startswith("navigation"):
        return "friction"
    text = " ".join(
        str(part or "")
        for part in (
            prediction.prediction_title,
            prediction.prediction_type,
            prediction.evidence_key,
            prediction.evidence_summary,
        )
    ).casefold()
    if "platform" in text or "login" in text or "connector" in text:
        return "platform_connection"
    if "friction" in text or "navigation" in text or "button" in text:
        return "friction"
    if "recovery" in text or "backup" in text or "restore" in text:
        return "recovery"
    if "notification" in text or "alert" in text:
        return "notification"
    if "telegram" in text or "polling" in text:
        return "telegram_bot"
    return "general"


def create_evidence_record(
    session: Session,
    *,
    evidence_type: str,
    category: str,
    summary: str,
    details: str | None = None,
    evidence_strength: str | None = None,
    linked_prediction_id: int | None = None,
    linked_decision_id: str | None = None,
    linked_recommendation_id: int | None = None,
    actor: User | None = None,
    metadata: dict | None = None,
) -> EvidenceRecord:
    strength = evidence_strength or _default_strength(
        evidence_type,
        details=details,
        linked_system_record=bool(linked_prediction_id or linked_decision_id or linked_recommendation_id),
    )
    record = EvidenceRecord(
        evidence_type=evidence_type,
        category=category,
        linked_prediction_id=linked_prediction_id,
        linked_decision_id=linked_decision_id,
        linked_recommendation_id=linked_recommendation_id,
        summary=summary,
        details=details,
        evidence_strength=strength,
        created_by=_actor_label(actor),
        metadata_json=sanitize_details(metadata or {}),
    )
    session.add(record)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name=f"evidence.created.{evidence_type}",
        resource_type="evidence_record",
        resource_id=str(record.id),
        payload=sanitize_details(
            {
                "category": category,
                "strength": strength,
                "linked_prediction": linked_prediction_id,
                "linked_decision": linked_decision_id,
                "linked_recommendation": linked_recommendation_id,
            }
        ),
    )
    return record


def record_owner_validation(
    session: Session,
    *,
    validation_outcome: str,
    actor: User | None = None,
    summary: str | None = None,
    details: str | None = None,
    linked_prediction_id: int | None = None,
    linked_decision_id: str | None = None,
    linked_recommendation_id: int | None = None,
    evidence_strength: str | None = None,
) -> OwnerValidation:
    prediction = session.get(PredictiveCOOPrediction, linked_prediction_id) if linked_prediction_id else _latest_prediction(session)
    prediction_id = linked_prediction_id or (prediction.id if prediction is not None else None)
    category = _prediction_category(prediction)
    label = VALIDATION_LABELS.get(validation_outcome, "Evidence")
    evidence = create_evidence_record(
        session,
        evidence_type="owner_validation" if validation_outcome != "add_evidence" else "owner_note",
        category=category,
        summary=summary or f"Owner marked prediction as {label.lower()}.",
        details=details,
        evidence_strength=evidence_strength,
        linked_prediction_id=prediction_id,
        linked_decision_id=linked_decision_id,
        linked_recommendation_id=linked_recommendation_id,
        actor=actor,
        metadata={"validation_outcome": validation_outcome},
    )
    validation = OwnerValidation(
        linked_prediction_id=prediction_id,
        linked_decision_id=linked_decision_id,
        linked_recommendation_id=linked_recommendation_id,
        evidence_record_id=evidence.id,
        validation_outcome=validation_outcome,
        summary=evidence.summary,
        created_by=_actor_label(actor),
        metadata_json={"evidence_strength": evidence.evidence_strength},
    )
    session.add(validation)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name=f"owner_validation.{validation_outcome}",
        resource_type="owner_validation",
        resource_id=str(validation.id),
        payload=sanitize_details(
            {
                "evidence_record_id": evidence.id,
                "linked_prediction": prediction_id,
                "strength": evidence.evidence_strength,
            }
        ),
    )
    return validation


def record_evidence_note(
    session: Session,
    *,
    summary: str,
    actor: User | None = None,
    details: str | None = None,
    linked_prediction_id: int | None = None,
    linked_decision_id: str | None = None,
    linked_recommendation_id: int | None = None,
    category: str | None = None,
) -> EvidenceRecord:
    prediction = session.get(PredictiveCOOPrediction, linked_prediction_id) if linked_prediction_id else _latest_prediction(session)
    return create_evidence_record(
        session,
        evidence_type="owner_note",
        category=category or _prediction_category(prediction),
        summary=summary,
        details=details,
        evidence_strength="weak",
        linked_prediction_id=linked_prediction_id or (prediction.id if prediction is not None else None),
        linked_decision_id=linked_decision_id,
        linked_recommendation_id=linked_recommendation_id,
        actor=actor,
    )


def create_knowledge_lesson(
    session: Session,
    *,
    lesson: str,
    actor: User | None = None,
    category: str = "general",
    evidence_records: list[EvidenceRecord] | None = None,
    confidence: str | None = None,
    source_summary: str | None = None,
) -> KnowledgeMemory:
    records = evidence_records or []
    strengths = {record.evidence_strength for record in records}
    inferred_confidence = confidence or ("high" if "strong" in strengths else "medium" if "medium" in strengths else "low")
    memory = KnowledgeMemory(
        category=category,
        lesson=lesson,
        confidence=inferred_confidence,
        evidence_record_ids=[record.id for record in records],
        source_summary=source_summary or "Lesson created from owner evidence.",
        created_by=_actor_label(actor),
        metadata_json={},
    )
    session.add(memory)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="knowledge_memory.created",
        resource_type="knowledge_memory",
        resource_id=str(memory.id),
        payload=sanitize_details({"category": category, "confidence": inferred_confidence}),
    )
    return memory


def evidence_capture_report(session: Session) -> EvidenceCaptureReport:
    evidence = list(session.scalars(select(EvidenceRecord).order_by(desc(EvidenceRecord.created_at), desc(EvidenceRecord.id))).all())
    validations = list(session.scalars(select(OwnerValidation).order_by(desc(OwnerValidation.created_at), desc(OwnerValidation.id))).all())
    lessons = tuple(session.scalars(select(KnowledgeMemory).order_by(desc(KnowledgeMemory.created_at), desc(KnowledgeMemory.id))).all())
    learned: list[str] = []
    strong = [record for record in evidence if record.evidence_strength == "strong"]
    medium = [record for record in evidence if record.evidence_strength == "medium"]
    if strong:
        learned.append(f"{strong[0].category.replace('_', ' ').title()} has strong evidence attached.")
    if validations:
        learned.append(f"Owner validation recorded: {VALIDATION_LABELS.get(validations[0].validation_outcome, validations[0].validation_outcome)}.")
    if lessons:
        learned.append(lessons[0].lesson)
    if not learned:
        learned.append("No owner evidence has been captured yet.")
    next_move = "Open Evidence Notes when a real-world outcome happens."
    if evidence and not lessons and (strong or medium):
        next_move = "Turn strong evidence into Knowledge Memory."
    return EvidenceCaptureReport(
        available=True,
        evidence_count=len(evidence),
        validation_count=len(validations),
        knowledge_count=len(lessons),
        latest_evidence=evidence[0] if evidence else None,
        latest_validation=validations[0] if validations else None,
        lessons=lessons,
        learned_lines=tuple(learned[:3]),
        next_best_move=next_move,
    )


def safe_evidence_capture_report(session: Session) -> EvidenceCaptureReport:
    try:
        return evidence_capture_report(session)
    except Exception as exc:
        return EvidenceCaptureReport(
            available=False,
            evidence_count=0,
            validation_count=0,
            knowledge_count=0,
            latest_evidence=None,
            latest_validation=None,
            lessons=(),
            learned_lines=("Evidence status is unavailable.",),
            next_best_move="Use system evidence until owner evidence is available again.",
            unavailable_reason=str(exc)[:160],
        )


def decision_timeline(session: Session) -> DecisionTimeline:
    try:
        prediction = _latest_prediction(session)
        outcome = None
        if prediction is not None:
            outcome = session.scalar(
                select(PredictionOutcome)
                .where(PredictionOutcome.prediction_id == prediction.id)
                .order_by(desc(PredictionOutcome.evaluated_at), desc(PredictionOutcome.id))
                .limit(1)
            )
        evidence = session.scalar(select(EvidenceRecord).order_by(desc(EvidenceRecord.created_at), desc(EvidenceRecord.id)).limit(1))
        validation = session.scalar(select(OwnerValidation).order_by(desc(OwnerValidation.created_at), desc(OwnerValidation.id)).limit(1))
        lesson = session.scalar(select(KnowledgeMemory).order_by(desc(KnowledgeMemory.created_at), desc(KnowledgeMemory.id)).limit(1))
        decision = session.scalar(select(DecisionMemory).order_by(desc(DecisionMemory.updated_at), desc(DecisionMemory.id)).limit(1))
        steps = (
            DecisionTimelineStep("Prediction", "Recorded" if prediction else "Waiting", prediction.prediction_title if prediction else "No prediction recorded yet."),
            DecisionTimelineStep("Recommendation", "Recorded" if decision else "Waiting", decision.evidence_summary if decision else "No linked recommendation memory yet."),
            DecisionTimelineStep("Evidence", "Captured" if evidence else "Waiting", evidence.summary if evidence else "No owner evidence captured yet."),
            DecisionTimelineStep(
                "Owner Validation",
                VALIDATION_LABELS.get(validation.validation_outcome, "Recorded") if validation else "Waiting",
                validation.summary if validation else "No owner validation recorded yet.",
            ),
            DecisionTimelineStep("Outcome", outcome.outcome.replace("_", " ").title() if outcome else "Waiting", outcome.evidence_summary if outcome else "No evaluated outcome yet."),
            DecisionTimelineStep("Lesson Learned", "Recorded" if lesson else "Waiting", lesson.lesson if lesson else "No durable lesson saved yet."),
        )
        return DecisionTimeline(
            available=True,
            steps=steps,
            next_best_move="Add evidence after the owner sees what happened in reality.",
        )
    except Exception as exc:
        return DecisionTimeline(
            available=False,
            steps=(),
            next_best_move="Use Reality Check from system evidence.",
            unavailable_reason=str(exc)[:160],
        )
