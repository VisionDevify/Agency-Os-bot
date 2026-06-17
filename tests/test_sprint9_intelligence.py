from datetime import UTC, datetime, timedelta

import pytest

from app.bot.navigation import screen_for_page
from app.models.audit import AuditLog
from app.models.automation import AutomationSimulationRun
from app.models.event_log import EventLog
from app.models.recommendation import Recommendation
from app.models.system import SystemHeartbeat
from app.services.accounts import create_account
from app.services.auth import USER_STATUS_ACTIVE, assign_role_to_user, get_or_create_telegram_user, setup_owner_if_needed
from app.services.automations import run_proxy_repair_simulation, update_simulation_status
from app.services.heartbeats import record_heartbeat, system_status_summary
from app.services.incidents import create_incident
from app.services.model_brands import create_model_brand
from app.services.notifications import (
    active_targets_for_event,
    create_notification_target,
    mask_target_chat_id,
    test_notification_target as record_notification_target_test,
)
from app.services.operations import executive_dashboard
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.proxies import create_proxy
from app.services.recommendations import generate_recommendations, update_recommendation_status
from app.services.tasks import create_task
from tests.utils import session_scope


def _active_user(session, telegram_id: int, display_name: str):
    user = get_or_create_telegram_user(session, telegram_user_id=telegram_id, display_name=display_name)
    user.status = USER_STATUS_ACTIVE
    user.is_active = True
    return user


def test_notification_target_creation_routing_and_test_timestamp() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        target = create_notification_target(
            session,
            actor=owner,
            name="Owner Alerts",
            target_type="telegram_user",
            purpose="owner",
            telegram_chat_id="123456789",
        )

        assert target.telegram_chat_id != "123456789"
        assert mask_target_chat_id(target) == "12...89"
        assert active_targets_for_event(session, "briefing.generated") == [target]

        record_notification_target_test(session, target, actor=owner)

        assert target.last_tested_at is not None
        assert session.query(EventLog).filter_by(event_type="notification_target.tested").count() == 1


def test_notification_target_management_requires_owner_or_admin() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        manager = _active_user(session, 51, "Manager")
        assign_role_to_user(session, manager, RoleName.MANAGER, actor=owner)

        with pytest.raises(PermissionError):
            create_notification_target(
                session,
                actor=manager,
                name="Ops",
                target_type="telegram_group",
                purpose="operations",
                telegram_chat_id="-1001",
            )

        denied = session.query(AuditLog).filter_by(action="access.denied", resource_type="notification_target").one()
        assert denied.details["permission"] == "owner_or_admin"


def test_proxy_repair_simulation_records_run_without_mutating_proxy() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        proxy = create_proxy(
            session,
            actor=owner,
            provider="provider",
            host="proxy.sim.local",
            port=8020,
            base_username="base",
            password="secret",
        )
        proxy.status = "critical"
        proxy.health_score = 35
        original_suffix = proxy.session_suffix
        original_rotation_count = proxy.rotation_count

        run = run_proxy_repair_simulation(session, actor=owner)

        assert run.status == "simulated"
        assert run.risk_level == "high"
        assert run.would_trigger_count == 1
        assert proxy.session_suffix == original_suffix
        assert proxy.rotation_count == original_rotation_count
        assert session.query(AutomationSimulationRun).count() == 1
        assert session.query(EventLog).filter_by(event_type="automation.simulated").count() == 1


def test_proxy_repair_simulation_medium_risk_branch() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        for index in range(6):
            proxy = create_proxy(
                session,
                actor=owner,
                provider="provider",
                host=f"proxy-medium-{index}.local",
                port=8030 + index,
                base_username="base",
                password="secret",
            )
            proxy.status = "warning"
            proxy.health_score = 65

        run = run_proxy_repair_simulation(session, actor=owner)

        assert run.risk_level == "medium"
        assert run.would_trigger_count == 6


def test_high_risk_simulation_approval_requires_owner() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        manager = _active_user(session, 52, "Automation Manager")
        assign_role_to_user(session, manager, RoleName.MANAGER, actor=owner)
        proxy = create_proxy(
            session,
            actor=owner,
            provider="provider",
            host="proxy.high.local",
            port=8021,
            base_username="base",
            password="secret",
        )
        proxy.status = "critical"
        proxy.health_score = 20
        run = run_proxy_repair_simulation(session, actor=owner)

        with pytest.raises(PermissionError):
            update_simulation_status(session, run, actor=manager, status="approved")

        update_simulation_status(session, run, actor=owner, status="approved")

        assert run.status == "approved"
        assert session.query(AuditLog).filter_by(action="access.denied", resource_type="automation_simulation_run").count() == 1


def test_recommendations_generation_status_changes_and_command_center_metrics() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        model = create_model_brand(session, actor=owner, display_name="Rec Model")
        account = create_account(session, model_brand=model, platform="instagram", username="rec", actor=owner)
        account.auth_status = "needs_login"
        create_task(
            session,
            actor=owner,
            title="Late recommendation",
            due_at=datetime.now(UTC) - timedelta(days=1),
        )
        create_incident(session, actor=owner, title="Critical rec", severity="critical", source_type="system")

        recommendations = generate_recommendations(session, actor=owner)
        dashboard = executive_dashboard(session)
        target = recommendations[0]
        update_recommendation_status(session, target, actor=owner, status="acknowledged")

        assert recommendations
        assert dashboard["top_recommendations"]
        assert dashboard["operational_status_banner"].startswith("🔴")
        assert target.status == "acknowledged"
        assert session.query(Recommendation).count() >= 1
        assert session.query(AuditLog).filter_by(action="recommendation.acknowledged").count() == 1
        assert session.query(EventLog).filter_by(event_type="recommendation.status_changed").count() == 1


def test_heartbeat_updates_and_status_summary() -> None:
    with session_scope() as session:
        record_heartbeat(session, service_name="bot", status="healthy", metadata={"source": "test"})
        record_heartbeat(session, service_name="railway_deployment", status="pending", metadata={"deployment_status": "not_created"})

        summary = system_status_summary(session)

        assert session.query(SystemHeartbeat).filter_by(service_name="bot").one().status == "healthy"
        assert summary["bot_status"] == "healthy"
        assert summary["last_deployment_status"] == "not_created"
        assert session.query(EventLog).filter_by(event_type="heartbeat.status_changed").count() == 2


def test_new_telegram_callbacks_do_not_crash() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1)
        principal = PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)

        for page in (
            "reports:executive",
            "reports:executive:recommendations",
            "automations",
            "automations:simulations",
            "bot_status",
            "notification_targets",
        ):
            screen = screen_for_page(page, principal, session=session, user=owner, chat_id=owner.telegram_id)
            assert screen.text
