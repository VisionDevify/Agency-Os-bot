from datetime import UTC, datetime, timedelta

import pytest

from app.bot.navigation import screen_for_page
from app.models.audit import AuditLog
from app.models.automation import AutomationApproval, AutomationRun, AutomationRunStep, AutomationSimulationRun
from app.models.event_log import EventLog
from app.services.auth import USER_STATUS_ACTIVE, assign_role_to_user, get_or_create_telegram_user, setup_owner_if_needed
from app.services.automations import (
    activate_automation_rule,
    approve_automation,
    automation_metrics,
    create_automation_rule,
    create_placeholder_automation_rule,
    latest_rule_approval,
    request_automation_approval,
    rollback_plan_for_rule,
    run_automation_rule,
    seed_builtin_automation_templates,
    simulate_automation_rule,
)
from app.services.incidents import create_incident
from app.services.notifications import create_delivery_attempt, create_notification_target, mark_delivery_failed
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.proxies import create_proxy
from app.services.tasks import create_task
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Owner")


def _active_user(session, telegram_id: int = 99, display_name: str = "Admin"):
    user = get_or_create_telegram_user(session, telegram_user_id=telegram_id, display_name=display_name)
    user.status = USER_STATUS_ACTIVE
    user.is_active = True
    return user


def test_automation_rule_creation_and_rollback_plan() -> None:
    with session_scope() as session:
        owner = _owner(session)

        rule = create_automation_rule(
            session,
            actor=owner,
            name="Proxy Safety Draft",
            automation_type="proxy_safety_draft",
            category="infrastructure",
            trigger_type="manual",
            actions=[{"type": "rotate_proxy_session"}],
            risk_level="high",
            requires_owner_approval=True,
        )
        plan = rollback_plan_for_rule(rule)

        assert rule.status == "draft"
        assert rule.category == "infrastructure"
        assert plan["available"] is True
        assert plan["steps"][0]["rollback"] == "rollback_proxy_session"


def test_builtin_templates_seed_idempotently() -> None:
    with session_scope() as session:
        owner = _owner(session)

        first = seed_builtin_automation_templates(session, actor=owner)
        second = seed_builtin_automation_templates(session, actor=owner)

        assert len(first) == 6
        assert len(second) == 6
        assert {rule.automation_type for rule in second} >= {
            "daily_intelligence_scan",
            "daily_executive_digest",
            "overdue_task_escalation",
            "critical_incident_escalation",
            "proxy_repair_assistant",
            "notification_failure_watch",
        }


def test_simulation_does_not_mutate_proxy() -> None:
    with session_scope() as session:
        owner = _owner(session)
        proxy = create_proxy(
            session,
            actor=owner,
            provider="provider",
            host="proxy.auto.example.com",
            port=8123,
            base_username="base",
            password="secret",
        )
        proxy.status = "critical"
        proxy.health_score = 25
        original_suffix = proxy.session_suffix
        rule = [rule for rule in seed_builtin_automation_templates(session, actor=owner) if rule.automation_type == "proxy_repair_assistant"][0]

        simulation = simulate_automation_rule(session, rule, actor=owner)

        assert simulation.status == "succeeded"
        assert simulation.would_trigger_count == 1
        assert proxy.session_suffix == original_suffix
        assert proxy.rotation_count == 0
        assert session.query(AutomationSimulationRun).count() == 1


def test_high_risk_approval_requires_owner_and_owner_can_approve() -> None:
    with session_scope() as session:
        owner = _owner(session)
        admin = _active_user(session)
        assign_role_to_user(session, admin, RoleName.ADMIN, actor=owner)
        rule = [rule for rule in seed_builtin_automation_templates(session, actor=owner) if rule.automation_type == "proxy_repair_assistant"][0]
        simulate_automation_rule(session, rule, actor=owner)
        approval = request_automation_approval(session, rule, actor=owner)

        with pytest.raises(PermissionError):
            approve_automation(session, approval, actor=admin)

        approve_automation(session, approval, actor=owner)

        assert approval.status == "approved"
        assert rule.status == "approved"
        assert rule.approved_by_user_id == owner.id


def test_expired_simulation_cannot_be_approved() -> None:
    with session_scope() as session:
        owner = _owner(session)
        rule = create_automation_rule(
            session,
            actor=owner,
            name="Expired Simulation Rule",
            automation_type="expired_simulation_rule",
            actions=[{"type": "write_event_log"}],
        )
        simulation = simulate_automation_rule(session, rule, actor=owner)
        approval = request_automation_approval(session, rule, actor=owner)
        simulation.expires_at = datetime.now(UTC) - timedelta(minutes=1)

        with pytest.raises(PermissionError):
            approve_automation(session, approval, actor=owner)


def test_execution_blocked_without_approval() -> None:
    with session_scope() as session:
        owner = _owner(session)
        rule = create_automation_rule(
            session,
            actor=owner,
            name="Blocked Execution",
            automation_type="blocked_execution",
            actions=[{"type": "write_event_log"}],
        )
        simulate_automation_rule(session, rule, actor=owner)
        rule.status = "active"

        with pytest.raises(PermissionError):
            run_automation_rule(session, rule, actor=owner)


def test_run_and_step_records_created_for_success() -> None:
    with session_scope() as session:
        owner = _owner(session)
        rule = create_automation_rule(
            session,
            actor=owner,
            name="Safe Event Writer",
            automation_type="safe_event_writer",
            actions=[{"type": "write_event_log", "event_name": "automation.test.event"}],
        )
        simulate_automation_rule(session, rule, actor=owner)
        approval = request_automation_approval(session, rule, actor=owner)
        approve_automation(session, approval, actor=owner)
        activate_automation_rule(session, rule, actor=owner)

        run = run_automation_rule(session, rule, actor=owner)

        assert run.status == "succeeded"
        assert session.query(AutomationRun).count() == 1
        assert session.query(AutomationRunStep).filter_by(status="succeeded").count() == 1
        assert session.query(EventLog).filter_by(event_type="automation.run.succeeded").count() == 1


def test_action_failure_records_failed_run_and_step() -> None:
    with session_scope() as session:
        owner = _owner(session)
        rule = create_automation_rule(
            session,
            actor=owner,
            name="Failure Capture",
            automation_type="failure_capture",
            actions=[{"type": "fail_action", "message": "expected failure"}],
        )
        simulate_automation_rule(session, rule, actor=owner)
        approval = request_automation_approval(session, rule, actor=owner)
        approve_automation(session, approval, actor=owner)
        activate_automation_rule(session, rule, actor=owner)

        run = run_automation_rule(session, rule, actor=owner)

        assert run.status == "failed"
        assert run.error_message == "expected failure"
        assert session.query(AutomationRunStep).filter_by(status="failed").count() == 1


def test_builtin_automation_simulations_cover_operations_cases() -> None:
    with session_scope() as session:
        owner = _owner(session)
        create_task(
            session,
            actor=owner,
            title="Overdue",
            due_at=datetime.now(UTC) - timedelta(days=1),
        )
        create_incident(session, actor=owner, title="Critical", severity="critical", source_type="system")
        target = create_notification_target(
            session,
            actor=owner,
            name="Testing",
            target_type="telegram_user",
            purpose="testing",
            telegram_chat_id="12345",
        )
        for _ in range(3):
            attempt = create_delivery_attempt(session, target, event_type="test", actor=owner)
            mark_delivery_failed(session, attempt, actor=owner, error_message="network issue")

        rules = seed_builtin_automation_templates(session, actor=owner)
        results = {rule.automation_type: simulate_automation_rule(session, rule, actor=owner) for rule in rules}

        assert results["daily_intelligence_scan"].would_trigger_count == 1
        assert results["daily_executive_digest"].would_trigger_count == 1
        assert results["overdue_task_escalation"].would_trigger_count == 1
        assert results["critical_incident_escalation"].would_trigger_count == 1
        assert results["notification_failure_watch"].would_trigger_count == 1


def test_automation_metrics_and_telegram_callbacks() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)
        seed_builtin_automation_templates(session, actor=owner)

        for page in (
            "automations",
            "automations:rules",
            "automations:templates",
            "automations:simulations",
            "automations:approvals",
            "automations:runs",
            "automations:health",
        ):
            screen = screen_for_page(page, principal, session=session, user=owner, chat_id=owner.telegram_id)
            assert screen.text

        metrics = automation_metrics(session)
        assert metrics["total_rules"] >= 6
        assert metrics["automation_success_rate"] == 100


def test_no_secrets_in_automation_logs_events_or_audits() -> None:
    with session_scope() as session:
        owner = _owner(session)
        rule = create_automation_rule(
            session,
            actor=owner,
            name="Secret Redaction",
            automation_type="secret_redaction",
            trigger_config={"token": "abc123", "nested": {"password": "super-secret"}},
            actions=[{"type": "write_event_log", "event_name": "automation.secret.test", "secret": "raw-action-secret"}],
        )
        simulate_automation_rule(session, rule, actor=owner)
        approval = request_automation_approval(session, rule, actor=owner)
        approve_automation(session, approval, actor=owner)
        activate_automation_rule(session, rule, actor=owner)
        run_automation_rule(session, rule, actor=owner)

        combined = str(rule.trigger_config_json) + str(rule.actions_json)
        combined += "".join(str(log.details) for log in session.query(AuditLog).all())
        combined += "".join(str(event.metadata_json) for event in session.query(EventLog).all())

        assert "abc123" not in combined
        assert "super-secret" not in combined
        assert "raw-action-secret" not in combined
