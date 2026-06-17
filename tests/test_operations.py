from datetime import UTC, datetime, timedelta

import pytest

from app.models.audit import AuditLog
from app.models.incident import Incident
from app.models.task import Task
from app.services.accounts import create_account
from app.services.auth import USER_STATUS_ACTIVE, assign_role_to_user, get_or_create_telegram_user, setup_owner_if_needed
from app.services.dashboard import dashboard_stats
from app.services.incidents import (
    assign_incident,
    create_incident,
    critical_incidents,
    escalate_incident,
    resolve_incident,
)
from app.services.model_brands import create_model_brand
from app.services.operations import executive_dashboard, generate_accountability_report, generate_daily_briefing
from app.services.permissions import RoleName
from app.services.tasks import (
    assign_task,
    complete_task,
    create_task,
    overdue_tasks,
    start_task,
)
from tests.utils import session_scope


def _active_user(session, telegram_id: int, display_name: str):
    user = get_or_create_telegram_user(session, telegram_user_id=telegram_id, display_name=display_name)
    user.status = USER_STATUS_ACTIVE
    user.is_active = True
    return user


def test_task_creation_assignment_completion_and_overdue_query() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        assignee = _active_user(session, 20, "Ops User")
        model = create_model_brand(session, actor=owner, display_name="Ops Model")
        account = create_account(session, model_brand=model, platform="instagram", username="ops", actor=owner)

        task = create_task(
            session,
            actor=owner,
            title="Check account health",
            priority="urgent",
            model_brand=model,
            account=account,
            due_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert task.status == "open"
        assert task in overdue_tasks(session)

        assign_task(session, task, assignee, actor=owner)
        start_task(session, task, actor=owner)
        complete_task(session, task, actor=owner)

        assert task.assigned_to_user_id == assignee.id
        assert task.status == "complete"
        assert task.completed_at is not None
        assert task not in overdue_tasks(session)
        assert session.query(AuditLog).filter_by(action="task.created").count() == 1
        assert session.query(AuditLog).filter_by(action="task.assigned").count() == 1
        assert session.query(AuditLog).filter_by(action="task.completed").count() == 1


def test_task_permission_restriction_records_audit() -> None:
    with session_scope() as session:
        setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        viewer = _active_user(session, 21, "Viewer")
        assign_role_to_user(session, viewer, RoleName.VIEWER)

        with pytest.raises(PermissionError):
            create_task(session, actor=viewer, title="Unauthorized task")

        denied = session.query(AuditLog).filter_by(action="access.denied", resource_type="task").one()
        assert denied.details["permission"] == "manage_tasks"


def test_incident_creation_escalation_resolution_and_critical_query() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        assignee = _active_user(session, 22, "Incident Owner")
        model = create_model_brand(session, actor=owner, display_name="Incident Model")

        incident = create_incident(
            session,
            actor=owner,
            title="Proxy failures rising",
            description="Repeated proxy failures need review.",
            severity="critical",
            source_type="system",
            model_brand=model,
        )
        assign_incident(session, incident, assignee, actor=owner)
        escalate_incident(session, incident, actor=owner)

        assert incident in critical_incidents(session)
        assert incident.status == "investigating"
        assert incident.escalation_level == 1
        assert incident.escalation_history

        resolve_incident(session, incident, actor=owner, resolution_notes="Rotated proxy pool.")

        assert incident.status == "resolved"
        assert incident.resolved_by_user_id == owner.id
        assert session.query(AuditLog).filter_by(action="incident.created").count() == 1
        assert session.query(AuditLog).filter_by(action="incident.assigned").count() == 1
        assert session.query(AuditLog).filter_by(action="incident.escalated").count() == 1
        assert session.query(AuditLog).filter_by(action="incident.resolved").count() == 1


def test_incident_permission_restriction_records_audit() -> None:
    with session_scope() as session:
        setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        viewer = _active_user(session, 23, "Viewer")
        assign_role_to_user(session, viewer, RoleName.VIEWER)

        with pytest.raises(PermissionError):
            create_incident(session, actor=viewer, title="Unauthorized incident")

        denied = session.query(AuditLog).filter_by(action="access.denied", resource_type="incident").one()
        assert denied.details["permission"] == "manage_incidents"


def test_dashboard_daily_briefing_and_accountability_counts() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        assignee = _active_user(session, 24, "Accountable User")
        model = create_model_brand(session, actor=owner, display_name="Briefing Model")
        account = create_account(session, model_brand=model, platform="instagram", username="briefing", actor=owner)
        task = create_task(
            session,
            actor=owner,
            title="Finish daily check",
            model_brand=model,
            account=account,
            assigned_to=assignee,
        )
        complete_task(session, task, actor=owner)
        create_task(
            session,
            actor=owner,
            title="Past due follow-up",
            assigned_to=assignee,
            due_at=datetime.now(UTC) - timedelta(days=1),
        )
        create_incident(
            session,
            actor=owner,
            title="Critical system incident",
            severity="critical",
            source_type="system",
            assigned_to=assignee,
        )

        stats = dashboard_stats(session)
        executive = executive_dashboard(session)
        briefing = generate_daily_briefing(session, actor=owner)
        accountability = generate_accountability_report(session, actor=owner)

        assert stats.open_tasks == 1
        assert stats.completed_tasks_today == 1
        assert stats.open_incidents == 1
        assert stats.critical_incidents == 1
        assert executive["completed_tasks_today"] == 1
        assert briefing["tasks_completed_today"] == 1
        assert briefing["critical_incidents"] == 1
        assert accountability["users"]
        row = next(row for row in accountability["users"] if row["user_id"] == assignee.id)
        assert row["completed_today"] == 1
        assert row["overdue_tasks"] == 1
        assert row["open_incidents_assigned"] == 1
        assert session.query(AuditLog).filter_by(action="briefing.generated").count() == 1
        assert session.query(AuditLog).filter_by(action="accountability.generated").count() == 1
        assert session.query(AuditLog).filter_by(action="task.overdue").count() == 1


def test_operations_models_have_required_columns() -> None:
    assert "priority" in Task.__table__.columns
    assert "due_at" in Task.__table__.columns
    assert "source_type" in Incident.__table__.columns
    assert "escalation_history" in Incident.__table__.columns
