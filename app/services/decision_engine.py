from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.event_log import EventLog
from app.models.opportunity import Opportunity
from app.models.recommendation import Recommendation
from app.models.user import User
from app.services.audit import sanitize_details
from app.services.auth import audit_action
from app.services.bot_instances import bot_instance_diagnostics
from app.services.button_health import button_health_summary
from app.services.events import emit_event
from app.services.learning import create_learning_event
from app.services.notification_intelligence import alert_health_summary
from app.services.platform_connections import platform_connections_overview
from app.services.recovery import recovery_risk_assessment
from app.services.recommendations import upsert_recommendation
from app.services.shared_status import SHARED_STATUS_ORDER
from app.services.system_truth import system_truth

DECISION_CATEGORIES = (
    "recovery",
    "system_health",
    "telegram_bot",
    "navigation",
    "notification",
    "platform_connection",
    "opportunity",
    "social_intelligence",
    "team",
    "learning",
    "friction",
    "setup",
    "deployment",
    "security",
    "general",
)

CONFIDENCE_LEVELS = ("high", "medium", "low")

SEVERITY_SCORE = {
    "healthy": 0,
    "needs_review": 25,
    "needs_attention": 55,
    "critical": 85,
    "info": 10,
    "warning": 55,
}

CATEGORY_LABELS = {
    "recovery": "Recovery",
    "system_health": "System Health",
    "telegram_bot": "Telegram Bot",
    "navigation": "Navigation",
    "notification": "Notifications",
    "platform_connection": "Platform Connections",
    "opportunity": "Opportunities",
    "social_intelligence": "Social Intelligence",
    "team": "Team",
    "learning": "Learning",
    "friction": "UX Friction",
    "setup": "Setup",
    "deployment": "Deployment",
    "security": "Security",
    "general": "General",
}

STATUS_ICONS = {
    "healthy": "🟢",
    "needs_review": "🟡",
    "needs_attention": "🟠",
    "critical": "🔴",
}


@dataclass(frozen=True)
class Decision:
    title: str
    category: str
    severity: str
    priority_rank: int
    impact: str
    risk: str
    recommendation: str
    confidence: str
    evidence_summary: str
    source_records: tuple[str, ...]
    next_best_move: str
    can_wait: bool
    created_at: datetime
    action_page: str = "menu"
    details: dict[str, object] = field(default_factory=dict)

    @property
    def category_label(self) -> str:
        return CATEGORY_LABELS.get(self.category, self.category.replace("_", " ").title())

    @property
    def severity_icon(self) -> str:
        return STATUS_ICONS.get(self.severity, "🟡")


@dataclass(frozen=True)
class CooBriefing:
    generated_at: datetime
    overall_status: str
    overall_label: str
    what_changed: tuple[str, ...]
    top_priority: Decision | None
    risks: tuple[Decision, ...]
    opportunities: tuple[Decision, ...]
    can_wait: tuple[Decision, ...]
    next_best_move: str
    decisions: tuple[Decision, ...]
    evidence_summary: tuple[str, ...]


def _now() -> datetime:
    return datetime.now(UTC)


def _severity_score(value: str) -> int:
    return SEVERITY_SCORE.get(value, SEVERITY_SCORE.get(value.casefold(), 25))


def _priority(
    *,
    severity: str,
    business_impact: int,
    urgency: int,
    data_loss_risk: int = 0,
    operational_blocking: int = 0,
    owner_action_required: bool = True,
    confidence: str = "medium",
    can_wait: bool = False,
) -> int:
    confidence_bonus = {"high": 8, "medium": 0, "low": -12}.get(confidence, 0)
    owner_bonus = 8 if owner_action_required else 0
    wait_penalty = 35 if can_wait else 0
    raw = (
        _severity_score(severity)
        + business_impact
        + urgency
        + data_loss_risk
        + operational_blocking
        + owner_bonus
        + confidence_bonus
        - wait_penalty
    )
    return max(1, min(100, int(round(raw / 4))))


def _decision(
    *,
    title: str,
    category: str,
    severity: str,
    impact: str,
    risk: str,
    recommendation: str,
    confidence: str,
    evidence_summary: str,
    source_records: tuple[str, ...],
    next_best_move: str,
    can_wait: bool,
    action_page: str,
    created_at: datetime,
    business_impact: int,
    urgency: int,
    data_loss_risk: int = 0,
    operational_blocking: int = 0,
    owner_action_required: bool = True,
    details: dict[str, object] | None = None,
) -> Decision | None:
    if category not in DECISION_CATEGORIES:
        raise ValueError(f"Invalid decision category: {category}")
    if confidence not in CONFIDENCE_LEVELS:
        confidence = "medium"
    if not evidence_summary.strip() or not source_records:
        return None
    return Decision(
        title=title,
        category=category,
        severity=severity,
        priority_rank=_priority(
            severity=severity,
            business_impact=business_impact,
            urgency=urgency,
            data_loss_risk=data_loss_risk,
            operational_blocking=operational_blocking,
            owner_action_required=owner_action_required,
            confidence=confidence,
            can_wait=can_wait,
        ),
        impact=impact,
        risk=risk,
        recommendation=recommendation,
        confidence=confidence,
        evidence_summary=evidence_summary,
        source_records=source_records,
        next_best_move=next_best_move,
        can_wait=can_wait,
        action_page=action_page,
        created_at=created_at,
        details=sanitize_details(details or {}),
    )


def _confidence_from_status(status: str, *, has_direct_evidence: bool = True) -> str:
    if not has_direct_evidence:
        return "low"
    if status in {"critical", "healthy", "needs_attention"}:
        return "high"
    return "medium"


def _sort_decisions(decisions: list[Decision]) -> tuple[Decision, ...]:
    return tuple(sorted(decisions, key=lambda item: (-item.priority_rank, item.can_wait, item.title)))


def generate_decisions(session: Session, *, actor: User | None = None) -> tuple[Decision, ...]:
    """Convert current evidence into ranked owner-facing decisions.

    This service intentionally reads existing truth services instead of storing a parallel
    health model. Every returned decision must include evidence and source records.
    """

    current_time = _now()
    decisions: list[Decision] = []

    truth = system_truth(session)
    recovery = recovery_risk_assessment(session)
    bot = bot_instance_diagnostics(session)
    buttons = button_health_summary(session)
    alert_health = alert_health_summary(session)
    platforms = platform_connections_overview(session)

    if recovery.status != "healthy":
        evidence = "; ".join(recovery.evidence[:3]) or recovery.next_best_move
        decisions.append(
            _decision(
                title="Recovery is not fully protected yet",
                category="recovery",
                severity=recovery.status,
                impact="Reduces data-loss risk and proves Fortuna can be restored.",
                risk=f"Recovery risk is {recovery.risk_score}/100 ({recovery.risk_level}).",
                recommendation=recovery.next_best_move,
                confidence="high",
                evidence_summary=evidence,
                source_records=("RecoveryAssessment", "BackupRun", "RestoreTestRun", "BackupStorageTarget"),
                next_best_move=recovery.next_best_move,
                can_wait=False,
                action_page="recovery_center",
                created_at=current_time,
                business_impact=95,
                urgency=85 if recovery.status == "critical" else 60,
                data_loss_risk=100 if recovery.status == "critical" else 70,
                operational_blocking=20,
                details={
                    "status": recovery.status,
                    "risk_score": recovery.risk_score,
                    "risk_level": recovery.risk_level,
                    "alerts": list(recovery.alerts),
                },
            )
        )

    if bot.get("risk") == "critical" and bot.get("polling_conflict_active"):
        reason = str(bot.get("latest_conflict_reason") or "Another process is using the same Telegram bot token.")
        decisions.append(
            _decision(
                title="Telegram polling conflict is active",
                category="telegram_bot",
                severity="critical",
                impact="Keeps Fortuna responsive and prevents duplicate or missing Telegram replies.",
                risk=reason,
                recommendation="Stop the duplicate poller or confirm the intended worker.",
                confidence="high",
                evidence_summary=reason,
                source_records=("BotInstanceDiagnostics", "TelegramPollingConflict"),
                next_best_move="Stop the duplicate poller or confirm the intended worker.",
                can_wait=False,
                action_page="bot_status",
                created_at=current_time,
                business_impact=100,
                urgency=100,
                operational_blocking=100,
                details={
                    "latest_conflict_at": bot.get("latest_conflict_at"),
                    "latest_conflict_source": bot.get("latest_conflict_source"),
                    "polling_lock_owner": bot.get("polling_lock_owner"),
                },
            )
        )

    if not truth.production_ready:
        for code, issue in zip(truth.current_issue_codes, truth.current_issues, strict=False):
            category = "telegram_bot" if code == "bot_polling" else "system_health"
            if category == "telegram_bot" and any(decision.category == "telegram_bot" for decision in decisions):
                continue
            severity = "critical" if code in {"storage", "redis", "bot_polling"} else "needs_attention"
            next_move = (
                "Stop the duplicate poller or confirm the intended worker."
                if code == "bot_polling"
                else "Open Production Observability."
            )
            decisions.append(
                _decision(
                    title="Telegram polling needs attention" if code == "bot_polling" else "Production health needs attention",
                    category=category,
                    severity=severity,
                    impact="Keeps Fortuna responsive and trustworthy in production.",
                    risk=issue,
                    recommendation=next_move,
                    confidence="high",
                    evidence_summary=issue,
                    source_records=("SystemTruth", f"issue:{code}"),
                    next_best_move=next_move,
                    can_wait=False,
                    action_page="bot_status" if code == "bot_polling" else "production_observability",
                    created_at=current_time,
                    business_impact=95 if code == "bot_polling" else 90,
                    urgency=95 if code == "bot_polling" else 80,
                    operational_blocking=100 if code == "bot_polling" else 70,
                    details={"code": code, "bot_risk": bot.get("risk")},
                )
            )

    if buttons.overall_status != "healthy":
        decisions.append(
            _decision(
                title="Navigation needs review",
                category="navigation",
                severity=buttons.overall_status,
                impact="Reduces confusion and prevents users from getting stuck in old or broken menus.",
                risk=f"{buttons.open_issue_count + buttons.telegram_ui_issue_count} button or Telegram UI issue(s) are open.",
                recommendation=buttons.telegram_ui_next_action if buttons.telegram_ui_status != "healthy" else "Open Button Health.",
                confidence=_confidence_from_status(buttons.overall_status),
                evidence_summary=buttons.telegram_ui_evidence if buttons.telegram_ui_status != "healthy" else "Button Health has open findings.",
                source_records=("ButtonIssue", "ChatCleanupMetrics"),
                next_best_move="Open Button Health.",
                can_wait=buttons.overall_status == "needs_review",
                action_page="button_health",
                created_at=current_time,
                business_impact=65,
                urgency=45,
                operational_blocking=40,
                details={
                    "technical": buttons.technical_issue_count,
                    "navigation": buttons.navigation_issue_count,
                    "ux": buttons.ux_issue_count,
                    "telegram_ui": buttons.telegram_ui_issue_count,
                },
            )
        )

    if alert_health.status != "healthy":
        decisions.append(
            _decision(
                title="Notification health needs review",
                category="notification",
                severity=alert_health.status,
                impact="Makes sure important alerts reach the right place without noise.",
                risk=alert_health.evidence,
                recommendation=alert_health.next_action,
                confidence=_confidence_from_status(alert_health.status),
                evidence_summary=alert_health.evidence,
                source_records=("NotificationDeliveryAttempt", "NotificationTarget"),
                next_best_move=alert_health.next_action,
                can_wait=alert_health.status == "needs_review",
                action_page="platforms:alert_health",
                created_at=current_time,
                business_impact=70,
                urgency=60 if alert_health.status in {"needs_attention", "critical"} else 35,
                operational_blocking=40,
                details={
                    "failed_attempts": alert_health.failed_attempts,
                    "stale_route_count": alert_health.stale_route_count,
                    "success_rate": alert_health.success_rate,
                },
            )
        )

    waiting_platforms = int(platforms.get("waiting") or 0)
    platform_attention = int(platforms.get("needs_attention") or 0)
    if platform_attention:
        decisions.append(
            _decision(
                title="Platform connection issue needs review",
                category="platform_connection",
                severity="needs_attention",
                impact="Keeps connected platforms reliable once they are active.",
                risk=f"{platform_attention} platform connection item(s) need attention.",
                recommendation=str(platforms.get("next_action") or "Open Platform Connections."),
                confidence="medium",
                evidence_summary=str(platforms.get("next_action") or "Platform overview reported attention needed."),
                source_records=("PlatformConnection",),
                next_best_move="Open Platform Connections.",
                can_wait=False,
                action_page="platforms",
                created_at=current_time,
                business_impact=70,
                urgency=55,
                operational_blocking=30,
            )
        )
    elif waiting_platforms:
        decisions.append(
            _decision(
                title="Platform logins can wait",
                category="platform_connection",
                severity="needs_review",
                impact="Final platform credentials can be connected when activation is ready.",
                risk="Not connected yet is expected during build and setup.",
                recommendation="Keep platforms prepared, then connect credentials during final activation.",
                confidence="high",
                evidence_summary=f"{waiting_platforms} platform connection(s) are waiting for approved credentials or setup.",
                source_records=("PlatformConnection",),
                next_best_move="No urgent platform action.",
                can_wait=True,
                action_page="platforms",
                created_at=current_time,
                business_impact=35,
                urgency=10,
                owner_action_required=False,
            )
        )

    open_recommendations = list(
        session.scalars(
            select(Recommendation)
            .where(Recommendation.status == "open")
            .order_by(desc(Recommendation.severity), desc(Recommendation.updated_at), desc(Recommendation.id))
            .limit(5)
        ).all()
    )
    for recommendation in open_recommendations[:2]:
        severity = "critical" if recommendation.severity == "critical" else "needs_review"
        if any(dec.title == recommendation.title for dec in decisions):
            continue
        decisions.append(
            _decision(
                title=recommendation.title,
                category="setup" if recommendation.recommendation_type.startswith("activation_") else "general",
                severity=severity,
                impact="Clears an open Fortuna recommendation.",
                risk=recommendation.description,
                recommendation="Open Recommendations.",
                confidence="medium",
                evidence_summary=recommendation.description,
                source_records=(f"Recommendation:{recommendation.id}",),
                next_best_move="Open Recommendations.",
                can_wait=recommendation.severity != "critical",
                action_page=f"recommendation:{recommendation.id}",
                created_at=current_time,
                business_impact=55,
                urgency=30 if recommendation.severity != "critical" else 85,
            )
        )

    open_opportunities = int(
        session.scalar(
            select(func.count(Opportunity.id)).where(Opportunity.status.in_(("discovered", "reviewing", "approved", "assigned")))
        )
        or 0
    )
    if open_opportunities:
        decisions.append(
            _decision(
                title="Review the best opportunity",
                category="opportunity",
                severity="needs_review",
                impact="Keeps growth work moving without automating platform actions.",
                risk=f"{open_opportunities} opportunity item(s) are waiting for human review or assignment.",
                recommendation="Open Best Opportunity.",
                confidence="medium",
                evidence_summary=f"{open_opportunities} open opportunity item(s) exist.",
                source_records=("Opportunity",),
                next_best_move="Review the best opportunity manually.",
                can_wait=False,
                action_page="opportunities:best",
                created_at=current_time,
                business_impact=60,
                urgency=45,
            )
        )

    return _sort_decisions([decision for decision in decisions if decision is not None])


def top_decision(session: Session, *, actor: User | None = None) -> Decision | None:
    active = [decision for decision in generate_decisions(session, actor=actor) if not decision.can_wait]
    return active[0] if active else None


def generate_coo_briefing(session: Session, *, actor: User | None = None) -> CooBriefing:
    try:
        decisions = generate_decisions(session, actor=actor)
    except Exception as exc:
        latest = session.scalar(
            select(EventLog)
            .where(EventLog.event_type == "decision_engine.briefing.generated")
            .order_by(desc(EventLog.created_at), desc(EventLog.id))
            .limit(1)
        )
        evidence = "Briefing refresh failed before Fortuna could collect fresh evidence."
        if latest is not None and latest.created_at:
            evidence = f"Briefing refresh failed; last known briefing was recorded at {latest.created_at.isoformat()}."
        fallback = Decision(
            title="COO Briefing needs a fresh check",
            category="system_health",
            severity="needs_review",
            priority_rank=45,
            impact="Keeps the daily briefing honest when a refresh fails.",
            risk="Fresh status collection failed, so this briefing may be stale.",
            recommendation="Open Production Observability.",
            confidence="low",
            evidence_summary=evidence,
            source_records=("EventLog", "DecisionEngine"),
            next_best_move="Open Production Observability.",
            can_wait=False,
            created_at=_now(),
            action_page="production_observability",
            details={"error": str(exc)[:160]},
        )
        return CooBriefing(
            generated_at=_now(),
            overall_status="needs_review",
            overall_label="Needs Review",
            what_changed=("Fortuna could not refresh every briefing input.",),
            top_priority=fallback,
            risks=(fallback,),
            opportunities=(),
            can_wait=(),
            next_best_move=fallback.next_best_move,
            decisions=(fallback,),
            evidence_summary=(evidence,),
        )
    active = tuple(decision for decision in decisions if not decision.can_wait)
    can_wait = tuple(decision for decision in decisions if decision.can_wait)
    top = active[0] if active else None
    status = top.severity if top else "healthy"
    if status not in SHARED_STATUS_ORDER:
        status = "needs_review"
    risks = tuple(decision for decision in active if decision.category in {"recovery", "system_health", "telegram_bot", "navigation", "notification"})[:5]
    opportunities = tuple(decision for decision in active if decision.category in {"opportunity", "social_intelligence", "team"})[:3]
    what_changed = (
        "Fortuna checked systems, recovery, notifications, platforms, and recent activity.",
        "Low-value setup noise was moved into Details.",
    )
    briefing = CooBriefing(
        generated_at=_now(),
        overall_status=status,
        overall_label={
            "healthy": "Healthy",
            "needs_review": "Needs Review",
            "needs_attention": "Needs Attention",
            "critical": "Critical",
        }[status],
        what_changed=what_changed,
        top_priority=top,
        risks=risks,
        opportunities=opportunities,
        can_wait=can_wait[:5],
        next_best_move=top.next_best_move if top else "Nothing urgent. Keep operating from Today.",
        decisions=decisions,
        evidence_summary=tuple(decision.evidence_summary for decision in decisions[:5]),
    )
    if actor is not None:
        audit_action(
            session,
            actor=actor,
            action="decision_engine.briefing.generated",
            resource_type="coo_briefing",
            details={"decisions": len(decisions), "top_priority": top.title if top else "None"},
        )
        emit_event(
            session,
            actor=actor,
            event_name="decision_engine.briefing.generated",
            resource_type="coo_briefing",
            payload={"decisions": len(decisions), "top_priority": top.title if top else "None"},
        )
    return briefing


def upsert_decision_recommendations(session: Session, *, actor: User | None = None, limit: int = 3) -> list[Recommendation]:
    created: list[Recommendation] = []
    for decision in generate_decisions(session, actor=actor)[:limit]:
        if decision.can_wait:
            continue
        severity = "critical" if decision.severity == "critical" else "warning"
        created.append(
            upsert_recommendation(
                session,
                actor=actor,
                recommendation_type=f"decision_{decision.category}",
                title=decision.title,
                description=(
                    f"Why: {decision.risk} Impact: {decision.impact} "
                    f"Confidence: {decision.confidence.title()}. Evidence: {decision.evidence_summary} "
                    f"Next: {decision.next_best_move}"
                ),
                severity=severity,
                entity_type="decision",
                entity_id=decision.category,
                metadata={
                    "impact": decision.impact,
                    "confidence": decision.confidence,
                    "evidence": decision.evidence_summary,
                    "priority_rank": decision.priority_rank,
                    "next_best_move": decision.next_best_move,
                },
            )
        )
    return created


def record_decision_interaction(
    session: Session,
    *,
    decision: Decision,
    action: str,
    actor: User | None = None,
) -> EventLog:
    normalized = action if action in {"shown", "opened", "ignored", "acted_on", "resolved"} else "shown"
    event = emit_event(
        session,
        actor=actor,
        event_name=f"decision.{normalized}",
        resource_type="decision",
        resource_id=decision.category,
        payload={
            "title": decision.title,
            "category": decision.category,
            "severity": decision.severity,
            "priority_rank": decision.priority_rank,
            "confidence": decision.confidence,
            "evidence": decision.evidence_summary,
        },
    )
    outcome = {
        "acted_on": "success",
        "resolved": "success",
        "ignored": "ignored",
        "opened": "partial",
        "shown": "unknown",
    }[normalized]
    create_learning_event(
        session,
        actor=actor,
        event_type=f"decision.{normalized}",
        source_type="system",
        source_id=decision.category,
        entity_type="decision",
        entity_id=decision.category,
        outcome=outcome,
        severity="warning" if decision.severity in {"needs_attention", "critical"} else "info",
        summary=f"Decision {normalized.replace('_', ' ')}: {decision.title}.",
        details={
            "priority_rank": decision.priority_rank,
            "confidence": decision.confidence,
            "evidence": decision.evidence_summary,
        },
        confidence_score={"high": 90, "medium": 70, "low": 45}.get(decision.confidence, 70),
        update_memory=True,
    )
    return event
