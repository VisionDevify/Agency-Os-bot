from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.social import SocialComment, SocialCommentProfile, SocialCommentProfileObservation
from app.models.user import User
from app.services.auth import audit_action, user_has_permission
from app.services.social_compliance import compliance_gate
from app.services.social_evidence import comment_evidence, profile_evidence, profile_evidence_summary
from app.services.social_events import create_social_event


def _now() -> datetime:
    return datetime.now(UTC)


def _clamp(value: int | float) -> int:
    return max(0, min(100, round(value)))


def _require_social_manage(session: Session, actor: User | None) -> None:
    if user_has_permission(actor, "manage_reports") or user_has_permission(actor, "manage_tasks"):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="social_profile_intelligence",
        status="denied",
        details={"permission": "manage_reports_or_manage_tasks"},
    )
    raise PermissionError("Missing social profile intelligence permission.")


def create_or_update_profile(
    session: Session,
    *,
    actor: User | None,
    platform: str,
    username: str,
    profile_url: str | None = None,
    niche: str | None = None,
    source_method: str = "manual",
    compliance_status: str = "approved",
    notes: str | None = None,
) -> SocialCommentProfile:
    _require_social_manage(session, actor)
    clean_username = username.strip().lstrip("@").lower()
    if not clean_username:
        raise ValueError("Profile username is required.")
    profile = session.scalar(
        select(SocialCommentProfile).where(
            SocialCommentProfile.platform == platform,
            SocialCommentProfile.username == clean_username,
        )
    )
    now = _now()
    if profile is None:
        profile = SocialCommentProfile(
            platform=platform,
            username=clean_username,
            profile_url=profile_url,
            niche=niche,
            first_seen_at=now,
            last_seen_at=now,
            source_method=source_method,
            compliance_status=compliance_status,
            notes=notes,
        )
        session.add(profile)
    else:
        profile.profile_url = profile_url or profile.profile_url
        profile.niche = niche or profile.niche
        profile.last_seen_at = now
        profile.source_method = source_method or profile.source_method
        profile.compliance_status = compliance_status or profile.compliance_status
        profile.notes = notes or profile.notes
    session.flush()
    gate = compliance_gate(
        session,
        entity_type="social_comment_profile",
        entity_id=profile.id,
        entity=profile,
        actor=actor,
        action="ingest",
        evidence={"username": clean_username, "platform": platform},
    )
    create_social_event(
        session,
        event_type="social.profile.created_or_updated",
        event_category="profile",
        source_module="profile_intelligence",
        entity_type="social_comment_profile",
        entity_id=profile.id,
        actor=actor,
        status="success" if gate.allowed else "warning",
        severity="info" if gate.allowed else "medium",
        summary=f"Fortuna recorded public profile @{clean_username}.",
        details={"compliance_log_id": gate.compliance_log_id},
        evidence=profile_evidence(profile),
    )
    return profile


def create_profile_observation(
    session: Session,
    *,
    actor: User | None,
    profile: SocialCommentProfile,
    comment: SocialComment,
    reason_flagged: str,
) -> SocialCommentProfileObservation:
    gate = compliance_gate(
        session,
        entity_type="social_comment_profile",
        entity_id=profile.id,
        entity=profile,
        actor=actor,
        action="evaluate",
        evidence=comment_evidence(comment),
    )
    if not gate.allowed:
        raise PermissionError(gate.reason)
    observation = SocialCommentProfileObservation(
        profile_id=profile.id,
        comment_id=comment.id,
        post_id=comment.post_id,
        platform=comment.platform,
        observed_at=comment.comment_time or _now(),
        engagement_score=comment.engagement_score,
        quality_score=comment.quality_score,
        reason_flagged=reason_flagged,
        created_at=_now(),
    )
    session.add(observation)
    profile.observed_comment_count += 1
    profile.last_seen_at = observation.observed_at
    if profile.first_seen_at is None:
        profile.first_seen_at = observation.observed_at
    total = profile.observed_comment_count
    profile.avg_comment_quality = _clamp(((profile.avg_comment_quality * (total - 1)) + comment.quality_score) / total)
    profile.avg_engagement = _clamp(((profile.avg_engagement * (total - 1)) + comment.engagement_score) / total)
    profile.repeated_appearance_count = max(0, total - 1)
    profile.potential_value_score = _clamp((profile.avg_comment_quality * 0.45) + (profile.avg_engagement * 0.35) + min(20, profile.repeated_appearance_count * 8))
    session.flush()
    create_social_event(
        session,
        event_type="social.profile.observation_created",
        event_category="profile",
        source_module="profile_intelligence",
        entity_type="social_comment_profile_observation",
        entity_id=observation.id,
        actor=actor,
        summary=f"Fortuna observed @{profile.username} in a public comment section.",
        details={"profile_id": profile.id, "comment_id": comment.id},
        evidence=profile_evidence(profile),
    )
    return observation


def detect_repeated_profiles(session: Session, *, actor: User | None = None, minimum_appearances: int = 2) -> list[SocialCommentProfile]:
    profiles = list(
        session.scalars(
            select(SocialCommentProfile)
            .where(SocialCommentProfile.observed_comment_count >= minimum_appearances)
            .order_by(desc(SocialCommentProfile.potential_value_score), desc(SocialCommentProfile.last_seen_at))
        ).all()
    )
    approved: list[SocialCommentProfile] = []
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
        if gate.allowed:
            approved.append(profile)
    return approved


def generate_profile_leads(session: Session, *, actor: User | None = None, limit: int = 5) -> list[SocialCommentProfile]:
    profiles = detect_repeated_profiles(session, actor=actor)
    leads: list[SocialCommentProfile] = []
    for profile in profiles:
        gate = compliance_gate(
            session,
            entity_type="social_comment_profile",
            entity_id=profile.id,
            entity=profile,
            actor=actor,
            action="recommend",
            evidence=profile_evidence(profile),
        )
        if gate.allowed:
            leads.append(profile)
        if len(leads) >= limit:
            break
    return leads


def get_profile_evidence(profile: SocialCommentProfile) -> dict:
    return profile_evidence(profile)


def comment_section_summary(session: Session, *, post_reference: str, actor: User | None = None) -> dict:
    comments = list(session.scalars(select(SocialComment).where(SocialComment.post_reference == post_reference)).all())
    profile_ids = [row[0] for row in session.execute(
        select(SocialCommentProfileObservation.profile_id)
        .join(SocialComment, SocialComment.id == SocialCommentProfileObservation.comment_id)
        .where(SocialComment.post_reference == post_reference)
        .distinct()
    ).all()]
    top_profile = None
    if profile_ids:
        top_profile = session.scalar(
            select(SocialCommentProfile)
            .where(SocialCommentProfile.id.in_(profile_ids))
            .order_by(desc(SocialCommentProfile.potential_value_score))
            .limit(1)
        )
    return {
        "comments": len(comments),
        "profiles": len(profile_ids),
        "top_profile": top_profile,
        "summary": (
            "Active conversation with profile leads."
            if top_profile
            else "Not enough comment/profile evidence yet."
        ),
        "evidence": profile_evidence_summary(top_profile) if top_profile else "Add public comment data to build evidence.",
    }
