from datetime import UTC, datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.automation import AUTOMATION_RISK_LEVELS, AUTOMATION_SIMULATION_STATUSES, AutomationSimulationRun
from app.models.incident import Incident
from app.models.proxy import Proxy
from app.models.task import Task
from app.models.user import User
from app.services.auth import audit_action, is_owner, user_has_permission
from app.services.events import emit_event
from app.services.operations import executive_dashboard
from app.services.proxies import simulation_mode_summary


def _now() -> datetime:
    return datetime.now(UTC)


def _require_manage_automations(session: Session, actor: User | None) -> None:
    if user_has_permission(actor, "manage_automations"):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="automation_simulation",
        status="denied",
        details={"permission": "manage_automations"},
    )
    raise PermissionError("Missing permission: manage_automations")


def list_simulation_runs(session: Session, *, limit: int = 20) -> list[AutomationSimulationRun]:
    return list(
        session.scalars(
            select(AutomationSimulationRun)
            .order_by(desc(AutomationSimulationRun.created_at), desc(AutomationSimulationRun.id))
            .limit(limit)
        ).all()
    )


def get_simulation_run(session: Session, run_id: int) -> AutomationSimulationRun | None:
    return session.get(AutomationSimulationRun, run_id)


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
) -> AutomationSimulationRun:
    _require_manage_automations(session, actor)
    if risk_level not in AUTOMATION_RISK_LEVELS:
        raise ValueError(f"Invalid risk level: {risk_level}")
    run = AutomationSimulationRun(
        automation_name=automation_name,
        automation_type=automation_type,
        status="simulated",
        simulated_by_user_id=actor.id,
        target_scope=target_scope,
        would_trigger_count=would_trigger_count,
        would_succeed_count=would_succeed_count,
        would_fail_count=would_fail_count,
        impact_summary_json=impact_summary,
        risk_level=risk_level,
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
    candidates = list(
        session.scalars(
            select(Proxy).where((Proxy.status.in_(("warning", "critical"))) | (Proxy.health_score < 70))
        ).all()
    )
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
        risk_level=risk_level,
    )


def run_daily_briefing_simulation(session: Session, *, actor: User) -> AutomationSimulationRun:
    stats = executive_dashboard(session)
    open_incidents = session.scalar(
        select(func.count(Incident.id)).where(Incident.status.in_(("open", "investigating")))
    ) or 0
    overdue_tasks = session.scalar(
        select(func.count(Task.id)).where(
            Task.due_at.is_not(None),
            Task.due_at < func.now(),
            Task.status.in_(("open", "in_progress", "blocked")),
        )
    ) or 0
    impact = {
        "mode": "simulation",
        "changes_applied": False,
        "agency_health_score": stats["agency_health_score"],
        "open_incidents": open_incidents,
        "overdue_tasks": overdue_tasks,
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
