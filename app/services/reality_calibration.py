from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.button_issue import ButtonIssue
from app.models.decision_trends import PredictiveCOOPrediction
from app.models.evidence import EvidenceRecord, OwnerValidation
from app.models.platform import PlatformConnection
from app.models.reality_calibration import PredictionOutcome
from app.models.recovery import RestoreTestRun
from app.models.user import User
from app.services.audit import sanitize_details
from app.services.events import emit_event
from app.services.notification_intelligence import alert_health_summary
from app.services.platform_connections import platform_connections_status
from app.services.recovery import latest_recovery_job_summary, recovery_risk_assessment


MIN_CALIBRATION_OUTCOMES = 2
PREDICTION_WINDOW_DAYS = 30
SUPPORTED_OUTCOME_TYPES = {
    "likely_next_priority",
    "recurring_risk",
    "likely_blocker",
    "upcoming_setup_need",
    "stale_decision_warning",
    "repeated_friction_warning",
}


@dataclass(frozen=True)
class OutcomeDecision:
    outcome: str
    evidence_summary: str
    evidence_records: tuple[str, ...]
    correction_summary: str | None = None


@dataclass(frozen=True)
class CalibrationBucket:
    label: str
    scope_type: str
    scope_value: str
    total_predictions: int
    evaluated_predictions: int
    correct_count: int
    wrong_count: int
    unresolved_count: int
    unknown_count: int
    accuracy_rate: float
    overconfidence_score: int
    underconfidence_score: int
    calibration_status: str
    evidence_summary: str
    next_improvement: str


@dataclass(frozen=True)
class RealityCalibrationReport:
    available: bool
    enabled: bool
    status: str
    generated_at: datetime
    outcome_counts: dict[str, int]
    outcomes: tuple[PredictionOutcome, ...]
    confidence_buckets: tuple[CalibrationBucket, ...]
    category_buckets: tuple[CalibrationBucket, ...]
    prediction_type_buckets: tuple[CalibrationBucket, ...]
    next_best_move: str
    unavailable_reason: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _as_aware(value: datetime | None, fallback: datetime | None = None) -> datetime:
    current = value or fallback or _now()
    if current.tzinfo is None:
        return current.replace(tzinfo=UTC)
    return current


def _prediction_timestamp(prediction: PredictiveCOOPrediction) -> datetime:
    return _as_aware(prediction.shown_at or prediction.created_at or prediction.updated_at)


def _prediction_category(prediction: PredictiveCOOPrediction) -> str:
    key = str(prediction.evidence_key or "").casefold()
    if key.startswith("general"):
        return "general"
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
    if "notification" in text or "alert" in text or "routing" in text:
        return "notification"
    if "telegram" in text or "polling" in text:
        return "telegram_bot"
    if "opportun" in text:
        return "opportunity"
    return "general"


def _human_category(category: str) -> str:
    labels = {
        "recovery": "Recovery",
        "telegram_bot": "Telegram Bot",
        "notification": "Notifications",
        "platform_connection": "Platforms",
        "navigation": "Navigation",
        "friction": "Friction",
        "opportunity": "Opportunities",
        "general": "General",
    }
    return labels.get(category, category.replace("_", " ").title())


def _confidence_weight(confidence: str) -> float:
    return {"high": 0.8, "medium": 0.6, "low": 0.4}.get(confidence, 0.5)


def _confidence_label(label: str) -> str:
    return {
        "high": "High Confidence",
        "medium": "Medium Confidence",
        "low": "Low Confidence",
    }.get(label, label.replace("_", " ").title())


def _latest_restore_after(session: Session, predicted_at: datetime) -> RestoreTestRun | None:
    restores = list(
        session.scalars(select(RestoreTestRun).order_by(desc(RestoreTestRun.finished_at), desc(RestoreTestRun.id))).all()
    )
    for restore in restores:
        seen_at = _as_aware(restore.finished_at or restore.started_at)
        if seen_at > predicted_at:
            return restore
    return None


def _restore_passed_at_or_before(session: Session, predicted_at: datetime) -> bool:
    restores = list(session.scalars(select(RestoreTestRun)).all())
    for restore in restores:
        seen_at = _as_aware(restore.finished_at or restore.started_at)
        if (
            seen_at <= predicted_at
            and restore.status in {"passed", "succeeded"}
            and bool(restore.full_restore_performed)
        ):
            return True
    return False


class PredictionEvaluationEngine:
    """Evaluates predictions against later evidence without treating silence as correctness."""

    def evaluate_predictions(self, session: Session, *, actor: User | None = None) -> RealityCalibrationReport:
        if not settings.reality_calibration_enabled:
            return RealityCalibrationReport(
                available=True,
                enabled=False,
                status="disabled",
                generated_at=_now(),
                outcome_counts={},
                outcomes=(),
                confidence_buckets=(),
                category_buckets=(),
                prediction_type_buckets=(),
                next_best_move="Reality Calibration is disabled.",
            )
        predictions = list(
            session.scalars(select(PredictiveCOOPrediction).order_by(PredictiveCOOPrediction.created_at, PredictiveCOOPrediction.id)).all()
        )
        outcomes = tuple(self.evaluate_prediction(session, prediction, actor=actor) for prediction in predictions)
        session.flush()
        return CalibrationEngine().build_report(session, outcomes=outcomes)

    def evaluate_prediction(
        self,
        session: Session,
        prediction: PredictiveCOOPrediction,
        *,
        actor: User | None = None,
    ) -> PredictionOutcome:
        category = _prediction_category(prediction)
        predicted_at = _prediction_timestamp(prediction)
        outcome = session.scalar(
            select(PredictionOutcome)
            .where(PredictionOutcome.prediction_id == prediction.id)
            .order_by(desc(PredictionOutcome.id))
            .limit(1)
        )
        if outcome is None:
            outcome = PredictionOutcome(
                prediction_id=prediction.id,
                prediction_type=prediction.prediction_type,
                category=category,
                confidence_at_prediction=prediction.confidence,
                predicted_at=predicted_at,
                due_at=predicted_at + timedelta(days=PREDICTION_WINDOW_DAYS),
                outcome="pending",
                evidence_summary="Waiting for evidence.",
                evidence_records=[],
            )
            session.add(outcome)
        outcome.prediction_type = prediction.prediction_type
        outcome.category = category
        outcome.confidence_at_prediction = prediction.confidence
        outcome.predicted_at = predicted_at
        outcome.due_at = outcome.due_at or predicted_at + timedelta(days=PREDICTION_WINDOW_DAYS)

        decision = self._evaluate_by_type(session, prediction, category=category, predicted_at=predicted_at)
        decision = self._apply_owner_evidence(session, prediction, decision)
        now = _now()
        if decision.outcome == "pending" and outcome.due_at and now > _as_aware(outcome.due_at):
            decision = OutcomeDecision(
                outcome="expired",
                evidence_summary="The prediction window passed without enough proof.",
                evidence_records=decision.evidence_records,
                correction_summary="Review whether this prediction is still useful.",
            )
        outcome.outcome = decision.outcome
        outcome.evaluated_at = now
        outcome.evidence_summary = decision.evidence_summary
        outcome.evidence_records = list(decision.evidence_records)
        outcome.correction_summary = decision.correction_summary
        session.flush()
        emit_event(
            session,
            actor=actor,
            event_name=f"prediction.evaluated.{outcome.outcome}",
            resource_type="prediction_outcome",
            resource_id=str(outcome.id),
            payload=sanitize_details(
                {
                    "prediction_type": outcome.prediction_type,
                    "category": outcome.category,
                    "confidence": outcome.confidence_at_prediction,
                    "evidence_summary": outcome.evidence_summary,
                }
            ),
        )
        return outcome

    def _evaluate_by_type(
        self,
        session: Session,
        prediction: PredictiveCOOPrediction,
        *,
        category: str,
        predicted_at: datetime,
    ) -> OutcomeDecision:
        if prediction.prediction_type not in SUPPORTED_OUTCOME_TYPES:
            return OutcomeDecision(
                "not_enough_evidence",
                "This prediction type does not have an evaluator yet.",
                (f"PredictiveCOOPrediction:{prediction.id}",),
                "Add an explicit evaluation rule before trusting this prediction type.",
            )
        if category == "recovery":
            return self._evaluate_recovery(session, prediction, predicted_at=predicted_at)
        if category == "platform_connection":
            return self._evaluate_platforms(session)
        if category == "notification":
            return self._evaluate_notifications(session)
        if category in {"friction", "navigation"}:
            return self._evaluate_friction(session)
        return OutcomeDecision(
            "not_enough_evidence",
            "Fortuna does not have enough supported evidence for this prediction yet.",
            (f"PredictiveCOOPrediction:{prediction.id}",),
            "Keep the prediction visible as learning, not proof.",
        )

    def _evaluate_recovery(
        self,
        session: Session,
        prediction: PredictiveCOOPrediction,
        *,
        predicted_at: datetime,
    ) -> OutcomeDecision:
        recovery = recovery_risk_assessment(session)
        job = latest_recovery_job_summary(session)
        evidence = (
            f"Backup: {job['latest_backup_status']}; restore: {job['latest_restore_status']}; "
            f"recovery status: {recovery.status}."
        )
        if "restore" in prediction.prediction_title.casefold() or "restore_path" in prediction.evidence_key:
            if _restore_passed_at_or_before(session, predicted_at):
                return OutcomeDecision(
                    "proven_wrong",
                    "Full restore evidence already existed when the restore-test blocker prediction was made.",
                    ("RestoreTestRun:full_restore_before_prediction",),
                    "Do not repeat restore-test blocker predictions after full restore evidence exists.",
                )
            later_restore = _latest_restore_after(session, predicted_at)
            if later_restore is None:
                return OutcomeDecision(
                    "pending",
                    "Waiting for later restore-test evidence.",
                    ("RestoreTestRun:pending",),
                )
            if later_restore.status in {"passed", "succeeded"} and later_restore.full_restore_performed:
                return OutcomeDecision(
                    "proven_correct",
                    "Later evidence shows the restore-test path was addressed with a full restore validation.",
                    (f"RestoreTestRun:{later_restore.id}",),
                )
            if later_restore.status in {"verified_only", "verified", "not_available", "failed"}:
                return OutcomeDecision(
                    "proven_correct",
                    "Later restore evidence confirms full restore testing was still the recovery blocker.",
                    (f"RestoreTestRun:{later_restore.id}",),
                )
            return OutcomeDecision("unresolved", evidence, (f"RestoreTestRun:{later_restore.id}",))
        if recovery.status in {"critical", "needs_attention"}:
            return OutcomeDecision(
                "proven_correct",
                "Recovery remained an active priority after the prediction.",
                ("RecoveryAssessment:current",),
            )
        if recovery.status == "healthy":
            return OutcomeDecision(
                "unresolved",
                "Recovery is currently healthy, so the earlier recovery prediction no longer needs owner attention.",
                ("RecoveryAssessment:healthy",),
            )
        return OutcomeDecision("pending", evidence, ("RecoveryAssessment:current",))

    def _evaluate_platforms(self, session: Session) -> OutcomeDecision:
        statuses = platform_connections_status(session)
        if not statuses:
            return OutcomeDecision("not_enough_evidence", "No platform status records were available.", ())
        failures = [
            item
            for item in statuses
            if item.connection.status == "failed" or item.stats.status == "failed" or item.readiness.status in {"needs_attention", "critical"}
        ]
        if failures:
            first = failures[0]
            return OutcomeDecision(
                "proven_wrong",
                f"{first.display_name} needed platform attention, so the can-wait prediction was not safe.",
                (f"PlatformConnection:{first.platform}",),
                "Escalate platform setup only when an active workflow depends on it.",
            )
        waiting = [item for item in statuses if item.connection.status in {"ready_to_connect", "not_connected"}]
        if waiting:
            return OutcomeDecision(
                "proven_correct",
                "Platform logins are still waiting for final activation and have not blocked operations.",
                tuple(f"PlatformConnection:{item.platform}" for item in waiting[:5]),
            )
        return OutcomeDecision(
            "unresolved",
            "Platform connection state has changed; no blocking failure was found.",
            tuple(f"PlatformConnection:{item.platform}" for item in statuses[:5]),
        )

    def _evaluate_notifications(self, session: Session) -> OutcomeDecision:
        alert_health = alert_health_summary(session)
        if alert_health.status in {"needs_attention", "critical"} or alert_health.failed_attempts:
            return OutcomeDecision(
                "proven_correct",
                "Notification evidence shows alert routing needs attention.",
                ("AlertHealth:current",),
            )
        if alert_health.status == "healthy":
            return OutcomeDecision(
                "unresolved",
                "Notification routing is currently healthy, so the prediction is not an active blocker.",
                ("AlertHealth:healthy",),
            )
        return OutcomeDecision(
            "not_enough_evidence",
            "Notification routing does not have enough rollout evidence yet.",
            ("AlertHealth:insufficient",),
        )

    def _evaluate_friction(self, session: Session) -> OutcomeDecision:
        open_issue = session.scalar(
            select(ButtonIssue).where(ButtonIssue.status == "open").order_by(desc(ButtonIssue.detected_at), desc(ButtonIssue.id)).limit(1)
        )
        if open_issue is not None:
            return OutcomeDecision(
                "proven_correct",
                "A continuing Button Health issue supports the friction prediction.",
                (f"ButtonIssue:{open_issue.id}",),
            )
        return OutcomeDecision(
            "unresolved",
            "No open Button Health issue currently proves or disproves the friction prediction.",
            ("ButtonIssue:none_open",),
        )

    def _apply_owner_evidence(
        self,
        session: Session,
        prediction: PredictiveCOOPrediction,
        decision: OutcomeDecision,
    ) -> OutcomeDecision:
        validations = list(
            session.scalars(
                select(OwnerValidation)
                .where(OwnerValidation.linked_prediction_id == prediction.id)
                .order_by(desc(OwnerValidation.created_at), desc(OwnerValidation.id))
            ).all()
        )
        evidence = list(
            session.scalars(
                select(EvidenceRecord)
                .where(EvidenceRecord.linked_prediction_id == prediction.id)
                .order_by(desc(EvidenceRecord.created_at), desc(EvidenceRecord.id))
            ).all()
        )
        if not validations and not evidence:
            return decision
        latest_validation = validations[0] if validations else None
        supporting_records = tuple(f"EvidenceRecord:{record.id}" for record in evidence[:5])
        strongest = next((record for record in evidence if record.evidence_strength == "strong"), None)
        medium = next((record for record in evidence if record.evidence_strength == "medium"), None)
        if latest_validation is None:
            if strongest is not None and decision.outcome in {"pending", "unresolved", "not_enough_evidence"}:
                return OutcomeDecision(
                    "partially_correct",
                    f"Owner evidence supports this prediction but needs validation: {strongest.summary}",
                    supporting_records or decision.evidence_records,
                    "Review owner evidence before marking fully correct.",
                )
            return decision
        validation = latest_validation.validation_outcome
        strength = str((latest_validation.metadata_json or {}).get("evidence_strength") or "")
        strong_enough = strength in {"medium", "strong"} or strongest is not None or medium is not None
        if validation == "too_early":
            return OutcomeDecision(
                "unresolved",
                "Owner validation says it is too early to tell.",
                supporting_records or decision.evidence_records,
            )
        if validation == "partially_correct":
            return OutcomeDecision(
                "partially_correct",
                f"Owner validation says this was partially correct: {latest_validation.summary}",
                supporting_records or decision.evidence_records,
                "Keep uncertainty visible and collect stronger evidence.",
            )
        if validation == "correct":
            if decision.outcome == "proven_wrong":
                return OutcomeDecision(
                    "partially_correct",
                    "Owner validation supports the prediction, but system evidence contradicts it.",
                    supporting_records + decision.evidence_records,
                    "Review disagreement between owner evidence and system records.",
                )
            if strong_enough and decision.outcome in {"pending", "unresolved", "not_enough_evidence", "expired"}:
                return OutcomeDecision(
                    "proven_correct",
                    f"Owner validation with evidence supports the prediction: {latest_validation.summary}",
                    supporting_records or decision.evidence_records,
                )
        if validation == "incorrect":
            if decision.outcome == "proven_correct":
                return OutcomeDecision(
                    "partially_correct",
                    "Owner validation contradicts system evidence that supported the prediction.",
                    supporting_records + decision.evidence_records,
                    "Review disagreement before changing future confidence.",
                )
            if strong_enough and decision.outcome in {"pending", "unresolved", "not_enough_evidence", "expired"}:
                return OutcomeDecision(
                    "proven_wrong",
                    f"Owner validation with evidence contradicts the prediction: {latest_validation.summary}",
                    supporting_records or decision.evidence_records,
                    "Use this correction to reduce similar prediction confidence.",
                )
        return decision


class CalibrationEngine:
    """Measures confidence accuracy from evaluated prediction outcomes."""

    def build_report(
        self,
        session: Session,
        *,
        outcomes: tuple[PredictionOutcome, ...] | None = None,
    ) -> RealityCalibrationReport:
        records = tuple(outcomes if outcomes is not None else session.scalars(select(PredictionOutcome)).all())
        counts = {
            name: 0
            for name in (
                "pending",
                "partially_correct",
                "proven_correct",
                "proven_wrong",
                "unresolved",
                "expired",
                "not_enough_evidence",
            )
        }
        for outcome in records:
            counts[outcome.outcome] = counts.get(outcome.outcome, 0) + 1
        confidence_buckets = tuple(self._bucket(records, "confidence", value, _confidence_label(value)) for value in ("high", "medium", "low"))
        categories = sorted({outcome.category for outcome in records} | {"recovery", "telegram_bot", "notification", "platform_connection", "navigation", "friction", "opportunity"})
        category_buckets = tuple(self._bucket(records, "category", category, _human_category(category)) for category in categories)
        prediction_types = sorted({outcome.prediction_type for outcome in records})
        prediction_type_buckets = tuple(self._bucket(records, "prediction_type", value, value.replace("_", " ").title()) for value in prediction_types)
        available_records = [bucket for bucket in confidence_buckets if bucket.calibration_status != "insufficient_data"]
        status = "learning"
        if any(bucket.calibration_status == "overconfident" for bucket in available_records):
            status = "needs_review"
        elif available_records and all(bucket.calibration_status == "calibrated" for bucket in available_records):
            status = "calibrated"
        next_move = self._next_best_move(counts, confidence_buckets)
        return RealityCalibrationReport(
            available=True,
            enabled=settings.reality_calibration_enabled,
            status=status,
            generated_at=_now(),
            outcome_counts=counts,
            outcomes=records,
            confidence_buckets=confidence_buckets,
            category_buckets=category_buckets,
            prediction_type_buckets=prediction_type_buckets,
            next_best_move=next_move,
        )

    def _bucket(
        self,
        records: tuple[PredictionOutcome, ...],
        scope_type: str,
        scope_value: str,
        label: str,
    ) -> CalibrationBucket:
        attr = "confidence_at_prediction" if scope_type == "confidence" else scope_type
        scoped = [outcome for outcome in records if getattr(outcome, attr) == scope_value]
        evaluated = [item for item in scoped if item.outcome in {"partially_correct", "proven_correct", "proven_wrong"}]
        correct = sum(1 for item in evaluated if item.outcome == "proven_correct")
        wrong = sum(1 for item in evaluated if item.outcome == "proven_wrong")
        partial = sum(1 for item in evaluated if item.outcome == "partially_correct")
        unresolved = sum(1 for item in scoped if item.outcome in {"pending", "unresolved"})
        unknown = sum(1 for item in scoped if item.outcome in {"expired", "not_enough_evidence"})
        if len(evaluated) < MIN_CALIBRATION_OUTCOMES:
            return CalibrationBucket(
                label=label,
                scope_type=scope_type,
                scope_value=scope_value,
                total_predictions=len(scoped),
                evaluated_predictions=len(evaluated),
                correct_count=correct,
                wrong_count=wrong,
                unresolved_count=unresolved,
                unknown_count=unknown,
                accuracy_rate=0.0,
                overconfidence_score=0,
                underconfidence_score=0,
                calibration_status="insufficient_data",
                evidence_summary="Not enough evaluated predictions yet.",
                next_improvement="Keep collecting evidence before changing confidence.",
            )
        accuracy = (correct + (partial * 0.5)) / len(evaluated)
        expected = _confidence_weight(scope_value) if scope_type == "confidence" else 0.6
        overconfidence = max(0, int(round((expected - accuracy) * 100)))
        underconfidence = max(0, int(round((accuracy - expected) * 100)))
        if overconfidence >= 20:
            status = "overconfident"
            evidence = f"{label} accuracy is {int(accuracy * 100)}%, below its confidence target."
            next_improvement = "Reduce confidence wording and require stronger evidence."
        elif underconfidence >= 25:
            status = "underconfident"
            evidence = f"{label} accuracy is {int(accuracy * 100)}%, higher than its conservative target."
            next_improvement = "Allow confidence to rise when evidence is strong."
        else:
            status = "calibrated"
            evidence = f"{label} accuracy is {int(accuracy * 100)}% across evaluated predictions."
            next_improvement = "Keep evaluating predictions with later evidence."
        return CalibrationBucket(
            label=label,
            scope_type=scope_type,
            scope_value=scope_value,
            total_predictions=len(scoped),
            evaluated_predictions=len(evaluated),
            correct_count=correct,
            wrong_count=wrong,
            unresolved_count=unresolved,
            unknown_count=unknown,
            accuracy_rate=accuracy,
            overconfidence_score=overconfidence,
            underconfidence_score=underconfidence,
            calibration_status=status,
            evidence_summary=evidence,
            next_improvement=next_improvement,
        )

    def _next_best_move(self, counts: dict[str, int], confidence_buckets: tuple[CalibrationBucket, ...]) -> str:
        if not sum(counts.values()):
            return "Open Prediction Preview so Fortuna has predictions to evaluate."
        if counts.get("pending", 0):
            return "Wait for real evidence before marking pending predictions right or wrong."
        overconfident = next((bucket for bucket in confidence_buckets if bucket.calibration_status == "overconfident"), None)
        if overconfident is not None:
            return overconfident.next_improvement
        return "Keep using prediction feedback and evidence notes."

    def adjusted_confidence(self, confidence: str, *, category: str, prediction_type: str, session: Session) -> str:
        if not settings.reality_calibration_enabled:
            return confidence
        records = tuple(session.scalars(select(PredictionOutcome)).all())
        category_bucket = self._bucket(records, "category", category, _human_category(category))
        type_bucket = self._bucket(records, "prediction_type", prediction_type, prediction_type.replace("_", " ").title())
        buckets = [bucket for bucket in (category_bucket, type_bucket) if bucket.calibration_status != "insufficient_data"]
        if any(bucket.calibration_status == "overconfident" for bucket in buckets):
            return {"high": "medium", "medium": "low"}.get(confidence, confidence)
        if confidence == "low" and any(bucket.calibration_status == "underconfident" for bucket in buckets):
            return "medium"
        return confidence


def safe_reality_calibration_report(session: Session, *, actor: User | None = None) -> RealityCalibrationReport:
    try:
        return PredictionEvaluationEngine().evaluate_predictions(session, actor=actor)
    except Exception as exc:
        try:
            emit_event(
                session,
                actor=actor,
                event_name="reality_calibration.unavailable",
                resource_type="prediction_outcome",
                status="warning",
                payload={"error": str(exc)[:160]},
            )
        except Exception:
            pass
        return RealityCalibrationReport(
            available=False,
            enabled=settings.reality_calibration_enabled,
            status="unavailable",
            generated_at=_now(),
            outcome_counts={},
            outcomes=(),
            confidence_buckets=(),
            category_buckets=(),
            prediction_type_buckets=(),
            next_best_move="Use COO Briefing from current evidence.",
            unavailable_reason=str(exc)[:160],
        )


def safe_adjust_prediction_confidence(
    session: Session,
    *,
    confidence: str,
    category: str,
    prediction_type: str,
) -> str:
    try:
        return CalibrationEngine().adjusted_confidence(confidence, category=category, prediction_type=prediction_type, session=session)
    except Exception:
        return confidence


def record_prediction_outcome_feedback(
    session: Session,
    *,
    action: str,
    actor: User | None = None,
    evidence_summary: str | None = None,
) -> PredictionOutcome | None:
    report = safe_reality_calibration_report(session, actor=actor)
    outcome = next((item for item in report.outcomes if item.outcome in {"pending", "unresolved", "not_enough_evidence"}), None)
    if outcome is None and report.outcomes:
        outcome = report.outcomes[0]
    if outcome is None:
        return None
    if action == "still_pending":
        outcome.outcome = "unresolved"
        outcome.evidence_summary = "Owner confirmed this prediction is still pending evidence."
        outcome.correction_summary = None
    elif action == "add_evidence":
        outcome.evidence_summary = evidence_summary or "Owner requested an evidence note for this prediction."
        outcome.correction_summary = "Owner evidence should be reviewed before marking correctness."
    elif action in {"right", "wrong"}:
        if evidence_summary:
            outcome.outcome = "proven_correct" if action == "right" else "proven_wrong"
            outcome.evidence_summary = evidence_summary
            outcome.correction_summary = None if action == "right" else "Owner supplied contradicting evidence."
        else:
            outcome.correction_summary = (
                "Owner said this looked right, but no evidence was attached."
                if action == "right"
                else "Owner said this looked wrong, but no contradicting evidence was attached."
            )
    outcome.evaluated_at = _now()
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name=f"prediction.outcome_feedback.{action}",
        resource_type="prediction_outcome",
        resource_id=str(outcome.id),
        payload=sanitize_details(
            {
                "outcome": outcome.outcome,
                "category": outcome.category,
                "evidence_attached": bool(evidence_summary),
            }
        ),
    )
    return outcome
