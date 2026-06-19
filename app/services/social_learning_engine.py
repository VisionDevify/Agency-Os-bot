from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.social import SocialCommentProfile
from app.models.user import User
from app.services.learning import create_confidence_record, create_learning_event
from app.services.social_compliance import compliance_gate
from app.services.social_evidence import profile_evidence
from app.services.social_events import create_social_event


def learn_from_profile_result(
    session: Session,
    profile: SocialCommentProfile,
    *,
    actor: User | None,
    outcome: str,
    notes: str | None = None,
    confidence_delta: int = 5,
) -> None:
    evidence = profile_evidence(profile)
    gate = compliance_gate(
        session,
        entity_type="social_comment_profile",
        entity_id=profile.id,
        entity=profile,
        actor=actor,
        action="learn",
        evidence=evidence,
    )
    if not gate.allowed:
        create_learning_event(
            session,
            actor=actor,
            event_type="social.compliance_review_needed",
            source_type="opportunity",
            source_id=profile.id,
            entity_type="social_comment_profile",
            entity_id=profile.id,
            outcome="ignored",
            severity="warning",
            summary="Fortuna could not learn from this profile until compliance review is complete.",
            details={"reason": gate.reason},
            confidence_score=0,
        )
        create_social_event(
            session,
            event_type="social.learning.blocked",
            event_category="learning",
            source_module="learning_engine",
            entity_type="social_comment_profile",
            entity_id=profile.id,
            actor=actor,
            status="blocked",
            severity="medium",
            summary=gate.reason,
            details={"compliance_log_id": gate.compliance_log_id},
            evidence=evidence,
        )
        return
    mapped_outcome = "success" if outcome in {"converted", "successful", "used"} else "ignored" if outcome in {"skipped", "not_useful"} else "partial"
    create_learning_event(
        session,
        actor=actor,
        event_type="social.profile_result_recorded",
        source_type="opportunity",
        source_id=profile.id,
        entity_type="social_comment_profile",
        entity_id=profile.id,
        outcome=mapped_outcome,
        severity="info",
        summary=f"Fortuna learned from @{profile.username}'s profile lead outcome.",
        details={"outcome": outcome, "notes": notes},
        confidence_score=profile.potential_value_score,
    )
    create_confidence_record(
        session,
        subject_type="opportunity",
        subject_id=f"social_comment_profile:{profile.id}",
        previous_score=max(0, profile.potential_value_score - confidence_delta),
        new_score=profile.potential_value_score,
        reason=f"Profile lead outcome recorded: {outcome}.",
        evidence={"outcome": outcome},
    )
    create_social_event(
        session,
        event_type="social.learning.updated",
        event_category="learning",
        source_module="learning_engine",
        entity_type="social_comment_profile",
        entity_id=profile.id,
        actor=actor,
        summary=f"Fortuna updated learning from @{profile.username}.",
        details={"outcome": outcome},
        evidence=evidence,
    )
