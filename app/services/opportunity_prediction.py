from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.learning import OutcomeMemory
from app.models.opportunity import Opportunity, OpportunityResult
from app.models.performance import TeamPerformanceSnapshot
from app.models.prediction import OpportunityPrediction
from app.models.social import SocialSourcePerformance
from app.models.user import User
from app.services.learning import create_confidence_record, create_learning_event
from app.services.team_intelligence import team_intelligence_summary


@dataclass(frozen=True)
class OpportunityPredictionResult:
    opportunity: Opportunity
    prediction: OpportunityPrediction


def _now() -> datetime:
    return datetime.now(UTC)


def _clamp(value: int | float) -> int:
    return max(0, min(100, round(value)))


def _priority_bonus(priority: str) -> int:
    return {"low": -5, "normal": 0, "high": 8, "critical": 14}.get(priority, 0)


def _source_performance(session: Session, opportunity: Opportunity) -> int:
    rows = list(
        session.scalars(
            select(SocialSourcePerformance).where(
                SocialSourcePerformance.platform == opportunity.platform,
                SocialSourcePerformance.niche == opportunity.niche,
            )
        ).all()
    )
    if rows:
        total = sum(max(1, row.reviewed_count + row.skipped_count) for row in rows)
        return _clamp(sum(row.historical_score * max(1, row.reviewed_count + row.skipped_count) for row in rows) / total)
    memory = session.scalar(
        select(OutcomeMemory)
        .where(OutcomeMemory.memory_type == "opportunity_result", OutcomeMemory.summary.ilike(f"%{opportunity.niche or ''}%"))
        .order_by(desc(OutcomeMemory.updated_at), desc(OutcomeMemory.id))
        .limit(1)
    )
    if memory is not None and memory.success_rate is not None:
        return _clamp(memory.success_rate)
    return 50


def _best_angle(session: Session, opportunity: Opportunity) -> str:
    if opportunity.suggested_angle:
        text = opportunity.suggested_angle.strip().lower()
        for candidate in ("curiosity", "relatable", "soft_cta", "playful", "question"):
            if candidate in text:
                return candidate
    row = session.scalar(
        select(SocialSourcePerformance)
        .where(SocialSourcePerformance.engagement_angle.is_not(None))
        .order_by(desc(SocialSourcePerformance.historical_score), desc(SocialSourcePerformance.updated_at))
        .limit(1)
    )
    return row.engagement_angle if row and row.engagement_angle else "curiosity"


def _recommended_chatter_id(session: Session) -> int | None:
    summary = team_intelligence_summary(session)
    if summary.best_chatter is not None:
        return summary.best_chatter.id
    snapshot = session.scalar(
        select(TeamPerformanceSnapshot)
        .order_by(
            desc(TeamPerformanceSnapshot.reliability_score),
            TeamPerformanceSnapshot.workload_score,
            desc(TeamPerformanceSnapshot.period_end),
        )
        .limit(1)
    )
    return snapshot.user_id if snapshot is not None else None


def predict_opportunity(session: Session, opportunity: Opportunity, *, actor: User | None = None) -> OpportunityPrediction:
    source_score = _source_performance(session, opportunity)
    base = max(opportunity.score or 0, 45)
    quality = _clamp((base * 0.45) + (source_score * 0.35) + 12 + _priority_bonus(opportunity.priority))
    confidence = _clamp(45 + (source_score * 0.3) + (15 if opportunity.niche else 0) + (10 if opportunity.model_brand_id else 0))
    angle = _best_angle(session, opportunity)
    chatter_id = opportunity.assigned_to_user_id or _recommended_chatter_id(session)
    reasons = [
        "Uses the opportunity score, source history, niche fit, timing assumptions, and team workload.",
        "Human review is required before any engagement.",
    ]
    if source_score != 50:
        reasons.append(f"Historical source/niche signal contributes {source_score}/100.")
    prediction = OpportunityPrediction(
        opportunity_id=opportunity.id,
        predicted_quality=quality,
        confidence_score=confidence,
        recommended_angle=angle,
        recommended_chatter_id=chatter_id,
        reasoning_summary=" ".join(reasons),
        risk_notes="Advisory only. Fortuna does not auto-post, auto-comment, auto-like, or auto-follow.",
        created_at=_now(),
    )
    session.add(prediction)
    session.flush()
    create_learning_event(
        session,
        event_type="opportunity.prediction_created",
        source_type="opportunity",
        source_id=opportunity.id,
        entity_type="opportunity",
        entity_id=opportunity.id,
        outcome="partial",
        severity="info",
        summary="Fortuna created an advisory opportunity prediction.",
        details={"predicted_quality": quality, "confidence_score": confidence, "angle": angle},
        confidence_score=confidence,
        actor=actor,
    )
    return prediction


def best_opportunity_prediction(session: Session, *, actor: User | None = None) -> OpportunityPredictionResult | None:
    opportunities = list(
        session.scalars(
            select(Opportunity)
            .where(Opportunity.status.in_(("discovered", "reviewing", "approved", "assigned")))
            .order_by(desc(Opportunity.score), desc(Opportunity.created_at), desc(Opportunity.id))
            .limit(15)
        ).all()
    )
    if not opportunities:
        return None
    predictions = [predict_opportunity(session, opportunity, actor=actor) for opportunity in opportunities[:5]]
    best = max(predictions, key=lambda item: (item.predicted_quality, item.confidence_score))
    opportunity_by_id = {opportunity.id: opportunity for opportunity in opportunities}
    return OpportunityPredictionResult(opportunity=opportunity_by_id[best.opportunity_id], prediction=best)


def latest_prediction_for(session: Session, opportunity_id: int) -> OpportunityPrediction | None:
    return session.scalar(
        select(OpportunityPrediction)
        .where(OpportunityPrediction.opportunity_id == opportunity_id)
        .order_by(desc(OpportunityPrediction.created_at), desc(OpportunityPrediction.id))
        .limit(1)
    )


def update_prediction_learning_from_result(
    session: Session,
    result: OpportunityResult,
    *,
    actor: User | None = None,
) -> None:
    prediction = latest_prediction_for(session, result.opportunity_id)
    if prediction is None:
        return
    successful = result.status == "posted" and ((result.conversions or 0) > 0 or (result.clicks or 0) > 0)
    new_score = _clamp(prediction.confidence_score + (4 if successful else -3))
    create_confidence_record(
        session,
        subject_type="opportunity",
        subject_id=result.opportunity_id,
        previous_score=prediction.confidence_score,
        new_score=new_score,
        reason="Opportunity result updated prediction confidence.",
        evidence={
            "result_status": result.status,
            "clicks": result.clicks,
            "conversions": result.conversions,
            "manual_entry_only": True,
        },
    )
    create_learning_event(
        session,
        event_type="opportunity.prediction_outcome",
        source_type="opportunity",
        source_id=result.opportunity_id,
        entity_type="opportunity_prediction",
        entity_id=prediction.id,
        outcome="success" if successful else ("ignored" if result.status in {"skipped", "rejected"} else "partial"),
        severity="info",
        summary="Fortuna updated opportunity prediction learning from a manual result.",
        details={
            "result_status": result.status,
            "clicks": result.clicks,
            "conversions": result.conversions,
            "recommended_angle": prediction.recommended_angle,
        },
        confidence_score=new_score,
        actor=actor,
    )
