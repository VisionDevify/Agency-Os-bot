from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.social import SocialComment
from app.models.user import User
from app.services.auth import audit_action, user_has_permission
from app.services.social_compliance import compliance_gate
from app.services.social_evidence import comment_evidence
from app.services.social_events import create_social_event
from app.services.social_profile_intelligence import create_or_update_profile, create_profile_observation


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
        resource_type="social_comment_intelligence",
        status="denied",
        details={"permission": "manage_reports_or_manage_tasks"},
    )
    raise PermissionError("Missing social comment intelligence permission.")


def _detect_angle(text: str) -> str:
    lowered = text.casefold()
    if "?" in text:
        return "question"
    if any(word in lowered for word in ("same", "relate", "felt", "been there")):
        return "relatable"
    if any(word in lowered for word in ("how", "why", "curious", "wonder")):
        return "curiosity"
    if any(word in lowered for word in ("tip", "learn", "because", "here's")):
        return "educational"
    return "supportive"


def _detect_sentiment(text: str) -> str:
    lowered = text.casefold()
    if any(word in lowered for word in ("love", "great", "smart", "useful", "agree")):
        return "positive"
    if any(word in lowered for word in ("hate", "bad", "wrong", "awful", "spam")):
        return "negative"
    return "neutral"


def ingest_comment(
    session: Session,
    *,
    actor: User | None,
    platform: str,
    post_reference: str,
    author_username: str,
    comment_text: str,
    post_id: str | None = None,
    author_profile_url: str | None = None,
    comment_time: datetime | None = None,
    like_count: int = 0,
    reply_count: int = 0,
    source_method: str = "manual",
    compliance_status: str = "approved",
    niche: str | None = None,
) -> SocialComment:
    """Ingest one human-provided or approved public comment reference."""
    _require_social_manage(session, actor)
    username = author_username.strip().lstrip("@").lower()
    reference = post_reference.strip()
    text = comment_text.strip()
    if not username:
        raise ValueError("Comment author username is required.")
    if not reference:
        raise ValueError("Post reference is required.")
    if not text:
        raise ValueError("Comment text is required.")
    comment = SocialComment(
        platform=platform,
        post_id=post_id,
        post_reference=reference,
        author_username=username,
        author_profile_url=author_profile_url,
        comment_text=text,
        comment_time=comment_time or _now(),
        like_count=max(0, like_count),
        reply_count=max(0, reply_count),
        source_method=source_method,
        compliance_status=compliance_status,
    )
    session.add(comment)
    session.flush()
    gate = compliance_gate(
        session,
        entity_type="social_comment",
        entity_id=comment.id,
        entity=comment,
        actor=actor,
        action="ingest",
        evidence={"post_reference": reference, "author": f"@{username}"},
    )
    if gate.allowed:
        create_or_update_profile(
            session,
            actor=actor,
            platform=platform,
            username=username,
            profile_url=author_profile_url,
            niche=niche,
            source_method=source_method,
            compliance_status=compliance_status,
        )
    create_social_event(
        session,
        event_type="social.comment.ingested",
        event_category="comment",
        source_module="comment_intelligence",
        entity_type="social_comment",
        entity_id=comment.id,
        actor=actor,
        status="success" if gate.allowed else "warning",
        severity="info" if gate.allowed else "medium",
        summary=f"Fortuna recorded a public comment from @{username}.",
        details={"compliance_log_id": gate.compliance_log_id},
        evidence={"post_reference": reference, "author": f"@{username}"},
    )
    return comment


def analyze_comment(session: Session, comment: SocialComment, *, actor: User | None, niche: str | None = None) -> SocialComment:
    """Analyze an approved comment and create profile observation evidence."""
    _require_social_manage(session, actor)
    gate = compliance_gate(
        session,
        entity_type="social_comment",
        entity_id=comment.id,
        entity=comment,
        actor=actor,
        action="evaluate",
        evidence={"post_reference": comment.post_reference, "author": f"@{comment.author_username}"},
    )
    if not gate.allowed:
        create_social_event(
            session,
            event_type="social.comment.analysis_blocked",
            event_category="comment",
            source_module="comment_intelligence",
            entity_type="social_comment",
            entity_id=comment.id,
            actor=actor,
            status="blocked",
            severity="medium",
            summary=gate.reason,
            details={"compliance_log_id": gate.compliance_log_id},
            evidence=gate.evidence,
        )
        raise PermissionError(gate.reason)
    length_bonus = min(35, len(comment.comment_text) // 8)
    question_bonus = 10 if "?" in comment.comment_text else 0
    quality = _clamp(35 + length_bonus + question_bonus + min(20, comment.reply_count * 4))
    engagement = _clamp((comment.like_count * 4) + (comment.reply_count * 12))
    comment.detected_angle = _detect_angle(comment.comment_text)
    comment.sentiment = _detect_sentiment(comment.comment_text)
    comment.quality_score = quality
    comment.engagement_score = engagement
    profile = create_or_update_profile(
        session,
        actor=actor,
        platform=comment.platform,
        username=comment.author_username,
        profile_url=comment.author_profile_url,
        niche=niche,
        source_method=comment.source_method,
        compliance_status=comment.compliance_status,
    )
    create_profile_observation(
        session,
        actor=actor,
        profile=profile,
        comment=comment,
        reason_flagged="Public comment had useful quality or engagement signals.",
    )
    session.flush()
    create_social_event(
        session,
        event_type="social.comment.analyzed",
        event_category="comment",
        source_module="comment_intelligence",
        entity_type="social_comment",
        entity_id=comment.id,
        actor=actor,
        summary=f"Fortuna analyzed a public comment from @{comment.author_username}.",
        details={"profile_id": profile.id},
        evidence=comment_evidence(comment),
    )
    return comment


def generate_comment_evidence(comment: SocialComment) -> dict:
    return comment_evidence(comment)
