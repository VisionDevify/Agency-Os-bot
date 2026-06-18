import pytest
from sqlalchemy import select

from app.bot.navigation import screen_for_page
from app.bot.screens import render_agency_activation_page, render_main_menu
from app.models.autonomous_operations import FollowUp, OperationsAction, OperationsWorkflow
from app.models.opportunity import CommentStrategy, CreatorWatch, Opportunity
from app.models.recommendation import Recommendation
from app.services.accounts import create_account
from app.services.auth import (
    USER_STATUS_ACTIVE,
    demote_owner,
    get_or_create_telegram_user,
    owner_count,
    promote_owner,
    setup_owner_if_needed,
)
from app.services.autonomous_operations import run_daily_autonomous_cycle, run_model_autopilot
from app.services.model_brands import create_model_brand, update_model_brand
from app.services.opportunities import create_creator_watch, create_manual_opportunity, help_copilot_answer
from app.services.permissions import PermissionPrincipal
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Owner")


def _active_user(session, telegram_id: int, display_name: str):
    user = get_or_create_telegram_user(session, telegram_user_id=telegram_id, display_name=display_name)
    user.status = USER_STATUS_ACTIVE
    user.is_active = True
    return user


def test_account_created_runs_autopilot_workflow_recommendations_and_followup() -> None:
    with session_scope() as session:
        owner = _owner(session)
        model = create_model_brand(session, actor=owner, display_name="Autopilot Model", stage_name="auto")

        account = create_account(
            session,
            actor=owner,
            model_brand=model,
            platform="instagram",
            username="autopilot_model",
        )

        workflow = session.scalar(
            select(OperationsWorkflow).where(
                OperationsWorkflow.workflow_type == "account_autopilot",
                OperationsWorkflow.source_type == "account",
                OperationsWorkflow.source_id == str(account.id),
            )
        )
        actions = {
            action.action_type: action
            for action in session.scalars(select(OperationsAction).where(OperationsAction.workflow_id == workflow.id))
        }

        assert workflow is not None
        assert workflow.status in {"ready", "blocked"}
        assert actions["assign_proxy"].status == "ready"
        assert actions["complete_auth_setup"].status == "ready"
        assert session.scalar(select(FollowUp).where(FollowUp.source_type == "account", FollowUp.source_id == str(account.id)))
        assert session.scalar(
            select(Recommendation).where(Recommendation.recommendation_type == "account_missing_proxy_autopilot")
        ) is not None


def test_model_autopilot_updates_after_model_completion_changes() -> None:
    with session_scope() as session:
        owner = _owner(session)
        model = create_model_brand(session, actor=owner, display_name="Completion Bot", stage_name="cb")

        update_model_brand(session, model, actor=owner, country="United States", timezone="America/New_York")
        workflow = run_model_autopilot(session, model, actor=owner)
        actions = {
            action.action_type: action.status
            for action in session.scalars(select(OperationsAction).where(OperationsAction.workflow_id == workflow.id))
        }

        assert actions["set_country"] == "completed"
        assert actions["set_timezone"] == "completed"
        assert actions["set_primary_platform"] == "ready"


def test_opportunity_and_creator_autopilots_prepare_next_actions() -> None:
    with session_scope() as session:
        owner = _owner(session)
        creator = create_creator_watch(
            session,
            actor=owner,
            platform="x",
            creator_name="Daily Creator",
            creator_username="daily_creator",
            niche="fitness",
            priority="high",
        )
        opportunity = create_manual_opportunity(
            session,
            actor=owner,
            title="Human-approved opener",
            platform="x",
            niche="fitness",
            priority="high",
        )

        creator_workflow = session.scalar(
            select(OperationsWorkflow).where(OperationsWorkflow.workflow_type == "creator_autopilot")
        )
        opportunity_workflow = session.scalar(
            select(OperationsWorkflow).where(
                OperationsWorkflow.workflow_type == "opportunity_autopilot",
                OperationsWorkflow.source_id == str(opportunity.id),
            )
        )

        assert creator_workflow is not None
        assert session.scalar(select(CreatorWatch).where(CreatorWatch.id == creator.id)) is not None
        assert opportunity_workflow is not None
        assert session.scalar(select(Opportunity).where(Opportunity.id == opportunity.id)).score > 0
        assert session.scalar(select(CommentStrategy).where(CommentStrategy.opportunity_id == opportunity.id)) is not None
        assert session.scalar(
            select(FollowUp).where(FollowUp.source_type == "opportunity", FollowUp.source_id == str(opportunity.id))
        )


def test_daily_cycle_records_safe_autonomous_actions() -> None:
    with session_scope() as session:
        owner = _owner(session)
        workflow = run_daily_autonomous_cycle(session, actor=owner)
        action_types = {
            action.action_type
            for action in session.scalars(select(OperationsAction).where(OperationsAction.workflow_id == workflow.id))
        }

        assert workflow.workflow_type == "daily_autonomous_cycle"
        assert {"readiness_scan", "recommendation_refresh"} <= action_types


def test_owner_management_supports_multiple_owners_and_blocks_final_demotion() -> None:
    with session_scope() as session:
        owner = _owner(session)
        teammate = _active_user(session, 2202, "Second Owner")

        promote_owner(session, teammate, actor=owner)
        assert teammate.is_owner is True
        assert owner_count(session) == 2

        demote_owner(session, teammate, actor=owner)
        assert teammate.is_owner is False
        assert owner_count(session) == 1

        with pytest.raises(PermissionError):
            demote_owner(session, owner, actor=owner)


def test_proxy_subpages_render_cleanly_and_fortuna_branding_appears() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True)

        root = render_main_menu()
        proxy_screen = screen_for_page("proxies:olympix", principal, session=session, user=owner)
        activation_screen = render_agency_activation_page(session)

        assert root.text.startswith("Fortuna OS")
        assert "Olympix Mobile SOCKS5 Wizard" in proxy_screen.text
        assert "password is never shown" in proxy_screen.text
        assert "{" not in proxy_screen.text
        assert "Fortuna Activation" in activation_screen.text
        assert "What Fortuna OS Did Today" in activation_screen.text


def test_help_copilot_uses_live_activation_state_for_next_step() -> None:
    with session_scope() as session:
        owner = _owner(session)
        create_model_brand(session, actor=owner, display_name="Needs Guidance")

        answer = help_copilot_answer(session, owner, question="What is stopping my agency from being ready?")

        assert answer["next_action"] == "agency_activation"
        assert "Fortuna readiness" in answer["answer"]
        assert "main blockers" in answer["answer"]
