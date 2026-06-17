from datetime import UTC, datetime

import pytest

from app.bot.navigation import screen_for_page
from app.models.audit import AuditLog
from app.models.event_log import EventLog
from app.models.learning import LearningEvent, OutcomeMemory
from app.models.model_brand import ModelBrand
from app.models.opportunity import CommentStrategy, CreatorWatch, OpportunityResult, PostWatch
from app.models.reporting import NotificationDeliveryAttempt
from app.models.task import Task
from app.services.auth import USER_STATUS_ACTIVE, assign_role_to_user, get_or_create_telegram_user, setup_owner_if_needed
from app.services.notifications import create_notification_target
from app.services.opportunities import (
    activation_score,
    assign_creator_watch,
    chatter_workspace,
    comment_strategies_for_opportunity,
    create_creator_watch,
    create_manual_opportunity,
    create_post_watch,
    help_copilot_answer,
    manager_opportunity_view,
    opportunity_learning_overview,
    opportunity_queue_summary,
    record_opportunity_result,
    route_opportunity_notification,
    score_opportunity,
    set_creator_watch_active,
    team_activation_summary,
)
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.tasks import complete_task, create_task
from app.services.team_experience import get_or_create_onboarding_checklist, role_home_items, update_onboarding_checklist
from app.services.team_operations import set_availability
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Owner")


def _active_user(session, telegram_id: int, display_name: str):
    user = get_or_create_telegram_user(session, telegram_user_id=telegram_id, display_name=display_name)
    user.status = USER_STATUS_ACTIVE
    user.is_active = True
    return user


def test_creator_watch_creation_assignment_and_status_audits() -> None:
    with session_scope() as session:
        owner = _owner(session)
        chatter = _active_user(session, 1701, "Creator Chatter")
        assign_role_to_user(session, chatter, RoleName.CHATTER, actor=owner)
        model = ModelBrand(display_name="Creator Model", stage_name="CM", status="active")
        session.add(model)
        session.flush()

        creator = create_creator_watch(
            session,
            actor=owner,
            platform="x",
            creator_name="Important Creator",
            creator_username="important_creator",
            niche="fitness",
            priority="high",
        )
        assign_creator_watch(session, creator, actor=owner, chatter=chatter, model_brand=model, team_id=10)
        set_creator_watch_active(session, creator, actor=owner, is_active=False, action="creator_watch.archived")

        assert session.query(CreatorWatch).count() == 1
        assert creator.assigned_chatter_id == chatter.id
        assert creator.assigned_model_id == model.id
        assert creator.assigned_team_id == 10
        assert creator.is_active is False
        assert session.query(AuditLog).filter(AuditLog.action.in_(("creator_watch.created", "creator_watch.archived"))).count() >= 2
        assert session.query(EventLog).filter(EventLog.event_type.like("creator_watch.%")).count() >= 2


def test_creator_watch_management_requires_manager_permission() -> None:
    with session_scope() as session:
        owner = _owner(session)
        chatter = _active_user(session, 1702, "No Manage Chatter")
        assign_role_to_user(session, chatter, RoleName.CHATTER, actor=owner)

        with pytest.raises(PermissionError):
            create_creator_watch(
                session,
                actor=chatter,
                platform="x",
                creator_name="Blocked",
                creator_username="blocked",
            )

        assert session.query(AuditLog).filter_by(action="access.denied", resource_type="opportunity").count() == 1


def test_post_watch_and_opportunity_queue_command_center() -> None:
    with session_scope() as session:
        owner = _owner(session)
        model = ModelBrand(display_name="Post Model", stage_name="PM", status="active")
        session.add(model)
        session.flush()
        post = create_post_watch(
            session,
            actor=owner,
            model_brand=model,
            platform="instagram",
            post_reference="ig-post-1",
            post_type="reel",
            status="attention_needed",
        )
        opportunity = create_manual_opportunity(
            session,
            actor=owner,
            title="High priority review",
            platform="instagram",
            niche="fitness",
            model_brand_id=model.id,
            reason="Needs manager review.",
            suggested_angle="educational",
        )
        score_opportunity(session, opportunity, actor=owner, score=85)

        queue = opportunity_queue_summary(session)
        manager = manager_opportunity_view(session)
        command = screen_for_page(
            "opportunities:command",
            PermissionPrincipal(telegram_id=owner.telegram_id, role=RoleName.OWNER),
            session=session,
            user=owner,
        )
        posts = screen_for_page(
            "opportunities:posts:attention",
            PermissionPrincipal(telegram_id=owner.telegram_id, role=RoleName.OWNER),
            session=session,
            user=owner,
        )

        assert post.status == "attention_needed"
        assert session.query(PostWatch).count() == 1
        assert queue["counts"]["reviewing"] == 1
        assert queue["high_priority"][0].id == opportunity.id
        assert manager["high_priority"][0].id == opportunity.id
        assert "Opportunity Command Center" in command.text
        assert "Attention Needed" in posts.text


def test_comment_strategy_scoring_is_human_review_only() -> None:
    with session_scope() as session:
        owner = _owner(session)
        opportunity = create_manual_opportunity(
            session,
            actor=owner,
            title="Strategy Opportunity",
            platform="x",
            niche="wellness",
            reason="Good audience overlap.",
            suggested_angle="curiosity",
        )
        score_opportunity(session, opportunity, actor=owner, score=75)

        strategies = comment_strategies_for_opportunity(session, opportunity, actor=owner)
        screen = screen_for_page(
            f"opportunity:{opportunity.id}:strategies",
            PermissionPrincipal(telegram_id=owner.telegram_id, role=RoleName.OWNER),
            session=session,
            user=owner,
        )

        assert len(strategies) == 10
        assert all(0 <= item.risk_score <= 100 for item in strategies)
        assert session.query(CommentStrategy).count() == 10
        assert "not automated comments" in screen.text
        assert "post automatically" not in screen.text.lower()


def test_chatter_workspace_help_copilot_and_activation_score() -> None:
    with session_scope() as session:
        owner = _owner(session)
        chatter = _active_user(session, 1703, "Activated Chatter")
        assign_role_to_user(session, chatter, RoleName.CHATTER, actor=owner)
        set_availability(session, chatter, actor=chatter, status="on_shift")
        checklist = get_or_create_onboarding_checklist(session, chatter)
        assert checklist.readiness_score < 100
        for field in ("onboarded", "help_center_viewed"):
            update_onboarding_checklist(session, chatter, actor=owner, field=field)
        task = create_task(session, actor=owner, title="Complete creator review", assigned_to=chatter, due_at=datetime.now(UTC))
        complete_task(session, task, actor=owner)
        opportunity = create_manual_opportunity(session, actor=owner, title="Assigned opportunity", suggested_angle="question")
        opportunity.assigned_to_user_id = chatter.id
        opportunity.status = "assigned"
        session.flush()
        record_opportunity_result(session, opportunity, actor=chatter, status="posted", clicks=4, conversions=1)

        workspace = chatter_workspace(session, chatter)
        answer = help_copilot_answer(session, chatter, question="How do I complete an opportunity?")
        score = activation_score(session, chatter)
        team = team_activation_summary(session)
        screen = screen_for_page(
            "chatter_workspace",
            PermissionPrincipal(telegram_id=chatter.telegram_id, role=RoleName.CHATTER),
            session=session,
            user=chatter,
        )

        assert "Chatter Workspace" in {label for label, _ in role_home_items(chatter)}
        assert workspace["assigned_opportunities"][0].id == opportunity.id
        assert answer["next_action"] == "my_opportunities"
        assert score["score"] >= 80
        assert any(item["user"].id == chatter.id for item in team)
        assert "Recommended Next Action" in screen.text


def test_opportunity_results_feed_learning_memory_and_rejected_status() -> None:
    with session_scope() as session:
        owner = _owner(session)
        opportunity = create_manual_opportunity(session, actor=owner, title="Rejected opportunity", niche="fashion")

        result = record_opportunity_result(session, opportunity, actor=owner, status="rejected", notes="Not a fit.")
        overview = opportunity_learning_overview(session)

        assert result.status == "rejected"
        assert opportunity.status == "rejected"
        assert session.query(OpportunityResult).count() == 1
        assert session.query(LearningEvent).filter_by(event_type="opportunity.rejected").count() == 1
        assert session.query(OutcomeMemory).filter_by(memory_key=f"opportunity_result:opportunity:{opportunity.id}").count() == 1
        assert "weak_sources" in overview


def test_opportunity_notification_routing_records_delivery_attempts() -> None:
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
        create_notification_target(
            session,
            actor=owner,
            name="Owner HQ",
            target_type="telegram_user",
            purpose="owner",
            telegram_chat_id="654321",
        )

        attempts = route_opportunity_notification(
            session,
            actor=owner,
            event_type="opportunity.high_priority",
            title="High Priority Opportunity",
            body="Human review needed.",
            severity="warning",
        )

        assert len(attempts) == 2
        assert session.query(NotificationDeliveryAttempt).count() == 2
        assert all(attempt.status == "pending" for attempt in attempts)


def test_sprint17_telegram_pages_do_not_crash() -> None:
    with session_scope() as session:
        owner = _owner(session)
        opportunity = create_manual_opportunity(session, actor=owner, title="Nav Opportunity")
        principal = PermissionPrincipal(telegram_id=owner.telegram_id, role=RoleName.OWNER)

        pages = [
            "opportunities",
            "opportunities:command",
            "opportunities:creators",
            "opportunities:posts",
            f"opportunity:{opportunity.id}",
            f"opportunity:{opportunity.id}:strategies",
            "help_copilot",
            "help_copilot:opportunity",
            "team_activation",
        ]
        texts = [screen_for_page(page, principal, session=session, user=owner).text for page in pages]

        assert any("Creator Watchlist" in text for text in texts)
        assert any("Suggested Strategies" in text for text in texts)
        assert any("Help Copilot" in text for text in texts)
        assert any("Team Activation" in text for text in texts)
