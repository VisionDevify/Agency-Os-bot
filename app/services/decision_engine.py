from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
import re

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.button_issue import ButtonIssue
from app.models.decision_memory import DecisionMemory
from app.models.event_log import EventLog
from app.models.opportunity import Opportunity
from app.models.recommendation import Recommendation
from app.models.recovery import BackupRun, RestoreTestRun
from app.models.user import User
from app.services.audit import sanitize_details
from app.services.auth import audit_action
from app.services.bot_instances import bot_instance_diagnostics
from app.services.button_health import button_health_summary
from app.services.db_safety import safe_db_side_effect
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
    learning_summary: tuple[str, ...] = ()


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


def decision_memory_key(decision: Decision) -> str:
    """Stable key for the current evidence-backed decision shape."""
    title = re.sub(r"[^a-z0-9]+", "-", decision.title.casefold()).strip("-")[:80] or "decision"
    action = re.sub(r"[^a-z0-9:]+", "-", decision.action_page.casefold()).strip("-")[:80] or "none"
    return f"{decision.category}:{title}:{action}"[:220]


def _recommendation_id_from_sources(decision: Decision) -> int | None:
    for source in decision.source_records:
        if source.startswith("Recommendation:"):
            raw_id = source.split(":", 1)[1]
            if raw_id.isdigit():
                return int(raw_id)
    return None


def _get_memory(session: Session, decision: Decision) -> DecisionMemory | None:
    return session.scalar(select(DecisionMemory).where(DecisionMemory.decision_id == decision_memory_key(decision)).limit(1))


def _memory_payload(decision: Decision) -> dict[str, object]:
    return {
        "title": decision.title,
        "category": decision.category,
        "severity": decision.severity,
        "priority_rank": decision.priority_rank,
        "confidence": decision.confidence,
        "can_wait": decision.can_wait,
        "next_best_move": decision.next_best_move,
        "action_page": decision.action_page,
        "details": sanitize_details(decision.details),
    }


def _sync_memory_from_decision(memory: DecisionMemory, decision: Decision) -> None:
    memory.recommendation_id = _recommendation_id_from_sources(decision)
    memory.category = decision.category
    memory.severity = decision.severity if decision.severity in {"healthy", "needs_review", "needs_attention", "critical"} else "needs_review"
    memory.priority_rank = decision.priority_rank
    memory.confidence = decision.confidence if decision.confidence in CONFIDENCE_LEVELS else "medium"
    memory.evidence_summary = decision.evidence_summary
    memory.source_records = list(decision.source_records)
    metadata = dict(memory.metadata_json or {})
    metadata.update(_memory_payload(decision))
    memory.metadata_json = sanitize_details(metadata)


def get_or_create_decision_memory(
    session: Session,
    decision: Decision,
    *,
    initial_outcome: str = "shown",
) -> DecisionMemory:
    memory = _get_memory(session, decision)
    if memory is None:
        memory = DecisionMemory(
            decision_id=decision_memory_key(decision),
            recommendation_id=_recommendation_id_from_sources(decision),
            category=decision.category,
            severity=decision.severity if decision.severity in {"healthy", "needs_review", "needs_attention", "critical"} else "needs_review",
            priority_rank=decision.priority_rank,
            confidence=decision.confidence if decision.confidence in CONFIDENCE_LEVELS else "medium",
            shown_at=_now(),
            outcome=initial_outcome if initial_outcome in {"shown", "opened", "acted_on", "ignored", "resolved", "failed", "stale", "dismissed"} else "shown",
            lifecycle_status="active",
            usefulness_score=50,
            evidence_summary=decision.evidence_summary,
            source_records=list(decision.source_records),
            metadata_json=_memory_payload(decision),
        )
        session.add(memory)
        session.flush()
    else:
        _sync_memory_from_decision(memory, decision)
    return memory


def _adjust_score(score: int, delta: int) -> int:
    return max(0, min(100, score + delta))


def _memory_status_for_action(action: str) -> tuple[str, str]:
    if action == "opened":
        return "opened", "opened"
    if action == "acted_on":
        return "acted_on", "in_progress"
    if action == "ignored":
        return "ignored", "active"
    if action == "dismissed":
        return "dismissed", "dismissed"
    if action == "resolved":
        return "resolved", "resolved"
    if action == "failed":
        return "failed", "stale"
    if action == "stale":
        return "stale", "stale"
    return "shown", "active"


def _learning_outcome_for_action(action: str) -> str:
    return {
        "acted_on": "partial",
        "resolved": "success",
        "dismissed": "ignored",
        "ignored": "ignored",
        "opened": "partial",
        "failed": "failure",
        "stale": "unknown",
        "shown": "unknown",
        "feedback_recorded": "partial",
    }.get(action, "unknown")


def record_decision_memory_event(
    session: Session,
    *,
    decision: Decision,
    action: str,
    actor: User | None = None,
    owner_feedback: str | None = None,
) -> EventLog:
    """Record evidence-backed decision memory and emit standard decision events."""
    feedback_action_map = {
        "helpful": ("feedback_recorded", 12, "Marked helpful."),
        "not_helpful": ("feedback_recorded", -12, "Marked not helpful."),
        "remind_later": ("stale", -2, "Remind later."),
        "learn_from_this": ("feedback_recorded", 6, "Learn from this."),
    }
    canonical_action = action if action in {
        "shown",
        "opened",
        "acted_on",
        "ignored",
        "dismissed",
        "resolved",
        "failed",
        "stale",
    } else "shown"
    usefulness_delta = 0
    feedback_note = owner_feedback
    event_name = canonical_action
    if action in feedback_action_map:
        event_name, usefulness_delta, default_note = feedback_action_map[action]
        feedback_note = owner_feedback or default_note
        canonical_action = "stale" if action == "remind_later" else "opened"

    memory = get_or_create_decision_memory(session, decision, initial_outcome="shown")
    now = _now()
    if memory.shown_at is None:
        memory.shown_at = now
    if action == "shown" and memory.outcome not in {"dismissed", "resolved"}:
        memory.outcome = "shown"
        memory.lifecycle_status = "active"
    elif action == "opened":
        memory.opened_at = memory.opened_at or now
        memory.outcome = "opened"
        memory.lifecycle_status = "opened"
        usefulness_delta += 2
    elif action == "acted_on":
        memory.acted_on_at = memory.acted_on_at or now
        memory.outcome = "acted_on"
        memory.lifecycle_status = "in_progress"
        usefulness_delta += 10
    elif action == "ignored":
        memory.ignored_at = memory.ignored_at or now
        memory.outcome = "ignored"
        memory.lifecycle_status = "active"
        usefulness_delta -= 3
    elif action == "dismissed":
        memory.ignored_at = memory.ignored_at or now
        memory.outcome = "dismissed"
        memory.lifecycle_status = "dismissed"
        usefulness_delta -= 18
    elif action == "resolved":
        memory.resolved_at = memory.resolved_at or now
        memory.outcome = "resolved"
        memory.lifecycle_status = "resolved"
        usefulness_delta += 20
    elif action in {"failed", "stale"}:
        memory.outcome = action
        memory.lifecycle_status = "stale"
        usefulness_delta -= 5 if action == "failed" else 2
    elif action == "remind_later":
        memory.outcome = "stale"
        memory.lifecycle_status = "waiting_for_evidence"
    elif action in {"helpful", "not_helpful", "learn_from_this"}:
        if memory.lifecycle_status == "active":
            memory.lifecycle_status = "opened"

    memory.usefulness_score = _adjust_score(memory.usefulness_score or 50, usefulness_delta)
    if feedback_note:
        memory.owner_feedback = feedback_note
    memory.metadata_json = sanitize_details({**(memory.metadata_json or {}), "last_action": action, "last_feedback": feedback_note})
    session.add(memory)
    session.flush()

    event_type = f"decision.{event_name}"
    event = emit_event(
        session,
        actor=actor,
        event_name=event_type,
        resource_type="decision",
        resource_id=memory.decision_id,
        payload={
            "decision_id": memory.decision_id,
            "category": decision.category,
            "severity": decision.severity,
            "priority_rank": decision.priority_rank,
            "confidence": decision.confidence,
            "evidence_summary": decision.evidence_summary,
            "owner_feedback": feedback_note,
        },
    )
    create_learning_event(
        session,
        actor=actor,
        event_type=event_type,
        source_type="system",
        source_id=memory.decision_id,
        entity_type="decision",
        entity_id=memory.decision_id,
        outcome=_learning_outcome_for_action(event_name),
        severity="warning" if decision.severity in {"needs_attention", "critical"} else "info",
        summary=f"Decision {event_name.replace('_', ' ')}: {decision.title}.",
        details={
            "category": decision.category,
            "priority_rank": decision.priority_rank,
            "confidence": decision.confidence,
            "evidence": decision.evidence_summary,
            "usefulness_score": memory.usefulness_score,
        },
        confidence_score={"high": 90, "medium": 70, "low": 45}.get(decision.confidence, 70),
        update_memory=True,
    )
    return event


def decision_memory_summary(session: Session) -> dict[str, object]:
    memories = list(session.scalars(select(DecisionMemory)).all())
    total = len(memories)
    if not total:
        return {
            "total": 0,
            "opened_rate": 0.0,
            "acted_on_rate": 0.0,
            "ignored_rate": 0.0,
            "resolved_rate": 0.0,
            "usefulness_score": 0,
            "meaningful_lines": (),
        }
    opened = sum(1 for item in memories if item.opened_at is not None)
    acted = sum(1 for item in memories if item.acted_on_at is not None or item.outcome == "acted_on")
    ignored = sum(1 for item in memories if item.outcome in {"ignored", "dismissed"})
    resolved = sum(1 for item in memories if item.resolved_at is not None or item.outcome == "resolved")
    avg_usefulness = int(round(sum(item.usefulness_score or 0 for item in memories) / total))
    lines: list[str] = []
    recovery_acted = any(item.category == "recovery" and item.outcome in {"acted_on", "resolved"} for item in memories)
    recovery_waiting = any(item.category == "recovery" and item.lifecycle_status == "waiting_for_evidence" for item in memories)
    platform_quieted = any(
        item.category == "platform_connection" and item.outcome in {"dismissed", "stale", "ignored"} for item in memories
    )
    if recovery_acted or recovery_waiting:
        lines.append("Recovery recommendations were acted on and improved the evidence trail.")
    if platform_quieted:
        lines.append("Platform login items are being treated as final activation work.")
    if any(item.severity == "critical" and item.lifecycle_status not in {"resolved", "dismissed"} for item in memories):
        lines.append("Critical safety recommendations stay visible until resolved.")
    return {
        "total": total,
        "opened_rate": opened / total,
        "acted_on_rate": acted / total,
        "ignored_rate": ignored / total,
        "resolved_rate": resolved / total,
        "usefulness_score": avg_usefulness,
        "meaningful_lines": tuple(lines[:3]),
    }


def _apply_memory_adjustments(session: Session, decisions: list[Decision]) -> list[Decision]:
    adjusted: list[Decision] = []
    for decision in decisions:
        memory = _get_memory(session, decision)
        if memory is None:
            adjusted.append(decision)
            continue
        priority = decision.priority_rank
        can_wait = decision.can_wait
        details = dict(decision.details)
        details["memory_outcome"] = memory.outcome
        details["memory_lifecycle"] = memory.lifecycle_status
        details["usefulness_score"] = memory.usefulness_score
        if decision.severity == "critical":
            adjusted.append(replace(decision, details=details))
            continue
        if memory.lifecycle_status == "resolved":
            continue
        if memory.lifecycle_status == "dismissed" and decision.category == "platform_connection":
            priority = max(1, priority - 18)
            can_wait = True
        elif memory.lifecycle_status == "waiting_for_evidence" and decision.category == "platform_connection":
            priority = max(1, priority - 10)
            can_wait = True
        elif memory.outcome == "resolved":
            continue
        elif memory.outcome in {"dismissed", "ignored"} and memory.usefulness_score < 35:
            priority = max(1, priority - 8)
        elif memory.outcome in {"acted_on", "resolved"} and memory.usefulness_score >= 60:
            priority = min(100, priority + 5)
        adjusted.append(replace(decision, priority_rank=priority, can_wait=can_wait, details=details))
    return adjusted


def _apply_quality_adjustments(session: Session, decisions: tuple[Decision, ...], *, actor: User | None = None) -> tuple[Decision, ...]:
    """Run optional quality scoring without risking the core priority path."""
    if not settings.decision_quality_enabled:
        return decisions
    try:
        from app.services.decision_quality import adjust_decisions_with_quality

        return adjust_decisions_with_quality(session, decisions, actor=actor)
    except Exception as exc:
        try:
            from app.services.decision_quality import log_quality_failure

            log_quality_failure(session, actor=actor, error=exc)
        except Exception:
            try:
                emit_event(
                    session,
                    actor=actor,
                    event_name="decision_quality.fallback_activated",
                    resource_type="decision_quality",
                    status="warning",
                    payload={"error": str(exc)[:160]},
                )
            except Exception:
                pass
        return decisions


def _safe_decision_memory_summary(session: Session, *, actor: User | None = None) -> dict[str, object]:
    try:
        return decision_memory_summary(session)
    except Exception as exc:
        try:
            emit_event(
                session,
                actor=actor,
                event_name="decision_memory.lookup_unavailable",
                resource_type="decision_memory",
                status="warning",
                payload={"error": str(exc)[:160]},
            )
        except Exception:
            pass
        return {
            "total": 0,
            "opened_rate": 0.0,
            "acted_on_rate": 0.0,
            "ignored_rate": 0.0,
            "resolved_rate": 0.0,
            "usefulness_score": 0,
            "meaningful_lines": ("Decision Memory is unavailable; current evidence is still being used.",),
        }


def apply_decision_resolvers(session: Session) -> list[DecisionMemory]:
    """Update memory only when current evidence proves an outcome changed."""
    updated: list[DecisionMemory] = []
    memories = list(
        session.scalars(
            select(DecisionMemory).where(DecisionMemory.lifecycle_status.notin_(("resolved", "dismissed"))).limit(100)
        ).all()
    )
    if not memories:
        return updated
    recovery = recovery_risk_assessment(session)
    bot = bot_instance_diagnostics(session)
    alert_health = alert_health_summary(session)
    button_health = button_health_summary(session)
    latest_backup = session.scalar(
        select(BackupRun)
        .where(BackupRun.status.in_(("success", "succeeded")), BackupRun.artifact_verified.is_(True))
        .order_by(desc(BackupRun.finished_at), desc(BackupRun.id))
        .limit(1)
    )
    latest_restore = session.scalar(
        select(RestoreTestRun)
        .where(RestoreTestRun.status.in_(("verified_only", "verified", "passed", "succeeded")))
        .order_by(desc(RestoreTestRun.finished_at), desc(RestoreTestRun.id))
        .limit(1)
    )
    open_button_issue_count = int(session.scalar(select(func.count(ButtonIssue.id)).where(ButtonIssue.status == "open")) or 0)
    for memory in memories:
        now = _now()
        if memory.category == "recovery":
            if recovery.status == "healthy":
                memory.outcome = "resolved"
                memory.lifecycle_status = "resolved"
                memory.resolved_at = memory.resolved_at or now
                memory.usefulness_score = _adjust_score(memory.usefulness_score, 20)
                memory.evidence_summary = "Recovery reached healthy status from verified backup and restore evidence."
                updated.append(memory)
            elif latest_backup is not None and latest_restore is not None:
                memory.outcome = "acted_on"
                memory.lifecycle_status = "waiting_for_evidence" if latest_restore.status == "verified_only" else "in_progress"
                memory.acted_on_at = memory.acted_on_at or now
                memory.usefulness_score = _adjust_score(memory.usefulness_score, 12)
                memory.evidence_summary = "Backup was verified; restore validation is not fully passed yet."
                updated.append(memory)
        elif memory.category == "telegram_bot":
            if not bot.get("polling_conflict_active") and bot.get("risk") != "critical":
                memory.outcome = "resolved"
                memory.lifecycle_status = "resolved"
                memory.resolved_at = memory.resolved_at or now
                memory.usefulness_score = _adjust_score(memory.usefulness_score, 20)
                memory.evidence_summary = "Telegram polling conflict is not active and bot diagnostics are not critical."
                updated.append(memory)
        elif memory.category == "notification":
            if alert_health.status == "healthy":
                memory.outcome = "resolved"
                memory.lifecycle_status = "resolved"
                memory.resolved_at = memory.resolved_at or now
                memory.usefulness_score = _adjust_score(memory.usefulness_score, 15)
                memory.evidence_summary = "Alert health is healthy from current notification evidence."
                updated.append(memory)
        elif memory.category in {"navigation", "friction"}:
            if button_health.overall_status == "healthy" and open_button_issue_count == 0:
                memory.outcome = "resolved"
                memory.lifecycle_status = "resolved"
                memory.resolved_at = memory.resolved_at or now
                memory.usefulness_score = _adjust_score(memory.usefulness_score, 15)
                memory.evidence_summary = "Button Health has no active navigation or UX issues."
                updated.append(memory)
        elif memory.category == "platform_connection":
            if memory.lifecycle_status != "dismissed":
                memory.lifecycle_status = "waiting_for_evidence"
                memory.metadata_json = sanitize_details({**(memory.metadata_json or {}), "can_wait": True})
                updated.append(memory)
    if updated:
        session.flush()
    return updated


def generate_decisions(session: Session, *, actor: User | None = None) -> tuple[Decision, ...]:
    """Convert current evidence into ranked owner-facing decisions.

    This service intentionally reads existing truth services instead of storing a parallel
    health model. Every returned decision must include evidence and source records.
    """

    apply_decision_resolvers(session)
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

    ranked = _sort_decisions(_apply_memory_adjustments(session, [decision for decision in decisions if decision is not None]))
    return _sort_decisions(list(_apply_quality_adjustments(session, ranked, actor=actor)))


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
            learning_summary=(),
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
    learning = _safe_decision_memory_summary(session, actor=actor)
    learning_lines = tuple(learning.get("meaningful_lines") or ())
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
        learning_summary=learning_lines,
    )
    if actor is not None:
        def record_shown_memory() -> None:
            for decision in decisions[:5]:
                record_decision_memory_event(session, decision=decision, action="shown", actor=actor)

        _, memory_result = safe_db_side_effect(session, "decision_memory.record_shown", record_shown_memory)
        if not memory_result.ok:
            safe_db_side_effect(
                session,
                "decision_memory.record_unavailable_event",
                lambda: emit_event(
                    session,
                    actor=actor,
                    event_name="decision_memory.record_unavailable",
                    resource_type="decision_memory",
                    status="warning",
                    payload={
                        "error": memory_result.safe_error_summary,
                        "table": memory_result.table,
                        "constraint": memory_result.constraint,
                        "column": memory_result.column,
                    },
                ),
            )

        safe_db_side_effect(
            session,
            "decision_engine.briefing_audit",
            lambda: audit_action(
                session,
                actor=actor,
                action="decision_engine.briefing.generated",
                resource_type="coo_briefing",
                details={"decisions": len(decisions), "top_priority": top.title if top else "None"},
            ),
        )
        safe_db_side_effect(
            session,
            "decision_engine.briefing_event",
            lambda: emit_event(
                session,
                actor=actor,
                event_name="decision_engine.briefing.generated",
                resource_type="coo_briefing",
                payload={"decisions": len(decisions), "top_priority": top.title if top else "None"},
            ),
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
    return record_decision_memory_event(session, decision=decision, action=action, actor=actor)
