from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from app.models.opportunity import Opportunity, OpportunityResult
from app.models.performance import TeamPerformanceSnapshot
from app.models.task import Task
from app.models.user import User
from app.services.team_experience import primary_role, role_names


@dataclass(frozen=True)
class TeamIntelligenceSummary:
    snapshots: tuple[TeamPerformanceSnapshot, ...]
    best_chatter: User | None
    overloaded_users: tuple[User, ...]
    idle_users: tuple[User, ...]
    next_best_move: str


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _clamp(value: int | float) -> int:
    return max(0, min(100, round(value)))


def _display_role(user: User) -> str:
    role = primary_role(user)
    return role if role != "Viewer" else (role_names(user)[0] if role_names(user) else "Viewer")


def generate_team_performance_snapshot(
    session: Session,
    user: User,
    *,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> TeamPerformanceSnapshot:
    end = period_end or _now()
    start = period_start or (end - timedelta(days=7))
    completed = session.scalar(
        select(func.count(Task.id)).where(
            Task.assigned_to_user_id == user.id,
            Task.status == "complete",
            Task.completed_at.is_not(None),
            Task.completed_at >= start,
            Task.completed_at <= end,
        )
    ) or 0
    overdue = session.scalar(
        select(func.count(Task.id)).where(
            Task.assigned_to_user_id == user.id,
            Task.status.in_(("open", "in_progress", "blocked")),
            Task.due_at.is_not(None),
            Task.due_at < end,
        )
    ) or 0
    reviewed = session.scalar(
        select(func.count(OpportunityResult.id)).where(
            OpportunityResult.posted_by_user_id == user.id,
            OpportunityResult.created_at >= start,
            OpportunityResult.created_at <= end,
        )
    ) or 0
    successful = session.scalar(
        select(func.count(OpportunityResult.id)).where(
            OpportunityResult.posted_by_user_id == user.id,
            OpportunityResult.status == "posted",
            OpportunityResult.created_at >= start,
            OpportunityResult.created_at <= end,
        )
    ) or 0
    open_tasks = session.scalar(
        select(func.count(Task.id)).where(Task.assigned_to_user_id == user.id, Task.status.in_(("open", "in_progress", "blocked")))
    ) or 0
    assigned_opps = session.scalar(
        select(func.count(Opportunity.id)).where(
            Opportunity.assigned_to_user_id == user.id,
            Opportunity.status.in_(("discovered", "reviewing", "approved", "assigned")),
        )
    ) or 0
    workload = _clamp((open_tasks * 12) + (assigned_opps * 10) + (overdue * 18))
    reliability = _clamp(72 + (completed * 4) + (successful * 8) - (overdue * 12))
    snapshot = TeamPerformanceSnapshot(
        user_id=user.id,
        role=_display_role(user),
        period_start=start,
        period_end=end,
        tasks_completed=int(completed),
        tasks_overdue=int(overdue),
        opportunities_reviewed=int(reviewed),
        opportunities_successful=int(successful),
        avg_response_minutes=None,
        workload_score=workload,
        reliability_score=reliability,
        notes="Generated from tasks and opportunity results. Friendly guidance only.",
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def latest_team_snapshots(session: Session, *, limit: int = 25) -> list[TeamPerformanceSnapshot]:
    return list(
        session.scalars(
            select(TeamPerformanceSnapshot)
            .order_by(desc(TeamPerformanceSnapshot.period_end), desc(TeamPerformanceSnapshot.id))
            .limit(limit)
        ).all()
    )


def team_intelligence_summary(session: Session) -> TeamIntelligenceSummary:
    users = list(
        session.scalars(
            select(User)
            .options(selectinload(User.roles))
            .where(User.status == "active", User.is_active.is_(True))
            .order_by(User.id)
        ).all()
    )
    recent_by_user: dict[int, TeamPerformanceSnapshot] = {}
    for snapshot in latest_team_snapshots(session, limit=100):
        recent_by_user.setdefault(snapshot.user_id, snapshot)
    snapshots: list[TeamPerformanceSnapshot] = []
    for user in users:
        snapshot = recent_by_user.get(user.id)
        if snapshot is None or _aware(snapshot.period_end) < _now() - timedelta(hours=24):
            snapshot = generate_team_performance_snapshot(session, user)
        snapshots.append(snapshot)

    user_by_id = {user.id: user for user in users}
    chatter_snapshots = [
        snapshot
        for snapshot in snapshots
        if "chatter" in snapshot.role.lower() or snapshot.role.lower() in {"owner", "manager"}
    ]
    best_snapshot = max(
        chatter_snapshots,
        key=lambda item: (item.reliability_score - max(0, item.workload_score - 60), -item.tasks_overdue),
        default=None,
    )
    overloaded = tuple(
        user_by_id[snapshot.user_id]
        for snapshot in snapshots
        if snapshot.user_id in user_by_id and (snapshot.workload_score >= 80 or snapshot.tasks_overdue > 0)
    )
    idle = tuple(
        user_by_id[snapshot.user_id]
        for snapshot in snapshots
        if snapshot.user_id in user_by_id and snapshot.workload_score <= 20 and snapshot.tasks_completed == 0
    )
    if best_snapshot is not None and best_snapshot.user_id in user_by_id:
        next_move = f"Assign new opportunities to {user_by_id[best_snapshot.user_id].display_name or user_by_id[best_snapshot.user_id].username or 'the most available chatter'}."
    elif users:
        next_move = "Review team availability before assigning new work."
    else:
        next_move = "Invite your first team member when you are ready."
    return TeamIntelligenceSummary(
        snapshots=tuple(snapshots),
        best_chatter=user_by_id.get(best_snapshot.user_id) if best_snapshot else None,
        overloaded_users=overloaded,
        idle_users=idle,
        next_best_move=next_move,
    )
