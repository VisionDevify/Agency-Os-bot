from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.automation import AutomationRun, AutomationRule
from app.models.incident import Incident
from app.models.learning import (
    CONFIDENCE_SUBJECT_TYPES,
    LEARNING_OUTCOMES,
    LEARNING_SEVERITIES,
    LEARNING_SOURCE_TYPES,
    OUTCOME_MEMORY_TYPES,
    PLAYBOOK_CATEGORIES,
    PLAYBOOK_RISK_LEVELS,
    PLAYBOOK_RUN_STATUSES,
    PLAYBOOK_STATUSES,
    ConfidenceRecord,
    LearningEvent,
    OutcomeMemory,
    Playbook,
    PlaybookRun,
)
from app.models.opportunity import Opportunity, OpportunityResult
from app.models.proxy import Proxy
from app.models.recommendation import Recommendation
from app.models.reporting import NotificationDeliveryAttempt
from app.models.task import Task
from app.models.user import User
from app.services.audit import SENSITIVE_KEYS, sanitize_details
from app.services.auth import audit_action, user_has_permission
from app.services.events import emit_event
from app.services.recommendations import upsert_recommendation


def _now() -> datetime:
    return datetime.now(UTC)


def _clamp_score(value: int | None, *, default: int = 70) -> int:
    if value is None:
        return default
    return max(0, min(100, int(value)))


def safe_learning_metadata(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[redacted]" if key.lower() in SENSITIVE_KEYS else safe_learning_metadata(inner)
            for key, inner in value.items()
        }
    if isinstance(value, list):
        return [safe_learning_metadata(item) for item in value]
    if isinstance(value, tuple):
        return [safe_learning_metadata(item) for item in value]
    return value


def _safe_dict(details: dict | None) -> dict:
    return sanitize_details(safe_learning_metadata(details or {}))


def _require_learning_access(session: Session, actor: User | None) -> None:
    if user_has_permission(actor, "view_dashboard") or user_has_permission(actor, "manage_reports"):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="learning",
        status="denied",
        details={"permission": "view_dashboard_or_manage_reports"},
    )
    raise PermissionError("Missing permission: view_dashboard or manage_reports")


def _require_learning_manage(session: Session, actor: User | None) -> None:
    if user_has_permission(actor, "manage_reports") or user_has_permission(actor, "manage_automations"):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="learning",
        status="denied",
        details={"permission": "manage_reports_or_manage_automations"},
    )
    raise PermissionError("Missing permission: manage_reports or manage_automations")


def _memory_type_for_event(event: LearningEvent) -> str:
    if event.source_type == "proxy":
        return "proxy_failure"
    if event.source_type == "account":
        return "account_issue"
    if event.source_type == "incident":
        return "incident_pattern"
    if event.source_type == "automation":
        return "automation_result"
    if event.source_type == "recommendation":
        return "recommendation_result"
    if event.source_type == "opportunity":
        return "opportunity_result"
    if event.source_type == "notification":
        return "notification_failure"
    if event.source_type == "task":
        return "task_overdue"
    return "system_health"


def _memory_key_for_event(event: LearningEvent) -> str:
    memory_type = _memory_type_for_event(event)
    if event.entity_type and event.entity_id:
        return f"{memory_type}:{event.entity_type}:{event.entity_id}"
    if event.source_id:
        return f"{memory_type}:{event.source_type}:{event.source_id}"
    return f"{memory_type}:{event.event_type}"


def _summary_for_memory(memory: OutcomeMemory) -> str:
    if memory.memory_type == "proxy_failure":
        return f"Proxy learning has seen {memory.occurrences} outcomes with {memory.success_count} successes."
    if memory.memory_type == "automation_result":
        return f"Automation learning success rate is {memory.success_rate}% across {memory.occurrences} runs."
    if memory.memory_type == "opportunity_result":
        return f"Opportunity memory has {memory.success_count} wins and {memory.failure_count} weak outcomes."
    if memory.memory_type == "task_overdue":
        return f"Task memory has seen {memory.occurrences} task outcomes and {memory.failure_count} overdue/failure signals."
    if memory.memory_type == "notification_failure":
        return f"Notification memory has {memory.failure_count} failures across {memory.occurrences} attempts."
    if memory.memory_type == "recommendation_result":
        return f"Recommendation memory success rate is {memory.success_rate}% across {memory.occurrences} feedback/outcomes."
    return f"{memory.memory_type.replace('_', ' ').title()} has {memory.occurrences} recorded outcomes."


def update_outcome_memory(session: Session, event: LearningEvent) -> OutcomeMemory:
    memory_key = _memory_key_for_event(event)
    memory_type = _memory_type_for_event(event)
    memory = session.scalar(select(OutcomeMemory).where(OutcomeMemory.memory_key == memory_key))
    if memory is None:
        memory = OutcomeMemory(
            memory_key=memory_key,
            memory_type=memory_type,
            entity_type=event.entity_type or event.source_type,
            entity_id=event.entity_id or event.source_id,
            last_seen_at=event.created_at or _now(),
            summary="Learning memory created.",
            metadata_json={},
        )
        session.add(memory)
        session.flush()

    memory.occurrences += 1
    if event.outcome == "success":
        memory.success_count += 1
    elif event.outcome == "failure":
        memory.failure_count += 1
    elif event.outcome == "partial":
        memory.partial_count += 1
    elif event.outcome == "ignored":
        memory.ignored_count += 1
    memory.success_rate = round((memory.success_count / memory.occurrences) * 100) if memory.occurrences else 0
    memory.last_outcome = event.outcome
    memory.last_seen_at = event.created_at or _now()
    memory.metadata_json = _safe_dict(
        {
            **(memory.metadata_json or {}),
            "last_event_type": event.event_type,
            "last_severity": event.severity,
            "last_summary": event.summary,
        }
    )
    memory.summary = _summary_for_memory(memory)
    memory.updated_at = _now()
    session.flush()
    return memory


def create_learning_event(
    session: Session,
    *,
    event_type: str,
    source_type: str,
    outcome: str,
    summary: str,
    actor: User | None = None,
    source_id: int | str | None = None,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    severity: str = "info",
    details: dict | None = None,
    confidence_score: int | None = None,
    update_memory: bool = True,
) -> LearningEvent:
    if source_type not in LEARNING_SOURCE_TYPES:
        raise ValueError(f"Invalid learning source type: {source_type}")
    if outcome not in LEARNING_OUTCOMES:
        raise ValueError(f"Invalid learning outcome: {outcome}")
    if severity not in LEARNING_SEVERITIES:
        raise ValueError(f"Invalid learning severity: {severity}")
    event = LearningEvent(
        event_type=event_type,
        source_type=source_type,
        source_id=str(source_id) if source_id is not None else None,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        outcome=outcome,
        severity=severity,
        summary=summary,
        details_json=_safe_dict(details),
        confidence_score=_clamp_score(confidence_score, default=70) if confidence_score is not None else None,
        created_by_user_id=actor.id if actor else None,
        created_at=_now(),
    )
    session.add(event)
    session.flush()
    if update_memory:
        update_outcome_memory(session, event)
    emit_event(
        session,
        actor=actor,
        event_name="learning.event.created",
        resource_type="learning_event",
        resource_id=str(event.id),
        payload={"event_type": event_type, "source_type": source_type, "outcome": outcome, "severity": severity},
    )
    return event


def create_confidence_record(
    session: Session,
    *,
    subject_type: str,
    subject_id: int | str,
    previous_score: int | None,
    new_score: int,
    reason: str,
    evidence: dict | None = None,
) -> ConfidenceRecord:
    if subject_type not in CONFIDENCE_SUBJECT_TYPES:
        raise ValueError(f"Invalid confidence subject type: {subject_type}")
    record = ConfidenceRecord(
        subject_type=subject_type,
        subject_id=str(subject_id),
        previous_score=previous_score,
        new_score=_clamp_score(new_score),
        reason=reason,
        evidence_json=_safe_dict(evidence),
        created_at=_now(),
    )
    session.add(record)
    session.flush()
    return record


def adjust_playbook_confidence(
    session: Session,
    playbook: Playbook,
    *,
    delta: int,
    reason: str,
    evidence: dict | None = None,
) -> ConfidenceRecord:
    previous = playbook.confidence_score
    playbook.confidence_score = _clamp_score(previous + delta)
    playbook.updated_at = _now()
    record = create_confidence_record(
        session,
        subject_type="playbook",
        subject_id=playbook.id,
        previous_score=previous,
        new_score=playbook.confidence_score,
        reason=reason,
        evidence=evidence,
    )
    session.flush()
    return record


@dataclass(frozen=True)
class PlaybookTemplate:
    name: str
    category: str
    trigger_summary: str
    diagnosis: tuple[str, ...]
    resolution: tuple[str, ...]
    verification: tuple[str, ...]
    rollback: tuple[str, ...] | None
    risk_level: str
    confidence_score: int


PLAYBOOK_TEMPLATES: tuple[PlaybookTemplate, ...] = (
    PlaybookTemplate(
        name="Proxy Recovery Playbook",
        category="proxy",
        trigger_summary="Proxy health fails or target location does not match.",
        diagnosis=("test proxy", "check session suffix", "verify target location", "inspect recent failures"),
        resolution=("rotate session suffix", "retest", "verify location", "rollback if failed", "create incident if unresolved"),
        verification=("health score improves", "detected location matches target", "account assignment remains intact"),
        rollback=("restore previous session suffix", "retest proxy", "reopen incident if rollback fails"),
        risk_level="high",
        confidence_score=72,
    ),
    PlaybookTemplate(
        name="Account Attention Playbook",
        category="account",
        trigger_summary="Account needs login, 2FA, expired auth, locked state, or critical health.",
        diagnosis=("inspect auth status", "inspect assigned proxy", "inspect recent account events", "inspect model health"),
        resolution=("create task for manager/admin", "start auth session if authorized", "mark status updated"),
        verification=("auth status updated", "account health improves", "audit history remains safe"),
        rollback=None,
        risk_level="high",
        confidence_score=68,
    ),
    PlaybookTemplate(
        name="Critical Incident Playbook",
        category="incident",
        trigger_summary="Critical incident is open.",
        diagnosis=("inspect source entity", "inspect timeline", "inspect assigned user", "inspect escalation level"),
        resolution=("assign owner", "escalate", "notify incidents target", "request resolution notes"),
        verification=("incident assigned", "timeline updated", "critical path acknowledged"),
        rollback=None,
        risk_level="medium",
        confidence_score=76,
    ),
    PlaybookTemplate(
        name="Overdue Task Recovery Playbook",
        category="task",
        trigger_summary="Task is overdue.",
        diagnosis=("inspect assignee availability", "inspect priority", "inspect related model/account", "inspect blockers"),
        resolution=("notify assignee if on shift", "escalate to manager if off shift", "create recommendation", "reassign if overloaded"),
        verification=("task has owner", "due status reviewed", "next action is visible"),
        rollback=("restore prior assignee if reassignment was incorrect",),
        risk_level="medium",
        confidence_score=74,
    ),
    PlaybookTemplate(
        name="Notification Failure Playbook",
        category="notification",
        trigger_summary="Repeated notification delivery failures.",
        diagnosis=("inspect target", "inspect recent attempts", "inspect purpose", "inspect Telegram target status"),
        resolution=("mark target warning", "create recommendation", "route to owner fallback"),
        verification=("test target succeeds", "delivery attempts show recovery", "chat IDs remain masked"),
        rollback=None,
        risk_level="low",
        confidence_score=78,
    ),
    PlaybookTemplate(
        name="Automation Failure Playbook",
        category="automation",
        trigger_summary="Automation run failed.",
        diagnosis=("inspect run steps", "inspect failed action", "inspect rollback availability", "inspect affected entities"),
        resolution=("pause rule if repeated failures", "create incident/recommendation", "suggest simulation before reactivation"),
        verification=("rule status reviewed", "failure step identified", "safe rerun plan exists"),
        rollback=("run supported rollback steps only", "record rollback limitation when unsupported"),
        risk_level="high",
        confidence_score=70,
    ),
    PlaybookTemplate(
        name="Opportunity Learning Playbook",
        category="opportunity",
        trigger_summary="Opportunity completed, rejected, skipped, or failed.",
        diagnosis=("inspect source", "inspect niche", "inspect angle", "inspect clicks/conversions/result"),
        resolution=("update opportunity memory", "update score rules", "recommend better angle/source if enough data"),
        verification=("outcome memory updated", "score reflects historical result", "no automatic posting occurred"),
        rollback=None,
        risk_level="low",
        confidence_score=66,
    ),
)


def seed_default_playbooks(session: Session, *, actor: User | None = None) -> list[Playbook]:
    playbooks: list[Playbook] = []
    for template in PLAYBOOK_TEMPLATES:
        playbook = session.scalar(select(Playbook).where(Playbook.name == template.name))
        if playbook is None:
            playbook = Playbook(
                name=template.name,
                category=template.category,
                trigger_summary=template.trigger_summary,
                diagnosis_steps_json=list(template.diagnosis),
                resolution_steps_json=list(template.resolution),
                verification_steps_json=list(template.verification),
                rollback_steps_json=list(template.rollback) if template.rollback else None,
                risk_level=template.risk_level,
                confidence_score=template.confidence_score,
                status="active",
                created_by_user_id=actor.id if actor else None,
            )
            session.add(playbook)
        else:
            playbook.category = template.category
            playbook.trigger_summary = template.trigger_summary
            playbook.diagnosis_steps_json = list(template.diagnosis)
            playbook.resolution_steps_json = list(template.resolution)
            playbook.verification_steps_json = list(template.verification)
            playbook.rollback_steps_json = list(template.rollback) if template.rollback else None
            playbook.risk_level = template.risk_level
            if playbook.status == "draft":
                playbook.status = "active"
        playbooks.append(playbook)
    session.flush()
    return playbooks


def _category_for_context(source_type: str | None, event_type: str | None, entity_type: str | None = None) -> str:
    text = " ".join(part for part in (source_type, event_type, entity_type) if part).lower()
    if "proxy" in text:
        return "proxy"
    if "account" in text:
        return "account"
    if "automation" in text:
        return "automation"
    if "notification" in text:
        return "notification"
    if "opportunity" in text:
        return "opportunity"
    if "task" in text or "overdue" in text:
        return "task"
    if "incident" in text or "critical" in text:
        return "incident"
    return "system"


def recommend_playbooks(
    session: Session,
    *,
    source_type: str | None = None,
    source_id: int | str | None = None,
    event_type: str | None = None,
    entity_type: str | None = None,
    severity: str | None = None,
    limit: int = 3,
) -> list[tuple[Playbook, str]]:
    seed_default_playbooks(session)
    category = _category_for_context(source_type, event_type, entity_type)
    playbooks = list(session.scalars(select(Playbook).where(Playbook.status == "active")).all())

    def score(playbook: Playbook) -> int:
        base = playbook.confidence_score
        if playbook.category == category:
            base += 35
        if severity == "critical" and playbook.risk_level in {"medium", "high", "critical"}:
            base += 10
        total = playbook.success_count + playbook.failure_count
        if total:
            base += round((playbook.success_count / total) * 15)
        return base

    ranked = sorted(playbooks, key=score, reverse=True)[:limit]
    reason = f"Matched {category} context"
    if source_id is not None:
        reason = f"{reason} for {source_type or entity_type} {source_id}"
    return [(playbook, reason) for playbook in ranked]


def create_playbook_run(
    session: Session,
    playbook: Playbook,
    *,
    actor: User | None,
    status: str = "suggested",
    source_type: str | None = None,
    source_id: int | str | None = None,
    metadata: dict | None = None,
) -> PlaybookRun:
    if status not in PLAYBOOK_RUN_STATUSES:
        raise ValueError(f"Invalid playbook run status: {status}")
    run = PlaybookRun(
        playbook_id=playbook.id,
        source_type=source_type,
        source_id=str(source_id) if source_id is not None else None,
        status=status,
        started_by_user_id=actor.id if actor else None,
        confidence_before=playbook.confidence_score,
        safe_metadata_json=_safe_dict(metadata),
    )
    session.add(run)
    playbook.last_used_at = _now()
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="playbook.suggested" if status == "suggested" else "playbook.run.created",
        resource_type="playbook_run",
        resource_id=str(run.id),
        payload={"playbook_id": playbook.id, "status": status, "source_type": source_type},
    )
    return run


def finish_playbook_run(
    session: Session,
    run: PlaybookRun,
    *,
    actor: User | None,
    status: str,
    result_summary: str,
    metadata: dict | None = None,
) -> PlaybookRun:
    if status not in PLAYBOOK_RUN_STATUSES:
        raise ValueError(f"Invalid playbook run status: {status}")
    playbook = run.playbook
    run.status = status
    run.result_summary = result_summary
    run.safe_metadata_json = _safe_dict({**(run.safe_metadata_json or {}), **(metadata or {})})
    run.finished_at = _now()
    if status == "succeeded":
        playbook.success_count += 1
        adjust_playbook_confidence(session, playbook, delta=3, reason="playbook run succeeded", evidence={"run_id": run.id})
    elif status in {"failed", "rolled_back"}:
        playbook.failure_count += 1
        adjust_playbook_confidence(session, playbook, delta=-4, reason=f"playbook run {status}", evidence={"run_id": run.id})
    run.confidence_after = playbook.confidence_score
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name=f"playbook.{status}",
        resource_type="playbook_run",
        resource_id=str(run.id),
        status="failed" if status == "failed" else "success",
        payload={"playbook_id": playbook.id, "status": status},
    )
    create_learning_event(
        session,
        actor=actor,
        event_type=f"playbook.{status}",
        source_type="system",
        source_id=run.id,
        entity_type="playbook",
        entity_id=playbook.id,
        outcome="success" if status == "succeeded" else "failure" if status == "failed" else "partial",
        severity="warning" if status in {"failed", "rolled_back"} else "info",
        summary=result_summary,
        details={"playbook_id": playbook.id, "run_id": run.id, **(metadata or {})},
    )
    return run


def capture_task_completed(session: Session, task: Task, *, actor: User | None) -> LearningEvent:
    return create_learning_event(
        session,
        actor=actor,
        event_type="task.completed",
        source_type="task",
        source_id=task.id,
        entity_type="task",
        entity_id=task.id,
        outcome="success",
        severity="info",
        summary=f"Task completed: {task.title}",
        details={"status": task.status, "assigned_to_user_id": task.assigned_to_user_id},
        confidence_score=80,
    )


def capture_task_blocked(session: Session, task: Task, *, actor: User | None) -> LearningEvent:
    return create_learning_event(
        session,
        actor=actor,
        event_type="task.blocked",
        source_type="task",
        source_id=task.id,
        entity_type="task",
        entity_id=task.id,
        outcome="partial",
        severity="warning",
        summary=f"Task blocked: {task.title}",
        details={"blocked_reason": task.blocked_reason, "assigned_to_user_id": task.assigned_to_user_id},
        confidence_score=60,
    )


def capture_task_overdue(session: Session, task: Task, *, actor: User | None) -> LearningEvent:
    return create_learning_event(
        session,
        actor=actor,
        event_type="task.overdue_detected",
        source_type="task",
        source_id=task.id,
        entity_type="user" if task.assigned_to_user_id else "task",
        entity_id=task.assigned_to_user_id or task.id,
        outcome="failure",
        severity="warning",
        summary=f"Task overdue: {task.title}",
        details={"task_id": task.id, "due_at": task.due_at.isoformat() if task.due_at else None},
        confidence_score=70,
    )


def capture_incident_resolved(session: Session, incident: Incident, *, actor: User | None) -> LearningEvent:
    return create_learning_event(
        session,
        actor=actor,
        event_type="incident.resolved",
        source_type="incident",
        source_id=incident.id,
        entity_type="incident",
        entity_id=incident.id,
        outcome="success",
        severity="info",
        summary=f"Incident resolved: {incident.title}",
        details={"severity": incident.severity, "source_type": incident.source_type},
        confidence_score=82,
    )


def capture_incident_escalated(session: Session, incident: Incident, *, actor: User | None) -> LearningEvent:
    return create_learning_event(
        session,
        actor=actor,
        event_type="incident.escalated",
        source_type="incident",
        source_id=incident.id,
        entity_type=incident.source_type or "incident",
        entity_id=incident.proxy_id or incident.account_id or incident.model_brand_id or incident.id,
        outcome="partial",
        severity="warning" if incident.severity != "critical" else "critical",
        summary=f"Incident escalated: {incident.title}",
        details={"severity": incident.severity, "escalation_level": incident.escalation_level},
        confidence_score=65,
    )


def capture_proxy_outcome(
    session: Session,
    proxy: Proxy,
    *,
    actor: User | None,
    event_type: str,
    succeeded: bool,
    summary: str | None = None,
    details: dict | None = None,
) -> LearningEvent:
    return create_learning_event(
        session,
        actor=actor,
        event_type=event_type,
        source_type="proxy",
        source_id=proxy.id,
        entity_type="proxy",
        entity_id=proxy.id,
        outcome="success" if succeeded else "failure",
        severity="info" if succeeded else "critical",
        summary=summary or f"Proxy outcome recorded: {event_type}",
        details={"proxy_id": proxy.id, "status": proxy.status, "health_score": proxy.health_score, **(details or {})},
        confidence_score=85 if succeeded else 45,
    )


def capture_automation_run(session: Session, run: AutomationRun, *, actor: User | None) -> LearningEvent:
    outcome = "success" if run.status == "succeeded" else "failure" if run.status == "failed" else "partial"
    severity = "critical" if run.status == "failed" else "info"
    event = create_learning_event(
        session,
        actor=actor,
        event_type=f"automation.run.{run.status}",
        source_type="automation",
        source_id=run.id,
        entity_type="automation_rule",
        entity_id=run.automation_rule_id,
        outcome=outcome,
        severity=severity,
        summary=f"Automation run {run.status}: {run.rule.name if run.rule else run.automation_rule_id}",
        details={
            "automation_rule_id": run.automation_rule_id,
            "steps": len(run.steps or []),
            "rollback_status": run.rollback_status,
            "error": run.error_message,
        },
        confidence_score=86 if outcome == "success" else 42,
    )
    rule = run.rule or session.get(AutomationRule, run.automation_rule_id)
    if rule is not None:
        if run.status == "failed":
            create_confidence_record(
                session,
                subject_type="automation",
                subject_id=rule.id,
                previous_score=None,
                new_score=45,
                reason="automation run failed",
                evidence={"run_id": run.id, "status": run.status},
            )
            upsert_recommendation(
                session,
                actor=actor,
                recommendation_type="automation_learning_pause_review",
                title="Review Failed Automation",
                description=f"{rule.name} failed and should be reviewed before another run.",
                severity="warning",
                entity_type="automation_rule",
                entity_id=rule.id,
                metadata={"run_id": run.id, "learning_event_id": event.id},
            )
        elif run.status == "succeeded":
            create_confidence_record(
                session,
                subject_type="automation",
                subject_id=rule.id,
                previous_score=None,
                new_score=85,
                reason="automation run succeeded",
                evidence={"run_id": run.id, "status": run.status},
            )
    return event


def capture_recommendation_status(
    session: Session,
    recommendation: Recommendation,
    *,
    actor: User | None,
    status: str,
) -> LearningEvent:
    outcome = "success" if status == "resolved" else "ignored" if status == "dismissed" else "partial"
    event = create_learning_event(
        session,
        actor=actor,
        event_type=f"recommendation.{status}",
        source_type="recommendation",
        source_id=recommendation.id,
        entity_type="recommendation",
        entity_id=recommendation.id,
        outcome=outcome,
        severity=recommendation.severity,
        summary=f"Recommendation {status}: {recommendation.title}",
        details={"recommendation_type": recommendation.recommendation_type, "status": status},
        confidence_score=80 if outcome == "success" else 50,
    )
    new_score = 82 if outcome == "success" else 58 if outcome == "partial" else 45
    create_confidence_record(
        session,
        subject_type="recommendation",
        subject_id=recommendation.id,
        previous_score=recommendation.metadata_json.get("confidence_score") if recommendation.metadata_json else None,
        new_score=new_score,
        reason=f"recommendation {status}",
        evidence={"learning_event_id": event.id, "recommendation_type": recommendation.recommendation_type},
    )
    metadata = dict(recommendation.metadata_json or {})
    metadata["confidence_score"] = new_score
    recommendation.metadata_json = _safe_dict(metadata)
    return event


def capture_opportunity_result(
    session: Session,
    result: OpportunityResult,
    *,
    actor: User | None,
) -> LearningEvent:
    opportunity = result.opportunity or session.get(Opportunity, result.opportunity_id)
    conversions = result.conversions or 0
    clicks = result.clicks or 0
    if result.status == "posted" and (conversions > 0 or clicks > 0):
        outcome = "success"
    elif result.status == "failed":
        outcome = "failure"
    elif result.status == "skipped":
        outcome = "partial"
    elif result.status == "rejected":
        outcome = "ignored"
    else:
        outcome = "unknown"
    event = create_learning_event(
        session,
        actor=actor,
        event_type=f"opportunity.{result.status}",
        source_type="opportunity",
        source_id=result.id,
        entity_type="opportunity",
        entity_id=result.opportunity_id,
        outcome=outcome,
        severity="warning" if outcome == "failure" else "info",
        summary=f"Opportunity result recorded: {opportunity.title if opportunity else result.opportunity_id}",
        details={
            "opportunity_id": result.opportunity_id,
            "platform": opportunity.platform if opportunity else None,
            "niche": opportunity.niche if opportunity else None,
            "source_id": opportunity.source_id if opportunity else None,
            "suggested_angle": opportunity.suggested_angle if opportunity else None,
            "clicks": clicks,
            "conversions": conversions,
            "posting": "manual_record_only",
        },
        confidence_score=80 if outcome == "success" else 50,
    )
    if opportunity is not None:
        score_delta = 8 if outcome == "success" else -8 if outcome == "failure" else -2
        previous = opportunity.score
        opportunity.score = _clamp_score(opportunity.score + score_delta)
        create_confidence_record(
            session,
            subject_type="opportunity",
            subject_id=opportunity.id,
            previous_score=previous,
            new_score=opportunity.score,
            reason=f"opportunity result {result.status}",
            evidence={"learning_event_id": event.id, "clicks": clicks, "conversions": conversions},
        )
    return event


def capture_notification_delivery(
    session: Session,
    attempt: NotificationDeliveryAttempt,
    *,
    actor: User | None,
) -> LearningEvent:
    outcome = "success" if attempt.status == "sent" else "failure" if attempt.status == "failed" else "partial"
    return create_learning_event(
        session,
        actor=actor,
        event_type=f"notification.delivery_{attempt.status}",
        source_type="notification",
        source_id=attempt.id,
        entity_type="notification_target",
        entity_id=attempt.notification_target_id,
        outcome=outcome,
        severity="warning" if outcome == "failure" else "info",
        summary=f"Notification delivery {attempt.status}",
        details={
            "event_type": attempt.event_type,
            "target_id": attempt.notification_target_id,
            "status": attempt.status,
            "error": attempt.error_message,
        },
        confidence_score=82 if outcome == "success" else 45,
    )


def record_feedback(
    session: Session,
    *,
    actor: User,
    subject_type: str,
    subject_id: int | str,
    feedback: str,
) -> LearningEvent:
    _require_learning_manage(session, actor)
    feedback_map = {
        "useful": ("success", 3),
        "not_useful": ("partial", -2),
        "wrong": ("failure", -5),
        "needs_review": ("partial", -1),
    }
    if feedback not in feedback_map:
        raise ValueError(f"Invalid feedback: {feedback}")
    outcome, delta = feedback_map[feedback]
    event = create_learning_event(
        session,
        actor=actor,
        event_type=f"{subject_type}.feedback.{feedback}",
        source_type="recommendation" if subject_type == "recommendation" else "system",
        source_id=subject_id,
        entity_type=subject_type,
        entity_id=subject_id,
        outcome=outcome,
        severity="warning" if feedback in {"wrong", "needs_review"} else "info",
        summary=f"{subject_type.replace('_', ' ').title()} feedback: {feedback.replace('_', ' ')}",
        details={"feedback": feedback, "subject_type": subject_type, "subject_id": str(subject_id)},
        confidence_score=70 + delta,
    )
    if subject_type == "playbook":
        playbook = session.get(Playbook, int(subject_id))
        if playbook is not None:
            adjust_playbook_confidence(
                session,
                playbook,
                delta=delta,
                reason=f"operator feedback: {feedback}",
                evidence={"learning_event_id": event.id},
            )
            if feedback == "needs_review":
                playbook.status = "needs_review"
    elif subject_type == "recommendation":
        recommendation = session.get(Recommendation, int(subject_id))
        previous = None
        if recommendation is not None:
            previous = (recommendation.metadata_json or {}).get("confidence_score")
            metadata = dict(recommendation.metadata_json or {})
            metadata["confidence_score"] = _clamp_score(int(previous or 70) + delta)
            metadata["last_feedback"] = feedback
            recommendation.metadata_json = _safe_dict(metadata)
        create_confidence_record(
            session,
            subject_type="recommendation",
            subject_id=subject_id,
            previous_score=previous,
            new_score=_clamp_score(int(previous or 70) + delta),
            reason=f"operator feedback: {feedback}",
            evidence={"learning_event_id": event.id},
        )
    audit_action(
        session,
        actor=actor,
        action=f"{subject_type}.feedback.{feedback}",
        resource_type=subject_type,
        resource_id=str(subject_id),
        details={"learning_event_id": event.id},
    )
    return event


def learning_center_metrics(session: Session) -> dict:
    seed_default_playbooks(session)
    total_events = session.scalar(select(func.count(LearningEvent.id))) or 0
    active_playbooks = session.scalar(select(func.count(Playbook.id)).where(Playbook.status == "active")) or 0
    outcome_memories = session.scalar(select(func.count(OutcomeMemory.id))) or 0
    recent_events = list(
        session.scalars(select(LearningEvent).order_by(desc(LearningEvent.created_at), desc(LearningEvent.id)).limit(5)).all()
    )
    repeated_failures = list(
        session.scalars(
            select(OutcomeMemory)
            .where(OutcomeMemory.failure_count >= 2)
            .order_by(desc(OutcomeMemory.failure_count), desc(OutcomeMemory.last_seen_at))
            .limit(5)
        ).all()
    )
    highest = list(session.scalars(select(Playbook).order_by(desc(Playbook.confidence_score), Playbook.name).limit(5)).all())
    lowest = list(session.scalars(select(Playbook).order_by(Playbook.confidence_score, Playbook.name).limit(5)).all())
    confidence_changes = list(
        session.scalars(select(ConfidenceRecord).order_by(desc(ConfidenceRecord.created_at), desc(ConfidenceRecord.id)).limit(5)).all()
    )
    return {
        "total_learning_events": total_events,
        "active_playbooks": active_playbooks,
        "outcome_memories": outcome_memories,
        "recent_events": recent_events,
        "repeated_failures": repeated_failures,
        "highest_confidence_playbooks": highest,
        "lowest_confidence_playbooks": lowest,
        "recent_confidence_changes": confidence_changes,
    }


def list_learning_events(session: Session, *, limit: int = 20) -> list[LearningEvent]:
    return list(session.scalars(select(LearningEvent).order_by(desc(LearningEvent.created_at), desc(LearningEvent.id)).limit(limit)).all())


def list_playbooks(session: Session, *, include_retired: bool = False) -> list[Playbook]:
    seed_default_playbooks(session)
    statement = select(Playbook).options(selectinload(Playbook.runs)).order_by(Playbook.category, desc(Playbook.confidence_score), Playbook.name)
    if not include_retired:
        statement = statement.where(Playbook.status != "retired")
    return list(session.scalars(statement).all())


def get_playbook(session: Session, playbook_id: int) -> Playbook | None:
    return session.scalar(select(Playbook).where(Playbook.id == playbook_id).options(selectinload(Playbook.runs)))


def list_outcome_memories(session: Session, *, memory_type: str | None = None, limit: int = 20) -> list[OutcomeMemory]:
    statement = select(OutcomeMemory).order_by(desc(OutcomeMemory.last_seen_at), desc(OutcomeMemory.occurrences), OutcomeMemory.memory_key)
    if memory_type is not None:
        if memory_type not in OUTCOME_MEMORY_TYPES:
            raise ValueError(f"Invalid outcome memory type: {memory_type}")
        statement = statement.where(OutcomeMemory.memory_type == memory_type)
    return list(session.scalars(statement.limit(limit)).all())


def list_confidence_records(
    session: Session,
    *,
    subject_type: str | None = None,
    subject_id: int | str | None = None,
    limit: int = 20,
) -> list[ConfidenceRecord]:
    statement = select(ConfidenceRecord).order_by(desc(ConfidenceRecord.created_at), desc(ConfidenceRecord.id))
    if subject_type is not None:
        statement = statement.where(ConfidenceRecord.subject_type == subject_type)
    if subject_id is not None:
        statement = statement.where(ConfidenceRecord.subject_id == str(subject_id))
    return list(session.scalars(statement.limit(limit)).all())


def automation_learning_summary(session: Session) -> dict:
    memories = list_outcome_memories(session, memory_type="automation_result", limit=10)
    failed_runs = session.scalar(select(func.count(AutomationRun.id)).where(AutomationRun.status == "failed")) or 0
    succeeded_runs = session.scalar(select(func.count(AutomationRun.id)).where(AutomationRun.status == "succeeded")) or 0
    skipped_runs = session.scalar(select(func.count(AutomationRun.id)).where(AutomationRun.status == "skipped")) or 0
    return {
        "memories": memories,
        "failed_runs": failed_runs,
        "succeeded_runs": succeeded_runs,
        "skipped_runs": skipped_runs,
        "success_rate": round((succeeded_runs / max(succeeded_runs + failed_runs + skipped_runs, 1)) * 100),
    }


def opportunity_learning_summary(session: Session) -> dict:
    memories = list_outcome_memories(session, memory_type="opportunity_result", limit=20)
    results = list(session.scalars(select(OpportunityResult).options(selectinload(OpportunityResult.opportunity))).all())
    by_niche: dict[str, dict[str, int]] = {}
    by_source: dict[str, dict[str, int]] = {}
    by_angle: dict[str, dict[str, int]] = {}
    for result in results:
        opportunity = result.opportunity
        niche = opportunity.niche if opportunity and opportunity.niche else "unknown"
        source = str(opportunity.source_id) if opportunity and opportunity.source_id else "manual"
        angle = (opportunity.suggested_angle or "unknown")[:80] if opportunity else "unknown"
        success = 1 if result.status == "posted" and ((result.conversions or 0) > 0 or (result.clicks or 0) > 0) else 0
        for bucket, key in ((by_niche, niche), (by_source, source), (by_angle, angle)):
            bucket.setdefault(key, {"success": 0, "total": 0})
            bucket[key]["success"] += success
            bucket[key]["total"] += 1
    return {
        "memories": memories,
        "best_niches": sorted(by_niche.items(), key=lambda item: (item[1]["success"], item[1]["total"]), reverse=True)[:5],
        "best_sources": sorted(by_source.items(), key=lambda item: (item[1]["success"], item[1]["total"]), reverse=True)[:5],
        "best_angles": sorted(by_angle.items(), key=lambda item: (item[1]["success"], item[1]["total"]), reverse=True)[:5],
        "weak_sources": sorted(by_source.items(), key=lambda item: (item[1]["success"], -item[1]["total"]))[:5],
    }


def executive_memory_briefing(session: Session) -> dict:
    metrics = learning_center_metrics(session)
    top_problem = metrics["repeated_failures"][0].summary if metrics["repeated_failures"] else "No repeated failures recorded yet."
    best_playbook = metrics["highest_confidence_playbooks"][0] if metrics["highest_confidence_playbooks"] else None
    lowest_playbook = metrics["lowest_confidence_playbooks"][0] if metrics["lowest_confidence_playbooks"] else None
    automation = automation_learning_summary(session)
    opportunity = opportunity_learning_summary(session)
    return {
        "top_recurring_problem": top_problem,
        "best_playbook": best_playbook,
        "lowest_confidence_playbook": lowest_playbook,
        "automation_success_rate": automation["success_rate"],
        "weakest_opportunity_source": opportunity["weak_sources"][0] if opportunity["weak_sources"] else None,
        "recent_confidence_changes": metrics["recent_confidence_changes"],
        "summary": (
            f"{best_playbook.name} has {best_playbook.confidence_score}% confidence."
            if best_playbook
            else "Learning engine is collecting its first playbook outcomes."
        ),
    }
