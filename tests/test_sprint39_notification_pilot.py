from app.bot.navigation import screen_for_page
from app.models.event_log import EventLog
from app.models.learning import LearningEvent
from app.models.opportunity import CreatorPostAlert, Opportunity, OwnPostAlert
from app.models.recommendation import Recommendation
from app.models.reporting import NotificationDeliveryAttempt, NotificationRoutingConfig
from app.services.auth import setup_owner_if_needed
from app.services.notifications import (
    active_targets_for_event,
    create_notification_target,
    notification_routing_mode,
    notification_routing_mode_summary,
    run_notification_purpose_test,
    set_notification_routing_mode,
)
from app.services.opportunities import run_creator_alert_pilot, run_own_post_alert_pilot
from app.services.observability import production_observability_summary
from app.services.permissions import PermissionPrincipal, RoleName
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Owner")


def test_routing_mode_defaults_to_three_groups_and_can_switch_to_two_group() -> None:
    with session_scope() as session:
        owner = _owner(session)
        assert notification_routing_mode(session) == "3_group"

        set_notification_routing_mode(session, actor=owner, mode="2_group")
        config = session.query(NotificationRoutingConfig).one()
        summary = notification_routing_mode_summary(session)

        assert config.mode == "2_group"
        assert summary.combined_ops_alerts is True
        assert summary.label == "2-group mode"
        assert session.query(EventLog).filter_by(event_type="notification.routing_mode_updated").count() == 1


def test_two_group_mode_routes_ops_events_to_alerts_target() -> None:
    with session_scope() as session:
        owner = _owner(session)
        alerts = create_notification_target(
            session,
            actor=owner,
            name="Fortuna Alerts Combined",
            target_type="telegram_group",
            purpose="alerts",
            telegram_chat_id="-1003901",
        )
        create_notification_target(
            session,
            actor=owner,
            name="Fortuna HQ",
            target_type="telegram_group",
            purpose="hq",
            telegram_chat_id="-1003902",
        )
        set_notification_routing_mode(session, actor=owner, mode="2_group")

        assert active_targets_for_event(session, "task.assigned") == [alerts]


def test_register_current_chat_screen_supports_routing_mode_and_missing_targets() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)

        screen = screen_for_page("notification_routing", principal, session=session, user=owner)

        assert "Mode: 3-group mode" in screen.text
        assert "HQ: Not registered yet" in screen.text
        assert "Register Current Chat" in str(screen.reply_markup.model_dump())
        assert "metadata_json" not in screen.text


def test_purpose_test_missing_target_creates_recommendation_without_crashing() -> None:
    with session_scope() as session:
        owner = _owner(session)

        result = run_notification_purpose_test(session, actor=owner, purpose="alerts")

        assert result.skipped == ("Fortuna Alerts: no active target",)
        assert session.query(NotificationDeliveryAttempt).count() == 0
        assert session.query(Recommendation).filter_by(recommendation_type="notification_target_missing_alerts").count() == 1
        assert session.query(EventLog).filter_by(event_type="notification.purpose_test.skipped").count() == 1


def test_purpose_test_with_target_records_safe_simulated_delivery_attempt() -> None:
    with session_scope() as session:
        owner = _owner(session)
        create_notification_target(
            session,
            actor=owner,
            name="Fortuna HQ",
            target_type="telegram_group",
            purpose="hq",
            telegram_chat_id="-1003903",
        )

        result = run_notification_purpose_test(session, actor=owner, purpose="hq")
        attempt = session.query(NotificationDeliveryAttempt).one()

        assert result.would_send == ("Fortuna HQ",)
        assert attempt.status == "skipped"
        assert attempt.event_type == "notification.test.hq"
        assert attempt.metadata_json["simulated"] is True


def test_creator_alert_pilot_creates_demo_pipeline_and_missing_target_recommendation() -> None:
    with session_scope() as session:
        owner = _owner(session)

        result = run_creator_alert_pilot(session, actor=owner)

        assert result["simulated"] is True
        assert session.query(CreatorPostAlert).count() == 1
        assert session.query(Opportunity).count() >= 1
        assert session.query(LearningEvent).filter_by(event_type="creator.post_alert_created").count() == 1
        assert session.query(Recommendation).filter_by(recommendation_type="notification_target_missing_alerts").count() == 1


def test_own_post_alert_pilot_creates_demo_alert_followup_and_learning() -> None:
    with session_scope() as session:
        owner = _owner(session)

        result = run_own_post_alert_pilot(session, actor=owner)

        assert result["simulated"] is True
        assert result["follow_up_task_id"] is not None
        assert session.query(OwnPostAlert).count() == 1
        assert session.query(LearningEvent).filter_by(event_type="own_post.alert_created").count() == 1


def test_observability_exposes_routing_status() -> None:
    with session_scope() as session:
        owner = _owner(session)
        create_notification_target(
            session,
            actor=owner,
            name="Fortuna HQ",
            target_type="telegram_group",
            purpose="hq",
            telegram_chat_id="-1003904",
        )

        summary = production_observability_summary(session)

        assert summary["notification_routing_mode"] == "3_group"
        assert summary["notification_hq_configured"] is True
        assert summary["notification_ops_configured"] is False
        assert summary["notification_alerts_configured"] is False
