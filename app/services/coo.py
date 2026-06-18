from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.account import Account
from app.models.automation import AutomationApproval, AutomationRun
from app.models.autonomous_operations import FollowUp, OperationsAction
from app.models.coo import PriorityItem
from app.models.incident import Incident
from app.models.model_brand import ModelBrand, ModelBrandMember
from app.models.opportunity import Opportunity
from app.models.recommendation import Recommendation
from app.models.reporting import NotificationDeliveryAttempt
from app.models.task import Task
from app.models.team_rollout import TeamOnboardingChecklist
from app.models.user import User
from app.services.agency_activation import build_activation_report, run_activation_scan
from app.services.audit import sanitize_details
from app.services.auth import USER_STATUS_ACTIVE, audit_action, user_has_permission
from app.services.autonomous_operations import create_follow_up, owner_attention_user, recent_operations_activity
from app.services.events import emit_event
from app.services.learning import create_learning_event
from app.services.recommendations import upsert_recommendation
from app.services.tasks import create_task

ACTIVE_TASK_STATUSES = ("open", "in_progress", "blocked")
ACTIVE_INCIDENT_STATUSES = ("open", "investigating")
ACTIVE_OPPORTUNITY_STATUSES = ("discovered", "reviewing", "approved", "assigned")
GENERATED_CATEGORIES = {
    "readiness_blocker",
    "missing_proxy",
    "missing_manager",
    "missing_team",
    "critical_incident",
    "overdue_task",
    "unassigned_opportunity",
    "broken_notification_target",
    "failed_automation",
}

GAIN_BY_BLOCKER_CODE = {
    "model.none": 20,
    "model.missing_country": 5,
    "model.missing_timezone": 5,
    "model.missing_platform": 6,
    "model.missing_accounts": 12,
    "model.missing_team": 10,
    "team.missing_manager": 10,
    "team.missing_chatter": 10,
    "model.missing_creators": 7,
    "model.missing_opportunities": 7,
    "account.missing_proxy": 12,
    "account.missing_auth": 10,
    "notifications.missing_targets": 8,
    "team.no_real_users": 10,
    "opportunity.unlinked": 6,
}


@dataclass(frozen=True)
class TopAction:
    title: str
    owner: str
    score: int
    action_page: str
    explanation: str


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(value)))


def score_priority(*, severity: str, urgency: str, confidence: int, business_impact: int) -> int:
    severity_score = {"info": 25, "warning": 60, "critical": 90}.get(severity, 25)
    urgency_score = {"low": 20, "normal": 45, "high": 75, "urgent": 95}.get(urgency, 45)
    return _clamp(round((severity_score * 0.35) + (urgency_score * 0.25) + (confidence * 0.2) + (business_impact * 0.2)))


def _category_for_blocker(blocker: dict) -> str:
    code = str(blocker.get("code") or "")
    if code == "account.missing_proxy":
        return "missing_proxy"
    if code == "team.missing_manager":
        return "missing_manager"
    if code in {"model.missing_team", "team.missing_chatter", "team.no_real_users"}:
        return "missing_team"
    return "readiness_blocker"


def _route_for_blocker(blocker: dict) -> str:
    code = str(blocker.get("code") or "")
    if code in {"account.missing_proxy", "account.missing_auth"}:
        return "Admin"
    if code in {"model.missing_team", "team.missing_manager", "team.missing_chatter", "opportunity.unlinked"}:
        return "Manager"
    if code == "notifications.missing_targets":
        return "Owner"
    if blocker.get("severity") == "critical":
        return "Owner"
    return "Manager"


def route_owner_for_item(item: PriorityItem | dict) -> str:
    category = item.category if isinstance(item, PriorityItem) else str(item.get("category") or "")
    severity = item.severity if isinstance(item, PriorityItem) else str(item.get("severity") or "")
    if category in {"critical_incident", "failed_automation"}:
        return "Owner"
    if category == "missing_proxy":
        return "Admin"
    if category in {"missing_manager", "missing_team", "unassigned_opportunity", "overdue_task"}:
        return "Manager"
    if severity == "critical":
        return "Owner"
    return "Manager"


def _upsert_priority(
    session: Session,
    *,
    source_type: str,
    source_id: int | str | None,
    category: str,
    severity: str,
    urgency: str,
    confidence: int,
    business_impact: int,
    explanation: str,
    recommended_owner: str,
) -> PriorityItem:
    source_id_text = str(source_id or "")
    score = score_priority(
        severity=severity,
        urgency=urgency,
        confidence=confidence,
        business_impact=business_impact,
    )
    item = session.scalar(
        select(PriorityItem).where(
            PriorityItem.source_type == source_type,
            PriorityItem.source_id == source_id_text,
            PriorityItem.category == category,
        )
    )
    if item is None:
        item = PriorityItem(
            source_type=source_type,
            source_id=source_id_text,
            category=category,
            severity=severity,
            urgency=urgency,
            confidence=_clamp(confidence),
            business_impact=_clamp(business_impact),
            score=score,
            explanation=explanation,
            recommended_owner=recommended_owner,
            status="open",
        )
        session.add(item)
    else:
        item.severity = severity
        item.urgency = urgency
        item.confidence = _clamp(confidence)
        item.business_impact = _clamp(business_impact)
        item.score = score
        item.explanation = explanation
        item.recommended_owner = recommended_owner
        if item.status == "resolved":
            item.status = "open"
        item.updated_at = _now()
    session.flush()
    return item


def _mark_stale_priorities_resolved(session: Session, seen_keys: set[tuple[str, str, str]]) -> None:
    stale = list(
        session.scalars(
            select(PriorityItem).where(PriorityItem.status == "open", PriorityItem.category.in_(GENERATED_CATEGORIES))
        ).all()
    )
    for item in stale:
        if (item.source_type, item.source_id, item.category) not in seen_keys:
            item.status = "resolved"
            item.updated_at = _now()
    session.flush()


def _priority_sort(items: list[PriorityItem]) -> list[PriorityItem]:
    urgency_rank = {"urgent": 4, "high": 3, "normal": 2, "low": 1}
    return sorted(
        items,
        key=lambda item: (
            item.score,
            urgency_rank.get(item.urgency, 0),
            _aware(item.updated_at) if item.updated_at else datetime.min.replace(tzinfo=UTC),
        ),
        reverse=True,
    )


def generate_priority_items(session: Session, *, actor: User | None = None) -> list[PriorityItem]:
    report = build_activation_report(session)
    items: list[PriorityItem] = []
    seen_keys: set[tuple[str, str, str]] = set()

    for blocker in report["blockers"]:
        category = _category_for_blocker(blocker)
        stable_category = category if category != "readiness_blocker" else str(blocker.get("code") or category).replace(".", "_")
        source_type = blocker.get("entity_type") or "readiness"
        source_id = blocker.get("entity_id") or blocker.get("code") or category
        severity = "critical" if blocker.get("severity") == "critical" else "warning"
        urgency = "urgent" if severity == "critical" else "high"
        gain = GAIN_BY_BLOCKER_CODE.get(str(blocker.get("code") or ""), 5)
        explanation = f"{blocker['title']}. {blocker['description']} Estimated readiness gain: +{gain}."
        item = _upsert_priority(
            session,
            source_type=source_type,
            source_id=source_id,
            category=stable_category,
            severity=severity,
            urgency=urgency,
            confidence=90,
            business_impact=80 if severity == "critical" else 65,
            explanation=explanation,
            recommended_owner=_route_for_blocker(blocker),
        )
        items.append(item)
        seen_keys.add((item.source_type, item.source_id, item.category))

    now = _now()
    critical_incidents = list(
        session.scalars(
            select(Incident)
            .where(Incident.status.in_(ACTIVE_INCIDENT_STATUSES), Incident.severity == "critical")
            .options(selectinload(Incident.assigned_to))
        ).all()
    )
    for incident in critical_incidents:
        item = _upsert_priority(
            session,
            source_type="incident",
            source_id=incident.id,
            category="critical_incident",
            severity="critical",
            urgency="urgent",
            confidence=95,
            business_impact=100,
            explanation=f"Critical incident is still open: {incident.title}",
            recommended_owner="Owner",
        )
        items.append(item)
        seen_keys.add((item.source_type, item.source_id, item.category))

    overdue_tasks = list(
        session.scalars(
            select(Task)
            .where(Task.status.in_(ACTIVE_TASK_STATUSES), Task.due_at.is_not(None), Task.due_at < now)
            .options(selectinload(Task.assigned_to), selectinload(Task.owner))
        ).all()
    )
    for task in overdue_tasks:
        urgent = task.priority in {"high", "urgent"} or task.escalation_level > 0
        item = _upsert_priority(
            session,
            source_type="task",
            source_id=task.id,
            category="overdue_task",
            severity="critical" if task.priority == "urgent" else "warning",
            urgency="urgent" if urgent else "high",
            confidence=90,
            business_impact=85 if urgent else 65,
            explanation=f"Task is overdue: {task.title}",
            recommended_owner="Manager",
        )
        items.append(item)
        seen_keys.add((item.source_type, item.source_id, item.category))

    unassigned_opportunities = list(
        session.scalars(
            select(Opportunity).where(
                Opportunity.status.in_(ACTIVE_OPPORTUNITY_STATUSES),
                Opportunity.assigned_to_user_id.is_(None),
            )
        ).all()
    )
    for opportunity in unassigned_opportunities:
        urgent = opportunity.priority in {"high", "critical"}
        item = _upsert_priority(
            session,
            source_type="opportunity",
            source_id=opportunity.id,
            category="unassigned_opportunity",
            severity="critical" if opportunity.priority == "critical" else "warning",
            urgency="high" if urgent else "normal",
            confidence=80,
            business_impact=75 if urgent else 55,
            explanation=f"Opportunity needs an assignee: {opportunity.title}",
            recommended_owner="Manager",
        )
        items.append(item)
        seen_keys.add((item.source_type, item.source_id, item.category))

    failed_targets = list(
        session.scalars(
            select(NotificationDeliveryAttempt.notification_target_id)
            .where(NotificationDeliveryAttempt.status == "failed")
            .group_by(NotificationDeliveryAttempt.notification_target_id)
            .having(func.count(NotificationDeliveryAttempt.id) >= 2)
        ).all()
    )
    for target_id in failed_targets:
        item = _upsert_priority(
            session,
            source_type="notification_target",
            source_id=target_id,
            category="broken_notification_target",
            severity="warning",
            urgency="high",
            confidence=85,
            business_impact=70,
            explanation="Notification target has repeated failed delivery attempts.",
            recommended_owner="Admin",
        )
        items.append(item)
        seen_keys.add((item.source_type, item.source_id, item.category))

    failed_runs = list(
        session.scalars(
            select(AutomationRun)
            .where(AutomationRun.status == "failed")
            .order_by(desc(AutomationRun.updated_at), desc(AutomationRun.id))
            .limit(10)
        ).all()
    )
    for run in failed_runs:
        item = _upsert_priority(
            session,
            source_type="automation_run",
            source_id=run.id,
            category="failed_automation",
            severity="critical",
            urgency="high",
            confidence=90,
            business_impact=80,
            explanation=f"Automation run failed and may need review: run #{run.id}",
            recommended_owner="Owner",
        )
        items.append(item)
        seen_keys.add((item.source_type, item.source_id, item.category))

    _mark_stale_priorities_resolved(session, seen_keys)
    if actor is not None:
        emit_event(
            session,
            actor=actor,
            event_name="coo.priority_scan.completed",
            resource_type="priority_item",
            payload={"open_priorities": len(items), "readiness_score": report["readiness_score"]},
        )
    return _priority_sort(items)


def top_priorities(session: Session, *, actor: User | None = None, limit: int = 10) -> list[PriorityItem]:
    generate_priority_items(session, actor=actor)
    items = list(
        session.scalars(select(PriorityItem).where(PriorityItem.status == "open").order_by(desc(PriorityItem.score)).limit(limit)).all()
    )
    return _priority_sort(items)


def todays_top_5_actions(session: Session, *, actor: User | None = None) -> list[TopAction]:
    actions: list[TopAction] = []
    for item in top_priorities(session, actor=actor, limit=5):
        page = {
            "readiness": "agency_activation",
            "model": f"model:{item.source_id}:complete" if item.source_id.isdigit() else "agency_activation",
            "account": f"account:{item.source_id}" if item.source_id.isdigit() else "accounts",
            "task": f"task:{item.source_id}" if item.source_id.isdigit() else "tasks",
            "incident": f"incident:{item.source_id}" if item.source_id.isdigit() else "incidents",
            "opportunity": f"opportunity:{item.source_id}" if item.source_id.isdigit() else "opportunities:command",
            "notification_target": "notification_targets",
            "automation_run": f"automation_run:{item.source_id}" if item.source_id.isdigit() else "automations:runs",
        }.get(item.source_type, "agency_activation")
        actions.append(
            TopAction(
                title=item.explanation.split(".")[0],
                owner=item.recommended_owner,
                score=item.score,
                action_page=page,
                explanation=item.explanation,
            )
        )
    return actions


def readiness_score_v2(session: Session) -> dict:
    report = build_activation_report(session)
    blockers = []
    for blocker in report["blockers"]:
        gain = GAIN_BY_BLOCKER_CODE.get(str(blocker.get("code") or ""), 5)
        blockers.append(
            {
                "title": blocker["title"],
                "description": blocker["description"],
                "section": blocker.get("section"),
                "action_page": blocker.get("action_page"),
                "estimated_gain": gain,
                "severity": blocker.get("severity"),
            }
        )
    fastest = sorted(blockers, key=lambda blocker: (blocker["estimated_gain"], blocker["severity"] == "critical"), reverse=True)
    section_scores = {
        "models": report["models_ready"],
        "accounts": report["accounts_ready"],
        "teams": report["teams_ready"],
        "creators": report["creators_ready"],
        "opportunities": report["opportunities_ready"],
        "notifications": report["notifications_ready"],
    }
    lowest_sections = sorted(section_scores.items(), key=lambda item: item[1])[:3]
    return {
        "readiness_score": report["readiness_score"],
        "section_scores": section_scores,
        "why_low": [f"{name.title()} is {score}%" for name, score in lowest_sections if score < 100],
        "biggest_blockers": fastest[:5],
        "fastest_path": fastest[:3],
    }


def _active_users(session: Session) -> list[User]:
    return list(
        session.scalars(
            select(User)
            .where(User.status == USER_STATUS_ACTIVE, User.is_active.is_(True))
            .options(selectinload(User.roles), selectinload(User.availability))
            .order_by(User.id)
        ).all()
    )


def _user_label(user: User | None) -> str:
    if user is None:
        return "Unassigned"
    return user.display_name or user.username or f"User {user.id}"


def team_load_balancer(session: Session) -> dict:
    now = _now()
    rows = []
    for user in _active_users(session):
        open_tasks = session.scalar(
            select(func.count(Task.id)).where(Task.assigned_to_user_id == user.id, Task.status.in_(ACTIVE_TASK_STATUSES))
        ) or 0
        overdue = session.scalar(
            select(func.count(Task.id)).where(
                Task.assigned_to_user_id == user.id,
                Task.status.in_(ACTIVE_TASK_STATUSES),
                Task.due_at.is_not(None),
                Task.due_at < now,
            )
        ) or 0
        open_incidents = session.scalar(
            select(func.count(Incident.id)).where(
                Incident.assigned_to_user_id == user.id,
                Incident.status.in_(ACTIVE_INCIDENT_STATUSES),
            )
        ) or 0
        critical_incidents = session.scalar(
            select(func.count(Incident.id)).where(
                Incident.assigned_to_user_id == user.id,
                Incident.status.in_(ACTIVE_INCIDENT_STATUSES),
                Incident.severity == "critical",
            )
        ) or 0
        open_opportunities = session.scalar(
            select(func.count(Opportunity.id)).where(
                Opportunity.assigned_to_user_id == user.id,
                Opportunity.status.in_(ACTIVE_OPPORTUNITY_STATUSES),
            )
        ) or 0
        score = int(open_tasks + (overdue * 3) + (open_incidents * 2) + (critical_incidents * 4) + open_opportunities)
        if score >= 12:
            status = "critical"
        elif score >= 8:
            status = "overloaded"
        elif score >= 4:
            status = "elevated"
        else:
            status = "normal"
        rows.append(
            {
                "user_id": user.id,
                "name": _user_label(user),
                "availability": user.availability.status if user.availability else "unknown",
                "open_tasks": open_tasks,
                "overdue_tasks": overdue,
                "open_incidents": open_incidents,
                "critical_incidents": critical_incidents,
                "open_opportunities": open_opportunities,
                "workload_score": score,
                "status": status,
            }
        )
    overloaded = [row for row in rows if row["status"] in {"overloaded", "critical"}]
    idle = [row for row in rows if row["workload_score"] == 0 and row["availability"] not in {"off_shift", "vacation", "unavailable"}]
    recommendations = []
    if overloaded and idle:
        recommendations.append(f"Review reassignment from {overloaded[0]['name']} to {idle[0]['name']}.")
    elif overloaded:
        recommendations.append(f"Review workload for {overloaded[0]['name']}; no automatic reassignment was made.")
    elif idle:
        recommendations.append(f"{idle[0]['name']} appears available for new work.")
    return {"users": rows, "overloaded": overloaded, "idle": idle, "recommendations": recommendations}


def manager_work_queue(session: Session, *, actor: User | None = None) -> dict:
    generate_priority_items(session, actor=actor)
    today_end = _now().replace(hour=23, minute=59, second=59, microsecond=999999)
    unassigned_tasks = list(
        session.scalars(
            select(Task).where(Task.status.in_(ACTIVE_TASK_STATUSES), Task.assigned_to_user_id.is_(None)).limit(10)
        ).all()
    )
    unassigned_opportunities = list(
        session.scalars(
            select(Opportunity)
            .where(Opportunity.status.in_(ACTIVE_OPPORTUNITY_STATUSES), Opportunity.assigned_to_user_id.is_(None))
            .limit(10)
        ).all()
    )
    approvals = list(
        session.scalars(select(AutomationApproval).where(AutomationApproval.status == "pending").limit(10)).all()
    )
    attention = [
        item
        for item in top_priorities(session, actor=actor, limit=10)
        if item.recommended_owner in {"Manager", "Admin"}
    ]
    escalation_tasks = list(
        session.scalars(
            select(Task).where(Task.status.in_(ACTIVE_TASK_STATUSES), Task.escalation_level > 0).limit(10)
        ).all()
    )
    escalation_incidents = list(
        session.scalars(
            select(Incident)
            .where(Incident.status.in_(ACTIVE_INCIDENT_STATUSES), Incident.escalation_level > 0)
            .limit(10)
        ).all()
    )
    due_today = list(
        session.scalars(
            select(Task)
            .where(Task.status.in_(ACTIVE_TASK_STATUSES), Task.due_at.is_not(None), Task.due_at <= today_end)
            .limit(10)
        ).all()
    )
    overdue = [task for task in due_today if task.due_at and _aware(task.due_at) < _now()]
    return {
        "needs_assignment": [
            *[{"type": "task", "id": task.id, "title": task.title} for task in unassigned_tasks],
            *[{"type": "opportunity", "id": opp.id, "title": opp.title} for opp in unassigned_opportunities],
        ],
        "needs_approval": [{"type": "automation", "id": approval.id, "title": f"Automation approval #{approval.id}"} for approval in approvals],
        "needs_attention": [{"id": item.id, "title": item.explanation.split(".")[0], "owner": item.recommended_owner, "score": item.score} for item in attention],
        "needs_escalation": [
            *[{"type": "task", "id": task.id, "title": task.title} for task in escalation_tasks],
            *[{"type": "incident", "id": incident.id, "title": incident.title} for incident in escalation_incidents],
        ],
        "due_today": [{"id": task.id, "title": task.title, "priority": task.priority} for task in due_today],
        "overdue": [{"id": task.id, "title": task.title, "priority": task.priority} for task in overdue],
    }


def chatter_work_queue(session: Session, user: User) -> dict:
    now = _now()
    due_soon = now + timedelta(days=3)
    tasks = list(
        session.scalars(
            select(Task)
            .where(Task.assigned_to_user_id == user.id, Task.status.in_(ACTIVE_TASK_STATUSES))
            .order_by(Task.due_at, desc(Task.priority), Task.id)
        ).all()
    )
    opportunities = list(
        session.scalars(
            select(Opportunity)
            .where(Opportunity.assigned_to_user_id == user.id, Opportunity.status.in_(ACTIVE_OPPORTUNITY_STATUSES))
            .order_by(desc(Opportunity.priority), desc(Opportunity.score), Opportunity.id)
        ).all()
    )
    return {
        "today": [task for task in tasks if task.due_at and task.due_at.date() == now.date()],
        "priority": [task for task in tasks if task.priority in {"high", "urgent"}],
        "due_soon": [task for task in tasks if task.due_at and now <= _aware(task.due_at) <= due_soon],
        "waiting_on_me": [task for task in tasks if task.status in {"open", "blocked"}],
        "opportunities": opportunities,
        "tasks": tasks,
    }


def team_activation_engine(session: Session, *, actor: User | None = None) -> dict:
    users = _active_users(session)
    issues = []
    tasks_created = 0
    follow_ups_created = 0
    for user in users:
        if user.is_owner:
            continue
        roles = [role.name for role in user.roles]
        checklist = session.scalar(select(TeamOnboardingChecklist).where(TeamOnboardingChecklist.user_id == user.id))
        user_issues = []
        if not roles:
            user_issues.append("missing role")
        if not user.timezone or user.timezone == "UTC":
            user_issues.append("timezone not confirmed")
        if checklist is None or not checklist.onboarded:
            user_issues.append("not onboarded")
        assigned_work = (
            session.scalar(select(func.count(Task.id)).where(Task.assigned_to_user_id == user.id, Task.status.in_(ACTIVE_TASK_STATUSES)))
            or 0
        ) + (
            session.scalar(
                select(func.count(Opportunity.id)).where(
                    Opportunity.assigned_to_user_id == user.id,
                    Opportunity.status.in_(ACTIVE_OPPORTUNITY_STATUSES),
                )
            )
            or 0
        )
        if assigned_work == 0:
            user_issues.append("no assigned work")
        if user_issues:
            title = f"Activate {_user_label(user)}"
            description = f"Team activation gaps: {', '.join(user_issues)}."
            upsert_recommendation(
                session,
                actor=actor,
                recommendation_type="team_activation",
                title=title,
                description=description,
                severity="warning",
                entity_type="user",
                entity_id=user.id,
                metadata={"issues": user_issues},
            )
            if actor is not None and user_has_permission(actor, "manage_tasks"):
                existing = session.scalar(
                    select(func.count(Task.id)).where(Task.title == f"Team Activation: {title}", Task.status.in_(ACTIVE_TASK_STATUSES))
                ) or 0
                if not existing:
                    create_task(
                        session,
                        actor=actor,
                        title=f"Team Activation: {title}",
                        description=description,
                        priority="normal",
                        assigned_to=actor,
                    )
                    tasks_created += 1
            existing_follow_up = session.scalar(
                select(FollowUp).where(FollowUp.source_type == "user", FollowUp.source_id == str(user.id), FollowUp.status == "pending")
            )
            if existing_follow_up is None:
                create_follow_up(
                    session,
                    source_type="user",
                    source_id=user.id,
                    due_at=_now() + timedelta(days=1),
                    assigned_user=actor or owner_attention_user(session),
                )
                follow_ups_created += 1
            issues.append({"user_id": user.id, "name": _user_label(user), "issues": user_issues})
    if actor is not None:
        create_learning_event(
            session,
            event_type="coo.team_activation_scan",
            source_type="system",
            outcome="success",
            summary=f"Fortuna checked {len(users)} users and found {len(issues)} activation gaps.",
            actor=actor,
            severity="info",
            details={"users_with_gaps": len(issues), "tasks_created": tasks_created, "follow_ups_created": follow_ups_created},
        )
    return {"users_checked": len(users), "issues": issues, "tasks_created": tasks_created, "follow_ups_created": follow_ups_created}


def coo_briefing(session: Session, *, actor: User | None = None) -> dict:
    priorities = top_priorities(session, actor=actor, limit=5)
    readiness = readiness_score_v2(session)
    load = team_load_balancer(session)
    queue = manager_work_queue(session, actor=actor)
    changed = recent_operations_activity(session, limit=5)
    briefing = {
        "what_changed": changed or ["No new autonomous actions yet today."],
        "needs_attention": [item.explanation.split(".")[0] for item in priorities],
        "blocked": [item["title"] for item in readiness["biggest_blockers"][:3]],
        "next_actions": [action.title for action in todays_top_5_actions(session, actor=actor)],
        "overloaded": [row["name"] for row in load["overloaded"]],
        "idle": [row["name"] for row in load["idle"][:5]],
        "delegate": load["recommendations"],
        "manager_queue_counts": {key: len(value) for key, value in queue.items()},
        "readiness_score": readiness["readiness_score"],
    }
    if actor is not None:
        audit_action(
            session,
            actor=actor,
            action="coo.briefing.generated",
            resource_type="coo_briefing",
            details=sanitize_details({"readiness_score": briefing["readiness_score"], "priorities": len(priorities)}),
        )
        emit_event(
            session,
            actor=actor,
            event_name="coo.briefing.generated",
            resource_type="coo_briefing",
            payload={"readiness_score": briefing["readiness_score"], "priorities": len(priorities)},
        )
    return briefing


def fortuna_messages(session: Session, *, actor: User | None = None) -> list[str]:
    priorities = top_priorities(session, actor=actor, limit=5)
    readiness = readiness_score_v2(session)
    actions_today = session.scalar(
        select(func.count(OperationsAction.id)).where(OperationsAction.created_at >= _now() - timedelta(hours=24))
    ) or 0
    messages = [
        f"Fortuna noticed {len(priorities)} open priorities.",
        f"Fortuna readiness is {readiness['readiness_score']}%.",
        f"Fortuna completed or prepared {actions_today} operations actions in the last 24 hours.",
    ]
    if readiness["fastest_path"]:
        messages.append(f"Fortuna recommends: {readiness['fastest_path'][0]['title']}.")
    return messages


def executive_mode_summary(session: Session, *, actor: User | None = None) -> dict:
    priorities = top_priorities(session, actor=actor, limit=5)
    readiness = readiness_score_v2(session)
    critical_incidents = session.scalar(
        select(func.count(Incident.id)).where(Incident.status.in_(ACTIVE_INCIDENT_STATUSES), Incident.severity == "critical")
    ) or 0
    open_recommendations = session.scalar(
        select(func.count(Recommendation.id)).where(Recommendation.status == "open")
    ) or 0
    failed_automations = session.scalar(select(func.count(AutomationRun.id)).where(AutomationRun.status == "failed")) or 0
    return {
        "agency_health": "Action Needed" if priorities and priorities[0].severity == "critical" else "Watch" if priorities else "Healthy",
        "readiness_score": readiness["readiness_score"],
        "top_priorities": priorities,
        "critical_issues": critical_incidents,
        "open_recommendations": open_recommendations,
        "failed_automations": failed_automations,
        "messages": fortuna_messages(session, actor=actor),
    }


def run_coo_scan(session: Session, *, actor: User) -> dict:
    if user_has_permission(actor, "manage_accounts") or user_has_permission(actor, "manage_users"):
        run_activation_scan(session, actor=actor, create_tasks=True)
    priorities = generate_priority_items(session, actor=actor)
    activation = team_activation_engine(session, actor=actor)
    emit_event(
        session,
        actor=actor,
        event_name="coo.scan.completed",
        resource_type="coo",
        payload={"priorities": len(priorities), "activation_gaps": len(activation["issues"])},
    )
    return {"priorities": priorities, "activation": activation}
