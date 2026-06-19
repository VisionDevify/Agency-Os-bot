from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.opportunity import Opportunity
from app.models.social import SocialCommentProfile
from app.models.user import User
from app.services.auth import audit_action, user_has_permission
from app.services.learning import create_confidence_record, create_learning_event
from app.services.opportunities import comment_strategies_for_opportunity, create_manual_opportunity
from app.services.social_compliance import compliance_gate
from app.services.social_evidence import profile_evidence, profile_evidence_summary
from app.services.social_events import create_social_event


def _require_opportunity_manage(session: Session, actor: User | None) -> None:
    if user_has_permission(actor, "manage_reports") or user_has_permission(actor, "manage_tasks"):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="social_opportunity_engine",
        status="denied",
        details={"permission": "manage_reports_or_manage_tasks"},
    )
    raise PermissionError("Missing social opportunity permission.")


def convert_profile_lead(
    session: Session,
    profile: SocialCommentProfile,
    *,
    actor: User | None,
    assigned_to_user_id: int | None = None,
) -> Opportunity:
    """Convert an approved public profile lead into a manual-review opportunity."""
    _require_opportunity_manage(session, actor)
    evidence = profile_evidence(profile)
    gate = compliance_gate(
        session,
        entity_type="social_comment_profile",
        entity_id=profile.id,
        entity=profile,
        actor=actor,
        action="convert_to_opportunity",
        evidence=evidence,
    )
    if not gate.allowed:
        create_social_event(
            session,
            event_type="social.opportunity.conversion_blocked",
            event_category="opportunity",
            source_module="opportunity",
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
    opportunity = create_manual_opportunity(
        session,
        actor=actor,
        title=f"Review @{profile.username}",
        platform=profile.platform if profile.platform in {"x", "instagram", "reddit", "other"} else "other",
        url=profile.profile_url,
        niche=profile.niche,
        priority="high" if profile.potential_value_score >= 80 else "normal",
        assigned_to_user_id=assigned_to_user_id,
        source_type="manual",
        source_reference_id=profile.id,
        reason=profile_evidence_summary(profile),
        suggested_angle="curiosity",
    )
    opportunity.score = profile.potential_value_score
    profile.status = "converted_to_opportunity"
    comment_strategies_for_opportunity(session, opportunity, actor=actor, create_if_missing=True)
    create_social_event(
        session,
        event_type="social.opportunity.converted",
        event_category="opportunity",
        source_module="opportunity",
        entity_type="opportunity",
        entity_id=opportunity.id,
        actor=actor,
        summary=f"Fortuna created an opportunity from @{profile.username} for human review.",
        details={"profile_id": profile.id, "manual_only": True, "auto_posting": False},
        evidence=evidence,
    )
    learn_gate = compliance_gate(
        session,
        entity_type="social_comment_profile",
        entity_id=profile.id,
        entity=profile,
        actor=actor,
        action="learn",
        evidence=evidence,
    )
    if learn_gate.allowed:
        create_learning_event(
            session,
            actor=actor,
            event_type="social.profile_opportunity_created",
            source_type="opportunity",
            source_id=opportunity.id,
            entity_type="social_comment_profile",
            entity_id=profile.id,
            outcome="partial",
            severity="info",
            summary="Profile-led opportunity created for manual review.",
            details={"profile": f"@{profile.username}", "auto_posting": False},
            confidence_score=profile.potential_value_score,
        )
        create_confidence_record(
            session,
            subject_type="opportunity",
            subject_id=opportunity.id,
            previous_score=None,
            new_score=profile.potential_value_score,
            reason="Profile lead converted to manual-review opportunity.",
            evidence={"profile_id": profile.id, "manual_only": True},
        )
    session.flush()
    return opportunity
