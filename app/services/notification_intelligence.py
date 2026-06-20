from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.button_issue import ButtonIssue
from app.models.friction import FrictionItem
from app.models.learning import LearningEvent
from app.models.platform import PlatformConnection
from app.models.recommendation import Recommendation
from app.models.reporting import NotificationDeliveryAttempt, NotificationTarget
from app.models.user import User
from app.services.events import emit_event
from app.services.learning import create_learning_event
from app.services.notifications import canonical_purpose
from app.services.platform_connections import (
    PLATFORM_DEFINITIONS,
    PlatformIntegrationStatus,
    platform_connection_status,
    platform_connections_status,
)
from app.services.recommendations import upsert_recommendation
from app.services.shared_status import StatusCondition, compute_shared_status, normalize_status

NOTIFICATION_PRIORITIES = ("low", "medium", "high", "critical")
PRIORITY_TO_STATUS = {
    "low": "healthy",
    "medium": "needs_review",
    "high": "needs_attention",
    "critical": "critical",
}


@dataclass(frozen=True)
class NotificationSignal:
    signal_type: str
    title: str
    summary: str
    priority: str
    source: str
    evidence: str
    recommended_action: str
    route: str | None = None


@dataclass(frozen=True)
class NotificationDecision:
    signal: NotificationSignal
    show_in_today: bool
    alert_owner: bool
    escalate: bool
    suppressed: bool
    route: str | None
    reason: str


@dataclass(frozen=True)
class AlertHealthSummary:
    status: str
    label: str
    success_rate: int | None
    total_attempts: int
    failed_attempts: int
    stale_route_count: int
    disabled_route_count: int
    last_delivery_at: datetime | None
    evidence: str
    next_action: str


@dataclass(frozen=True)
class AlertRouteSummary:
    source_label: str
    route_label: str
    status: str
    evidence: str


@dataclass(frozen=True)
class FrictionSignalSummary:
    status: str
    repeated_help_count: int
    repeated_back_count: int
    open_button_issue_count: int
    evidence: str
    recommendation: str


@dataclass(frozen=True)
class CooBriefingFoundation:
    top_alerts: tuple[str, ...]
    top_blockers: tuple[str, ...]
    system_health_summary: str
    next_action: str


def _now() -> datetime:
    return datetime.now(UTC)


def _priority(value: str) -> str:
    normalized = (value or "low").strip().casefold()
    return normalized if normalized in NOTIFICATION_PRIORITIES else "low"


def _platform_label(platform: str) -> str:
    definition = PLATFORM_DEFINITIONS.get(platform)
    if definition is None:
        return platform.replace("_", " ").title()
    return f"{definition.emoji} {definition.display_name}"


def _route_label(route: str | None) -> str:
    if not route:
        return "No route yet"
    return {
        "hq": "Fortuna HQ",
        "ops": "Fortuna Ops",
        "alerts": "Fortuna Alerts",
        "owner": "Owner",
        "owner+hq": "Owner + HQ",
    }.get(route, route.replace("_", " ").title())


def evaluate_notification_signal(signal: NotificationSignal) -> NotificationDecision:
    priority = _priority(signal.priority)
    if priority == "low":
        return NotificationDecision(
            signal=signal,
            show_in_today=False,
            alert_owner=False,
            escalate=False,
            suppressed=True,
            route=signal.route,
            reason="Low-priority information is kept quiet by default.",
        )
    if priority == "medium":
        return NotificationDecision(
            signal=signal,
            show_in_today=True,
            alert_owner=False,
            escalate=False,
            suppressed=False,
            route=signal.route,
            reason="Medium-priority items appear in Today instead of interrupting the owner.",
        )
    if priority == "high":
        return NotificationDecision(
            signal=signal,
            show_in_today=True,
            alert_owner=True,
            escalate=False,
            suppressed=False,
            route=signal.route or "owner",
            reason="High-priority items should alert the owner.",
        )
    return NotificationDecision(
        signal=signal,
        show_in_today=True,
        alert_owner=True,
        escalate=True,
        suppressed=False,
        route=signal.route or "owner+hq",
        reason="Critical items escalate immediately.",
    )


def record_notification_decision(
    session: Session,
    decision: NotificationDecision,
    *,
    actor: User | None = None,
) -> None:
    priority = _priority(decision.signal.priority)
    emit_event(
        session,
        actor=actor,
        event_name="notification_intelligence.evaluated",
        resource_type="notification_signal",
        resource_id=decision.signal.signal_type,
        status="skipped" if decision.suppressed else "success",
        payload={
            "priority": priority,
            "show_in_today": decision.show_in_today,
            "alert_owner": decision.alert_owner,
            "escalate": decision.escalate,
            "route": decision.route,
            "summary": decision.signal.summary,
        },
    )
    if priority in {"medium", "high", "critical"}:
        severity = "critical" if priority == "critical" else "warning"
        upsert_recommendation(
            session,
            actor=actor,
            recommendation_type=f"notification_signal_{decision.signal.signal_type}",
            title=decision.signal.title[:200],
            description=f"{decision.signal.summary} Next: {decision.signal.recommended_action}",
            severity=severity,
            entity_type="notification_signal",
            entity_id=decision.signal.signal_type,
            metadata={"priority": priority, "route": decision.route, "evidence": decision.signal.evidence},
        )


def platform_notification_signal(status: PlatformIntegrationStatus) -> NotificationSignal:
    if status.notifications.status == "failed":
        priority = "critical"
        title = f"{status.display_name} notification route is broken"
        summary = f"{status.display_name} alerts cannot be trusted right now."
        action = "Open Notification Center and fix the route."
    elif status.notifications.status == "not_configured":
        priority = "medium"
        title = f"{status.display_name} alerts need setup"
        summary = f"{status.display_name} can be monitored, but no alert route is configured yet."
        action = "Register Fortuna Alerts or HQ before enabling real alerts."
    elif status.stats.status == "stale":
        priority = "medium"
        title = f"{status.display_name} stats are stale"
        summary = f"{status.display_name} stats need a fresh check."
        action = "Run a stats check after connection is verified."
    else:
        priority = "low"
        title = f"{status.display_name} notification check completed"
        summary = f"{status.display_name} notification status is {status.notifications.label.lower()}."
        action = status.notifications.next_action or "No owner alert needed."
    return NotificationSignal(
        signal_type=f"platform_{status.platform}_notifications",
        title=title,
        summary=summary,
        priority=priority,
        source=status.platform,
        evidence=status.notifications.evidence,
        recommended_action=action,
        route=PLATFORM_DEFINITIONS[status.platform].notification_purpose,
    )


def refresh_platform_status(session: Session, platform: str) -> PlatformIntegrationStatus:
    # Non-blocking in product terms: this only reads/persists prepared status. Website checks run only on explicit Test Website.
    status = platform_connection_status(session, platform)
    connection = session.scalar(select(PlatformConnection).where(PlatformConnection.platform == platform))
    if connection is not None:
        evidence = dict(connection.evidence_json or {})
        evidence["notification_refresh"] = {
            "checked_at": _now().isoformat(),
            "status": status.notifications.status,
            "summary": status.notifications.evidence,
        }
        connection.evidence_json = evidence
        connection.last_notification_check_at = _now()
        session.flush()
    signal = platform_notification_signal(status)
    record_notification_decision(session, evaluate_notification_signal(signal))
    session.flush()
    return platform_connection_status(session, platform)


def refresh_all_platform_statuses(session: Session) -> list[PlatformIntegrationStatus]:
    statuses = [refresh_platform_status(session, status.platform) for status in platform_connections_status(session)]
    session.flush()
    return statuses


def alert_health_summary(session: Session, *, lookback_hours: int = 168) -> AlertHealthSummary:
    since = _now() - timedelta(hours=lookback_hours)
    attempts = list(
        session.scalars(
            select(NotificationDeliveryAttempt)
            .where(NotificationDeliveryAttempt.attempted_at >= since)
            .order_by(desc(NotificationDeliveryAttempt.attempted_at), desc(NotificationDeliveryAttempt.id))
        ).all()
    )
    total = len(attempts)
    failed = sum(1 for attempt in attempts if attempt.status == "failed")
    sent = sum(1 for attempt in attempts if attempt.status == "sent")
    success_rate = int(round((sent / total) * 100)) if total else None
    last_delivery_at = attempts[0].attempted_at if attempts else None
    disabled_routes = int(session.scalar(select(func.count(NotificationTarget.id)).where(NotificationTarget.is_active.is_(False))) or 0)
    active_targets = list(session.scalars(select(NotificationTarget).where(NotificationTarget.is_active.is_(True))).all())
    stale_cutoff = _now() - timedelta(days=7)
    stale_routes = sum(1 for target in active_targets if target.last_tested_at is None or target.last_tested_at < stale_cutoff)
    if total and failed == total:
        status = "critical"
        evidence = "All recent notification delivery attempts failed."
        next_action = "Open Notification Center and test the active route."
    elif failed >= 3:
        status = "needs_attention"
        evidence = f"{failed} delivery attempt(s) failed in the last {lookback_hours} hours."
        next_action = "Review failed deliveries and confirm the Telegram targets."
    elif stale_routes:
        status = "needs_review"
        evidence = f"{stale_routes} active route(s) have not been tested recently."
        next_action = "Run a safe route test."
    elif total == 0:
        status = "needs_review"
        evidence = "No recent delivery attempts have been recorded."
        next_action = "Configure a target or run a safe simulation."
    else:
        status = "healthy"
        evidence = f"{sent}/{total} recent notification attempt(s) were sent successfully."
        next_action = "No action needed."
    return AlertHealthSummary(
        status=status,
        label={
            "healthy": "Healthy",
            "needs_review": "Needs Review",
            "needs_attention": "Needs Attention",
            "critical": "Critical",
        }[status],
        success_rate=success_rate,
        total_attempts=total,
        failed_attempts=failed,
        stale_route_count=stale_routes,
        disabled_route_count=disabled_routes,
        last_delivery_at=last_delivery_at,
        evidence=evidence,
        next_action=next_action,
    )


def alert_route_summaries(session: Session) -> list[AlertRouteSummary]:
    active_purposes = {
        canonical_purpose(purpose)
        for purpose in session.scalars(select(NotificationTarget.purpose).where(NotificationTarget.is_active.is_(True))).all()
    }
    rows = [
        ("📸 Instagram", "alerts"),
        ("𝕏 X", "alerts"),
        ("🔥 OnlyFans", "alerts"),
        ("📢 Telegram", "hq"),
        ("📧 Email", None),
        ("🚨 Critical System Alerts", "owner+hq" if {"hq", "alerts"} & active_purposes else "hq"),
        ("🧠 Intelligence", "hq"),
    ]
    summaries: list[AlertRouteSummary] = []
    for source, route in rows:
        configured = bool(route and any(part in active_purposes for part in str(route).split("+")))
        status = "configured" if configured else "not_configured"
        summaries.append(
            AlertRouteSummary(
                source_label=source,
                route_label=_route_label(route),
                status=status,
                evidence="A matching active notification target exists." if configured else "No active target is registered yet.",
            )
        )
    return summaries


def friction_detector_summary(session: Session) -> FrictionSignalSummary:
    help_count = int(
        session.scalar(
            select(func.count(FrictionItem.id)).where(
                FrictionItem.screen.ilike("%notification%"),
                FrictionItem.issue.ilike("%help%"),
            )
        )
        or 0
    )
    back_count = int(
        session.scalar(
            select(func.count(FrictionItem.id)).where(
                FrictionItem.screen.ilike("%notification%"),
                FrictionItem.issue.ilike("%back%"),
            )
        )
        or 0
    )
    open_button_issues = int(
        session.scalar(
            select(func.count(ButtonIssue.id)).where(
                ButtonIssue.status == "open",
                ButtonIssue.screen.ilike("%notification%"),
            )
        )
        or 0
    )
    conditions = [
        StatusCondition("help_usage", "needs_review" if help_count >= 3 else "healthy", "Repeated Help usage.", help_count if help_count >= 3 else 0),
        StatusCondition("back_usage", "needs_review" if back_count >= 3 else "healthy", "Repeated Back usage.", back_count if back_count >= 3 else 0),
        StatusCondition("button_issues", "needs_attention" if open_button_issues else "healthy", "Open notification button issues.", open_button_issues),
    ]
    shared = compute_shared_status(conditions)
    recommendation = "No UX action needed." if shared.is_healthy else "Simplify Notification Center and review button paths."
    if not shared.is_healthy:
        upsert_recommendation(
            session,
            actor=None,
            recommendation_type="notification_center_friction",
            title="Simplify Notification Center",
            description="Fortuna noticed repeated friction around Notification Center. Review Help, Back, and button paths.",
            severity="warning",
            entity_type="screen",
            entity_id="platforms:notifications",
            metadata={"help_count": help_count, "back_count": back_count, "button_issues": open_button_issues},
        )
    return FrictionSignalSummary(
        status=shared.status,
        repeated_help_count=help_count,
        repeated_back_count=back_count,
        open_button_issue_count=open_button_issues,
        evidence="No repeated notification friction detected." if shared.is_healthy else "; ".join(shared.evidence),
        recommendation=recommendation,
    )


def record_notification_outcome(
    session: Session,
    *,
    alert_key: str,
    outcome: str,
    actor: User | None = None,
) -> LearningEvent:
    aliases = {
        "acted": "success",
        "acted_on": "success",
        "opened": "partial",
        "dismissed": "ignored",
    }
    normalized = aliases.get(outcome, outcome)
    normalized = normalized if normalized in {"success", "ignored", "partial", "failure", "unknown"} else "unknown"
    summary = {
        "success": "Notification was acted on.",
        "ignored": "Notification was ignored.",
        "partial": "Notification was reviewed but not fully acted on.",
        "failure": "Notification did not produce the intended action.",
        "unknown": "Notification outcome was recorded.",
    }[normalized]
    return create_learning_event(
        session,
        event_type="notification.outcome_recorded",
        source_type="notification",
        source_id=alert_key,
        entity_type="notification_alert",
        entity_id=alert_key,
        outcome=normalized,
        severity="info" if normalized in {"success", "ignored", "partial", "unknown"} else "warning",
        summary=summary,
        actor=actor,
        details={"alert_key": alert_key, "usefulness_signal": normalized},
    )


def notification_learning_summary(session: Session) -> dict[str, int]:
    events = list(
        session.scalars(
            select(LearningEvent).where(LearningEvent.source_type == "notification").order_by(desc(LearningEvent.created_at)).limit(200)
        ).all()
    )
    return {
        "total": len(events),
        "acted_on": sum(1 for event in events if event.outcome == "success"),
        "ignored": sum(1 for event in events if event.outcome == "ignored"),
        "partial": sum(1 for event in events if event.outcome == "partial"),
    }


def coo_briefing_foundation(session: Session) -> CooBriefingFoundation:
    health = alert_health_summary(session)
    friction = friction_detector_summary(session)
    recommendations = list(
        session.scalars(
            select(Recommendation)
            .where(Recommendation.status == "open")
            .where(Recommendation.severity.in_(("warning", "critical")))
            .order_by(desc(Recommendation.created_at), desc(Recommendation.id))
            .limit(5)
        ).all()
    )
    top_alerts = tuple(item.title for item in recommendations[:3]) or ("No high-priority alerts right now.",)
    blockers = []
    if health.status != "healthy":
        blockers.append(f"Alert health: {health.next_action}")
    if friction.status != "healthy":
        blockers.append("Notification Center friction needs review.")
    if not blockers:
        blockers.append("No notification blockers found.")
    return CooBriefingFoundation(
        top_alerts=top_alerts,
        top_blockers=tuple(blockers[:3]),
        system_health_summary=f"Alert health is {health.label.lower()}.",
        next_action=health.next_action if health.status != "healthy" else "Keep alerts quiet until a meaningful signal appears.",
    )
