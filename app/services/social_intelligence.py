from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from math import log1p

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.opportunity import CreatorWatch, Opportunity, OpportunityResult
from app.models.reporting import NotificationDeliveryAttempt
from app.models.social import (
    SOCIAL_COMPLIANCE_STATUSES,
    SOCIAL_DISCOVERY_LEAD_STATUSES,
    SOCIAL_DISCOVERY_RUN_STATUSES,
    SOCIAL_DISCOVERY_RUN_TYPES,
    SOCIAL_DISCOVERY_SOURCE_TYPES,
    SOCIAL_FOLLOWER_TIERS,
    SOCIAL_PLATFORMS,
    SOCIAL_SOURCE_TYPES,
    SocialDiscoveryLead,
    SocialDiscoveryRun,
    SocialDiscoverySourceConfig,
    SocialOpportunityScore,
    SocialPost,
    SocialSignal,
    SocialSource,
    SocialSourcePerformance,
)
from app.models.user import User
from app.services.audit import sanitize_details
from app.services.auth import audit_action, user_has_permission
from app.services.events import emit_event
from app.services.learning import create_confidence_record, create_learning_event
from app.services.notifications import active_targets_for_purposes, create_delivery_attempt
from app.services.opportunities import comment_strategies_for_opportunity, create_manual_opportunity
from app.services.recommendations import upsert_recommendation


@dataclass(frozen=True)
class EngagementStrategy:
    angle: str
    sample: str
    why: str
    risk: str


def _now() -> datetime:
    return datetime.now(UTC)


def _clamp(value: int | float, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, round(value)))


def _require_social_view(session: Session, actor: User | None) -> None:
    if user_has_permission(actor, "view_dashboard") or user_has_permission(actor, "manage_reports"):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="social_intelligence",
        status="denied",
        details={"permission": "view_dashboard_or_manage_reports"},
    )
    raise PermissionError("Missing permission: view_dashboard or manage_reports")


def _require_social_manage(session: Session, actor: User | None) -> None:
    if user_has_permission(actor, "manage_reports") or user_has_permission(actor, "manage_tasks"):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="social_intelligence",
        status="denied",
        details={"permission": "manage_reports_or_manage_tasks"},
    )
    raise PermissionError("Missing permission: manage_reports or manage_tasks")


def create_social_source(
    session: Session,
    *,
    actor: User | None,
    platform: str,
    creator_username: str,
    display_name: str | None = None,
    profile_url: str | None = None,
    niche: str | None = None,
    follower_tier: str = "unknown",
    source_type: str = "manual",
    compliance_status: str = "approved",
    watch_reason: str | None = None,
) -> SocialSource:
    _require_social_manage(session, actor)
    if platform not in SOCIAL_PLATFORMS:
        raise ValueError(f"Invalid social platform: {platform}")
    if follower_tier not in SOCIAL_FOLLOWER_TIERS:
        raise ValueError(f"Invalid follower tier: {follower_tier}")
    if source_type not in SOCIAL_SOURCE_TYPES:
        raise ValueError(f"Invalid social source type: {source_type}")
    if compliance_status not in SOCIAL_COMPLIANCE_STATUSES:
        raise ValueError(f"Invalid compliance status: {compliance_status}")
    username = creator_username.strip().lstrip("@")
    if not username:
        raise ValueError("Creator/page username is required.")
    source = SocialSource(
        platform=platform,
        creator_username=username,
        display_name=(display_name or username).strip(),
        profile_url=profile_url,
        niche=niche,
        follower_tier=follower_tier,
        source_type=source_type,
        compliance_status=compliance_status,
        watch_reason=watch_reason,
    )
    session.add(source)
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="social_source.created",
        resource_type="social_source",
        resource_id=str(source.id),
        details={"platform": platform, "niche": niche, "source_type": source_type, "compliance_status": compliance_status},
    )
    emit_event(
        session,
        actor=actor,
        event_name="social_source.created",
        resource_type="social_source",
        resource_id=str(source.id),
        payload={"platform": platform, "niche": niche, "compliance_status": compliance_status},
    )
    return source


def create_social_post(
    session: Session,
    *,
    actor: User | None,
    source: SocialSource | None,
    platform: str,
    post_reference: str,
    post_url: str | None = None,
    post_time: datetime | None = None,
    niche: str | None = None,
    content_summary: str | None = None,
    engagement_signals: dict | None = None,
    audience_fit: int = 50,
    niche_match: int = 50,
    creator_relevance: int = 50,
    competition_level: int = 50,
    content_quality: int = 50,
    comment_activity_quality: int = 50,
    compliance_status: str = "approved",
    compliance_notes: str | None = None,
    is_private_data: bool = False,
) -> SocialPost:
    _require_social_manage(session, actor)
    if platform not in SOCIAL_PLATFORMS:
        raise ValueError(f"Invalid social platform: {platform}")
    if compliance_status not in SOCIAL_COMPLIANCE_STATUSES:
        raise ValueError(f"Invalid compliance status: {compliance_status}")
    if is_private_data:
        compliance_status = "blocked"
        compliance_notes = compliance_notes or "Private data is not eligible for Fortuna social opportunity scoring."
    clean_reference = post_reference.strip()
    if not clean_reference:
        raise ValueError("Post URL or reference is required.")
    post = SocialPost(
        social_source_id=source.id if source else None,
        platform=platform,
        post_url=post_url,
        post_reference=clean_reference,
        post_time=post_time,
        niche=niche or (source.niche if source else None),
        content_summary=content_summary,
        engagement_signals_json=sanitize_details(engagement_signals or {}),
        audience_fit=_clamp(audience_fit),
        niche_match=_clamp(niche_match),
        creator_relevance=_clamp(creator_relevance),
        competition_level=_clamp(competition_level),
        content_quality=_clamp(content_quality),
        comment_activity_quality=_clamp(comment_activity_quality),
        compliance_status=compliance_status,
        compliance_notes=compliance_notes,
        is_private_data=is_private_data,
    )
    session.add(post)
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="social_post.created",
        resource_type="social_post",
        resource_id=str(post.id),
        details={"platform": platform, "source_id": source.id if source else None, "compliance_status": compliance_status},
    )
    emit_event(
        session,
        actor=actor,
        event_name="social_post.created",
        resource_type="social_post",
        resource_id=str(post.id),
        payload={"platform": platform, "compliance_status": compliance_status},
    )
    return post


def _recency_score(post: SocialPost, now: datetime | None = None) -> int:
    if post.post_time is None:
        return 50
    current = now or _now()
    age_hours = max(0.0, (current - post.post_time).total_seconds() / 3600)
    if age_hours <= 2:
        return 100
    if age_hours <= 8:
        return 85
    if age_hours <= 24:
        return 65
    if age_hours <= 72:
        return 40
    return 20


def _velocity_score(signals: dict, post: SocialPost, now: datetime | None = None) -> int:
    likes = int(signals.get("likes") or 0)
    comments = int(signals.get("comments") or 0)
    reposts = int(signals.get("shares") or signals.get("reposts") or 0)
    views = int(signals.get("views") or 0)
    age_hours = 6
    if post.post_time is not None:
        age_hours = max(1, int(((now or _now()) - post.post_time).total_seconds() / 3600))
    velocity = ((likes * 0.25) + (comments * 1.5) + (reposts * 1.2) + (views * 0.02)) / age_hours
    return _clamp(log1p(velocity) * 18)


def _source_performance_score(session: Session, source: SocialSource | None, niche: str | None) -> int:
    if source is None:
        return 50
    rows = list(
        session.scalars(
            select(SocialSourcePerformance).where(
                SocialSourcePerformance.social_source_id == source.id,
                SocialSourcePerformance.niche == niche,
            )
        ).all()
    )
    if not rows:
        return source.historical_score or 50
    total = sum(row.reviewed_count + row.skipped_count for row in rows) or len(rows)
    weighted = sum(row.historical_score * max(1, row.reviewed_count + row.skipped_count) for row in rows)
    return _clamp(weighted / total)


def _performance_bucket(
    session: Session,
    source: SocialSource | None,
    platform: str,
    niche: str | None,
    engagement_angle: str | None,
) -> SocialSourcePerformance:
    source_id = source.id if source is not None else None
    performance = session.scalar(
        select(SocialSourcePerformance).where(
            SocialSourcePerformance.social_source_id == source_id,
            SocialSourcePerformance.niche == niche,
            SocialSourcePerformance.engagement_angle == engagement_angle,
        )
    )
    if performance is None:
        performance = SocialSourcePerformance(
            social_source_id=source_id,
            platform=platform,
            niche=niche,
            engagement_angle=engagement_angle,
            metadata_json={"manual_only": True, "auto_posting": False},
        )
        session.add(performance)
        session.flush()
    return performance


def score_social_post(session: Session, post: SocialPost, *, actor: User | None = None, now: datetime | None = None) -> SocialOpportunityScore:
    _require_social_view(session, actor)
    source = post.source
    recency = _recency_score(post, now)
    velocity = _velocity_score(post.engagement_signals_json or {}, post, now)
    historical = _source_performance_score(session, source, post.niche)
    competition_score = 100 - post.competition_level
    components = {
        "audience_fit": post.audience_fit,
        "recency": recency,
        "engagement_velocity": velocity,
        "comment_activity_quality": post.comment_activity_quality,
        "niche_match": post.niche_match,
        "creator_relevance": post.creator_relevance,
        "competition": competition_score,
        "content_quality": post.content_quality,
        "historical_performance": historical,
    }
    score = _clamp(
        (post.audience_fit * 0.18)
        + (recency * 0.14)
        + (velocity * 0.14)
        + (post.comment_activity_quality * 0.12)
        + (post.niche_match * 0.12)
        + (post.creator_relevance * 0.1)
        + (competition_score * 0.08)
        + (post.content_quality * 0.07)
        + (historical * 0.05)
    )
    confidence = _clamp(45 + (15 if source else 0) + (15 if post.post_time else 0) + (10 if post.engagement_signals_json else 0))
    compliance_warning = None
    if post.compliance_status == "blocked":
        score = 0
        confidence = 95
        compliance_warning = "Blocked: private, non-compliant, or unapproved data cannot be used."
    elif post.compliance_status == "review_required":
        score = min(score, 60)
        compliance_warning = "Review required before a human uses this opportunity."
    angle = suggested_engagement_angle(post, score=score)
    timing = best_timing_window(post, recency_score=recency)
    existing = session.scalar(select(SocialOpportunityScore).where(SocialOpportunityScore.social_post_id == post.id))
    if existing is None:
        existing = SocialOpportunityScore(social_post_id=post.id)
        session.add(existing)
    existing.score = score
    existing.confidence_score = confidence
    existing.components_json = sanitize_details(components)
    existing.best_timing_window = timing
    existing.suggested_engagement_angle = angle
    existing.confidence_summary = confidence_summary(confidence, components)
    existing.compliance_warning = compliance_warning
    existing.status = "new" if existing.status == "archived" else existing.status
    session.flush()
    _upsert_social_signal(session, existing, actor=actor)
    return existing


def confidence_summary(confidence: int, components: dict) -> str:
    strongest = max(components, key=lambda key: components[key])
    if confidence >= 80:
        return f"High confidence. Strongest signal: {strongest.replace('_', ' ')}."
    if confidence >= 60:
        return f"Medium confidence. Strongest signal: {strongest.replace('_', ' ')}."
    return "Low confidence. Add more manual engagement context before assigning."


def best_timing_window(post: SocialPost, *, recency_score: int) -> str:
    if post.compliance_status == "blocked":
        return "Do not use"
    if recency_score >= 85:
        return "Review now"
    if recency_score >= 65:
        return "Review today"
    return "Review only if strategically relevant"


def suggested_engagement_angle(post: SocialPost, *, score: int) -> str:
    if post.compliance_status == "blocked":
        return "Do not engage"
    summary = (post.content_summary or "").casefold()
    if "question" in summary or "ask" in summary:
        return "question"
    if post.comment_activity_quality >= 75 and score >= 70:
        return "curiosity"
    if post.content_quality >= 75:
        return "educational"
    if post.competition_level >= 75:
        return "relatable"
    return "soft_cta" if score >= 80 else "supportive"


def engagement_strategies_for_score(score: SocialOpportunityScore) -> list[EngagementStrategy]:
    post = score.post
    if post.compliance_status == "blocked":
        return [
            EngagementStrategy(
                "warning",
                "Do not use this post.",
                "The source is blocked or private/non-compliant.",
                "high",
            )
        ]
    niche = post.niche or "this topic"
    return [
        EngagementStrategy("curiosity", f"What made you notice {niche} from this angle?", "Invites a real reply without pushing.", "low"),
        EngagementStrategy("relatable", f"This is the part of {niche} people usually feel but do not say.", "Sounds human and contextual.", "low"),
        EngagementStrategy("soft CTA", f"If you want the simplest next step, this is worth saving.", "Gentle, not spammy.", "medium"),
        EngagementStrategy("playful", f"This one has the rare useful-comment energy.", "Works only when the post tone is casual.", "medium"),
        EngagementStrategy("question", f"How would you compare this with the usual advice around {niche}?", "Creates conversation for a human to review.", "low"),
    ]


def _upsert_social_signal(session: Session, score: SocialOpportunityScore, *, actor: User | None) -> SocialSignal:
    severity = "critical" if score.score >= 90 else "warning" if score.score >= 75 else "info"
    title = "High-score social opportunity" if score.score >= 75 else "Social opportunity scored"
    existing = session.scalar(
        select(SocialSignal).where(
            SocialSignal.social_opportunity_score_id == score.id,
            SocialSignal.signal_type == "social_opportunity.scored",
            SocialSignal.status == "open",
        )
    )
    if existing is None:
        existing = SocialSignal(
            social_source_id=score.post.social_source_id,
            social_post_id=score.social_post_id,
            social_opportunity_score_id=score.id,
            signal_type="social_opportunity.scored",
            severity=severity,
            title=title,
            description=f"Fortuna scored this public/manual opportunity at {score.score}/100.",
            metadata_json={},
        )
        session.add(existing)
    existing.severity = severity
    existing.title = title
    existing.description = f"Fortuna scored this public/manual opportunity at {score.score}/100."
    existing.metadata_json = sanitize_details(
        {
            "score": score.score,
            "confidence": score.confidence_score,
            "angle": score.suggested_engagement_angle,
            "manual_only": True,
        }
    )
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="social_signal.generated",
        resource_type="social_signal",
        resource_id=str(existing.id),
        payload={"signal_type": existing.signal_type, "severity": existing.severity, "score": score.score},
    )
    return existing


def create_opportunity_from_social_score(
    session: Session,
    score: SocialOpportunityScore,
    *,
    actor: User | None,
    assigned_to_user_id: int | None = None,
) -> Opportunity:
    _require_social_manage(session, actor)
    post = score.post
    if post.compliance_status == "blocked":
        raise PermissionError("Blocked or private data cannot create an opportunity.")
    title_source = post.source.display_name if post.source and post.source.display_name else post.post_reference[:60]
    opportunity = create_manual_opportunity(
        session,
        actor=actor,
        title=f"Review {title_source}",
        platform=post.platform if post.platform in {"x", "instagram", "reddit", "other"} else "other",
        url=post.post_url,
        niche=post.niche,
        priority="high" if score.score >= 80 else "normal",
        assigned_to_user_id=assigned_to_user_id,
        reason=f"Fortuna scored this manual/compliant post at {score.score}/100 for human review.",
        suggested_angle=score.suggested_engagement_angle,
        source_type="manual",
    )
    opportunity.score = score.score
    score.opportunity_id = opportunity.id
    score.status = "opportunity_created"
    post.review_status = "opportunity_created"
    comment_strategies_for_opportunity(session, opportunity, actor=actor, create_if_missing=True)
    audit_action(
        session,
        actor=actor,
        action="social_opportunity.created",
        resource_type="opportunity",
        resource_id=str(opportunity.id),
        details={"social_score_id": score.id, "manual_only": True, "auto_posting": False},
    )
    create_learning_event(
        session,
        actor=actor,
        event_type="social.opportunity_created",
        source_type="opportunity",
        source_id=opportunity.id,
        entity_type="social_post",
        entity_id=post.id,
        outcome="partial",
        severity="info",
        summary="Social opportunity created for human review.",
        details={"score": score.score, "manual_only": True, "auto_posting": False},
        confidence_score=score.confidence_score,
    )
    session.flush()
    return opportunity


def record_social_outcome(
    session: Session,
    score: SocialOpportunityScore,
    *,
    actor: User | None,
    outcome: str,
    clicks: int = 0,
    replies: int = 0,
    profile_visits: int = 0,
    conversions: int = 0,
    notes: str | None = None,
) -> SocialSourcePerformance:
    _require_social_manage(session, actor)
    if outcome not in {"reviewed", "skipped", "success", "failure", "partial"}:
        raise ValueError(f"Invalid social outcome: {outcome}")
    post = score.post
    source = post.source
    angle = score.suggested_engagement_angle
    row = session.scalar(
        select(SocialSourcePerformance).where(
            SocialSourcePerformance.social_source_id == (source.id if source else None),
            SocialSourcePerformance.niche == post.niche,
            SocialSourcePerformance.engagement_angle == angle,
        )
    )
    if row is None:
        row = SocialSourcePerformance(
            social_source_id=source.id if source else None,
            platform=post.platform,
            niche=post.niche,
            engagement_angle=angle,
            reviewed_count=0,
            skipped_count=0,
            clicks=0,
            replies=0,
            profile_visits=0,
            conversions=0,
            success_rate=0,
            historical_score=0,
            metadata_json={},
        )
        session.add(row)
    if outcome == "skipped":
        row.skipped_count += 1
        learning_outcome = "ignored"
    else:
        row.reviewed_count += 1
        learning_outcome = "success" if conversions or clicks or replies or profile_visits else "partial"
    row.clicks += max(0, clicks)
    row.replies += max(0, replies)
    row.profile_visits += max(0, profile_visits)
    row.conversions += max(0, conversions)
    total = row.reviewed_count + row.skipped_count
    positive = row.conversions + row.replies + row.clicks
    row.success_rate = _clamp((positive / max(1, total)) * 20)
    row.historical_score = _clamp((row.success_rate * 0.7) + (score.score * 0.3))
    row.last_outcome = outcome
    row.best_timing_window = score.best_timing_window
    row.metadata_json = sanitize_details({"notes": notes, "last_score": score.score, "manual_only": True})
    if source is not None:
        source.historical_score = max(source.historical_score, row.historical_score)
        if learning_outcome == "success":
            source.last_useful_post_at = _now()
        creator = session.scalar(
            select(CreatorWatch).where(
                CreatorWatch.platform == source.platform,
                CreatorWatch.creator_username == source.creator_username,
            )
        )
        if creator is not None:
            creator.historical_score = max(creator.historical_score, row.historical_score)
            if learning_outcome == "success":
                creator.last_useful_post_at = _now()
            if source.watch_reason and not creator.watch_reason:
                creator.watch_reason = source.watch_reason
    score.status = "skipped" if outcome == "skipped" else "reviewed"
    post.review_status = "skipped" if outcome == "skipped" else "reviewed"
    session.flush()
    create_learning_event(
        session,
        actor=actor,
        event_type="social.outcome_recorded",
        source_type="opportunity",
        source_id=score.opportunity_id,
        entity_type="social_source",
        entity_id=source.id if source else None,
        outcome=learning_outcome,
        severity="info",
        summary="Social opportunity outcome recorded from manual review.",
        details={
            "outcome": outcome,
            "clicks": clicks,
            "replies": replies,
            "profile_visits": profile_visits,
            "conversions": conversions,
            "manual_only": True,
        },
        confidence_score=score.confidence_score,
    )
    audit_action(
        session,
        actor=actor,
        action="social_opportunity.outcome_recorded",
        resource_type="social_opportunity_score",
        resource_id=str(score.id),
        details={"outcome": outcome, "manual_only": True},
    )
    return row


def best_social_sources(session: Session, *, limit: int = 5) -> list[SocialSourcePerformance]:
    return list(
        session.scalars(
            select(SocialSourcePerformance)
            .order_by(desc(SocialSourcePerformance.historical_score), desc(SocialSourcePerformance.success_rate))
            .limit(limit)
        ).all()
    )


def best_social_opportunities(session: Session, *, limit: int = 5) -> list[SocialOpportunityScore]:
    return list(
        session.scalars(
            select(SocialOpportunityScore)
            .options(selectinload(SocialOpportunityScore.post).selectinload(SocialPost.source))
            .where(SocialOpportunityScore.status.in_(("new", "reviewing")))
            .order_by(desc(SocialOpportunityScore.score), desc(SocialOpportunityScore.confidence_score), desc(SocialOpportunityScore.updated_at))
            .limit(limit)
        ).all()
    )


def route_social_opportunity_alert(
    session: Session,
    score: SocialOpportunityScore,
    *,
    actor: User | None,
    simulate_only: bool = True,
) -> list[NotificationDeliveryAttempt]:
    _require_social_view(session, actor)
    purposes = ["alerts"]
    if score.score >= 90:
        purposes.append("hq")
    targets = active_targets_for_purposes(session, purposes)
    attempts: list[NotificationDeliveryAttempt] = []
    if not targets:
        upsert_recommendation(
            session,
            actor=actor,
            recommendation_type="social_alert_target_missing",
            title="Register Fortuna Alerts target",
            description="High-score social opportunity alerts need a Fortuna Alerts notification target before live delivery.",
            severity="warning",
            entity_type="social_opportunity_score",
            entity_id=score.id,
            metadata={"score": score.score, "purposes": purposes},
        )
        session.add(SocialSignal(
            social_source_id=score.post.social_source_id,
            social_post_id=score.social_post_id,
            social_opportunity_score_id=score.id,
            signal_type="social_notification.target_missing",
            severity="warning",
            title="Social alert target missing",
            description="Fortuna could not route this alert because no matching target is registered.",
            metadata_json={"purposes": purposes},
        ))
        session.flush()
        return attempts
    for target in targets:
        attempts.append(
            create_delivery_attempt(
                session,
                target,
                event_type="social.opportunity.alert",
                actor=actor,
                status="skipped" if simulate_only else "pending",
                metadata={
                    "score": score.score,
                    "confidence": score.confidence_score,
                    "purpose": target.purpose,
                    "manual_only": True,
                    "simulated": simulate_only,
                },
            )
        )
    emit_event(
        session,
        actor=actor,
        event_name="social.opportunity.alert_routed",
        resource_type="social_opportunity_score",
        resource_id=str(score.id),
        payload={"attempts": len(attempts), "simulate_only": simulate_only},
    )
    return attempts


def social_notification_framework_status(session: Session) -> dict:
    latest_attempt = session.scalar(
        select(NotificationDeliveryAttempt)
        .where(NotificationDeliveryAttempt.event_type == "social.opportunity.alert")
        .order_by(desc(NotificationDeliveryAttempt.created_at), desc(NotificationDeliveryAttempt.id))
        .limit(1)
    )
    return {
        "activity_notification_placeholder": True,
        "creator_model_routing_placeholder": True,
        "alert_preference_settings_placeholder": True,
        "notification_queue_placeholder": True,
        "dashboard_notification_display_placeholder": True,
        "last_social_alert_status": latest_attempt.status if latest_attempt else "none",
    }


def official_api_adapter_status() -> dict:
    return {
        "x_official_api": "placeholder_only",
        "instagram_official_api": "placeholder_only",
        "scraping": "not_supported",
        "auto_posting": "not_supported",
    }


def create_social_discovery_source_config(
    session: Session,
    *,
    actor: User | None,
    platform: str,
    name: str,
    source_type: str = "manual",
    reference_url: str | None = None,
    niche: str | None = None,
    compliance_status: str = "approved",
) -> SocialDiscoverySourceConfig:
    _require_social_manage(session, actor)
    if platform not in SOCIAL_PLATFORMS:
        raise ValueError(f"Invalid social platform: {platform}")
    if source_type not in SOCIAL_DISCOVERY_SOURCE_TYPES:
        raise ValueError(f"Invalid discovery source type: {source_type}")
    if compliance_status not in SOCIAL_COMPLIANCE_STATUSES:
        raise ValueError(f"Invalid compliance status: {compliance_status}")
    config = SocialDiscoverySourceConfig(
        platform=platform,
        source_type=source_type,
        name=name.strip() or "Manual Source",
        reference_url=reference_url,
        niche=niche,
        compliance_status=compliance_status,
        is_active=True,
        metadata_json={"manual_only": True, "auto_posting": False},
    )
    session.add(config)
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="social_discovery.source_config_created",
        resource_type="social_discovery_source_config",
        resource_id=str(config.id),
        details={"platform": platform, "source_type": source_type, "compliance_status": compliance_status},
    )
    return config


def create_social_discovery_run(
    session: Session,
    *,
    actor: User | None,
    run_type: str,
    source_config: SocialDiscoverySourceConfig | None = None,
    status: str = "succeeded",
    summary: dict | None = None,
) -> SocialDiscoveryRun:
    _require_social_manage(session, actor)
    if run_type not in SOCIAL_DISCOVERY_RUN_TYPES:
        raise ValueError(f"Invalid discovery run type: {run_type}")
    if status not in SOCIAL_DISCOVERY_RUN_STATUSES:
        raise ValueError(f"Invalid discovery run status: {status}")
    run = SocialDiscoveryRun(
        run_type=run_type,
        status=status,
        source_config_id=source_config.id if source_config else None,
        started_by_user_id=actor.id if actor else None,
        summary_json=sanitize_details(summary or {"manual_only": True, "auto_posting": False}),
        finished_at=_now() if status in {"succeeded", "failed"} else None,
    )
    session.add(run)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="social_discovery.run_completed" if status == "succeeded" else "social_discovery.run_started",
        resource_type="social_discovery_run",
        resource_id=str(run.id),
        payload={"run_type": run_type, "status": status},
    )
    return run


def _lead_score_from_inputs(
    *,
    confidence_score: int,
    source_performance: int,
    compliance_status: str,
    reason_found: str,
) -> int:
    text = reason_found.casefold()
    quality_hint = 15 if any(word in text for word in ("active", "niche", "conversation", "match", "timing")) else 0
    score = _clamp((confidence_score * 0.55) + (source_performance * 0.3) + quality_hint)
    if compliance_status == "review_required":
        return min(score, 65)
    if compliance_status == "blocked":
        return 0
    return score


def create_social_discovery_lead(
    session: Session,
    *,
    actor: User | None,
    platform: str,
    source_name: str,
    source_reference: str | None = None,
    post_reference: str | None = None,
    niche: str | None = None,
    reason_found: str = "Manual public lead added for human review.",
    confidence_score: int = 60,
    compliance_status: str = "approved",
    recommended_angle: str | None = None,
    discovery_run: SocialDiscoveryRun | None = None,
    social_source: SocialSource | None = None,
) -> SocialDiscoveryLead:
    _require_social_manage(session, actor)
    if platform not in SOCIAL_PLATFORMS:
        raise ValueError(f"Invalid social platform: {platform}")
    if compliance_status not in SOCIAL_COMPLIANCE_STATUSES:
        raise ValueError(f"Invalid compliance status: {compliance_status}")
    performance = _source_performance_score(session, social_source, niche)
    score = _lead_score_from_inputs(
        confidence_score=confidence_score,
        source_performance=performance,
        compliance_status=compliance_status,
        reason_found=reason_found,
    )
    lead = SocialDiscoveryLead(
        discovery_run_id=discovery_run.id if discovery_run else None,
        social_source_id=social_source.id if social_source else None,
        platform=platform,
        source_name=source_name.strip() or "Manual Source",
        source_reference=source_reference,
        post_reference=post_reference,
        niche=niche,
        reason_found=reason_found,
        confidence_score=_clamp(confidence_score),
        opportunity_score=score,
        compliance_status=compliance_status,
        recommended_angle=recommended_angle or ("curiosity" if score >= 70 else "question"),
        status="new",
        metadata_json={"manual_only": True, "auto_posting": False, "source_performance": performance},
    )
    session.add(lead)
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="social_discovery.lead_created",
        resource_type="social_discovery_lead",
        resource_id=str(lead.id),
        details={"platform": platform, "score": score, "compliance_status": compliance_status, "manual_only": True},
    )
    create_learning_event(
        session,
        actor=actor,
        event_type="social_discovery.lead_created",
        source_type="opportunity",
        source_id=lead.id,
        entity_type="social_discovery_lead",
        entity_id=lead.id,
        outcome="partial",
        severity="info",
        summary="Social discovery lead created for human review.",
        details={"platform": platform, "score": score, "manual_only": True, "auto_posting": False},
        confidence_score=lead.confidence_score,
    )
    return lead


def rank_social_opportunity_leads(session: Session, *, limit: int = 5) -> list[SocialDiscoveryLead]:
    leads = list(
        session.scalars(
            select(SocialDiscoveryLead)
            .where(SocialDiscoveryLead.status == "new")
            .order_by(
                desc(SocialDiscoveryLead.opportunity_score),
                desc(SocialDiscoveryLead.confidence_score),
                desc(SocialDiscoveryLead.created_at),
                desc(SocialDiscoveryLead.id),
            )
            .limit(limit)
        ).all()
    )
    return leads


def explain_social_discovery_lead(lead: SocialDiscoveryLead) -> str:
    if lead.compliance_status == "blocked":
        return "This lead is blocked for compliance and should not be used."
    if lead.opportunity_score >= 80:
        return "Strong niche fit, useful timing, and enough confidence for human review."
    if lead.opportunity_score >= 60:
        return "Promising enough to review manually, but not urgent."
    return "Low-confidence lead. Review only if it matches today’s focus."


def comment_angles_for_discovery_lead(lead: SocialDiscoveryLead) -> list[EngagementStrategy]:
    if lead.compliance_status == "blocked":
        return [EngagementStrategy("warning", "Do not use this lead.", "Compliance blocked.", "high")]
    niche = lead.niche or "this topic"
    return [
        EngagementStrategy("curiosity", f"What made this angle around {niche} stand out?", "Invites a human reply without pushing.", "low"),
        EngagementStrategy("relatable", f"This is the part of {niche} people usually feel but rarely say.", "Feels natural and contextual.", "low"),
        EngagementStrategy("playful", "This has useful comment-section energy.", "Only use when the post tone is casual.", "medium"),
        EngagementStrategy("question", f"How would you compare this with the usual advice around {niche}?", "Keeps the reply conversational.", "low"),
        EngagementStrategy("soft CTA", "Worth saving if you want the simplest next step.", "Gentle and human-reviewed.", "medium"),
    ]


def create_opportunity_from_discovery_lead(
    session: Session,
    lead: SocialDiscoveryLead,
    *,
    actor: User | None,
    assigned_to_user_id: int | None = None,
) -> Opportunity:
    _require_social_manage(session, actor)
    if lead.compliance_status == "blocked":
        raise PermissionError("Blocked social discovery leads cannot become opportunities.")
    opportunity = create_manual_opportunity(
        session,
        actor=actor,
        title=f"Review {lead.source_name}",
        platform=lead.platform,
        url=lead.post_reference or lead.source_reference,
        niche=lead.niche,
        priority="high" if lead.opportunity_score >= 80 else "normal",
        assigned_to_user_id=assigned_to_user_id,
        reason=f"Discovery lead scored {lead.opportunity_score}/100 for human review.",
        suggested_angle=lead.recommended_angle,
        source_type="manual",
    )
    opportunity.score = lead.opportunity_score
    lead.status = "converted_to_opportunity"
    lead.metadata_json = sanitize_details({**(lead.metadata_json or {}), "opportunity_id": opportunity.id})
    comment_strategies_for_opportunity(session, opportunity, actor=actor, create_if_missing=True)
    create_learning_event(
        session,
        actor=actor,
        event_type="social_discovery.lead_converted",
        source_type="opportunity",
        source_id=opportunity.id,
        entity_type="social_discovery_lead",
        entity_id=lead.id,
        outcome="success",
        severity="info",
        summary="Discovery lead converted to a human-reviewed opportunity.",
        details={"lead_id": lead.id, "score": lead.opportunity_score, "manual_only": True, "auto_posting": False},
        confidence_score=lead.confidence_score,
    )
    create_confidence_record(
        session,
        subject_type="opportunity",
        subject_id=opportunity.id,
        previous_score=None,
        new_score=lead.opportunity_score,
        reason="Discovery lead converted to opportunity.",
        evidence={"lead_id": lead.id, "manual_only": True},
    )
    if lead.social_source_id:
        source = session.get(SocialSource, lead.social_source_id)
        performance = _performance_bucket(session, source, lead.platform, lead.niche, lead.recommended_angle)
        performance.reviewed_count += 1
        performance.clicks += 0
        performance.replies += 1
        performance.last_outcome = "converted"
        performance.historical_score = _clamp(performance.historical_score + 4)
        performance.success_rate = round((performance.replies / max(1, performance.reviewed_count)) * 100)
        performance.metadata_json = sanitize_details(
            {**(performance.metadata_json or {}), "last_discovery_lead_id": lead.id, "manual_only": True}
        )
        if source is not None:
            source.historical_score = max(source.historical_score or 0, performance.historical_score)
            source.last_useful_post_at = _now()
    audit_action(
        session,
        actor=actor,
        action="social_discovery.lead_converted",
        resource_type="opportunity",
        resource_id=str(opportunity.id),
        details={"lead_id": lead.id, "manual_only": True, "auto_posting": False},
    )
    session.flush()
    return opportunity


def record_social_discovery_lead_feedback(
    session: Session,
    lead: SocialDiscoveryLead,
    *,
    actor: User | None,
    status: str,
    notes: str | None = None,
) -> SocialDiscoveryLead:
    _require_social_manage(session, actor)
    if status not in SOCIAL_DISCOVERY_LEAD_STATUSES:
        raise ValueError(f"Invalid lead status: {status}")
    previous_score = lead.confidence_score
    lead.status = status
    if status == "skipped":
        lead.confidence_score = max(0, lead.confidence_score - 5)
        outcome = "ignored"
    elif status in {"reviewed", "converted_to_opportunity"}:
        lead.confidence_score = min(100, lead.confidence_score + 3)
        outcome = "partial" if status == "reviewed" else "success"
    else:
        outcome = "unknown"
    lead.metadata_json = sanitize_details({**(lead.metadata_json or {}), "feedback_notes": notes})
    if lead.social_source_id:
        source = session.get(SocialSource, lead.social_source_id)
        performance = _performance_bucket(session, source, lead.platform, lead.niche, lead.recommended_angle)
        if status == "skipped":
            performance.skipped_count += 1
            performance.last_outcome = "skipped"
            performance.historical_score = max(0, performance.historical_score - 2)
        elif status in {"reviewed", "converted_to_opportunity"}:
            performance.reviewed_count += 1
            performance.last_outcome = "reviewed" if status == "reviewed" else "converted"
            performance.historical_score = _clamp(performance.historical_score + (2 if status == "reviewed" else 4))
        performance.success_rate = round((performance.replies / max(1, performance.reviewed_count)) * 100)
        performance.metadata_json = sanitize_details(
            {**(performance.metadata_json or {}), "last_discovery_feedback": status, "manual_only": True}
        )
        if source is not None:
            source.historical_score = max(0, min(100, performance.historical_score))
    create_learning_event(
        session,
        actor=actor,
        event_type=f"social_discovery.lead_{status}",
        source_type="opportunity",
        source_id=lead.id,
        entity_type="social_discovery_lead",
        entity_id=lead.id,
        outcome=outcome,
        severity="info",
        summary=f"Discovery lead marked {status}.",
        details={"notes": notes, "manual_only": True},
        confidence_score=lead.confidence_score,
    )
    create_confidence_record(
        session,
        subject_type="opportunity",
        subject_id=f"discovery_lead:{lead.id}",
        previous_score=previous_score,
        new_score=lead.confidence_score,
        reason=f"Discovery lead feedback: {status}.",
        evidence={"status": status, "manual_only": True},
    )
    session.flush()
    return lead


def route_social_discovery_lead_alert(
    session: Session,
    lead: SocialDiscoveryLead,
    *,
    actor: User | None,
    simulate_only: bool = True,
) -> list[NotificationDeliveryAttempt]:
    _require_social_view(session, actor)
    purposes = ["alerts"]
    if lead.opportunity_score >= 90:
        purposes.append("hq")
    targets = active_targets_for_purposes(session, purposes)
    if not targets:
        upsert_recommendation(
            session,
            actor=actor,
            recommendation_type="social_discovery_alert_target_missing",
            title="Register Fortuna Alerts target",
            description="Discovery alerts need a Fortuna Alerts target before live delivery.",
            severity="warning",
            entity_type="social_discovery_lead",
            entity_id=lead.id,
            metadata={"score": lead.opportunity_score, "purposes": purposes, "simulated": True},
        )
        emit_event(
            session,
            actor=actor,
            event_name="social_discovery.alert_simulated",
            resource_type="social_discovery_lead",
            resource_id=str(lead.id),
            payload={"reason": "missing_target", "purposes": purposes},
        )
        return []
    attempts: list[NotificationDeliveryAttempt] = []
    for target in targets:
        attempts.append(
            create_delivery_attempt(
                session,
                target,
                event_type="social.discovery.alert",
                actor=actor,
                status="skipped" if simulate_only else "pending",
                metadata={
                    "lead_id": lead.id,
                    "score": lead.opportunity_score,
                    "purpose": target.purpose,
                    "manual_only": True,
                    "simulated": simulate_only,
                },
            )
        )
    return attempts
