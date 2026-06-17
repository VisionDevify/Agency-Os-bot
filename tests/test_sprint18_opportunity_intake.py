from datetime import UTC, datetime, timedelta

from app.bot.navigation import screen_for_page
from app.models.audit import AuditLog
from app.models.event_log import EventLog
from app.models.learning import LearningEvent, OutcomeMemory
from app.models.model_brand import ModelBrand
from app.models.opportunity import CommentStrategy, CreatorWatch, Opportunity, OpportunityResult, PostWatch
from app.models.reporting import NotificationDeliveryAttempt
from app.models.task import Task
from app.services.auth import USER_STATUS_ACTIVE, assign_role_to_user, get_or_create_telegram_user, setup_owner_if_needed
from app.services.notifications import create_notification_target, target_purposes_for_event
from app.services.opportunities import (
    active_users_for_opportunity_assignment,
    assign_creator_watch,
    assign_opportunity,
    assign_post_watch,
    chatter_workspace,
    comment_strategies_for_opportunity,
    create_creator_watch,
    create_manual_opportunity,
    create_opportunity_from_creator,
    create_opportunity_from_post,
    create_post_watch,
    create_task_from_opportunity,
    help_copilot_answer,
    manager_opportunity_view,
    record_opportunity_result,
    regenerate_comment_strategies,
    route_opportunity_notification,
    team_activation_qa,
    update_creator_watch,
    update_post_watch_status,
)
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.team_operations import set_availability
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Owner")


def _active_user(session, telegram_id: int, display_name: str):
    user = get_or_create_telegram_user(session, telegram_user_id=telegram_id, display_name=display_name)
    user.status = USER_STATUS_ACTIVE
    user.is_active = True
    return user


def test_creator_guided_creation_assignment_archive_and_opportunity_conversion() -> None:
    with session_scope() as session:
        owner = _owner(session)
        chatter = _active_user(session, 1801, "Daily Chatter")
        assign_role_to_user(session, chatter, RoleName.CHATTER, actor=owner)
        model = ModelBrand(display_name="Sprint 18 Model", stage_name="S18", status="active")
        session.add(model)
        session.flush()

        creator = create_creator_watch(
            session,
            actor=owner,
            platform="x",
            creator_name="Creator Display",
            display_name="Creator Display",
            creator_username="creator_daily",
            niche="wellness",
            priority="critical",
            notes="Watch daily.",
        )
        assign_creator_watch(session, creator, actor=owner, chatter=chatter, model_brand=model)
        update_creator_watch(session, creator, actor=owner, niche="fitness", priority="high")
        opportunity = create_opportunity_from_creator(session, creator, actor=owner)
        update_creator_watch(session, creator, actor=owner, status="archived")

        assert creator.display_name == "Creator Display"
        assert creator.status == "archived"
        assert creator.is_active is False
        assert opportunity.source_type == "creator_watch"
        assert opportunity.source_reference_id == creator.id
        assert opportunity.assigned_to_user_id == chatter.id
        assert session.query(AuditLog).filter(AuditLog.action.in_(("creator.created", "creator.assigned", "creator.updated"))).count() >= 3
        assert session.query(EventLog).filter(EventLog.event_type.in_(("creator.created", "creator.assigned", "creator.priority_changed"))).count() >= 3


def test_own_post_guided_creation_assignment_and_opportunity_conversion() -> None:
    with session_scope() as session:
        owner = _owner(session)
        chatter = _active_user(session, 1802, "Post Chatter")
        assign_role_to_user(session, chatter, RoleName.CHATTER, actor=owner)
        model = ModelBrand(display_name="Post Brand", stage_name="PB", status="active")
        session.add(model)
        session.flush()

        post = create_post_watch(
            session,
            actor=owner,
            model_brand=model,
            platform="instagram",
            post_reference="https://example.test/post",
            post_type="reel",
            attention_level="urgent",
            notes="Needs fast review.",
        )
        assign_post_watch(session, post, actor=owner, chatter=chatter)
        update_post_watch_status(session, post, actor=owner, status="attention_needed")
        opportunity = create_opportunity_from_post(session, post, actor=owner)

        assert post.assigned_chatter_id == chatter.id
        assert post.attention_level == "urgent"
        assert opportunity.source_type == "own_post"
        assert opportunity.source_reference_id == post.id
        assert opportunity.priority == "critical"
        assert session.query(PostWatch).count() == 1


def test_opportunity_assignment_status_task_and_strategy_v2() -> None:
    with session_scope() as session:
        owner = _owner(session)
        chatter = _active_user(session, 1803, "Strategy Chatter")
        assign_role_to_user(session, chatter, RoleName.CHATTER, actor=owner)
        opportunity = create_manual_opportunity(
            session,
            actor=owner,
            title="Comment with care",
            platform="x",
            niche="fitness",
            priority="high",
            due_at=datetime.now(UTC) + timedelta(hours=2),
        )

        assign_opportunity(session, opportunity, chatter, actor=owner)
        task = create_task_from_opportunity(session, opportunity, actor=owner)
        strategies = comment_strategies_for_opportunity(session, opportunity, actor=owner)
        refreshed = regenerate_comment_strategies(session, opportunity, actor=owner)

        assert opportunity.assigned_at is not None
        assert task.title.startswith("Work opportunity")
        assert task.assigned_to_user_id == chatter.id
        assert len(strategies) == 10
        assert len(refreshed) == 10
        assert all(strategy.sample_comment for strategy in refreshed)
        assert all(strategy.risk_score <= 100 for strategy in refreshed)
        assert session.query(CommentStrategy).count() == 10


def test_result_recording_updates_learning_outcome_memory_and_completion() -> None:
    with session_scope() as session:
        owner = _owner(session)
        opportunity = create_manual_opportunity(session, actor=owner, title="Result opportunity", priority="normal")

        posted = record_opportunity_result(
            session,
            opportunity,
            actor=owner,
            status="posted",
            clicks=8,
            conversions=1,
            reason="Good fit.",
            notes="Posted manually.",
        )

        assert posted.reason == "Good fit."
        assert opportunity.status == "completed"
        assert opportunity.completed_at is not None
        assert session.query(OpportunityResult).count() == 1
        assert session.query(LearningEvent).filter_by(event_type="opportunity.posted").count() == 1
        assert session.query(OutcomeMemory).filter_by(memory_key=f"opportunity_result:opportunity:{opportunity.id}").count() == 1


def test_chatter_workspace_manager_view_help_and_activation_qa() -> None:
    with session_scope() as session:
        owner = _owner(session)
        chatter = _active_user(session, 1804, "Workspace Chatter")
        assign_role_to_user(session, chatter, RoleName.CHATTER, actor=owner)
        set_availability(session, chatter, actor=chatter, status="on_shift")
        opportunity = create_manual_opportunity(session, actor=owner, title="Assigned daily item", priority="high")
        assign_opportunity(session, opportunity, chatter, actor=owner)
        pending = get_or_create_telegram_user(session, telegram_user_id=1805, display_name="Pending Teammate")

        workspace = chatter_workspace(session, chatter)
        manager = manager_opportunity_view(session)
        answer = help_copilot_answer(session, chatter, question="How do I record results?")
        activation = team_activation_qa(session)

        assert workspace["opportunity_tabs"]["new"][0].id == opportunity.id
        assert manager["counts"]["assigned"] >= 1
        assert answer["next_action"] == "my_opportunities"
        assert any(item["user"].id == pending.id and "pending approval" in item["flags"] for item in activation)
        assert active_users_for_opportunity_assignment(session)[0].status == USER_STATUS_ACTIVE


def test_notification_digest_events_and_delivery_attempts() -> None:
    with session_scope() as session:
        owner = _owner(session)
        create_notification_target(
            session,
            actor=owner,
            name="Operations",
            target_type="telegram_group",
            purpose="operations",
            telegram_chat_id="123456",
        )

        attempts = route_opportunity_notification(
            session,
            actor=owner,
            event_type="opportunity.result_recorded",
            title="Result",
            body="Human result recorded.",
        )

        assert "operations" in target_purposes_for_event("creator.created")
        assert "operations" in target_purposes_for_event("post_watch.created")
        assert len(attempts) == 1
        assert session.query(NotificationDeliveryAttempt).count() == 1


def test_sprint18_telegram_pages_do_not_crash() -> None:
    with session_scope() as session:
        owner = _owner(session)
        chatter = _active_user(session, 1806, "Nav Chatter")
        assign_role_to_user(session, chatter, RoleName.CHATTER, actor=owner)
        model = ModelBrand(display_name="Nav Model", stage_name="NM", status="active")
        session.add(model)
        session.flush()
        creator = create_creator_watch(session, actor=owner, platform="x", creator_name="Nav Creator", creator_username="nav")
        post = create_post_watch(session, actor=owner, model_brand=model, platform="x", post_reference="nav-post", post_type="text")
        opportunity = create_manual_opportunity(session, actor=owner, title="Nav Opportunity")
        principal = PermissionPrincipal(telegram_id=owner.telegram_id, role=RoleName.OWNER)

        pages = [
            "opportunities:creators:add",
            "opportunities:creators:add:platform:x",
            "opportunities:add",
            "opportunities:add:source:manual",
            "opportunities:add:source:manual:platform:x",
            "opportunities:posts:add",
            f"creator:{creator.id}",
            f"creator:{creator.id}:priority",
            f"creator:{creator.id}:assign_chatter",
            f"post:{post.id}",
            f"post:{post.id}:assign_chatter",
            f"opportunity:{opportunity.id}:assign",
            f"opportunity:{opportunity.id}:status",
            f"opportunity:{opportunity.id}:record_result",
            f"opportunity:{opportunity.id}:result:posted",
            "help_copilot:add_creator",
            "help_copilot:record_results",
            "team_activation",
        ]
        texts = [screen_for_page(page, principal, session=session, user=owner).text for page in pages]

        assert any("Add Creator" in text for text in texts)
        assert any("Add Opportunity" in text for text in texts)
        assert any("Record Result" in text for text in texts)
        assert any("Team Activation QA" in text for text in texts)
