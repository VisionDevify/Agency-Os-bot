from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.account import Account
from app.models.audit import AuditLog
from app.models.event_log import EventLog
from app.models.incident import Incident
from app.models.intelligence import (
    ExecutiveInsight,
    IntelligenceRun,
    IntelligenceSignal,
    IssuePattern,
    TrendSnapshot,
    WorkloadSnapshot,
)
from app.models.model_brand import ModelBrand
from app.models.proxy import Proxy
from app.models.recommendation import Recommendation
from app.models.reporting import NotificationDeliveryAttempt
from app.models.system import SystemHeartbeat
from app.models.task import Task
from app.models.user import User
from app.services.account_health import calculate_account_health
from app.services.audit import sanitize_details
from app.services.auth import USER_STATUS_ACTIVE, audit_action, user_has_permission
from app.services.events import emit_event
from app.services.model_health import calculate_model_health
from app.services.notifications import (
    active_targets_for_event,
    create_delivery_attempt,
    record_notification_routed,
)
from app.services.operations import agency_health_score
from app.services.recommendations import upsert_recommendation
from app.services.tasks import count_tasks


BAD_TREND_METRICS = {
    "open_incidents",
    "critical_incidents",
    "overdue_tasks",
    "notification_failures",
    "recommendations_open",
}
GOOD_TREND_METRICS = {
    "agency_health_score",
    "model_health_score",
    "account_health_score",
    "proxy_health_score",
    "completed_tasks",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _today(current_time: datetime | None = None) -> date:
    return (current_time or _now()).date()


def _require_intelligence_access(session: Session, actor: User | None) -> None:
    if user_has_permission(actor, "manage_reports") or user_has_permission(actor, "view_dashboard"):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="intelligence",
        status="denied",
        details={"permission": "manage_reports_or_view_dashboard"},
    )
    raise PermissionError("Missing permission: manage_reports or view_dashboard")


def _safe_metadata(metadata: dict | None) -> dict:
    return sanitize_details(metadata or {})


def _identity(user: User) -> str:
    return user.display_name or user.username or f"User {user.id}"


def _entity_id(value: int | str | None) -> str | None:
    return str(value) if value is not None else None


def _upsert_signal(
    session: Session,
    *,
    actor: User | None,
    signal_type: str,
    title: str,
    description: str,
    severity: str = "info",
    confidence_score: int = 80,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    occurrence_count: int = 1,
    metadata: dict | None = None,
) -> IntelligenceSignal:
    current_time = _now()
    entity_id_text = _entity_id(entity_id)
    signal = session.scalar(
        select(IntelligenceSignal)
        .where(
            IntelligenceSignal.signal_type == signal_type,
            IntelligenceSignal.entity_type == entity_type,
            IntelligenceSignal.entity_id == entity_id_text,
            IntelligenceSignal.status.in_(("open", "acknowledged")),
        )
        .order_by(desc(IntelligenceSignal.last_seen_at), desc(IntelligenceSignal.id))
        .limit(1)
    )
    created = signal is None
    if signal is None:
        signal = IntelligenceSignal(
            signal_type=signal_type,
            severity=severity,
            entity_type=entity_type,
            entity_id=entity_id_text,
            title=title,
            description=description,
            confidence_score=max(0, min(100, confidence_score)),
            metadata_json=_safe_metadata(metadata),
            first_seen_at=current_time,
            last_seen_at=current_time,
            occurrence_count=max(1, occurrence_count),
            status="open",
        )
        session.add(signal)
    else:
        signal.severity = severity
        signal.title = title
        signal.description = description
        signal.confidence_score = max(0, min(100, confidence_score))
        signal.metadata_json = _safe_metadata(metadata)
        signal.last_seen_at = current_time
        signal.occurrence_count = max(signal.occurrence_count, occurrence_count)
        signal.updated_at = current_time
    session.flush()
    if created:
        emit_event(
            session,
            actor=actor,
            event_name="intelligence.signal.created",
            resource_type="intelligence_signal",
            resource_id=str(signal.id),
            payload={
                "signal_type": signal.signal_type,
                "severity": signal.severity,
                "entity_type": signal.entity_type,
                "entity_id": signal.entity_id,
                "confidence_score": signal.confidence_score,
            },
        )
    if signal.severity == "critical":
        route_critical_signal_notification(session, signal, actor=actor)
    return signal


def create_or_update_signal(
    session: Session,
    *,
    actor: User | None,
    signal_type: str,
    title: str,
    description: str,
    severity: str = "info",
    confidence_score: int = 80,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    occurrence_count: int = 1,
    metadata: dict | None = None,
) -> IntelligenceSignal:
    return _upsert_signal(
        session,
        actor=actor,
        signal_type=signal_type,
        title=title,
        description=description,
        severity=severity,
        confidence_score=confidence_score,
        entity_type=entity_type,
        entity_id=entity_id,
        occurrence_count=occurrence_count,
        metadata=metadata,
    )


def _upsert_pattern(
    session: Session,
    *,
    actor: User | None,
    pattern_type: str,
    title: str,
    description: str,
    severity: str,
    confidence_score: int,
    suggested_action: str,
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    occurrence_count: int = 1,
    related_event_ids: list[int] | None = None,
) -> IssuePattern:
    current_time = _now()
    entity_id_text = _entity_id(entity_id)
    pattern = session.scalar(
        select(IssuePattern)
        .where(
            IssuePattern.pattern_type == pattern_type,
            IssuePattern.entity_type == entity_type,
            IssuePattern.entity_id == entity_id_text,
            IssuePattern.status.in_(("active", "acknowledged")),
        )
        .order_by(desc(IssuePattern.last_seen_at), desc(IssuePattern.id))
        .limit(1)
    )
    created = pattern is None
    if pattern is None:
        pattern = IssuePattern(
            pattern_type=pattern_type,
            title=title,
            description=description,
            entity_type=entity_type,
            entity_id=entity_id_text,
            severity=severity,
            confidence_score=max(0, min(100, confidence_score)),
            occurrence_count=max(1, occurrence_count),
            related_event_ids_json=list(related_event_ids or []),
            suggested_action=suggested_action,
            status="active",
            first_seen_at=current_time,
            last_seen_at=current_time,
        )
        session.add(pattern)
    else:
        pattern.title = title
        pattern.description = description
        pattern.severity = severity
        pattern.confidence_score = max(0, min(100, confidence_score))
        pattern.occurrence_count = max(pattern.occurrence_count, occurrence_count)
        pattern.related_event_ids_json = list(related_event_ids or pattern.related_event_ids_json or [])
        pattern.suggested_action = suggested_action
        pattern.last_seen_at = current_time
        pattern.updated_at = current_time
    session.flush()
    if created:
        emit_event(
            session,
            actor=actor,
            event_name="intelligence.pattern.detected",
            resource_type="issue_pattern",
            resource_id=str(pattern.id),
            payload={
                "pattern_type": pattern.pattern_type,
                "severity": pattern.severity,
                "entity_type": pattern.entity_type,
                "entity_id": pattern.entity_id,
                "confidence_score": pattern.confidence_score,
            },
        )
    return pattern


def _events_in_window(session: Session, event_types: tuple[str, ...], *, hours: int = 24) -> list[EventLog]:
    since = _now() - timedelta(hours=hours)
    return list(
        session.scalars(
            select(EventLog)
            .where(EventLog.event_type.in_(event_types), EventLog.created_at >= since)
            .order_by(EventLog.id)
        ).all()
    )


def _audit_in_window(session: Session, actions: tuple[str, ...], *, hours: int = 24) -> list[AuditLog]:
    since = _now() - timedelta(hours=hours)
    return list(
        session.scalars(
            select(AuditLog)
            .where(AuditLog.action.in_(actions), AuditLog.created_at >= since)
            .order_by(AuditLog.id)
        ).all()
    )


def _group_by_entity(rows: list[EventLog | AuditLog]) -> dict[tuple[str | None, str | None], list[EventLog | AuditLog]]:
    grouped: dict[tuple[str | None, str | None], list[EventLog | AuditLog]] = defaultdict(list)
    for row in rows:
        entity_type = getattr(row, "entity_type", None) or getattr(row, "resource_type", None)
        entity_id = getattr(row, "entity_id", None) or getattr(row, "resource_id", None)
        grouped[(entity_type, entity_id)].append(row)
    return grouped


def _related_ids(rows: list[EventLog | AuditLog]) -> list[int]:
    return [row.id for row in rows[:50]]


def _create_pattern_artifacts(
    session: Session,
    *,
    actor: User | None,
    signal_type: str,
    pattern_type: str,
    title: str,
    description: str,
    severity: str,
    confidence_score: int,
    suggested_action: str,
    recommendation_type: str,
    recommendation_title: str,
    recommendation_description: str,
    entity_type: str | None,
    entity_id: int | str | None,
    occurrence_count: int,
    related_event_ids: list[int],
    metadata: dict | None = None,
) -> dict[str, Any]:
    signal = _upsert_signal(
        session,
        actor=actor,
        signal_type=signal_type,
        title=title,
        description=description,
        severity=severity,
        confidence_score=confidence_score,
        entity_type=entity_type,
        entity_id=entity_id,
        occurrence_count=occurrence_count,
        metadata={
            "occurrence_count": occurrence_count,
            "source_event_ids": related_event_ids,
            **(metadata or {}),
        },
    )
    pattern = _upsert_pattern(
        session,
        actor=actor,
        pattern_type=pattern_type,
        title=title,
        description=description,
        severity=severity,
        confidence_score=confidence_score,
        suggested_action=suggested_action,
        entity_type=entity_type,
        entity_id=entity_id,
        occurrence_count=occurrence_count,
        related_event_ids=related_event_ids,
    )
    recommendation = upsert_recommendation(
        session,
        actor=actor,
        recommendation_type=recommendation_type,
        title=recommendation_title,
        description=recommendation_description,
        severity=severity,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata={
            "reason": description,
            "confidence_score": confidence_score,
            "source_signal_ids": [signal.id],
            "source_pattern_id": pattern.id,
            "suggested_action": suggested_action,
            "occurrence_count": occurrence_count,
        },
    )
    audit_action(
        session,
        actor=actor,
        action="intelligence.pattern_detected",
        resource_type="issue_pattern",
        resource_id=str(pattern.id),
        details={
            "pattern_type": pattern_type,
            "severity": severity,
            "signal_id": signal.id,
            "recommendation_id": recommendation.id,
        },
    )
    return {"signal": signal, "pattern": pattern, "recommendation": recommendation}


def detect_patterns(session: Session, *, actor: User | None = None) -> dict[str, int]:
    _require_intelligence_access(session, actor)
    created = {"signals": 0, "patterns": 0, "recommendations": 0}

    proxy_failures = _events_in_window(
        session,
        ("proxy.repair.failed", "proxy.rotation.failed", "proxy.health.changed"),
    )
    proxy_failures.extend(_audit_in_window(session, ("proxy.repair.failed", "proxy.rotation.failed")))
    for (entity_type, entity_id), rows in _group_by_entity(proxy_failures).items():
        if entity_type != "proxy" or entity_id is None or len(rows) < 3:
            continue
        artifacts = _create_pattern_artifacts(
            session,
            actor=actor,
            signal_type="recurring_proxy_failures",
            pattern_type="recurring_proxy_failures",
            title="Recurring Proxy Failures",
            description=f"Proxy {entity_id} failed {len(rows)} times in the last 24 hours.",
            severity="critical",
            confidence_score=90,
            suggested_action="Replace or rotate the proxy and review affected accounts.",
            recommendation_type="replace_rotate_proxy",
            recommendation_title="Replace or Rotate Proxy",
            recommendation_description=f"Proxy {entity_id} is repeatedly failing and should be reviewed.",
            entity_type="proxy",
            entity_id=entity_id,
            occurrence_count=len(rows),
            related_event_ids=_related_ids(rows),
        )
        created["signals"] += int(artifacts["signal"] is not None)
        created["patterns"] += int(artifacts["pattern"] is not None)
        created["recommendations"] += int(artifacts["recommendation"] is not None)

    location_mismatches = _events_in_window(session, ("proxy.location.mismatch",))
    location_mismatches.extend(_audit_in_window(session, ("proxy.location.mismatch",)))
    for (entity_type, entity_id), rows in _group_by_entity(location_mismatches).items():
        if entity_type != "proxy" or entity_id is None or len(rows) < 2:
            continue
        _create_pattern_artifacts(
            session,
            actor=actor,
            signal_type="repeated_location_mismatch",
            pattern_type="repeated_location_mismatch",
            title="Repeated Proxy Location Mismatch",
            description=f"Proxy {entity_id} mismatched target location {len(rows)} times recently.",
            severity="warning",
            confidence_score=85,
            suggested_action="Run location verification and rotate sessions until target state matches.",
            recommendation_type="proxy_location_mismatch",
            recommendation_title="Fix Proxy Location Mismatch",
            recommendation_description=f"Proxy {entity_id} needs location verification.",
            entity_type="proxy",
            entity_id=entity_id,
            occurrence_count=len(rows),
            related_event_ids=_related_ids(rows),
        )

    for account in session.scalars(select(Account).where(Account.status.in_(("warning", "critical")))).all():
        _create_pattern_artifacts(
            session,
            actor=actor,
            signal_type="account_health_degradation",
            pattern_type="account_health_degradation",
            title="Account Health Degradation",
            description=f"Account @{account.username} is {account.status} with auth status {account.auth_status}.",
            severity="critical" if account.status == "critical" else "warning",
            confidence_score=80,
            suggested_action="Review account auth state, proxy assignment, and recent incidents.",
            recommendation_type="review_account_health",
            recommendation_title="Review Account Health",
            recommendation_description=f"Account @{account.username} needs attention.",
            entity_type="account",
            entity_id=account.id,
            occurrence_count=1,
            related_event_ids=[],
        )

    for model in session.scalars(select(ModelBrand).where(ModelBrand.status.in_(("warning", "disabled")))).all():
        _create_pattern_artifacts(
            session,
            actor=actor,
            signal_type="model_health_decline",
            pattern_type="model_health_decline",
            title="Model Health Decline",
            description=f"Model/Brand {model.display_name} is currently {model.status}.",
            severity="critical" if model.status == "disabled" else "warning",
            confidence_score=75,
            suggested_action="Review model team assignment, open tasks, and open incidents.",
            recommendation_type="review_model_health",
            recommendation_title="Review Model Health",
            recommendation_description=f"Model/Brand {model.display_name} needs health review.",
            entity_type="model_brand",
            entity_id=model.id,
            occurrence_count=1,
            related_event_ids=[],
        )

    overdue_tasks = list(
        session.scalars(
            select(Task).where(
                Task.status.in_(("open", "in_progress", "blocked")),
                Task.due_at.is_not(None),
                Task.due_at < _now(),
            )
        ).all()
    )
    tasks_by_user: dict[int, list[Task]] = defaultdict(list)
    tasks_by_model: dict[int, list[Task]] = defaultdict(list)
    for task in overdue_tasks:
        if task.assigned_to_user_id is not None:
            tasks_by_user[task.assigned_to_user_id].append(task)
        if task.model_brand_id is not None:
            tasks_by_model[task.model_brand_id].append(task)
    for user_id, tasks in tasks_by_user.items():
        if len(tasks) < 2:
            continue
        _create_pattern_artifacts(
            session,
            actor=actor,
            signal_type="repeated_overdue_tasks",
            pattern_type="repeated_overdue_tasks",
            title="Repeated Overdue Tasks",
            description=f"User {user_id} has {len(tasks)} overdue tasks.",
            severity="warning",
            confidence_score=85,
            suggested_action="Reassign work or adjust due dates after manager review.",
            recommendation_type="reassign_work",
            recommendation_title="Reassign Work",
            recommendation_description=f"User {user_id} is carrying repeated overdue tasks.",
            entity_type="user",
            entity_id=user_id,
            occurrence_count=len(tasks),
            related_event_ids=[],
        )
    for model_id, tasks in tasks_by_model.items():
        if len(tasks) < 2:
            continue
        _create_pattern_artifacts(
            session,
            actor=actor,
            signal_type="model_overdue_tasks",
            pattern_type="model_overdue_tasks",
            title="Model Has Repeated Overdue Tasks",
            description=f"Model/Brand {model_id} has {len(tasks)} overdue tasks.",
            severity="warning",
            confidence_score=80,
            suggested_action="Review model workload and assignment.",
            recommendation_type="clean_up_stale_tasks",
            recommendation_title="Clean Up Stale Tasks",
            recommendation_description=f"Model/Brand {model_id} has repeated overdue work.",
            entity_type="model_brand",
            entity_id=model_id,
            occurrence_count=len(tasks),
            related_event_ids=[],
        )

    open_incidents = list(
        session.scalars(select(Incident).where(Incident.status.in_(("open", "investigating")))).all()
    )
    incident_groups: dict[tuple[str, int], list[Incident]] = defaultdict(list)
    for incident in open_incidents:
        if incident.proxy_id is not None:
            incident_groups[("proxy", incident.proxy_id)].append(incident)
        if incident.account_id is not None:
            incident_groups[("account", incident.account_id)].append(incident)
        if incident.model_brand_id is not None:
            incident_groups[("model_brand", incident.model_brand_id)].append(incident)
    for (entity_type, entity_id), incidents in incident_groups.items():
        if len(incidents) < 2:
            continue
        severity = "critical" if any(incident.severity == "critical" for incident in incidents) else "warning"
        _create_pattern_artifacts(
            session,
            actor=actor,
            signal_type="incident_recurrence",
            pattern_type="incident_recurrence",
            title="Recurring Incidents",
            description=f"{entity_type}:{entity_id} has {len(incidents)} open or investigating incidents.",
            severity=severity,
            confidence_score=88,
            suggested_action="Investigate root cause and consolidate active incident response.",
            recommendation_type="investigate_recurring_incident",
            recommendation_title="Investigate Recurring Incident",
            recommendation_description=f"{entity_type}:{entity_id} has recurring incidents.",
            entity_type=entity_type,
            entity_id=entity_id,
            occurrence_count=len(incidents),
            related_event_ids=[],
        )

    failed_delivery_rows = list(
        session.scalars(
            select(NotificationDeliveryAttempt).where(NotificationDeliveryAttempt.status == "failed")
        ).all()
    )
    failures_by_target: dict[int, list[NotificationDeliveryAttempt]] = defaultdict(list)
    for attempt in failed_delivery_rows:
        failures_by_target[attempt.notification_target_id].append(attempt)
    for target_id, attempts in failures_by_target.items():
        if len(attempts) < 3:
            continue
        _create_pattern_artifacts(
            session,
            actor=actor,
            signal_type="notification_delivery_failure_cluster",
            pattern_type="notification_delivery_failure_cluster",
            title="Notification Delivery Failure Cluster",
            description=f"Notification target {target_id} has {len(attempts)} failed attempts.",
            severity="warning",
            confidence_score=90,
            suggested_action="Check target registration and send a sandbox test.",
            recommendation_type="fix_notification_target",
            recommendation_title="Fix Notification Target",
            recommendation_description=f"Notification target {target_id} is repeatedly failing.",
            entity_type="notification_target",
            entity_id=target_id,
            occurrence_count=len(attempts),
            related_event_ids=[],
        )

    degraded_heartbeats = list(
        session.scalars(select(SystemHeartbeat).where(~SystemHeartbeat.status.in_(("healthy", "running", "ok")))).all()
    )
    for heartbeat in degraded_heartbeats:
        _create_pattern_artifacts(
            session,
            actor=actor,
            signal_type="production_instability",
            pattern_type="production_instability",
            title="Production Instability",
            description=f"{heartbeat.service_name} heartbeat is {heartbeat.status}.",
            severity="critical" if heartbeat.status in {"offline", "critical"} else "warning",
            confidence_score=85,
            suggested_action="Open Production Status and inspect Railway service logs.",
            recommendation_type="escalate_critical_issue",
            recommendation_title="Review Production Status",
            recommendation_description=f"{heartbeat.service_name} heartbeat is degraded.",
            entity_type="system_heartbeat",
            entity_id=heartbeat.id,
            occurrence_count=1,
            related_event_ids=[],
        )

    return created


def _previous_trend_snapshot(
    session: Session,
    *,
    metric_name: str,
    comparison_window: str,
    entity_type: str | None,
    entity_id: str | None,
) -> TrendSnapshot | None:
    return session.scalar(
        select(TrendSnapshot)
        .where(
            TrendSnapshot.metric_name == metric_name,
            TrendSnapshot.comparison_window == comparison_window,
            TrendSnapshot.entity_type.is_(None) if entity_type is None else TrendSnapshot.entity_type == entity_type,
            TrendSnapshot.entity_id.is_(None) if entity_id is None else TrendSnapshot.entity_id == entity_id,
        )
        .order_by(desc(TrendSnapshot.created_at), desc(TrendSnapshot.id))
        .limit(1)
    )


def _trend_direction(previous: int | None, current: int) -> tuple[str, int | None]:
    if previous is None:
        return "flat", None
    if previous == current:
        return "flat", 0
    if previous == 0:
        return ("up" if current > 0 else "flat"), 100 if current > 0 else 0
    percent_change = round(((current - previous) / previous) * 100)
    if abs(percent_change) >= 50 and previous > 0:
        return "volatile", percent_change
    return ("up" if current > previous else "down"), percent_change


def _negative_trend(metric_name: str, direction: str, percent_change: int | None) -> bool:
    if percent_change is None:
        return False
    magnitude = abs(percent_change)
    if metric_name in BAD_TREND_METRICS and direction in {"up", "volatile"} and percent_change > 0:
        return magnitude >= 15
    if metric_name in GOOD_TREND_METRICS and direction in {"down", "volatile"} and percent_change < 0:
        return magnitude >= 15
    return False


def record_trend_snapshot(
    session: Session,
    *,
    actor: User | None,
    metric_name: str,
    value_numeric: int,
    comparison_window: str = "daily",
    entity_type: str | None = None,
    entity_id: int | str | None = None,
    metadata: dict | None = None,
) -> TrendSnapshot:
    entity_id_text = _entity_id(entity_id)
    previous = _previous_trend_snapshot(
        session,
        metric_name=metric_name,
        comparison_window=comparison_window,
        entity_type=entity_type,
        entity_id=entity_id_text,
    )
    direction, percent_change = _trend_direction(previous.value_numeric if previous else None, value_numeric)
    snapshot = TrendSnapshot(
        snapshot_date=_today(),
        metric_name=metric_name,
        entity_type=entity_type,
        entity_id=entity_id_text,
        value_numeric=value_numeric,
        comparison_window=comparison_window,
        trend_direction=direction,
        percent_change=percent_change,
        metadata_json=_safe_metadata(metadata),
    )
    session.add(snapshot)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="intelligence.trend.recorded",
        resource_type="trend_snapshot",
        resource_id=str(snapshot.id),
        payload={
            "metric_name": metric_name,
            "value_numeric": value_numeric,
            "trend_direction": direction,
            "percent_change": percent_change,
        },
    )
    if _negative_trend(metric_name, direction, percent_change):
        _upsert_signal(
            session,
            actor=actor,
            signal_type="negative_trend",
            title="Negative Trend Detected",
            description=f"{metric_name} moved {direction} by {percent_change}%.",
            severity="warning",
            confidence_score=80,
            entity_type=entity_type,
            entity_id=entity_id_text,
            occurrence_count=1,
            metadata={
                "metric_name": metric_name,
                "trend_snapshot_id": snapshot.id,
                "trend_direction": direction,
                "percent_change": percent_change,
            },
        )
    return snapshot


def _average_account_health(session: Session) -> int:
    accounts = list(session.scalars(select(Account).where(Account.status != "archived")).all())
    if not accounts:
        return 100
    return round(sum(calculate_account_health(account).score for account in accounts) / len(accounts))


def _average_proxy_health(session: Session) -> int:
    count = session.scalar(select(func.count(Proxy.id))) or 0
    if not count:
        return 100
    return round(session.scalar(select(func.avg(Proxy.health_score))) or 100)


def _average_model_health(session: Session) -> int:
    models = list(session.scalars(select(ModelBrand).where(ModelBrand.status != "archived")).all())
    if not models:
        return 100
    accounts = list(session.scalars(select(Account).where(Account.status != "archived")).all())
    total = 0
    for model in models:
        model_accounts = [account for account in accounts if account.model_brand_id == model.id]
        total += calculate_model_health(
            model,
            open_incidents=session.scalar(
                select(func.count(Incident.id)).where(
                    Incident.model_brand_id == model.id,
                    Incident.status.in_(("open", "investigating")),
                )
            )
            or 0,
            disabled_accounts=sum(1 for account in model_accounts if account.status == "disabled"),
            warning_accounts=sum(
                1
                for account in model_accounts
                if account.status in {"warning", "critical"}
                or account.auth_status in {"needs_login", "needs_2fa", "expired", "locked"}
            ),
        ).score
    return round(total / len(models))


def run_trend_analysis(session: Session, *, actor: User | None = None) -> list[TrendSnapshot]:
    _require_intelligence_access(session, actor)
    current_time = _now()
    start = current_time - timedelta(days=1)
    metrics = {
        "agency_health_score": agency_health_score(session),
        "model_health_score": _average_model_health(session),
        "account_health_score": _average_account_health(session),
        "proxy_health_score": _average_proxy_health(session),
        "open_incidents": session.scalar(
            select(func.count(Incident.id)).where(Incident.status.in_(("open", "investigating")))
        )
        or 0,
        "critical_incidents": session.scalar(
            select(func.count(Incident.id)).where(
                Incident.status.in_(("open", "investigating")),
                Incident.severity == "critical",
            )
        )
        or 0,
        "overdue_tasks": count_tasks(session, overdue=True),
        "completed_tasks": session.scalar(
            select(func.count(Task.id)).where(
                Task.status == "complete",
                Task.completed_at.is_not(None),
                Task.completed_at >= start,
            )
        )
        or 0,
        "notification_failures": session.scalar(
            select(func.count(NotificationDeliveryAttempt.id)).where(NotificationDeliveryAttempt.status == "failed")
        )
        or 0,
        "recommendations_open": session.scalar(
            select(func.count(Recommendation.id)).where(Recommendation.status == "open")
        )
        or 0,
    }
    return [
        record_trend_snapshot(
            session,
            actor=actor,
            metric_name=name,
            value_numeric=int(value),
            metadata={"source": "trend_analysis"},
        )
        for name, value in metrics.items()
    ]


def calculate_workload_score(
    *,
    open_tasks: int,
    overdue_tasks: int,
    open_incidents: int,
    critical_incidents: int,
    completed_tasks_24h: int,
    resolved_incidents_24h: int,
    availability_status: str,
) -> int:
    score = (
        open_tasks * 10
        + overdue_tasks * 20
        + open_incidents * 12
        + critical_incidents * 25
        - completed_tasks_24h * 3
        - resolved_incidents_24h * 5
    )
    if availability_status in {"off_shift", "away", "vacation", "unavailable"} and (open_tasks or open_incidents):
        score += 10
    return max(0, min(150, score))


def classify_overload(score: int) -> str:
    if score >= 90:
        return "critical"
    if score >= 60:
        return "overloaded"
    if score >= 30:
        return "elevated"
    return "normal"


def _completed_tasks_24h(session: Session, user_id: int, *, since: datetime) -> int:
    return session.scalar(
        select(func.count(Task.id)).where(
            Task.assigned_to_user_id == user_id,
            Task.status == "complete",
            Task.completed_at.is_not(None),
            Task.completed_at >= since,
        )
    ) or 0


def _resolved_incidents_24h(session: Session, user_id: int, *, since: datetime) -> int:
    return session.scalar(
        select(func.count(Incident.id)).where(
            Incident.resolved_by_user_id == user_id,
            Incident.resolved_at.is_not(None),
            Incident.resolved_at >= since,
        )
    ) or 0


def analyze_workload(session: Session, *, actor: User | None = None) -> list[WorkloadSnapshot]:
    _require_intelligence_access(session, actor)
    current_time = _now()
    since = current_time - timedelta(hours=24)
    users = list(
        session.scalars(
            select(User)
            .where(User.status == USER_STATUS_ACTIVE, User.is_active.is_(True))
            .options(selectinload(User.availability))
            .order_by(User.id)
        ).all()
    )
    snapshots: list[WorkloadSnapshot] = []
    for user in users:
        availability_status = user.availability.status if user.availability else "off_shift"
        open_task_count = count_tasks(
            session,
            statuses=("open", "in_progress", "blocked"),
            assigned_to_user_id=user.id,
        )
        overdue_task_count = count_tasks(session, assigned_to_user_id=user.id, overdue=True)
        open_incident_count = (
            session.scalar(
                select(func.count(Incident.id)).where(
                    Incident.assigned_to_user_id == user.id,
                    Incident.status.in_(("open", "investigating")),
                )
            )
            or 0
        )
        critical_incident_count = (
            session.scalar(
                select(func.count(Incident.id)).where(
                    Incident.assigned_to_user_id == user.id,
                    Incident.status.in_(("open", "investigating")),
                    Incident.severity == "critical",
                )
            )
            or 0
        )
        completed = _completed_tasks_24h(session, user.id, since=since)
        resolved = _resolved_incidents_24h(session, user.id, since=since)
        score = calculate_workload_score(
            open_tasks=open_task_count,
            overdue_tasks=overdue_task_count,
            open_incidents=open_incident_count,
            critical_incidents=critical_incident_count,
            completed_tasks_24h=completed,
            resolved_incidents_24h=resolved,
            availability_status=availability_status,
        )
        overload_status = classify_overload(score)
        snapshot = WorkloadSnapshot(
            snapshot_date=_today(current_time),
            user_id=user.id,
            open_tasks=open_task_count,
            overdue_tasks=overdue_task_count,
            open_incidents=open_incident_count,
            critical_incidents=critical_incident_count,
            completed_tasks_24h=completed,
            resolved_incidents_24h=resolved,
            availability_status=availability_status,
            workload_score=score,
            overload_status=overload_status,
            metadata_json=_safe_metadata({"display_name": _identity(user)}),
        )
        session.add(snapshot)
        session.flush()
        snapshots.append(snapshot)
        if overload_status in {"overloaded", "critical"}:
            signal = _upsert_signal(
                session,
                actor=actor,
                signal_type="user_workload_overload",
                title="User Workload Overload",
                description=f"{_identity(user)} is {overload_status} with workload score {score}.",
                severity="critical" if overload_status == "critical" else "warning",
                confidence_score=85,
                entity_type="user",
                entity_id=user.id,
                metadata={
                    "workload_snapshot_id": snapshot.id,
                    "workload_score": score,
                    "overload_status": overload_status,
                },
            )
            upsert_recommendation(
                session,
                actor=actor,
                recommendation_type="reassign_work",
                title="Reassign Work From Overloaded User",
                description=f"{_identity(user)} may need workload relief.",
                severity="critical" if overload_status == "critical" else "warning",
                entity_type="user",
                entity_id=user.id,
                metadata={
                    "reason": f"Workload score {score} classified as {overload_status}.",
                    "confidence_score": 85,
                    "source_signal_ids": [signal.id],
                    "suggested_action": "Move urgent tasks or incidents to an available teammate.",
                },
            )
        if availability_status != "on_shift" and (open_task_count or open_incident_count):
            signal = _upsert_signal(
                session,
                actor=actor,
                signal_type="off_shift_work_assigned",
                title="Off-Shift User Has Active Work",
                description=f"{_identity(user)} is {availability_status} with active assignments.",
                severity="warning",
                confidence_score=75,
                entity_type="user",
                entity_id=user.id,
                metadata={"workload_snapshot_id": snapshot.id, "availability_status": availability_status},
            )
            upsert_recommendation(
                session,
                actor=actor,
                recommendation_type="review_team_availability",
                title="Review Team Availability",
                description=f"{_identity(user)} has work while marked {availability_status}.",
                severity="warning",
                entity_type="user",
                entity_id=user.id,
                metadata={
                    "reason": "Assignments exist for a user not currently on shift.",
                    "confidence_score": 75,
                    "source_signal_ids": [signal.id],
                    "suggested_action": "Route new work to operations or an on-shift manager.",
                },
            )
    emit_event(
        session,
        actor=actor,
        event_name="workload.analysis.completed",
        resource_type="workload_snapshot",
        payload={"users": len(snapshots)},
    )
    return snapshots


def generate_intelligence_recommendations(session: Session, *, actor: User | None = None) -> list[Recommendation]:
    _require_intelligence_access(session, actor)
    recommendations: list[Recommendation] = []
    open_signals = list(
        session.scalars(
            select(IntelligenceSignal).where(IntelligenceSignal.status == "open").order_by(desc(IntelligenceSignal.last_seen_at))
        ).all()
    )
    for signal in open_signals[:25]:
        rec_type = {
            "recurring_proxy_failures": "replace_rotate_proxy",
            "repeated_location_mismatch": "replace_rotate_proxy",
            "account_health_degradation": "review_account_health",
            "model_health_decline": "review_model_health",
            "incident_recurrence": "investigate_recurring_incident",
            "user_workload_overload": "reassign_work",
            "notification_delivery_failure_cluster": "fix_notification_target",
            "production_instability": "escalate_critical_issue",
            "negative_trend": "escalate_critical_issue",
        }.get(signal.signal_type, "review_operational_signal")
        recommendations.append(
            upsert_recommendation(
                session,
                actor=actor,
                recommendation_type=rec_type,
                title=signal.title,
                description=signal.description,
                severity=signal.severity,
                entity_type=signal.entity_type,
                entity_id=signal.entity_id,
                metadata={
                    "reason": signal.description,
                    "confidence_score": signal.confidence_score,
                    "source_signal_ids": [signal.id],
                    "suggested_action": _suggested_action_for_signal(signal),
                },
            )
        )
    emit_event(
        session,
        actor=actor,
        event_name="recommendation_generation.completed",
        resource_type="recommendation",
        payload={"recommendations": len(recommendations), "source": "intelligence_v2"},
    )
    return recommendations


def _suggested_action_for_signal(signal: IntelligenceSignal) -> str:
    return {
        "recurring_proxy_failures": "Rotate or replace the proxy and review attached accounts.",
        "repeated_location_mismatch": "Run location verification and confirm target state/city.",
        "account_health_degradation": "Review auth status, proxy assignment, and account incidents.",
        "model_health_decline": "Review team assignment, open work, and incidents.",
        "repeated_overdue_tasks": "Reassign or reprioritize overdue work.",
        "incident_recurrence": "Investigate root cause and consolidate response.",
        "notification_delivery_failure_cluster": "Check notification target configuration.",
        "production_instability": "Open Production Status and inspect deployment logs.",
        "user_workload_overload": "Move work from the overloaded user to available teammates.",
        "negative_trend": "Review the metric and assign an owner for corrective action.",
    }.get(signal.signal_type, "Review the signal and decide the next operational action.")


def recommendation_why(recommendation: Recommendation) -> dict:
    metadata = recommendation.metadata_json or {}
    return {
        "reason": metadata.get("reason") or recommendation.description,
        "confidence_score": metadata.get("confidence_score"),
        "source_signal_ids": metadata.get("source_signal_ids", []),
        "source_pattern_id": metadata.get("source_pattern_id"),
        "suggested_action": metadata.get("suggested_action") or "Review recommendation details.",
        "related_entity": (
            f"{recommendation.entity_type}:{recommendation.entity_id}"
            if recommendation.entity_type and recommendation.entity_id
            else "General"
        ),
    }


def _create_executive_insight(
    session: Session,
    *,
    actor: User | None,
    insight_type: str,
    title: str,
    body: str,
    severity: str,
    confidence_score: int,
    recommended_action: str,
    source_signal_ids: list[int] | None = None,
) -> ExecutiveInsight:
    insight = ExecutiveInsight(
        insight_type=insight_type,
        title=title,
        body=body,
        severity=severity,
        confidence_score=confidence_score,
        recommended_action=recommended_action,
        source_signal_ids_json=list(source_signal_ids or []),
        status="open",
    )
    session.add(insight)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="executive_insight.created",
        resource_type="executive_insight",
        resource_id=str(insight.id),
        payload={"insight_type": insight_type, "severity": severity, "confidence_score": confidence_score},
    )
    return insight


def generate_executive_intelligence_briefing(session: Session, *, actor: User | None = None) -> dict:
    _require_intelligence_access(session, actor)
    detect_patterns(session, actor=actor)
    run_trend_analysis(session, actor=actor)
    analyze_workload(session, actor=actor)
    generate_intelligence_recommendations(session, actor=actor)
    signals = list_signals(session, status="open", limit=25)
    patterns = list_patterns(session, status="active", limit=10)
    trends = list_trends(session, limit=10)
    workloads = list_workload_snapshots(session, limit=25)
    recommendations = list(
        session.scalars(select(Recommendation).where(Recommendation.status == "open").order_by(desc(Recommendation.created_at)).limit(10)).all()
    )
    critical_signals = [signal for signal in signals if signal.severity == "critical"]
    negative_trends = [trend for trend in trends if _negative_trend(trend.metric_name, trend.trend_direction, trend.percent_change)]
    overloaded = [snapshot for snapshot in workloads if snapshot.overload_status in {"overloaded", "critical"}]
    score = agency_health_score(session)
    summary_text = (
        f"Agency health is {score}/100 with {len(critical_signals)} critical signals, "
        f"{len(patterns)} active patterns, and {len(overloaded)} overloaded users."
    )
    top_risks = [signal.title for signal in critical_signals[:3]] or [signal.title for signal in signals[:3]]
    top_improvements = [recommendation.title for recommendation in recommendations[:3]]
    source_signal_ids = [signal.id for signal in signals[:10]]
    insight = _create_executive_insight(
        session,
        actor=actor,
        insight_type="executive_intelligence_briefing",
        title="Executive Intelligence Briefing",
        body=summary_text,
        severity="critical" if critical_signals or score < 60 else ("warning" if score < 80 else "info"),
        confidence_score=85,
        recommended_action=top_improvements[0] if top_improvements else "Keep monitoring command center signals.",
        source_signal_ids=source_signal_ids,
    )
    briefing = {
        "insight_id": insight.id,
        "generated_at": _now().isoformat(),
        "agency_health_score": score,
        "summary_text": summary_text,
        "top_risks": top_risks[:3],
        "top_improvements": top_improvements[:3],
        "patterns_detected": [pattern.title for pattern in patterns[:5]],
        "negative_trends": [
            f"{trend.metric_name}: {trend.trend_direction} {trend.percent_change}%"
            for trend in negative_trends[:5]
        ],
        "overloaded_users": [snapshot.metadata_json.get("display_name", f"User {snapshot.user_id}") for snapshot in overloaded[:5]],
        "recurring_incidents": [
            pattern.title
            for pattern in patterns
            if pattern.pattern_type == "incident_recurrence"
        ][:5],
        "recommended_actions": top_improvements[:5],
        "production_status": session.scalar(select(SystemHeartbeat.status).where(SystemHeartbeat.service_name == "api")) or "unknown",
        "confidence_notes": "Deterministic V1 analysis from internal Agency OS events, audits, and persisted operational records.",
    }
    emit_event(
        session,
        actor=actor,
        event_name="executive_intelligence_briefing.generated",
        resource_type="executive_insight",
        resource_id=str(insight.id),
        payload={
            "agency_health_score": score,
            "critical_signals": len(critical_signals),
            "active_patterns": len(patterns),
            "overloaded_users": len(overloaded),
        },
    )
    return briefing


def command_center_intelligence_status(session: Session) -> dict:
    open_signals = session.scalar(
        select(func.count(IntelligenceSignal.id)).where(IntelligenceSignal.status == "open")
    ) or 0
    critical_signals = session.scalar(
        select(func.count(IntelligenceSignal.id)).where(
            IntelligenceSignal.status == "open",
            IntelligenceSignal.severity == "critical",
        )
    ) or 0
    active_patterns = session.scalar(
        select(func.count(IssuePattern.id)).where(IssuePattern.status == "active")
    ) or 0
    latest_trends = list_trends(session, limit=25)
    negative_trends = sum(
        1
        for trend in latest_trends
        if _negative_trend(trend.metric_name, trend.trend_direction, trend.percent_change)
    )
    latest_workload = list_workload_snapshots(session, limit=50)
    overloaded_users = sum(
        1
        for snapshot in latest_workload
        if snapshot.overload_status in {"overloaded", "critical"}
    )
    open_insights = session.scalar(
        select(func.count(ExecutiveInsight.id)).where(ExecutiveInsight.status == "open")
    ) or 0
    if critical_signals or overloaded_users:
        status = "\U0001f534 Action Needed"
    elif active_patterns or negative_trends:
        status = "\U0001f7e1 Watch"
    elif open_signals:
        status = "\U0001f535 Processing"
    else:
        status = "\U0001f7e2 Stable"
    return {
        "status": status,
        "open_signals": open_signals,
        "critical_signals": critical_signals,
        "active_patterns": active_patterns,
        "negative_trends": negative_trends,
        "overloaded_users": overloaded_users,
        "open_executive_insights": open_insights,
    }


def run_intelligence_analysis(session: Session, *, actor: User | None, run_type: str) -> IntelligenceRun:
    _require_intelligence_access(session, actor)
    run = IntelligenceRun(
        run_type=run_type,
        status="running",
        started_by_user_id=actor.id if actor else None,
        started_at=_now(),
        summary_json={},
    )
    session.add(run)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="intelligence_run.started",
        resource_type="intelligence_run",
        resource_id=str(run.id),
        payload={"run_type": run_type},
    )
    try:
        if run_type == "pattern_detection":
            result = detect_patterns(session, actor=actor)
        elif run_type == "trend_analysis":
            result = {"trend_snapshots": len(run_trend_analysis(session, actor=actor))}
        elif run_type == "workload_analysis":
            result = {"workload_snapshots": len(analyze_workload(session, actor=actor))}
        elif run_type == "recommendation_generation":
            result = {"recommendations": len(generate_intelligence_recommendations(session, actor=actor))}
        elif run_type == "executive_briefing":
            result = generate_executive_intelligence_briefing(session, actor=actor)
        elif run_type == "opportunity_scoring":
            from app.services.opportunities import run_opportunity_scoring

            result = {"opportunities_scored": run_opportunity_scoring(session, actor=actor)}
        else:
            raise ValueError(f"Invalid intelligence run type: {run_type}")
        run.status = "succeeded"
        run.summary_json = _safe_metadata(result)
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)[:500]
        run.summary_json = {"error": "run failed"}
        raise
    finally:
        run.finished_at = _now()
        session.flush()
        emit_event(
            session,
            actor=actor,
            event_name=f"intelligence_run.{run.status}",
            resource_type="intelligence_run",
            resource_id=str(run.id),
            status=run.status,
            payload={"run_type": run.run_type, "summary": run.summary_json},
        )
    return run


def run_full_intelligence_scan(session: Session, *, actor: User | None) -> list[IntelligenceRun]:
    runs = []
    for run_type in (
        "pattern_detection",
        "trend_analysis",
        "workload_analysis",
        "recommendation_generation",
        "executive_briefing",
        "opportunity_scoring",
    ):
        runs.append(run_intelligence_analysis(session, actor=actor, run_type=run_type))
    return runs


def route_critical_signal_notification(
    session: Session,
    signal: IntelligenceSignal,
    *,
    actor: User | None,
) -> list[NotificationDeliveryAttempt]:
    if signal.severity != "critical":
        return []
    event_type = "intelligence.signal.critical"
    targets = active_targets_for_event(session, event_type, severity="critical")
    if not targets and signal.entity_type == "incident":
        targets = active_targets_for_event(session, "incident.created", severity="critical")
    attempts: list[NotificationDeliveryAttempt] = []
    for target in targets:
        attempts.append(
            create_delivery_attempt(
                session,
                target,
                event_type=event_type,
                actor=actor,
                status="pending",
                metadata={"signal_id": signal.id, "signal_type": signal.signal_type, "severity": signal.severity},
            )
        )
    if attempts:
        record_notification_routed(session, actor=actor, event_type=event_type, target_count=len(attempts))
    return attempts


def list_signals(session: Session, *, status: str | None = "open", limit: int = 20) -> list[IntelligenceSignal]:
    statement = select(IntelligenceSignal).order_by(desc(IntelligenceSignal.last_seen_at), desc(IntelligenceSignal.id))
    if status is not None:
        statement = statement.where(IntelligenceSignal.status == status)
    return list(session.scalars(statement.limit(limit)).all())


def list_patterns(session: Session, *, status: str | None = "active", limit: int = 20) -> list[IssuePattern]:
    statement = select(IssuePattern).order_by(desc(IssuePattern.last_seen_at), desc(IssuePattern.id))
    if status is not None:
        statement = statement.where(IssuePattern.status == status)
    return list(session.scalars(statement.limit(limit)).all())


def list_trends(session: Session, *, limit: int = 20) -> list[TrendSnapshot]:
    return list(
        session.scalars(
            select(TrendSnapshot).order_by(desc(TrendSnapshot.created_at), desc(TrendSnapshot.id)).limit(limit)
        ).all()
    )


def list_workload_snapshots(session: Session, *, limit: int = 20) -> list[WorkloadSnapshot]:
    return list(
        session.scalars(
            select(WorkloadSnapshot).order_by(desc(WorkloadSnapshot.created_at), desc(WorkloadSnapshot.id)).limit(limit)
        ).all()
    )


def list_executive_insights(session: Session, *, limit: int = 20) -> list[ExecutiveInsight]:
    return list(
        session.scalars(
            select(ExecutiveInsight).order_by(desc(ExecutiveInsight.created_at), desc(ExecutiveInsight.id)).limit(limit)
        ).all()
    )


def list_intelligence_runs(session: Session, *, limit: int = 20) -> list[IntelligenceRun]:
    return list(
        session.scalars(
            select(IntelligenceRun).order_by(desc(IntelligenceRun.started_at), desc(IntelligenceRun.id)).limit(limit)
        ).all()
    )
