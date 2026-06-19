from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models.social import SocialCommentProfile
from app.models.user import User
from app.services.auth import audit_action, user_has_permission
from app.services.social_compliance import compliance_gate
from app.services.social_evidence import profile_evidence, profile_evidence_summary
from app.services.social_events import create_social_event


@dataclass(frozen=True)
class SocialProfileEvaluation:
    profile: SocialCommentProfile
    recommendation_strength: str
    score: int
    explanation: str
    suggested_action: str
    evidence: dict


def _require_social_view(session: Session, actor: User | None) -> None:
    if user_has_permission(actor, "view_dashboard") or user_has_permission(actor, "manage_reports"):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="social_evaluation",
        status="denied",
        details={"permission": "view_dashboard_or_manage_reports"},
    )
    raise PermissionError("Missing social evaluation permission.")


def _strength(score: int) -> str:
    if score >= 80:
        return "strong"
    if score >= 55:
        return "promising"
    return "early"


def score_social_comment_profile(
    session: Session,
    profile: SocialCommentProfile,
    *,
    actor: User | None = None,
) -> SocialProfileEvaluation:
    _require_social_view(session, actor)
    evidence = profile_evidence(profile)
    gate = compliance_gate(
        session,
        entity_type="social_comment_profile",
        entity_id=profile.id,
        entity=profile,
        actor=actor,
        action="evaluate",
        evidence=evidence,
    )
    if not gate.allowed:
        create_social_event(
            session,
            event_type="social.evaluation.blocked",
            event_category="evaluation",
            source_module="evaluation_engine",
            entity_type="social_comment_profile",
            entity_id=profile.id,
            actor=actor,
            status="blocked",
            severity="medium",
            summary=gate.reason,
            details={"compliance_log_id": gate.compliance_log_id},
            evidence=evidence,
        )
        raise PermissionError(gate.reason)
    score = round(
        (profile.avg_comment_quality * 0.35)
        + (profile.avg_engagement * 0.3)
        + min(25, profile.repeated_appearance_count * 8)
        + min(10, profile.observed_comment_count * 2)
    )
    score = max(0, min(100, score))
    profile.potential_value_score = max(profile.potential_value_score, score)
    session.flush()
    explanation = profile_evidence_summary(profile)
    create_social_event(
        session,
        event_type="social.evaluation.scored",
        event_category="evaluation",
        source_module="evaluation_engine",
        entity_type="social_comment_profile",
        entity_id=profile.id,
        actor=actor,
        summary=f"Fortuna evaluated @{profile.username} as a {_strength(score)} public profile lead.",
        details={"score": score, "recommendation_strength": _strength(score)},
        evidence=evidence,
    )
    return SocialProfileEvaluation(
        profile=profile,
        recommendation_strength=_strength(score),
        score=score,
        explanation=explanation,
        suggested_action="Review the profile manually.",
        evidence=evidence,
    )


def rank_social_comment_profiles(
    session: Session,
    *,
    actor: User | None = None,
    limit: int = 10,
) -> list[SocialProfileEvaluation]:
    _require_social_view(session, actor)
    profiles = list(
        session.scalars(
            select(SocialCommentProfile)
            .where(SocialCommentProfile.status != "archived")
            .order_by(desc(SocialCommentProfile.potential_value_score), desc(SocialCommentProfile.last_seen_at))
            .limit(max(limit * 3, limit))
        ).all()
    )
    ranked: list[SocialProfileEvaluation] = []
    for profile in profiles:
        gate = compliance_gate(
            session,
            entity_type="social_comment_profile",
            entity_id=profile.id,
            entity=profile,
            actor=actor,
            action="rank",
            evidence=profile_evidence(profile),
        )
        if not gate.allowed:
            continue
        ranked.append(score_social_comment_profile(session, profile, actor=actor))
        if len(ranked) >= limit:
            break
    return sorted(ranked, key=lambda item: item.score, reverse=True)


def recommend_social_comment_profile(
    session: Session,
    profile: SocialCommentProfile,
    *,
    actor: User | None = None,
) -> SocialProfileEvaluation:
    evaluation = score_social_comment_profile(session, profile, actor=actor)
    gate = compliance_gate(
        session,
        entity_type="social_comment_profile",
        entity_id=profile.id,
        entity=profile,
        actor=actor,
        action="recommend",
        evidence=evaluation.evidence,
    )
    if not gate.allowed:
        raise PermissionError(gate.reason)
    create_social_event(
        session,
        event_type="social.evaluation.recommended",
        event_category="evaluation",
        source_module="evaluation_engine",
        entity_type="social_comment_profile",
        entity_id=profile.id,
        actor=actor,
        summary=f"Fortuna recommended reviewing @{profile.username}.",
        details={"score": evaluation.score, "strength": evaluation.recommendation_strength},
        evidence=evaluation.evidence,
    )
    return evaluation
