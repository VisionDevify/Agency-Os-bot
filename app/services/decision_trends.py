from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from hashlib import sha256
from typing import Iterable

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.decision_memory import DecisionMemory
from app.models.decision_trends import DecisionQualityTrend, PredictiveCOOPrediction
from app.models.platform import PlatformConnection
from app.models.user import User
from app.services.audit import sanitize_details
from app.services.decision_engine import DECISION_CATEGORIES, CATEGORY_LABELS, Decision, generate_decisions
from app.services.events import emit_event
from app.services.notification_intelligence import alert_health_summary
from app.services.platform_connections import platform_connections_overview
from app.services.recovery import latest_recovery_job_summary, recovery_risk_assessment


TREND_CATEGORIES = (
    "recovery",
    "telegram_bot",
    "notification",
    "platform_connection",
    "opportunity",
    "navigation",
    "friction",
)
MIN_TREND_RECORDS = 3


@dataclass(frozen=True)
class CategoryTrendSummary:
    category: str
    label: str
    direction: str
    reason: str
    next_action: str
    decisions_shown: int
    decisions_opened: int
    decisions_acted_on: int
    decisions_resolved: int
    decisions_ignored: int
    usefulness_score_avg: int
    confidence_accuracy_avg: int
    recommendation_score_avg: int


@dataclass(frozen=True)
class DecisionTrendReport:
    available: bool
    status: str
    generated_at: datetime
    trends: tuple[CategoryTrendSummary, ...]
    insights: tuple[str, ...]
    next_best_move: str
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class Prediction:
    prediction_title: str
    prediction_type: str
    confidence: str
    reason: str
    evidence_summary: str
    recommended_next_action: str
    can_wait: bool
    created_at: datetime
    evidence_key: str


@dataclass(frozen=True)
class PredictionQualitySummary:
    prediction_count: int
    helpful_rate: float
    acted_on_rate: float
    proven_correct_rate: float
    proven_wrong_rate: float
    confidence_accuracy: int


@dataclass(frozen=True)
class PredictiveCOOReport:
    available: bool
    enabled: bool
    status: str
    generated_at: datetime
    predictions: tuple[Prediction, ...]
    primary: Prediction | None
    current_critical_active: bool
    quality: PredictionQualitySummary
    next_best_move: str
    unavailable_reason: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def _clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, value))


def _hash_text(*parts: object) -> str:
    return sha256("|".join(str(part or "") for part in parts).encode("utf-8")).hexdigest()[:32]


def _confidence_score(value: str) -> int:
    return {"high": 88, "medium": 68, "low": 42}.get(value, 55)


def _outcome_score(memory: DecisionMemory) -> int:
    outcome = memory.outcome or "shown"
    if outcome == "resolved":
        return 95
    if outcome == "acted_on":
        return 82
    if outcome == "opened":
        return 62
    if outcome in {"ignored", "dismissed"}:
        return 42
    if outcome == "failed":
        return 20
    return 50


def _confidence_accuracy(memory: DecisionMemory) -> int:
    outcome = _outcome_score(memory)
    confidence = _confidence_score(memory.confidence or "medium")
    return _clamp(100 - abs(confidence - outcome))


def _recommendation_score(memory: DecisionMemory) -> int:
    metadata = memory.metadata_json or {}
    value = metadata.get("recommendation_quality_score")
    if isinstance(value, int):
        return _clamp(value)
    return _clamp(int(memory.usefulness_score or 0))


def _human_category(category: str) -> str:
    return CATEGORY_LABELS.get(category, category.replace("_", " ").title())


class DecisionTrendEngine:
    """Calculate deterministic Decision Memory trends without inventing outcomes."""

    def calculate_category_trend(
        self,
        session: Session,
        *,
        category: str,
        time_window: str = "weekly",
        persist: bool = True,
    ) -> CategoryTrendSummary:
        memories = list(
            session.scalars(
                select(DecisionMemory)
                .where(DecisionMemory.category == category)
                .order_by(DecisionMemory.shown_at, DecisionMemory.id)
            ).all()
        )
        total = len(memories)
        opened = sum(1 for item in memories if item.opened_at is not None or item.outcome in {"opened", "acted_on", "resolved"})
        acted = sum(1 for item in memories if item.acted_on_at is not None or item.outcome in {"acted_on", "resolved"})
        resolved = sum(1 for item in memories if item.resolved_at is not None or item.outcome == "resolved")
        ignored = sum(1 for item in memories if item.outcome in {"ignored", "dismissed"})
        usefulness = int(round(sum(item.usefulness_score or 0 for item in memories) / total)) if total else 0
        confidence_accuracy = int(round(sum(_confidence_accuracy(item) for item in memories) / total)) if total else 0
        recommendation_score = int(round(sum(_recommendation_score(item) for item in memories) / total)) if total else 0

        if total < MIN_TREND_RECORDS:
            direction = "insufficient_data"
            reason = "Not enough decision memory records yet."
            next_action = "Keep using feedback buttons so Fortuna can learn."
        else:
            success_rate = (acted + resolved) / total
            ignored_rate = ignored / total
            if success_rate >= 0.45 and usefulness >= 55:
                direction = "improving"
                reason = f"{_human_category(category)} recommendations are being acted on or resolved."
                next_action = "Keep recording outcomes when this work improves."
            elif ignored_rate >= 0.5 and usefulness < 50:
                direction = "declining"
                reason = f"{_human_category(category)} recommendations are often ignored or dismissed."
                next_action = "Review whether these recommendations are still useful."
            else:
                direction = "stable"
                reason = f"{_human_category(category)} recommendations are steady but not clearly improving yet."
                next_action = "Keep gathering outcome evidence."

        summary = CategoryTrendSummary(
            category=category,
            label=_human_category(category),
            direction=direction,
            reason=reason,
            next_action=next_action,
            decisions_shown=total,
            decisions_opened=opened,
            decisions_acted_on=acted,
            decisions_resolved=resolved,
            decisions_ignored=ignored,
            usefulness_score_avg=usefulness,
            confidence_accuracy_avg=confidence_accuracy,
            recommendation_score_avg=recommendation_score,
        )
        if persist:
            self._upsert_trend(session, summary, time_window=time_window)
        return summary

    def calculate_trends(self, session: Session, *, time_window: str = "weekly") -> DecisionTrendReport:
        categories = set(TREND_CATEGORIES)
        categories.update(session.scalars(select(DecisionMemory.category).distinct()).all())
        ordered = [category for category in TREND_CATEGORIES if category in categories]
        ordered.extend(sorted(category for category in categories if category not in ordered and category in DECISION_CATEGORIES))
        trends = tuple(self.calculate_category_trend(session, category=category, time_window=time_window) for category in ordered)
        meaningful = [trend for trend in trends if trend.direction != "insufficient_data"]
        improving = [trend for trend in trends if trend.direction == "improving"]
        declining = [trend for trend in trends if trend.direction == "declining"]
        status = "learning"
        if declining:
            status = "needs_review"
        elif improving:
            status = "improving"
        insights = self._insights(trends)
        next_move = (
            declining[0].next_action
            if declining
            else "Keep using Helpful / Dismiss / Remind Later so Fortuna can learn."
            if not meaningful
            else "Keep recording outcomes for the categories that matter most."
        )
        return DecisionTrendReport(
            available=True,
            status=status,
            generated_at=_now(),
            trends=trends,
            insights=insights,
            next_best_move=next_move,
        )

    def _upsert_trend(self, session: Session, summary: CategoryTrendSummary, *, time_window: str) -> DecisionQualityTrend:
        trend = session.scalar(
            select(DecisionQualityTrend)
            .where(DecisionQualityTrend.category == summary.category, DecisionQualityTrend.time_window == time_window)
            .limit(1)
        )
        if trend is None:
            trend = DecisionQualityTrend(category=summary.category, time_window=time_window)
            session.add(trend)
        trend.decisions_shown = summary.decisions_shown
        trend.decisions_opened = summary.decisions_opened
        trend.decisions_acted_on = summary.decisions_acted_on
        trend.decisions_resolved = summary.decisions_resolved
        trend.decisions_ignored = summary.decisions_ignored
        trend.usefulness_score_avg = summary.usefulness_score_avg
        trend.confidence_accuracy_avg = summary.confidence_accuracy_avg
        trend.recommendation_score_avg = summary.recommendation_score_avg
        trend.trend_direction = summary.direction
        trend.evidence_summary = summary.reason
        session.flush()
        return trend

    def _insights(self, trends: Iterable[CategoryTrendSummary]) -> tuple[str, ...]:
        lines: list[str] = []
        for trend in trends:
            if trend.direction == "improving":
                lines.append(f"{trend.label} recommendations are being acted on.")
            elif trend.direction == "declining":
                lines.append(f"{trend.label} recommendations may need review.")
            elif trend.category == "platform_connection" and trend.direction in {"stable", "insufficient_data"}:
                lines.append("Platform setup items can stay quiet until final activation.")
        if not lines:
            lines.append("Fortuna needs more outcome data before calling a trend.")
        return tuple(dict.fromkeys(lines))[:4]


class PredictiveCOOEngine:
    """Evidence-backed deterministic prediction layer for future COO briefings."""

    def generate_predictions(
        self,
        session: Session,
        *,
        decisions: tuple[Decision, ...] | list[Decision] | None = None,
        actor: User | None = None,
    ) -> PredictiveCOOReport:
        if not settings.predictive_coo_enabled:
            return PredictiveCOOReport(
                available=True,
                enabled=False,
                status="disabled",
                generated_at=_now(),
                predictions=(),
                primary=None,
                current_critical_active=False,
                quality=self.prediction_quality(session),
                next_best_move="Predictive COO is disabled.",
            )
        current_decisions = tuple(decisions if decisions is not None else generate_decisions(session, actor=actor))
        current_critical = any(decision.severity == "critical" and not decision.can_wait for decision in current_decisions)
        trends = safe_decision_trend_report(session)
        predictions = []
        predictions.extend(self._recovery_predictions(session, trends=trends))
        predictions.extend(self._platform_predictions(session))
        predictions.extend(self._notification_predictions(session))
        predictions.extend(self._friction_predictions(trends))
        ranked = tuple(self._rank_predictions(predictions))
        for prediction in ranked[:4]:
            self._record_prediction(session, prediction, actor=actor, action="shown")
        primary = None if current_critical else next((prediction for prediction in ranked if not prediction.can_wait), ranked[0] if ranked else None)
        return PredictiveCOOReport(
            available=True,
            enabled=True,
            status="learning" if ranked else "insufficient_data",
            generated_at=_now(),
            predictions=ranked,
            primary=primary,
            current_critical_active=current_critical,
            quality=self.prediction_quality(session),
            next_best_move=primary.recommended_next_action if primary else "Current verified priorities still come first.",
        )

    def prediction_quality(self, session: Session) -> PredictionQualitySummary:
        records = list(session.scalars(select(PredictiveCOOPrediction)).all())
        total = len(records)
        if not total:
            return PredictionQualitySummary(0, 0.0, 0.0, 0.0, 0.0, 0)
        helpful = sum(1 for item in records if item.status == "helpful")
        acted = sum(1 for item in records if item.acted_on_at is not None or item.status == "acted_on")
        correct = sum(1 for item in records if item.status == "proven_correct")
        wrong = sum(1 for item in records if item.status == "proven_wrong")
        confidence_points = []
        for item in records:
            expected = _confidence_score(item.confidence)
            outcome = 90 if item.status == "proven_correct" else 20 if item.status == "proven_wrong" else 65 if item.status in {"helpful", "acted_on"} else 50
            confidence_points.append(_clamp(100 - abs(expected - outcome)))
        return PredictionQualitySummary(
            prediction_count=total,
            helpful_rate=helpful / total,
            acted_on_rate=acted / total,
            proven_correct_rate=correct / total,
            proven_wrong_rate=wrong / total,
            confidence_accuracy=int(round(sum(confidence_points) / total)),
        )

    def record_feedback(
        self,
        session: Session,
        *,
        action: str,
        actor: User | None = None,
        evidence_summary: str | None = None,
    ) -> PredictiveCOOPrediction | None:
        report = self.generate_predictions(session, actor=actor)
        prediction = report.primary or (report.predictions[0] if report.predictions else None)
        if prediction is None:
            return None
        if action in {"proven_correct", "proven_wrong"} and not evidence_summary:
            return self._record_prediction(session, prediction, actor=actor, action="opened")
        return self._record_prediction(session, prediction, actor=actor, action=action, evidence_summary=evidence_summary)

    def _recovery_predictions(self, session: Session, *, trends: DecisionTrendReport) -> list[Prediction]:
        recovery = recovery_risk_assessment(session)
        job = latest_recovery_job_summary(session)
        predictions: list[Prediction] = []
        if job["latest_backup_status"] in {"success", "succeeded"} and job["latest_restore_status"] in {"verified_only", "verified"}:
            predictions.append(
                Prediction(
                    prediction_title="Restore-test path is likely the next recovery blocker",
                    prediction_type="likely_blocker",
                    confidence="medium",
                    reason="Backups are verified, but full restore testing still needs a restore database or test path.",
                    evidence_summary=f"Latest backup is {job['latest_backup_status']}; latest restore validation is {job['latest_restore_status']}.",
                    recommended_next_action="Create a restore-test database path when you are ready.",
                    can_wait=recovery.status in {"healthy", "needs_review"},
                    created_at=_now(),
                    evidence_key=_hash_text("recovery_restore_path", job["latest_backup_status"], job["latest_restore_status"]),
                )
            )
        elif recovery.status in {"critical", "needs_attention"}:
            predictions.append(
                Prediction(
                    prediction_title="Recovery setup will keep driving priority until backup evidence is complete",
                    prediction_type="likely_next_priority",
                    confidence="high" if recovery.evidence else "medium",
                    reason="Recovery is a current verified risk, so it remains more important than future setup items.",
                    evidence_summary="; ".join(recovery.evidence[:2]) or recovery.next_best_move,
                    recommended_next_action=recovery.next_best_move,
                    can_wait=False,
                    created_at=_now(),
                    evidence_key=_hash_text("recovery_current", recovery.status, recovery.risk_score),
                )
            )
        if trends.available:
            recovery_trend = next((trend for trend in trends.trends if trend.category == "recovery"), None)
            if recovery_trend and recovery_trend.direction == "improving":
                predictions.append(
                    Prediction(
                        prediction_title="Recovery recommendations are starting to pay off",
                        prediction_type="recurring_risk",
                        confidence="medium",
                        reason="Recent Recovery recommendations were acted on or resolved.",
                        evidence_summary=recovery_trend.reason,
                        recommended_next_action=recovery_trend.next_action,
                        can_wait=True,
                        created_at=_now(),
                        evidence_key=_hash_text("recovery_trend", recovery_trend.direction, recovery_trend.decisions_shown),
                    )
                )
        return predictions

    def _platform_predictions(self, session: Session) -> list[Prediction]:
        overview = platform_connections_overview(session)
        waiting = int(overview.get("waiting") or 0)
        if waiting <= 0:
            return []
        return [
            Prediction(
                prediction_title="Platform logins can stay in final activation",
                prediction_type="upcoming_setup_need",
                confidence="medium",
                reason="Not connected yet is expected while platform credentials are intentionally held for final setup.",
                evidence_summary=f"{waiting} platform connection item(s) are waiting for approved credentials or setup.",
                recommended_next_action="Keep platform connectors in Can Wait until final activation starts.",
                can_wait=True,
                created_at=_now(),
                evidence_key=_hash_text("platform_waiting", waiting),
            )
        ]

    def _notification_predictions(self, session: Session) -> list[Prediction]:
        alert_health = alert_health_summary(session)
        if alert_health.status == "healthy":
            return []
        if alert_health.status == "needs_review":
            confidence = "low"
        else:
            confidence = "medium"
        return [
            Prediction(
                prediction_title="Alert routing may become important during team rollout",
                prediction_type="upcoming_setup_need",
                confidence=confidence,
                reason="Notification routes matter more once critical alerts and team workflows depend on them.",
                evidence_summary=alert_health.evidence,
                recommended_next_action=alert_health.next_action,
                can_wait=alert_health.status == "needs_review",
                created_at=_now(),
                evidence_key=_hash_text("notification", alert_health.status, alert_health.failed_attempts, alert_health.stale_route_count),
            )
        ]

    def _friction_predictions(self, trends: DecisionTrendReport) -> list[Prediction]:
        if not trends.available:
            return []
        friction = next((trend for trend in trends.trends if trend.category in {"friction", "navigation"} and trend.direction == "declining"), None)
        if friction is None:
            return []
        return [
            Prediction(
                prediction_title=f"{friction.label} may keep creating friction",
                prediction_type="repeated_friction_warning",
                confidence="medium",
                reason=friction.reason,
                evidence_summary=friction.reason,
                recommended_next_action=friction.next_action,
                can_wait=False,
                created_at=_now(),
                evidence_key=_hash_text("friction", friction.category, friction.direction, friction.decisions_shown),
            )
        ]

    def _rank_predictions(self, predictions: list[Prediction]) -> list[Prediction]:
        type_rank = {
            "likely_next_priority": 0,
            "likely_blocker": 1,
            "recurring_risk": 2,
            "repeated_friction_warning": 3,
            "upcoming_setup_need": 4,
            "stale_decision_warning": 5,
        }
        confidence_rank = {"high": 0, "medium": 1, "low": 2}
        return sorted(predictions, key=lambda item: (item.can_wait, type_rank.get(item.prediction_type, 9), confidence_rank.get(item.confidence, 9), item.prediction_title))

    def _record_prediction(
        self,
        session: Session,
        prediction: Prediction,
        *,
        actor: User | None,
        action: str,
        evidence_summary: str | None = None,
    ) -> PredictiveCOOPrediction:
        record = session.scalar(
            select(PredictiveCOOPrediction)
            .where(PredictiveCOOPrediction.evidence_key == prediction.evidence_key)
            .order_by(desc(PredictiveCOOPrediction.created_at), desc(PredictiveCOOPrediction.id))
            .limit(1)
        )
        now = _now()
        if record is None:
            record = PredictiveCOOPrediction(
                prediction_title=prediction.prediction_title,
                prediction_type=prediction.prediction_type,
                confidence=prediction.confidence,
                reason=prediction.reason,
                evidence_summary=prediction.evidence_summary,
                recommended_next_action=prediction.recommended_next_action,
                can_wait=prediction.can_wait,
                status="shown",
                shown_at=now,
                evidence_key=prediction.evidence_key,
                metadata_json={},
            )
            session.add(record)
        else:
            record.prediction_title = prediction.prediction_title
            record.prediction_type = prediction.prediction_type
            record.confidence = prediction.confidence
            record.reason = prediction.reason
            record.evidence_summary = prediction.evidence_summary
            record.recommended_next_action = prediction.recommended_next_action
            record.can_wait = prediction.can_wait
            record.shown_at = record.shown_at or now
        if action == "opened":
            record.opened_at = record.opened_at or now
        elif action == "acted_on":
            record.acted_on_at = record.acted_on_at or now
        elif action in {"helpful", "not_helpful", "remind_later", "dismissed", "proven_correct", "proven_wrong"}:
            record.feedback_at = now
        if action in {"proven_correct", "proven_wrong"}:
            record.resolved_at = now
            if evidence_summary:
                record.evidence_summary = evidence_summary
        if action == "shown" and record.status not in {
            "helpful",
            "not_helpful",
            "remind_later",
            "dismissed",
            "acted_on",
            "proven_correct",
            "proven_wrong",
        }:
            record.status = action
        elif action in {
            "opened",
            "helpful",
            "not_helpful",
            "remind_later",
            "dismissed",
            "acted_on",
            "proven_correct",
            "proven_wrong",
        }:
            record.status = action
        record.metadata_json = sanitize_details({**(record.metadata_json or {}), "last_action": action})
        session.flush()
        emit_event(
            session,
            actor=actor,
            event_name=f"prediction.{action}",
            resource_type="predictive_coo_prediction",
            resource_id=str(record.id),
            payload={
                "prediction_type": prediction.prediction_type,
                "confidence": prediction.confidence,
                "evidence_summary": evidence_summary or prediction.evidence_summary,
                "can_wait": prediction.can_wait,
            },
        )
        return record


def safe_decision_trend_report(session: Session, *, time_window: str = "weekly") -> DecisionTrendReport:
    try:
        return DecisionTrendEngine().calculate_trends(session, time_window=time_window)
    except Exception as exc:
        try:
            emit_event(
                session,
                actor=None,
                event_name="decision_trends.unavailable",
                resource_type="decision_quality_trends",
                status="warning",
                payload={"error": str(exc)[:160]},
            )
        except Exception:
            pass
        return DecisionTrendReport(
            available=False,
            status="unavailable",
            generated_at=_now(),
            trends=(),
            insights=("Decision quality trends are unavailable.",),
            next_best_move="Use COO Briefing from current evidence.",
            unavailable_reason=str(exc)[:160],
        )


def safe_predictive_coo_report(
    session: Session,
    *,
    decisions: tuple[Decision, ...] | list[Decision] | None = None,
    actor: User | None = None,
) -> PredictiveCOOReport:
    try:
        return PredictiveCOOEngine().generate_predictions(session, decisions=decisions, actor=actor)
    except Exception as exc:
        try:
            emit_event(
                session,
                actor=actor,
                event_name="predictive_coo.unavailable",
                resource_type="predictive_coo_prediction",
                status="warning",
                payload={"error": str(exc)[:160]},
            )
        except Exception:
            pass
        return PredictiveCOOReport(
            available=False,
            enabled=settings.predictive_coo_enabled,
            status="unavailable",
            generated_at=_now(),
            predictions=(),
            primary=None,
            current_critical_active=False,
            quality=PredictionQualitySummary(0, 0.0, 0.0, 0.0, 0.0, 0),
            next_best_move="Use COO Briefing from current evidence.",
            unavailable_reason=str(exc)[:160],
        )


def record_prediction_feedback(
    session: Session,
    *,
    action: str,
    actor: User | None = None,
    evidence_summary: str | None = None,
) -> PredictiveCOOPrediction | None:
    return PredictiveCOOEngine().record_feedback(session, action=action, actor=actor, evidence_summary=evidence_summary)
