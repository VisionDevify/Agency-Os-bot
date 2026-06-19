from app.bot.navigation import screen_for_page
from app.bot.screens import render_creator_post_alert_detail_page, render_own_post_alert_detail_page
from app.models.event_log import EventLog
from app.models.learning import LearningEvent
from app.models.model_brand import ModelBrand
from app.models.opportunity import CommentStrategy, CreatorPostAlert, Opportunity, OwnPostAlert
from app.models.reporting import NotificationDeliveryAttempt
from app.models.task import Task
from app.services.auth import USER_STATUS_ACTIVE, assign_role_to_user, get_or_create_telegram_user, setup_owner_if_needed
from app.services.help_brain import help_brain_answer
from app.services.notifications import active_targets_for_event, create_notification_target, notification_group_setup_status, target_purposes_for_event
from app.services.opportunities import (
    create_creator_post_alert,
    create_creator_watch,
    create_own_post_alert,
    create_post_watch,
)
from app.services.permissions import PermissionPrincipal, RoleName
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Owner")


def _active_user(session, telegram_id: int, display_name: str):
    user = get_or_create_telegram_user(session, telegram_user_id=telegram_id, display_name=display_name, owner_telegram_id=1)
    user.status = USER_STATUS_ACTIVE
    user.is_active = True
    return user


def test_three_group_routing_supports_legacy_aliases() -> None:
    with session_scope() as session:
        owner = _owner(session)
        hq = create_notification_target(
            session,
            actor=owner,
            name="Fortuna HQ",
            target_type="telegram_group",
            purpose="hq",
            telegram_chat_id="-100111",
        )
        ops = create_notification_target(
            session,
            actor=owner,
            name="Fortuna Ops",
            target_type="telegram_group",
            purpose="ops",
            telegram_chat_id="-100222",
        )
        alerts = create_notification_target(
            session,
            actor=owner,
            name="Fortuna Alerts",
            target_type="telegram_group",
            purpose="alerts",
            telegram_chat_id="-100333",
        )
        legacy_ops = create_notification_target(
            session,
            actor=owner,
            name="Legacy Operations",
            target_type="telegram_group",
            purpose="operations",
            telegram_chat_id="-100444",
        )

        assert target_purposes_for_event("creator.post_alert") == ("alerts",)
        assert active_targets_for_event(session, "creator.post_alert") == [alerts]
        assert set(active_targets_for_event(session, "task.assigned")) == {ops, legacy_ops}
        assert hq in active_targets_for_event(session, "incident.created", severity="critical")

        statuses = notification_group_setup_status(session)
        assert [status.purpose for status in statuses] == ["hq", "ops", "alerts"]
        assert all(status.configured for status in statuses)


def test_creator_post_alert_creates_opportunity_strategy_delivery_and_learning() -> None:
    with session_scope() as session:
        owner = _owner(session)
        chatter = _active_user(session, 3801, "Alert Chatter")
        assign_role_to_user(session, chatter, RoleName.CHATTER, actor=owner)
        model = ModelBrand(display_name="Alert Model", stage_name="AM", status="active")
        session.add(model)
        session.flush()
        create_notification_target(
            session,
            actor=owner,
            name="Fortuna Alerts",
            target_type="telegram_group",
            purpose="alerts",
            telegram_chat_id="-100333",
        )
        creator = create_creator_watch(
            session,
            actor=owner,
            platform="x",
            creator_name="Fitness Creator",
            creator_username="fit_creator",
            niche="fitness",
            priority="high",
            assigned_model_id=model.id,
            assigned_chatter_id=chatter.id,
            assigned_group="alerts",
        )

        alert = create_creator_post_alert(
            session,
            creator,
            actor=owner,
            post_reference="https://x.example/fit_creator/status/1",
            notes="fast window",
        )
        screen = render_creator_post_alert_detail_page(session, alert.id)

        opportunity = session.get(Opportunity, alert.opportunity_id)
        assert session.query(CreatorPostAlert).count() == 1
        assert opportunity is not None
        assert opportunity.source_type == "creator_watch"
        assert opportunity.assigned_to_user_id == chatter.id
        assert session.query(CommentStrategy).filter_by(opportunity_id=opportunity.id).count() >= 3
        assert session.query(NotificationDeliveryAttempt).filter_by(event_type="creator.post_alert").count() == 1
        assert session.query(LearningEvent).filter_by(event_type="creator.post_alert_created").count() == 1
        assert "post manually" in screen.text
        assert "password" not in screen.text.lower()
        assert "auto-post" not in screen.text.lower()
        assert session.query(EventLog).filter(EventLog.event_type == "creator.post_alert").count() == 1


def test_own_post_alert_creates_followup_opportunity_and_delivery_attempt() -> None:
    with session_scope() as session:
        owner = _owner(session)
        chatter = _active_user(session, 3802, "Own Post Chatter")
        assign_role_to_user(session, chatter, RoleName.CHATTER, actor=owner)
        model = ModelBrand(display_name="Own Post Model", stage_name="OPM", status="active")
        session.add(model)
        session.flush()
        create_notification_target(
            session,
            actor=owner,
            name="Fortuna Alerts",
            target_type="telegram_group",
            purpose="alerts",
            telegram_chat_id="-100333",
        )
        post = create_post_watch(
            session,
            actor=owner,
            model_brand=model,
            platform="instagram",
            post_reference="https://instagram.example/p/1",
            post_type="reel",
            attention_level="urgent",
            assigned_chatter_id=chatter.id,
            assigned_group="alerts",
        )

        alert = create_own_post_alert(session, post, actor=owner, notes="watch timing")
        screen = render_own_post_alert_detail_page(session, alert.id)

        assert session.query(OwnPostAlert).count() == 1
        assert alert.opportunity_id is not None
        assert alert.follow_up_task_id is not None
        assert session.get(Task, alert.follow_up_task_id).assigned_to_user_id == chatter.id
        assert session.query(NotificationDeliveryAttempt).filter_by(event_type="own_post.alert").count() == 1
        assert session.query(LearningEvent).filter_by(event_type="own_post.alert_created").count() == 1
        assert "platform action manual" in screen.text.lower()
        assert "password" not in screen.text.lower()


def test_alert_callbacks_render_without_dead_ends_or_raw_output() -> None:
    with session_scope() as session:
        owner = _owner(session)
        model = ModelBrand(display_name="Callback Model", stage_name="CB", status="active")
        session.add(model)
        session.flush()
        creator = create_creator_watch(
            session,
            actor=owner,
            platform="x",
            creator_name="Callback Creator",
            creator_username="callback_creator",
            assigned_model_id=model.id,
        )
        post = create_post_watch(
            session,
            actor=owner,
            model_brand=model,
            platform="instagram",
            post_reference="manual-post",
        )
        principal = PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)

        pages = [
            f"creator:{creator.id}:alert",
            f"post:{post.id}:alert",
            "notification_group_setup",
            "notification_group_pilot",
        ]
        for page in pages:
            screen = screen_for_page(page, principal, session=session, user=owner)
            assert screen.text
            assert "{" not in screen.text
            assert "metadata_json" not in screen.text
            assert "password" not in screen.text.lower()


def test_help_brain_explains_creator_alerts_and_simplified_groups() -> None:
    with session_scope() as session:
        owner = _owner(session)
        creator_answer = help_brain_answer(session, owner, question="How do creator alerts work?")
        groups_answer = help_brain_answer(session, owner, question="How do I register notification groups?")

        assert "human review only" in creator_answer.answer.lower()
        assert creator_answer.next_action == "opportunities:creators"
        assert "Fortuna HQ" in groups_answer.answer
        assert "Fortuna Ops" in groups_answer.answer
        assert "Fortuna Alerts" in groups_answer.answer
