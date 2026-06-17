from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models.account import Account
from app.models.audit import AuditLog
from app.models.model_brand import ModelBrand
from app.models.proxy import Proxy
from app.models.task import TASK_PRIORITIES, TASK_STATUSES, Task
from app.models.user import User
from app.services.auth import USER_STATUS_ACTIVE, audit_action, user_has_permission
from app.services.events import emit_event


def _now() -> datetime:
    return datetime.now(UTC)


def _require_manage_tasks(session: Session, actor: User | None) -> None:
    if user_has_permission(actor, "manage_tasks"):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="task",
        status="denied",
        details={"permission": "manage_tasks"},
    )
    raise PermissionError("Missing permission: manage_tasks")


def _task_payload(task: Task, extra: dict | None = None) -> dict:
    payload = {
        "task_id": task.id,
        "status": task.status,
        "priority": task.priority,
        "model_brand_id": task.model_brand_id,
        "account_id": task.account_id,
        "proxy_id": task.proxy_id,
        "owner_user_id": task.owner_user_id,
        "assigned_to_user_id": task.assigned_to_user_id,
        "escalation_level": task.escalation_level,
    }
    payload.update(extra or {})
    return payload


def _base_task_query():
    return select(Task).options(
        selectinload(Task.model_brand),
        selectinload(Task.account),
        selectinload(Task.proxy),
        selectinload(Task.owner),
        selectinload(Task.assigned_to),
        selectinload(Task.created_by),
    )


def list_tasks(session: Session, *, include_archived: bool = False) -> list[Task]:
    statement = _base_task_query().order_by(Task.priority.desc(), Task.due_at, Task.id)
    if not include_archived:
        statement = statement.where(Task.status != "archived")
    return list(session.scalars(statement).all())


def get_task(session: Session, task_id: int) -> Task | None:
    return session.scalar(_base_task_query().where(Task.id == task_id))


def tasks_for_model(session: Session, model_brand_id: int, *, include_archived: bool = False) -> list[Task]:
    statement = _base_task_query().where(Task.model_brand_id == model_brand_id).order_by(Task.id)
    if not include_archived:
        statement = statement.where(Task.status != "archived")
    return list(session.scalars(statement).all())


def create_task(
    session: Session,
    *,
    actor: User,
    title: str,
    description: str | None = None,
    priority: str = "normal",
    model_brand: ModelBrand | None = None,
    account: Account | None = None,
    proxy: Proxy | None = None,
    owner_user: User | None = None,
    assigned_to: User | None = None,
    due_at: datetime | None = None,
) -> Task:
    _require_manage_tasks(session, actor)
    clean_title = title.strip()
    if not clean_title:
        raise ValueError("Task title is required")
    if priority not in TASK_PRIORITIES:
        raise ValueError(f"Invalid task priority: {priority}")
    if assigned_to is not None and (assigned_to.status != USER_STATUS_ACTIVE or not assigned_to.is_active):
        raise PermissionError("Only active users can be assigned tasks")
    task = Task(
        title=clean_title,
        description=description,
        status="open",
        priority=priority,
        model_brand_id=model_brand.id if model_brand else None,
        account_id=account.id if account else None,
        proxy_id=proxy.id if proxy else None,
        owner_user_id=owner_user.id if owner_user else actor.id,
        assigned_to_user_id=assigned_to.id if assigned_to else None,
        created_by_user_id=actor.id,
        due_at=due_at,
    )
    session.add(task)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="task.created",
        resource_type="task",
        resource_id=str(task.id),
        payload=_task_payload(task),
    )
    if assigned_to is not None:
        emit_event(
            session,
            actor=actor,
            event_name="task.assigned",
            resource_type="task",
            resource_id=str(task.id),
            payload=_task_payload(task, {"assigned_to_user_id": assigned_to.id}),
        )
    return task


def create_default_task(session: Session, *, actor: User) -> Task:
    next_number = session.scalar(select(func.count(Task.id))) or 0
    return create_task(
        session,
        actor=actor,
        title=f"New Task {next_number + 1}",
        description="Created from Telegram. TODO: replace with a real task description.",
        priority="normal",
        due_at=_now() + timedelta(days=1),
    )


def assign_task(session: Session, task: Task, assignee: User, *, actor: User) -> Task:
    _require_manage_tasks(session, actor)
    if assignee.status != USER_STATUS_ACTIVE or not assignee.is_active:
        raise PermissionError("Only active users can be assigned tasks")
    previous_assignee_id = task.assigned_to_user_id
    task.assigned_to_user_id = assignee.id
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="task.assigned",
        resource_type="task",
        resource_id=str(task.id),
        payload=_task_payload(
            task,
            {"assigned_to_user_id": assignee.id, "previous_assignee_id": previous_assignee_id},
        ),
    )
    if previous_assignee_id is not None and previous_assignee_id != assignee.id:
        emit_event(
            session,
            actor=actor,
            event_name="task.reassigned",
            resource_type="task",
            resource_id=str(task.id),
            payload=_task_payload(
                task,
                {"assigned_to_user_id": assignee.id, "previous_assignee_id": previous_assignee_id},
            ),
        )
    return task


def update_task_status(
    session: Session,
    task: Task,
    *,
    actor: User,
    status: str,
    event_name: str,
) -> Task:
    _require_manage_tasks(session, actor)
    if status not in TASK_STATUSES:
        raise ValueError(f"Invalid task status: {status}")
    task.status = status
    if status == "in_progress" and task.started_at is None:
        task.started_at = _now()
    if status == "complete":
        task.completed_at = _now()
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name=event_name,
        resource_type="task",
        resource_id=str(task.id),
        payload=_task_payload(task),
    )
    if event_name == "task.completed":
        from app.services.learning import capture_task_completed

        capture_task_completed(session, task, actor=actor)
    elif event_name == "task.blocked":
        from app.services.learning import capture_task_blocked

        capture_task_blocked(session, task, actor=actor)
    return task


def start_task(session: Session, task: Task, *, actor: User) -> Task:
    return update_task_status(session, task, actor=actor, status="in_progress", event_name="task.started")


def block_task(session: Session, task: Task, *, actor: User, reason: str | None = None) -> Task:
    task.blocked_reason = reason or "Blocked from Telegram operations workflow."
    return update_task_status(session, task, actor=actor, status="blocked", event_name="task.blocked")


def complete_task(session: Session, task: Task, *, actor: User) -> Task:
    return update_task_status(session, task, actor=actor, status="complete", event_name="task.completed")


def archive_task(session: Session, task: Task, *, actor: User) -> Task:
    return update_task_status(session, task, actor=actor, status="archived", event_name="task.archived")


def escalate_task(session: Session, task: Task, *, actor: User) -> Task:
    _require_manage_tasks(session, actor)
    task.escalation_level += 1
    task.last_escalated_at = _now()
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="task.escalated",
        resource_type="task",
        resource_id=str(task.id),
        payload=_task_payload(task),
    )
    return task


def my_tasks(session: Session, user: User) -> list[Task]:
    return list(
        session.scalars(
            _base_task_query()
            .where(Task.assigned_to_user_id == user.id, Task.status != "archived")
            .order_by(Task.due_at, Task.id)
        ).all()
    )


def assigned_tasks(session: Session) -> list[Task]:
    return list(
        session.scalars(
            _base_task_query()
            .where(Task.assigned_to_user_id.is_not(None), Task.status != "archived")
            .order_by(Task.due_at, Task.id)
        ).all()
    )


def open_tasks(session: Session) -> list[Task]:
    return list(
        session.scalars(
            _base_task_query()
            .where(Task.status.in_(("open", "in_progress", "blocked")))
            .order_by(Task.due_at, Task.id)
        ).all()
    )


def blocked_tasks(session: Session) -> list[Task]:
    return list(session.scalars(_base_task_query().where(Task.status == "blocked").order_by(Task.id)).all())


def overdue_tasks(session: Session, *, now: datetime | None = None) -> list[Task]:
    current_time = now or _now()
    return list(
        session.scalars(
            _base_task_query()
            .where(
                Task.due_at.is_not(None),
                Task.due_at < current_time,
                Task.status.in_(("open", "in_progress", "blocked")),
            )
            .order_by(Task.due_at, Task.id)
        ).all()
    )


def record_overdue_tasks(session: Session, *, actor: User | None = None, now: datetime | None = None) -> int:
    tasks = overdue_tasks(session, now=now)
    for task in tasks:
        payload = _task_payload(task, {"due_at": task.due_at.isoformat() if task.due_at else None})
        emit_event(
            session,
            actor=actor,
            event_name="task.overdue_detected",
            resource_type="task",
            resource_id=str(task.id),
            status="overdue",
            payload=payload,
        )
        emit_event(
            session,
            actor=actor,
            event_name="task.overdue",
            resource_type="task",
            resource_id=str(task.id),
            status="overdue",
            payload=payload,
        )
        from app.services.learning import capture_task_overdue

        capture_task_overdue(session, task, actor=actor)
    return len(tasks)


def completed_today_count(session: Session, *, now: datetime | None = None) -> int:
    current_time = now or _now()
    start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return (
        session.scalar(
            select(func.count(Task.id)).where(
                Task.status == "complete",
                Task.completed_at.is_not(None),
                Task.completed_at >= start,
                Task.completed_at < end,
            )
        )
        or 0
    )


def completed_today_by_user(session: Session, *, now: datetime | None = None, limit: int = 5) -> list[tuple[User, int]]:
    current_time = now or _now()
    start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    rows = session.execute(
        select(User, func.count(Task.id))
        .join(Task, Task.assigned_to_user_id == User.id)
        .where(
            Task.status == "complete",
            Task.completed_at.is_not(None),
            Task.completed_at >= start,
            Task.completed_at < end,
        )
        .group_by(User.id)
        .order_by(func.count(Task.id).desc(), User.id)
        .limit(limit)
    ).all()
    return [(user, count) for user, count in rows]


def count_tasks(
    session: Session,
    *,
    statuses: tuple[str, ...] | None = None,
    assigned_to_user_id: int | None = None,
    overdue: bool = False,
    now: datetime | None = None,
) -> int:
    filters = []
    if statuses is not None:
        filters.append(Task.status.in_(statuses))
    if assigned_to_user_id is not None:
        filters.append(Task.assigned_to_user_id == assigned_to_user_id)
    if overdue:
        current_time = now or _now()
        filters.extend(
            [
                Task.due_at.is_not(None),
                Task.due_at < current_time,
                Task.status.in_(("open", "in_progress", "blocked")),
            ]
        )
    statement = select(func.count(Task.id))
    if filters:
        statement = statement.where(and_(*filters))
    return session.scalar(statement) or 0


def task_audit_logs(session: Session, task: Task, *, limit: int = 10) -> list[AuditLog]:
    return list(
        session.scalars(
            select(AuditLog)
            .where(AuditLog.resource_type == "task", AuditLog.resource_id == str(task.id))
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
        ).all()
    )


def tasks_requiring_attention(session: Session) -> list[Task]:
    return list(
        session.scalars(
            _base_task_query()
            .where(or_(Task.status == "blocked", Task.priority == "urgent"))
            .where(Task.status != "archived")
            .order_by(Task.priority.desc(), Task.due_at, Task.id)
        ).all()
    )
