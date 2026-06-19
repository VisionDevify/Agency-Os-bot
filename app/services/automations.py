from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.automation import (
    AUTOMATION_APPROVAL_STATUSES,
    AUTOMATION_CATEGORIES,
    AUTOMATION_RISK_LEVELS,
    AUTOMATION_RULE_STATUSES,
    AUTOMATION_SIMULATION_STATUSES,
    AutomationApproval,
    AutomationRule,
    AutomationRun,
    AutomationRunStep,
    AutomationSchedule,
    AutomationSimulationRun,
)
from app.models.event_log import EventLog
from app.models.incident import Incident
from app.models.proxy import Proxy
from app.models.recommendation import Recommendation
from app.models.reporting import NotificationDeliveryAttempt, NotificationTarget
from app.models.task import Task
from app.models.user import User, UserAvailability
from app.services.audit import sanitize_details
from app.services.auth import audit_action, is_owner, user_has_permission
from app.services.events import emit_event
from app.services.incidents import create_incident, critical_incidents, escalate_incident
from app.services.intelligence import (
    detect_patterns,
    generate_executive_intelligence_briefing,
    generate_intelligence_recommendations,
    run_trend_analysis,
    analyze_workload,
)
from app.services.notifications import (
    create_delivery_attempt,
    mark_delivery_sent,
)
from app.services.operations import executive_dashboard, generate_daily_digest
from app.services.permissions import RoleName
from app.services.proxies import (
    ProxyTestResult,
    create_proxy_incident,
    list_proxies,
    repair_proxy,
    rotate_session,
    simulation_mode_summary,
)
from app.services.recommendations import upsert_recommendation
from app.services.recovery import run_backup
from app.services.tasks import create_task, escalate_task, overdue_tasks


MUTATING_ACTIONS = {
    "rotate_proxy_session",
    "create_proxy_incident",
    "escalate_proxy_incident",
    "create_task",
    "assign_task",
    "escalate_task",
    "create_incident",
    "assign_incident",
    "escalate_incident",
    "generate_daily_digest",
    "generate_executive_intelligence_briefing",
    "generate_recommendations",
    "run_intelligence_scan",
    "run_pattern_detection",
    "run_trend_analysis",
    "run_workload_analysis",
    "create_intelligence_signal",
    "send_notification_to_purpose",
    "send_digest_to_hq",
    "send_critical_incident_alert",
    "create_recommendation",
    "mark_recommendation_acknowledged_placeholder",
    "write_event_log",
    "run_recovery_backup",
}


@dataclass(frozen=True)
class AutomationTemplate:
    name: str
    automation_type: str
    description: str
    category: str
    trigger_type: str
    trigger_config: dict[str, Any]
    conditions: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    risk_level: str
    requires_owner_approval: bool
    schedule_type: str = "manual"


BUILTIN_AUTOMATION_TEMPLATES: tuple[AutomationTemplate, ...] = (
    AutomationTemplate(
        name="Daily Intelligence Scan",
        automation_type="daily_intelligence_scan",
        description="Runs the deterministic intelligence engines and refreshes recommendations.",
        category="intelligence",
        trigger_type="scheduled",
        trigger_config={"schedule": "daily"},
        conditions=[{"type": "time_window_allowed", "window": "daily"}],
        actions=[
            {"type": "run_pattern_detection"},
            {"type": "run_trend_analysis"},
            {"type": "run_workload_analysis"},
            {"type": "generate_recommendations"},
            {"type": "generate_executive_intelligence_briefing"},
        ],
        risk_level="low",
        requires_owner_approval=False,
        schedule_type="daily",
    ),
    AutomationTemplate(
        name="Daily Executive Digest",
        automation_type="daily_executive_digest",
        description="Generates the daily digest and routes it to owner/HQ destinations when configured.",
        category="reports",
        trigger_type="scheduled",
        trigger_config={"schedule": "daily"},
        conditions=[{"type": "time_window_allowed", "window": "daily"}],
        actions=[
            {"type": "generate_daily_digest"},
            {"type": "send_notification_to_purpose", "purpose": "owner", "event_type": "digest.generated"},
            {"type": "send_notification_to_purpose", "purpose": "operations", "event_type": "digest.generated"},
        ],
        risk_level="medium",
        requires_owner_approval=False,
        schedule_type="daily",
    ),
    AutomationTemplate(
        name="Overdue Task Escalation",
        automation_type="overdue_task_escalation",
        description="Escalates overdue operational tasks and creates an owner-visible recommendation.",
        category="operations",
        trigger_type="condition",
        trigger_config={"event": "task.overdue_detected"},
        conditions=[
            {"type": "overdue_count_above_threshold", "threshold": 0},
        ],
        actions=[
            {"type": "escalate_overdue_tasks"},
            {
                "type": "create_recommendation",
                "recommendation_type": "automation_suggestion",
                "title": "Review Overdue Task Escalation",
                "description": "Overdue tasks were detected and should be reviewed.",
                "severity": "warning",
            },
            {"type": "send_notification_to_purpose", "purpose": "operations", "event_type": "task.overdue_detected"},
        ],
        risk_level="medium",
        requires_owner_approval=False,
        schedule_type="event_based",
    ),
    AutomationTemplate(
        name="Critical Incident Escalation",
        automation_type="critical_incident_escalation",
        description="Routes and escalates critical incidents for fast owner visibility.",
        category="operations",
        trigger_type="event",
        trigger_config={"event": "incident.created"},
        conditions=[
            {"type": "critical_incidents_open", "threshold": 0},
        ],
        actions=[
            {"type": "escalate_critical_incidents"},
            {
                "type": "create_recommendation",
                "recommendation_type": "automation_suggestion",
                "title": "Critical Incident Needs Owner Attention",
                "description": "A critical incident was found during automation evaluation.",
                "severity": "critical",
            },
            {"type": "send_notification_to_purpose", "purpose": "incidents", "event_type": "incident.created"},
            {"type": "send_notification_to_purpose", "purpose": "owner", "event_type": "incident.created"},
        ],
        risk_level="high",
        requires_owner_approval=True,
        schedule_type="event_based",
    ),
    AutomationTemplate(
        name="Proxy Repair Assistant",
        automation_type="proxy_repair_assistant",
        description="Simulates proxy repairs first, then runs approved repair actions only after owner approval.",
        category="infrastructure",
        trigger_type="event",
        trigger_config={"event": "proxy.health.changed"},
        conditions=[
            {"type": "proxy_health_below_threshold", "threshold": 70},
        ],
        actions=[
            {"type": "simulate_proxy_repair"},
            {"type": "rotate_proxy_session", "max_entities": 1},
            {"type": "test_proxy_health"},
            {"type": "create_proxy_incident"},
        ],
        risk_level="high",
        requires_owner_approval=True,
        schedule_type="event_based",
    ),
    AutomationTemplate(
        name="Notification Failure Watch",
        automation_type="notification_failure_watch",
        description="Creates a repair recommendation when notification delivery repeatedly fails.",
        category="notifications",
        trigger_type="event",
        trigger_config={"event": "notification.delivery_failed"},
        conditions=[
            {"type": "notification_failures_above_threshold", "threshold": 2},
        ],
        actions=[
            {
                "type": "create_recommendation",
                "recommendation_type": "automation_suggestion",
                "title": "Fix Notification Target",
                "description": "Repeated delivery failures were detected.",
                "severity": "warning",
            },
            {"type": "send_notification_to_purpose", "purpose": "owner", "event_type": "notification.delivery_failed"},
        ],
        risk_level="low",
        requires_owner_approval=False,
        schedule_type="event_based",
    ),
    AutomationTemplate(
        name="Nightly Recovery Backup",
        automation_type="nightly_recovery_backup",
        description="Runs an evidence-checked encrypted backup through the configured recovery storage target.",
        category="infrastructure",
        trigger_type="scheduled",
        trigger_config={"schedule": "nightly"},
        conditions=[{"type": "time_window_allowed", "window": "nightly"}],
        actions=[{"type": "run_recovery_backup", "backup_type": "nightly"}],
        risk_level="medium",
        requires_owner_approval=False,
        schedule_type="daily",
    ),
)


def _now() -> datetime:
    return datetime.now(UTC)


def _safe_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _safe_json(redacted) for key, redacted in sanitize_details(value).items()}
    if isinstance(value, list):
        return [_safe_json(item) for item in value]
    if isinstance(value, tuple):
        return [_safe_json(item) for item in value]
    if isinstance(value, str) and len(value) > 500:
        return value[:500]
    return value


def _require_manage_automations(session: Session, actor: User | None) -> None:
    if user_has_permission(actor, "manage_automations"):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="automation",
        status="denied",
        details={"permission": "manage_automations"},
    )
    raise PermissionError("Missing permission: manage_automations")


def _is_admin(actor: User | None) -> bool:
    return bool(actor and any(role.name == RoleName.ADMIN.value for role in actor.roles))


def _approval_allowed(actor: User, rule: AutomationRule) -> bool:
    if is_owner(actor):
        return True
    if rule.risk_level in {"high", "critical"} or rule.requires_owner_approval:
        return False
    return _is_admin(actor) and user_has_permission(actor, "manage_automations")


def _rule_actions(rule: AutomationRule) -> list[dict[str, Any]]:
    return list(rule.actions_json or [])


def rule_has_mutating_actions(rule: AutomationRule) -> bool:
    return any(action.get("type") in MUTATING_ACTIONS for action in _rule_actions(rule))


def rule_requires_approval(rule: AutomationRule) -> bool:
    return (
        rule.requires_owner_approval
        or rule.risk_level in {"high", "critical"}
        or rule_has_mutating_actions(rule)
        or rule.automation_type == "proxy_repair_assistant"
    )


def rollback_plan_for_rule(rule: AutomationRule) -> dict[str, Any]:
    steps: list[dict[str, str]] = []
    limitations: list[str] = []
    for action in _rule_actions(rule):
        action_type = action.get("type")
        if action_type == "rotate_proxy_session":
            steps.append({"action": action_type, "rollback": "rollback_proxy_session"})
        elif action_type in {"assign_task", "escalate_task", "escalate_overdue_tasks"}:
            steps.append({"action": action_type, "rollback": "restore_previous_task_assignment_or_level_if_recorded"})
        elif action_type in {"assign_incident", "escalate_incident", "escalate_critical_incidents"}:
            steps.append({"action": action_type, "rollback": "restore_previous_incident_assignment_or_level_if_recorded"})
        elif action_type in {"mark_recommendation_acknowledged_placeholder", "create_recommendation"}:
            steps.append({"action": action_type, "rollback": "restore_previous_recommendation_status_if_recorded"})
        elif action_type == "send_notification_to_purpose":
            limitations.append("Sent notifications cannot be unsent; delivery attempts can only be audited.")
        elif action_type in {"generate_daily_digest", "generate_executive_intelligence_briefing"}:
            limitations.append("Generated report records remain as audit history.")
        else:
            limitations.append(f"{action_type or 'unknown'} has no automatic rollback in V1.")
    return {
        "available": bool(steps),
        "steps": steps,
        "limitations": limitations or ["Rollback plan is informational for this automation."],
    }


def list_automation_rules(session: Session, *, include_retired: bool = False) -> list[AutomationRule]:
    statement = (
        select(AutomationRule)
        .options(selectinload(AutomationRule.approvals), selectinload(AutomationRule.runs))
        .order_by(AutomationRule.id)
    )
    if not include_retired:
        statement = statement.where(AutomationRule.status != "retired")
    return list(session.scalars(statement).all())


def get_automation_rule(session: Session, rule_id: int) -> AutomationRule | None:
    return session.scalar(
        select(AutomationRule)
        .where(AutomationRule.id == rule_id)
        .options(
            selectinload(AutomationRule.simulations),
            selectinload(AutomationRule.approvals),
            selectinload(AutomationRule.runs).selectinload(AutomationRun.steps),
            selectinload(AutomationRule.schedules),
        )
    )


def seed_builtin_automation_templates(session: Session, *, actor: User | None = None) -> list[AutomationRule]:
    rules: list[AutomationRule] = []
    for template in BUILTIN_AUTOMATION_TEMPLATES:
        rule = session.scalar(select(AutomationRule).where(AutomationRule.automation_type == template.automation_type))
        if rule is None:
            rule = AutomationRule(
                name=template.name,
                automation_type=template.automation_type,
                status="draft",
                created_by_user_id=actor.id if actor else None,
            )
            session.add(rule)
        rule.description = template.description
        rule.category = template.category
        rule.trigger_type = template.trigger_type
        rule.trigger_config_json = _safe_json(template.trigger_config)
        rule.conditions_json = _safe_json(template.conditions)
        rule.actions_json = _safe_json(template.actions)
        rule.risk_level = template.risk_level
        rule.requires_owner_approval = template.requires_owner_approval
        rule.rollback_plan_json = rollback_plan_for_rule(rule)
        rule.metadata_json = {
            **(rule.metadata_json or {}),
            "built_in": True,
            "template": template.automation_type,
            "lifecycle": "draft_simulate_review_approve_activate_run_verify_report_rollback",
        }
        session.flush()
        if not rule.schedules:
            schedule = AutomationSchedule(
                automation_rule_id=rule.id,
                schedule_type=template.schedule_type,
                timezone="UTC",
                is_active=False,
            )
            session.add(schedule)
        rules.append(rule)
    session.flush()
    return rules


def create_automation_rule(
    session: Session,
    *,
    actor: User,
    name: str,
    automation_type: str,
    category: str = "system",
    description: str | None = None,
    trigger_type: str = "manual",
    trigger_config: dict | None = None,
    conditions: list | None = None,
    actions: list | None = None,
    risk_level: str = "low",
    requires_owner_approval: bool = False,
) -> AutomationRule:
    _require_manage_automations(session, actor)
    if category not in AUTOMATION_CATEGORIES:
        raise ValueError(f"Invalid automation category: {category}")
    if risk_level not in AUTOMATION_RISK_LEVELS:
        raise ValueError(f"Invalid risk level: {risk_level}")
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("Automation name is required")
    rule = AutomationRule(
        name=clean_name,
        description=description,
        category=category,
        automation_type=automation_type.strip() or clean_name.lower().replace(" ", "_"),
        status="draft",
        trigger_type=trigger_type,
        trigger_config_json=_safe_json(trigger_config or {}),
        conditions_json=_safe_json(conditions or []),
        actions_json=_safe_json(actions or []),
        risk_level=risk_level,
        requires_owner_approval=requires_owner_approval,
        created_by_user_id=actor.id,
        metadata_json={"created_from": "telegram_or_service"},
    )
    rule.rollback_plan_json = rollback_plan_for_rule(rule)
    session.add(rule)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="automation.rule.created",
        resource_type="automation_rule",
        resource_id=str(rule.id),
        payload={"automation_type": rule.automation_type, "risk_level": rule.risk_level},
    )
    return rule


def create_placeholder_automation_rule(session: Session, *, actor: User) -> AutomationRule:
    next_number = session.scalar(select(func.count(AutomationRule.id))) or 0
    return create_automation_rule(
        session,
        actor=actor,
        name=f"Draft Automation {next_number + 1}",
        automation_type=f"draft_automation_{next_number + 1}",
        category="system",
        description="Placeholder draft. Add triggers, conditions, and actions before activation.",
        trigger_type="manual",
        actions=[{"type": "write_event_log", "event_name": "automation.placeholder.executed"}],
        risk_level="low",
    )


def _automation_targets_for_rule(session: Session, rule: AutomationRule) -> list[dict[str, Any]]:
    if rule.automation_type == "proxy_repair_assistant":
        proxies = [
            proxy
            for proxy in list_proxies(session)
            if proxy.status in {"warning", "critical"} or proxy.health_score < 70
        ]
        return [{"entity_type": "proxy", "entity_id": proxy.id, "status": proxy.status} for proxy in proxies[:50]]
    if rule.automation_type == "overdue_task_escalation":
        return [{"entity_type": "task", "entity_id": task.id, "status": task.status} for task in overdue_tasks(session)[:50]]
    if rule.automation_type == "critical_incident_escalation":
        return [
            {"entity_type": "incident", "entity_id": incident.id, "severity": incident.severity}
            for incident in critical_incidents(session)[:50]
        ]
    if rule.automation_type == "notification_failure_watch":
        rows = session.execute(
            select(NotificationDeliveryAttempt.notification_target_id, func.count(NotificationDeliveryAttempt.id))
            .where(NotificationDeliveryAttempt.status == "failed")
            .group_by(NotificationDeliveryAttempt.notification_target_id)
            .having(func.count(NotificationDeliveryAttempt.id) >= 3)
        ).all()
        return [
            {"entity_type": "notification_target", "entity_id": target_id, "failed_attempts": count}
            for target_id, count in rows
        ]
    if rule.automation_type in {"daily_intelligence_scan", "daily_executive_digest"}:
        return [{"entity_type": "agency", "entity_id": "daily"}]
    return [{"entity_type": "automation_rule", "entity_id": rule.id}]


def evaluate_condition(session: Session, condition: dict[str, Any], *, context: dict | None = None) -> tuple[bool, str]:
    context = context or {}
    condition_type = condition.get("type")
    if condition_type == "entity_status_equals":
        entity = context.get("entity")
        expected = condition.get("status")
        return (bool(entity and getattr(entity, "status", None) == expected), f"entity status equals {expected}")
    if condition_type == "severity_equals":
        entity = context.get("entity")
        expected = condition.get("severity")
        return (bool(entity and getattr(entity, "severity", None) == expected), f"severity equals {expected}")
    if condition_type in {"health_score_below_threshold", "proxy_health_below_threshold"}:
        threshold = int(condition.get("threshold", 70))
        count = (
            session.scalar(
                select(func.count(Proxy.id)).where(
                    Proxy.status != "disabled",
                    (Proxy.health_score < threshold) | (Proxy.status.in_(("warning", "critical"))),
                )
            )
            or 0
        )
        return (count > 0, f"{count} proxies below health threshold {threshold}")
    if condition_type == "overdue_count_above_threshold":
        threshold = int(condition.get("threshold", 0))
        count = len(overdue_tasks(session))
        return (count > threshold, f"{count} overdue tasks above threshold {threshold}")
    if condition_type == "critical_incidents_open":
        threshold = int(condition.get("threshold", 0))
        count = len(critical_incidents(session))
        return (count > threshold, f"{count} critical incidents above threshold {threshold}")
    if condition_type == "availability_status_equals":
        user_id = condition.get("user_id")
        expected = condition.get("status")
        availability = session.scalar(select(UserAvailability).where(UserAvailability.user_id == user_id))
        return (bool(availability and availability.status == expected), f"user availability equals {expected}")
    if condition_type == "notification_failures_above_threshold":
        threshold = int(condition.get("threshold", 2))
        max_failed = session.scalar(
            select(func.count(NotificationDeliveryAttempt.id))
            .where(NotificationDeliveryAttempt.status == "failed")
            .group_by(NotificationDeliveryAttempt.notification_target_id)
            .order_by(func.count(NotificationDeliveryAttempt.id).desc())
            .limit(1)
        ) or 0
        return (max_failed > threshold, f"max notification failures {max_failed} above threshold {threshold}")
    if condition_type == "time_window_allowed":
        return True, f"time window {condition.get('window', 'any')} allowed"
    if condition_type == "user_has_role":
        user = session.get(User, condition.get("user_id"))
        role_name = condition.get("role")
        return (bool(user and any(role.name == role_name for role in user.roles)), f"user has role {role_name}")
    if condition_type == "entity_exists":
        entity_type = condition.get("entity_type")
        entity_id = condition.get("entity_id")
        model = {"task": Task, "incident": Incident, "proxy": Proxy, "recommendation": Recommendation}.get(entity_type)
        return (bool(model and entity_id and session.get(model, int(entity_id)) is not None), f"{entity_type} exists")
    if condition_type == "recommendation_severity_equals":
        severity = condition.get("severity")
        count = session.scalar(select(func.count(Recommendation.id)).where(Recommendation.severity == severity, Recommendation.status == "open")) or 0
        return (count > 0, f"{count} open recommendations with severity {severity}")
    return True, "condition not configured; allowed"


def evaluate_conditions(session: Session, rule: AutomationRule) -> list[dict[str, Any]]:
    results = []
    for condition in rule.conditions_json or []:
        passed, reason = evaluate_condition(session, condition)
        results.append({"condition": _safe_json(condition), "passed": passed, "reason": reason})
    return results


def _simulation_counts(session: Session, rule: AutomationRule, affected: list[dict[str, Any]]) -> tuple[int, int, int]:
    trigger_count = max(len(affected), 1 if rule.trigger_type in {"manual", "scheduled"} else 0)
    fail_count = 0
    if rule.automation_type == "proxy_repair_assistant":
        fail_count = sum(1 for item in affected if item.get("status") == "critical")
    elif rule.risk_level in {"high", "critical"} and affected:
        fail_count = 1
    succeed_count = max(trigger_count - fail_count, 0)
    return trigger_count, succeed_count, fail_count


def simulate_automation_rule(session: Session, rule: AutomationRule, *, actor: User) -> AutomationSimulationRun:
    _require_manage_automations(session, actor)
    if rule.status == "retired":
        raise PermissionError("Retired automations cannot be simulated")
    started = _now()
    run = AutomationSimulationRun(
        automation_rule_id=rule.id,
        automation_name=rule.name,
        automation_type=rule.automation_type,
        status="running",
        simulated_by_user_id=actor.id,
        target_scope=rule.category,
        risk_level=rule.risk_level,
        expires_at=started + timedelta(hours=24),
    )
    session.add(run)
    session.flush()
    try:
        condition_results = evaluate_conditions(session, rule)
        affected = _automation_targets_for_rule(session, rule)
        trigger_count, succeed_count, fail_count = _simulation_counts(session, rule, affected)
        warnings: list[str] = []
        if rule.risk_level in {"high", "critical"}:
            warnings.append("High-risk automation requires Owner approval before activation.")
        if rule_has_mutating_actions(rule):
            warnings.append("This automation includes actions that can change Fortuna OS records.")
        if any(not item["passed"] for item in condition_results):
            warnings.append("One or more checks would currently prevent execution.")
        run.status = "succeeded"
        run.finished_at = _now()
        run.would_trigger_count = trigger_count
        run.would_succeed_count = succeed_count if all(item["passed"] for item in condition_results) else 0
        run.would_fail_count = fail_count
        run.affected_entities_json = _safe_json(affected)
        run.impact_summary_json = _safe_json(
            {
                "changes_applied": False,
                "conditions": condition_results,
                "actions": [action.get("type") for action in _rule_actions(rule)],
                "rollback_available": bool((rule.rollback_plan_json or {}).get("available")),
            }
        )
        run.warnings_json = _safe_json(warnings)
        rule.last_simulated_at = run.finished_at
        if rule.status == "draft":
            rule.status = "simulated"
        session.flush()
        emit_event(
            session,
            actor=actor,
            event_name="automation.simulated",
            resource_type="automation_simulation_run",
            resource_id=str(run.id),
            payload={
                "automation_rule_id": rule.id,
                "automation_type": rule.automation_type,
                "risk_level": rule.risk_level,
                "would_trigger_count": run.would_trigger_count,
                "would_succeed_count": run.would_succeed_count,
                "would_fail_count": run.would_fail_count,
            },
        )
        return run
    except Exception as exc:
        run.status = "failed"
        run.finished_at = _now()
        run.impact_summary_json = {"error": _safe_error(str(exc))}
        session.flush()
        raise


def latest_valid_simulation(session: Session, rule: AutomationRule) -> AutomationSimulationRun | None:
    return session.scalar(
        select(AutomationSimulationRun)
        .where(
            AutomationSimulationRun.automation_rule_id == rule.id,
            AutomationSimulationRun.status.in_(("succeeded", "simulated", "approved")),
            AutomationSimulationRun.expires_at > _now(),
        )
        .order_by(desc(AutomationSimulationRun.created_at), desc(AutomationSimulationRun.id))
        .limit(1)
    )


def request_automation_approval(
    session: Session,
    rule: AutomationRule,
    *,
    actor: User,
    reason: str | None = None,
) -> AutomationApproval:
    _require_manage_automations(session, actor)
    simulation = latest_valid_simulation(session, rule)
    if simulation is None:
        audit_action(
            session,
            actor=actor,
            action="automation.activation_blocked",
            resource_type="automation_rule",
            resource_id=str(rule.id),
            status="denied",
            details={"reason": "simulation_required"},
        )
        raise PermissionError("Simulation must exist before approval")
    approval = AutomationApproval(
        automation_rule_id=rule.id,
        requested_by_user_id=actor.id,
        status="pending",
        approval_reason=reason,
        expires_at=_now() + timedelta(hours=24),
    )
    session.add(approval)
    rule.status = "pending_approval"
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="automation.approval.requested",
        resource_type="automation_approval",
        resource_id=str(approval.id),
        payload={"automation_rule_id": rule.id, "risk_level": rule.risk_level},
    )
    return approval


def approve_automation(
    session: Session,
    approval: AutomationApproval,
    *,
    actor: User,
    reason: str | None = None,
) -> AutomationApproval:
    _require_manage_automations(session, actor)
    if approval.status != "pending":
        raise PermissionError("Only pending approvals can be decided")
    if approval.expires_at and approval.expires_at <= _now():
        approval.status = "expired"
        session.flush()
        raise PermissionError("Expired approval cannot be approved")
    rule = approval.rule
    if latest_valid_simulation(session, rule) is None:
        raise PermissionError("Expired or missing simulation cannot be approved")
    if not _approval_allowed(actor, rule):
        audit_action(
            session,
            actor=actor,
            action="automation.activation_blocked",
            resource_type="automation_rule",
            resource_id=str(rule.id),
            status="denied",
            details={"reason": "approval_requires_owner", "risk_level": rule.risk_level},
        )
        raise PermissionError("This automation requires Owner approval")
    approval.status = "approved"
    approval.approved_by_user_id = actor.id
    approval.decided_at = _now()
    approval.approval_reason = reason or approval.approval_reason
    rule.status = "approved"
    rule.approved_by_user_id = actor.id
    rule.approved_at = approval.decided_at
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="automation.approved",
        resource_type="automation_rule",
        resource_id=str(rule.id),
        payload={"approval_id": approval.id, "risk_level": rule.risk_level},
    )
    return approval


def reject_automation(
    session: Session,
    approval: AutomationApproval,
    *,
    actor: User,
    reason: str | None = None,
) -> AutomationApproval:
    _require_manage_automations(session, actor)
    if approval.status != "pending":
        raise PermissionError("Only pending approvals can be decided")
    approval.status = "rejected"
    approval.approved_by_user_id = actor.id
    approval.decided_at = _now()
    approval.rejection_reason = reason or "Rejected from Telegram."
    approval.rule.status = "simulated"
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="automation.rejected",
        resource_type="automation_rule",
        resource_id=str(approval.automation_rule_id),
        payload={"approval_id": approval.id},
    )
    return approval


def approve_from_simulation(session: Session, simulation: AutomationSimulationRun, *, actor: User) -> AutomationApproval | None:
    if simulation.expires_at <= _now():
        simulation.status = "expired"
        session.flush()
        raise PermissionError("Expired simulation cannot be approved")
    if simulation.rule is None:
        update_simulation_status(session, simulation, actor=actor, status="approved")
        return None
    approval = request_automation_approval(session, simulation.rule, actor=actor, reason="Approved from simulation preview.")
    return approve_automation(session, approval, actor=actor, reason="Approved from simulation preview.")


def activate_automation_rule(session: Session, rule: AutomationRule, *, actor: User) -> AutomationRule:
    _require_manage_automations(session, actor)
    if rule.status not in {"approved", "paused"}:
        audit_action(
            session,
            actor=actor,
            action="automation.activation_blocked",
            resource_type="automation_rule",
            resource_id=str(rule.id),
            status="denied",
            details={"reason": "approval_required", "status": rule.status},
        )
        raise PermissionError("Automation must be approved before activation")
    if latest_valid_simulation(session, rule) is None:
        raise PermissionError("Simulation must exist before activation")
    if rule_requires_approval(rule) and rule.approved_by_user_id is None:
        raise PermissionError("Approval is required before activation")
    rule.status = "active"
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="automation.activated",
        resource_type="automation_rule",
        resource_id=str(rule.id),
        payload={"risk_level": rule.risk_level},
    )
    return rule


def pause_automation_rule(session: Session, rule: AutomationRule, *, actor: User) -> AutomationRule:
    _require_manage_automations(session, actor)
    rule.status = "paused"
    session.flush()
    emit_event(session, actor=actor, event_name="automation.paused", resource_type="automation_rule", resource_id=str(rule.id))
    return rule


def resume_automation_rule(session: Session, rule: AutomationRule, *, actor: User) -> AutomationRule:
    return activate_automation_rule(session, rule, actor=actor)


def retire_automation_rule(session: Session, rule: AutomationRule, *, actor: User) -> AutomationRule:
    _require_manage_automations(session, actor)
    rule.status = "retired"
    session.flush()
    emit_event(session, actor=actor, event_name="automation.retired", resource_type="automation_rule", resource_id=str(rule.id))
    return rule


def _safe_error(error: str | None) -> str | None:
    if not error:
        return None
    lowered = error.lower()
    if any(marker in lowered for marker in ("token", "secret", "password", "credential", "key")):
        return "automation error; sensitive details redacted"
    return error[:500]


def _create_run_step(run: AutomationRun, *, step_order: int, action: dict[str, Any]) -> AutomationRunStep:
    step = AutomationRunStep(
        automation_run_id=run.id,
        step_order=step_order,
        action_type=action.get("type", "unknown"),
        status="pending",
        input_json=_safe_json(action),
    )
    return step


def _target_proxy_for_action(session: Session, action: dict[str, Any]) -> Proxy | None:
    proxy_id = action.get("proxy_id")
    if proxy_id:
        return session.get(Proxy, int(proxy_id))
    return session.scalar(
        select(Proxy)
        .where(Proxy.status != "disabled", (Proxy.status.in_(("warning", "critical"))) | (Proxy.health_score < 70))
        .order_by(Proxy.health_score, Proxy.id)
        .limit(1)
    )


def _send_to_purpose(session: Session, *, actor: User | None, purpose: str, event_type: str) -> dict[str, Any]:
    targets = list(
        session.scalars(
            select(NotificationTarget).where(NotificationTarget.is_active.is_(True), NotificationTarget.purpose == purpose)
        ).all()
    )
    attempts = []
    for target in targets:
        attempt = create_delivery_attempt(
            session,
            target,
            event_type=event_type,
            actor=actor,
            status="pending",
            metadata={"purpose": purpose, "automation": True},
        )
        mark_delivery_sent(session, attempt, actor=actor)
        attempts.append(attempt.id)
    return {"purpose": purpose, "targets": len(targets), "attempt_ids": attempts}


def execute_action(session: Session, action: dict[str, Any], *, actor: User | None) -> dict[str, Any]:
    action_type = action.get("type")
    if action_type == "run_pattern_detection":
        return detect_patterns(session, actor=actor)
    if action_type == "run_trend_analysis":
        return {"snapshots": len(run_trend_analysis(session, actor=actor))}
    if action_type == "run_workload_analysis":
        return {"snapshots": len(analyze_workload(session, actor=actor))}
    if action_type in {"generate_recommendations", "run_intelligence_scan"}:
        if action_type == "run_intelligence_scan":
            detect_patterns(session, actor=actor)
            run_trend_analysis(session, actor=actor)
            analyze_workload(session, actor=actor)
        return {"recommendations": len(generate_intelligence_recommendations(session, actor=actor))}
    if action_type == "generate_executive_intelligence_briefing":
        insight = generate_executive_intelligence_briefing(session, actor=actor)
        return {"executive_insight_id": insight.id}
    if action_type == "generate_daily_digest":
        digest = generate_daily_digest(session, actor=actor)
        return {"briefing_id": digest.get("briefing_id"), "agency_health_score": digest.get("agency_health_score")}
    if action_type in {"send_notification_to_purpose", "send_digest_to_hq", "send_critical_incident_alert"}:
        purpose = action.get("purpose") or ("owner" if action_type == "send_digest_to_hq" else "incidents")
        event_type = action.get("event_type") or "automation.notification"
        return _send_to_purpose(session, actor=actor, purpose=purpose, event_type=event_type)
    if action_type == "simulate_proxy_repair":
        summary = simulation_mode_summary(session)
        return {
            "changes_applied": False,
            "would_rotate": summary.would_rotate,
            "would_repair": summary.would_repair,
            "would_fail": summary.would_fail,
        }
    if action_type == "rotate_proxy_session":
        proxy = _target_proxy_for_action(session, action)
        if proxy is None:
            return {"skipped": True, "reason": "no proxy candidates"}
        rotation = rotate_session(session, proxy, actor=actor)
        return {"proxy_id": proxy.id, "rotation_id": rotation.id, "status": rotation.status}
    if action_type == "test_proxy_health":
        proxy = _target_proxy_for_action(session, action)
        if proxy is None:
            return {"skipped": True, "reason": "no proxy candidates"}
        return {"proxy_id": proxy.id, "status": proxy.status, "health_score": proxy.health_score}
    if action_type == "create_proxy_incident":
        proxy = _target_proxy_for_action(session, action)
        if proxy is None:
            return {"skipped": True, "reason": "no proxy candidates"}
        incident = create_proxy_incident(
            session,
            proxy,
            actor=actor,
            title="Proxy Repair Automation Needs Review",
            severity="warning",
            reason="automation_proxy_repair_review",
        )
        return {"incident_id": incident.id, "proxy_id": proxy.id}
    if action_type == "escalate_proxy_incident":
        incident = session.scalar(
            select(Incident)
            .where(Incident.source_type == "proxy", Incident.status.in_(("open", "investigating")))
            .order_by(desc(Incident.id))
            .limit(1)
        )
        if incident is None or actor is None:
            return {"skipped": True, "reason": "no proxy incident"}
        escalate_incident(session, incident, actor=actor)
        return {"incident_id": incident.id, "escalation_level": incident.escalation_level}
    if action_type == "create_task":
        if actor is None:
            raise PermissionError("Task automation requires an actor")
        task = create_task(
            session,
            actor=actor,
            title=action.get("title", "Automation-created task"),
            description=action.get("description", "Created by Fortuna OS automation."),
            priority=action.get("priority", "normal"),
        )
        return {"task_id": task.id}
    if action_type in {"escalate_task", "escalate_overdue_tasks"}:
        if actor is None:
            raise PermissionError("Task automation requires an actor")
        tasks = overdue_tasks(session)
        if action_type == "escalate_task" and action.get("task_id"):
            task = session.get(Task, int(action["task_id"]))
            tasks = [task] if task is not None else []
        for task in tasks[: int(action.get("max_entities", 10))]:
            escalate_task(session, task, actor=actor)
        return {"escalated_tasks": [task.id for task in tasks[: int(action.get("max_entities", 10))]]}
    if action_type == "create_incident":
        incident = create_incident(
            session,
            actor=actor,
            title=action.get("title", "Automation-created incident"),
            description=action.get("description", "Created by Fortuna OS automation."),
            severity=action.get("severity", "warning"),
            source_type="automation",
        )
        return {"incident_id": incident.id}
    if action_type in {"escalate_incident", "escalate_critical_incidents"}:
        if actor is None:
            raise PermissionError("Incident automation requires an actor")
        incidents = critical_incidents(session)
        if action_type == "escalate_incident" and action.get("incident_id"):
            incident = session.get(Incident, int(action["incident_id"]))
            incidents = [incident] if incident is not None else []
        for incident in incidents[: int(action.get("max_entities", 10))]:
            escalate_incident(session, incident, actor=actor)
        return {"escalated_incidents": [incident.id for incident in incidents[: int(action.get("max_entities", 10))]]}
    if action_type == "create_recommendation":
        recommendation = upsert_recommendation(
            session,
            actor=actor,
            recommendation_type=action.get("recommendation_type", "automation_suggestion"),
            title=action.get("title", "Automation Recommendation"),
            description=action.get("description", "Fortuna OS automation generated a recommendation."),
            severity=action.get("severity", "info"),
            entity_type=action.get("entity_type"),
            entity_id=action.get("entity_id"),
            metadata={"source": "automation", "suggested_action": action.get("suggested_action")},
        )
        return {"recommendation_id": recommendation.id}
    if action_type == "mark_recommendation_acknowledged_placeholder":
        return {"placeholder": True, "message": "Recommendation status rollback-safe placeholder only."}
    if action_type == "write_event_log":
        event = emit_event(
            session,
            actor=actor,
            event_name=action.get("event_name", "automation.event"),
            resource_type="automation",
            resource_id=action.get("resource_id"),
            payload={"source": "automation_action"},
        )
        return {"audit_id": event.id}
    if action_type == "run_recovery_backup":
        run = run_backup(session, actor=actor, backup_type=action.get("backup_type", "nightly"))
        return {
            "backup_run_id": run.id,
            "status": run.status,
            "artifact_verified": run.artifact_verified,
            "external_storage_used": run.external_storage_used,
        }
    if action_type == "fail_action":
        raise RuntimeError(action.get("message", "Intentional automation failure"))
    return {"skipped": True, "reason": f"unsupported action {action_type}"}


def _execution_conditions_pass(session: Session, rule: AutomationRule) -> tuple[bool, list[dict[str, Any]]]:
    results = evaluate_conditions(session, rule)
    return all(item["passed"] for item in results), results


def _approved_for_execution(session: Session, rule: AutomationRule) -> bool:
    if not rule_requires_approval(rule):
        return True
    if rule.approved_by_user_id is not None and rule.approved_at is not None:
        return True
    return (
        session.scalar(
            select(func.count(AutomationApproval.id)).where(
                AutomationApproval.automation_rule_id == rule.id,
                AutomationApproval.status == "approved",
            )
        )
        or 0
    ) > 0


def run_automation_rule(
    session: Session,
    rule: AutomationRule,
    *,
    actor: User | None,
    trigger_event_id: int | None = None,
) -> AutomationRun:
    if actor is not None:
        _require_manage_automations(session, actor)
    if rule.status != "active":
        audit_action(
            session,
            actor=actor,
            action="automation.execution_blocked",
            resource_type="automation_rule",
            resource_id=str(rule.id),
            status="denied",
            details={"reason": "rule_not_active", "status": rule.status},
        )
        raise PermissionError("Automation must be active before running")
    if latest_valid_simulation(session, rule) is None:
        raise PermissionError("Simulation must exist before execution")
    if not _approved_for_execution(session, rule):
        raise PermissionError("Approval is required before execution")
    conditions_pass, condition_results = _execution_conditions_pass(session, rule)
    run = AutomationRun(
        automation_rule_id=rule.id,
        status="running",
        started_by_user_id=actor.id if actor else None,
        started_at=_now(),
        trigger_event_id=trigger_event_id,
        rollback_available=bool((rule.rollback_plan_json or {}).get("available")),
        rollback_status="available" if (rule.rollback_plan_json or {}).get("available") else "not_needed",
    )
    session.add(run)
    session.flush()
    if not conditions_pass:
        run.status = "skipped"
        run.finished_at = _now()
        run.result_summary_json = {"conditions": condition_results, "skipped": True}
        session.flush()
        emit_event(
            session,
            actor=actor,
            event_name="automation.run.skipped",
            resource_type="automation_run",
            resource_id=str(run.id),
            payload={"automation_rule_id": rule.id},
        )
        from app.services.learning import capture_automation_run

        capture_automation_run(session, run, actor=actor)
        return run

    affected: list[dict[str, Any]] = []
    try:
        for index, action in enumerate(_rule_actions(rule), start=1):
            step = _create_run_step(run, step_order=index, action=action)
            session.add(step)
            session.flush()
            step.status = "running"
            step.started_at = _now()
            session.flush()
            output = execute_action(session, action, actor=actor)
            step.output_json = _safe_json(output)
            step.status = "succeeded"
            step.finished_at = _now()
            entity_type = output.get("entity_type") if isinstance(output, dict) else None
            entity_id = output.get("entity_id") if isinstance(output, dict) else None
            if entity_type and entity_id:
                step.entity_type = str(entity_type)
                step.entity_id = str(entity_id)
            affected.append({"step_id": step.id, "action_type": step.action_type, "output": step.output_json})
            session.flush()
        run.status = "succeeded"
        run.finished_at = _now()
        run.affected_entities_json = _safe_json(affected)
        run.result_summary_json = {"steps": len(_rule_actions(rule)), "conditions": condition_results}
        rule.last_run_at = run.finished_at
        session.flush()
        emit_event(
            session,
            actor=actor,
            event_name="automation.run.succeeded",
            resource_type="automation_run",
            resource_id=str(run.id),
            payload={"automation_rule_id": rule.id, "steps": len(_rule_actions(rule))},
        )
        from app.services.learning import capture_automation_run

        capture_automation_run(session, run, actor=actor)
        return run
    except Exception as exc:
        if run.steps:
            run.steps[-1].status = "failed"
            run.steps[-1].error_message = _safe_error(str(exc))
            run.steps[-1].finished_at = _now()
        run.status = "failed"
        run.finished_at = _now()
        run.error_message = _safe_error(str(exc))
        run.affected_entities_json = _safe_json(affected)
        run.result_summary_json = {"steps": len(run.steps), "conditions": condition_results}
        rule.last_run_at = run.finished_at
        rule.status = "failed"
        session.flush()
        emit_event(
            session,
            actor=actor,
            event_name="automation.run.failed",
            resource_type="automation_run",
            resource_id=str(run.id),
            status="failed",
            payload={"automation_rule_id": rule.id, "error": run.error_message},
        )
        from app.services.learning import capture_automation_run

        capture_automation_run(session, run, actor=actor)
        return run


def latest_automation_runs(session: Session, *, limit: int = 20) -> list[AutomationRun]:
    return list(
        session.scalars(
            select(AutomationRun)
            .options(selectinload(AutomationRun.rule), selectinload(AutomationRun.steps))
            .order_by(desc(AutomationRun.started_at), desc(AutomationRun.id))
            .limit(limit)
        ).all()
    )


def get_automation_run(session: Session, run_id: int) -> AutomationRun | None:
    return session.scalar(
        select(AutomationRun)
        .where(AutomationRun.id == run_id)
        .options(selectinload(AutomationRun.rule), selectinload(AutomationRun.steps))
    )


def get_automation_step(session: Session, step_id: int) -> AutomationRunStep | None:
    return session.get(AutomationRunStep, step_id)


def pending_approvals(session: Session, *, limit: int = 20) -> list[AutomationApproval]:
    return list(
        session.scalars(
            select(AutomationApproval)
            .where(AutomationApproval.status == "pending")
            .options(selectinload(AutomationApproval.rule))
            .order_by(desc(AutomationApproval.created_at), desc(AutomationApproval.id))
            .limit(limit)
        ).all()
    )


def latest_rule_approval(session: Session, rule: AutomationRule) -> AutomationApproval | None:
    return session.scalar(
        select(AutomationApproval)
        .where(AutomationApproval.automation_rule_id == rule.id)
        .order_by(desc(AutomationApproval.created_at), desc(AutomationApproval.id))
        .limit(1)
    )


def automation_metrics(session: Session) -> dict[str, Any]:
    rules = list_automation_rules(session, include_retired=True)
    runs = list(session.scalars(select(AutomationRun)).all())
    simulations = list(session.scalars(select(AutomationSimulationRun)).all())
    status_counts = Counter(rule.status for rule in rules)
    run_counts = Counter(run.status for run in runs)
    active_rules = status_counts.get("active", 0)
    failed_rules = status_counts.get("failed", 0)
    pending = session.scalar(select(func.count(AutomationApproval.id)).where(AutomationApproval.status == "pending")) or 0
    latest_run = session.scalar(select(AutomationRun).order_by(desc(AutomationRun.started_at), desc(AutomationRun.id)).limit(1))
    successful_runs = run_counts.get("succeeded", 0)
    total_finished = sum(run_counts[status] for status in ("succeeded", "failed", "skipped", "rolled_back"))
    success_rate = int((successful_runs / total_finished) * 100) if total_finished else 100
    durations = [
        (run.finished_at - run.started_at).total_seconds()
        for run in runs
        if run.started_at and run.finished_at
    ]
    return {
        "total_rules": len(rules),
        "active_automations": active_rules,
        "failed_automations": failed_rules,
        "pending_approvals": pending,
        "total_simulations": len(simulations),
        "total_runs": len(runs),
        "success_count": successful_runs,
        "failure_count": run_counts.get("failed", 0),
        "skipped_count": run_counts.get("skipped", 0),
        "rollback_count": run_counts.get("rolled_back", 0),
        "last_run_status": latest_run.status if latest_run else "none",
        "last_run_time": latest_run.started_at.isoformat() if latest_run else "none",
        "last_automation_run": latest_run.rule.name if latest_run and latest_run.rule else "none",
        "average_duration_seconds": round(sum(durations) / len(durations), 2) if durations else 0,
        "affected_entities_count": sum(len(run.affected_entities_json or []) for run in runs),
        "automation_success_rate": success_rate,
    }


def suggest_automation_from_recommendation(session: Session, recommendation: Recommendation, *, actor: User | None) -> Recommendation:
    mapping = {
        "replace_rotate_proxy": "Proxy Repair Assistant",
        "proxy_location_mismatch": "Proxy Repair Assistant",
        "reassign_work": "Overdue Task Escalation",
        "clean_up_stale_tasks": "Overdue Task Escalation",
        "fix_notification_target": "Notification Failure Watch",
        "investigate_recurring_incident": "Critical Incident Escalation",
    }
    template = mapping.get(recommendation.recommendation_type)
    if not template:
        return recommendation
    metadata = dict(recommendation.metadata_json or {})
    metadata["automation_suggestion"] = template
    metadata["create_draft_placeholder"] = True
    recommendation.recommendation_type = "automation_suggestion"
    recommendation.metadata_json = _safe_json(metadata)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="automation.suggested",
        resource_type="recommendation",
        resource_id=str(recommendation.id),
        payload={"template": template},
    )
    return recommendation


def list_simulation_runs(session: Session, *, limit: int = 20) -> list[AutomationSimulationRun]:
    return list(
        session.scalars(
            select(AutomationSimulationRun)
            .options(selectinload(AutomationSimulationRun.rule))
            .order_by(desc(AutomationSimulationRun.created_at), desc(AutomationSimulationRun.id))
            .limit(limit)
        ).all()
    )


def get_simulation_run(session: Session, run_id: int) -> AutomationSimulationRun | None:
    return session.scalar(
        select(AutomationSimulationRun)
        .where(AutomationSimulationRun.id == run_id)
        .options(selectinload(AutomationSimulationRun.rule))
    )


def create_simulation_run(
    session: Session,
    *,
    actor: User,
    automation_name: str,
    automation_type: str,
    target_scope: str,
    would_trigger_count: int,
    would_succeed_count: int,
    would_fail_count: int,
    impact_summary: dict,
    risk_level: str,
    automation_rule: AutomationRule | None = None,
    affected_entities: list | None = None,
    warnings: list | None = None,
) -> AutomationSimulationRun:
    _require_manage_automations(session, actor)
    if risk_level not in AUTOMATION_RISK_LEVELS:
        raise ValueError(f"Invalid risk level: {risk_level}")
    run = AutomationSimulationRun(
        automation_rule_id=automation_rule.id if automation_rule else None,
        automation_name=automation_name,
        automation_type=automation_type,
        status="simulated",
        simulated_by_user_id=actor.id,
        target_scope=target_scope,
        would_trigger_count=would_trigger_count,
        would_succeed_count=would_succeed_count,
        would_fail_count=would_fail_count,
        impact_summary_json=_safe_json(impact_summary),
        affected_entities_json=_safe_json(affected_entities or []),
        warnings_json=_safe_json(warnings or []),
        risk_level=risk_level,
        finished_at=_now(),
        expires_at=_now() + timedelta(hours=24),
    )
    session.add(run)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="automation.simulated",
        resource_type="automation_simulation_run",
        resource_id=str(run.id),
        payload={
            "automation_type": automation_type,
            "target_scope": target_scope,
            "would_trigger_count": would_trigger_count,
            "would_succeed_count": would_succeed_count,
            "would_fail_count": would_fail_count,
            "risk_level": risk_level,
        },
    )
    return run


def run_proxy_repair_simulation(session: Session, *, actor: User) -> AutomationSimulationRun:
    summary = simulation_mode_summary(session)
    candidates = [
        proxy
        for proxy in list_proxies(session)
        if proxy.status in {"warning", "critical"} or proxy.health_score < 70
    ]
    risk_level = "low"
    if summary.would_fail:
        risk_level = "high"
    elif summary.would_rotate > 5:
        risk_level = "medium"
    impact = {
        "mode": "simulation",
        "changes_applied": False,
        "candidate_proxy_ids": [proxy.id for proxy in candidates[:25]],
        "would_rotate": summary.would_rotate,
        "would_repair": summary.would_repair,
        "would_fail": summary.would_fail,
    }
    return create_simulation_run(
        session,
        actor=actor,
        automation_name="Proxy Repair Simulation",
        automation_type="proxy_repair",
        target_scope="proxy_vault",
        would_trigger_count=summary.would_rotate,
        would_succeed_count=max(summary.would_repair - summary.would_fail, 0),
        would_fail_count=summary.would_fail,
        impact_summary=impact,
        affected_entities=[{"entity_type": "proxy", "entity_id": proxy.id} for proxy in candidates[:25]],
        warnings=["Proxy repair remains simulation-first and approval-gated."],
        risk_level=risk_level,
    )


def run_daily_briefing_simulation(session: Session, *, actor: User) -> AutomationSimulationRun:
    stats = executive_dashboard(session)
    open_incidents = session.scalar(
        select(func.count(Incident.id)).where(Incident.status.in_(("open", "investigating")))
    ) or 0
    overdue_task_count = (
        session.scalar(
            select(func.count(Task.id)).where(
                Task.due_at.is_not(None),
                Task.due_at < func.now(),
                Task.status.in_(("open", "in_progress", "blocked")),
            )
        )
        or 0
    )
    impact = {
        "mode": "simulation",
        "changes_applied": False,
        "agency_health_score": stats["agency_health_score"],
        "open_incidents": open_incidents,
        "overdue_tasks": overdue_task_count,
        "delivery_preview": "Daily briefing would route to owner and operations targets.",
    }
    return create_simulation_run(
        session,
        actor=actor,
        automation_name="Daily Briefing Simulation",
        automation_type="daily_briefing",
        target_scope="reports",
        would_trigger_count=1,
        would_succeed_count=1,
        would_fail_count=0,
        impact_summary=impact,
        risk_level="low",
    )


def update_simulation_status(
    session: Session,
    run: AutomationSimulationRun,
    *,
    actor: User,
    status: str,
) -> AutomationSimulationRun:
    _require_manage_automations(session, actor)
    if status not in AUTOMATION_SIMULATION_STATUSES:
        raise ValueError(f"Invalid simulation status: {status}")
    if status == "approved" and run.risk_level in {"high", "critical"} and not is_owner(actor):
        audit_action(
            session,
            actor=actor,
            action="access.denied",
            resource_type="automation_simulation_run",
            resource_id=str(run.id),
            status="denied",
            details={"reason": "high_risk_simulation_requires_owner", "risk_level": run.risk_level},
        )
        raise PermissionError("High-risk simulations require Owner approval")
    old_status = run.status
    run.status = status
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name=f"automation.simulation.{status}",
        resource_type="automation_simulation_run",
        resource_id=str(run.id),
        payload={"from": old_status, "to": status, "risk_level": run.risk_level},
    )
    return run


def simulation_status() -> dict[str, object]:
    return {
        "status": "ready",
        "simulation_mode": True,
        "message": "Automations default to simulation mode until live actions are explicitly enabled.",
    }
