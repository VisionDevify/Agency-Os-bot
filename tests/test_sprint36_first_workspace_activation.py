from sqlalchemy import select

from app.bot.navigation import screen_for_page
from app.bot.screens import render_first_workspace_flow_page, render_model_completion_page, render_placeholder_cleanup_page
from app.models.autonomous_operations import OperationsAction, OperationsWorkflow
from app.models.opportunity import Opportunity
from app.models.proxy import ProxyHealthCheckResult
from app.services.accounts import create_account
from app.services.agency_activation import account_setup_states, build_activation_report
from app.services.auth import setup_owner_if_needed
from app.services.model_brands import create_model_brand
from app.services.opportunities import create_manual_opportunity
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.production_activation import daily_autopilot_summary, run_daily_autopilot_now
from app.services.proxies import assign_proxy_to_account, create_olympix_proxy_from_string
from app.services.setup_wizard import add_setup_creator, add_setup_opportunity
from tests.utils import session_scope


PROXY_STRING = "host.olympix.io:1080:user_abcdef,type_mobile,session_bf534e5c:super-secret"


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Rex")


def _principal(owner):
    return PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)


def _labels(screen) -> str:
    return " ".join(button.text for row in screen.reply_markup.inline_keyboard for button in row)


def test_first_workspace_uses_linked_records_not_stray_data() -> None:
    with session_scope() as session:
        owner = _owner(session)
        first = create_model_brand(
            session,
            actor=owner,
            display_name="Ashley",
            country="United States",
            timezone="America/New_York",
            primary_platform="instagram",
        )
        other = create_model_brand(
            session,
            actor=owner,
            display_name="Other Model",
            country="United States",
            timezone="America/New_York",
            primary_platform="x",
        )
        create_account(session, model_brand=other, platform="instagram", username="other", actor=owner)
        create_manual_opportunity(session, actor=owner, title="Other Opportunity", model_brand_id=other.id)
        create_olympix_proxy_from_string(session, actor=owner, proxy_string=PROXY_STRING)

        screen = render_first_workspace_flow_page(session, owner)

        assert first.id < other.id
        assert "Complete model profile: Done" in screen.text
        assert "Add first account: Needs Attention" in screen.text
        assert "Create first opportunity: Needs Attention" in screen.text
        assert "Add proxy: Done" in screen.text


def test_first_workspace_progression_through_real_setup_path() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)
        model = create_model_brand(
            session,
            actor=owner,
            display_name="Ashley",
            country="United States",
            timezone="America/New_York",
            primary_platform="instagram",
        )
        account = create_account(session, model_brand=model, platform="instagram", username="ashley", actor=owner)
        proxy = create_olympix_proxy_from_string(session, actor=owner, proxy_string=PROXY_STRING)
        before = build_activation_report(session)["accounts_ready"]
        assign_proxy_to_account(session, proxy, account, actor=owner)
        after = build_activation_report(session)["accounts_ready"]
        add_setup_creator(
            session,
            actor=owner,
            model=model,
            platform="x",
            username="creator_one",
            display_name="Creator One",
            niche="fitness",
        )
        add_setup_opportunity(
            session,
            actor=owner,
            model=model,
            title="Starter Opportunity",
            platform="x",
            niche="fitness",
            assigned_to_user_id=owner.id,
        )

        screen_for_page("first_workspace:skip_team", principal, session=session, user=owner)
        run_daily_autopilot_now(session, actor=owner)
        screen = render_first_workspace_flow_page(session, owner)

        assert after > before
        assert session.scalar(select(ProxyHealthCheckResult).where(ProxyHealthCheckResult.proxy_id == proxy.id)) is not None
        assert "Complete model profile: Done" in screen.text
        assert "Add first account: Done" in screen.text
        assert "Assign proxy to account: Done" in screen.text
        assert "Add team member or skip: Done" in screen.text
        assert "Add creator watch: Done" in screen.text
        assert "Create first opportunity: Done" in screen.text
        assert "Run daily cycle: Done" in screen.text
        assert daily_autopilot_summary(session, owner)["last_result"] == "Daily autopilot completed."
        assert session.scalar(select(OperationsWorkflow).where(OperationsWorkflow.workflow_type == "daily_autonomous_cycle"))
        assert session.scalar(select(OperationsAction).where(OperationsAction.action_type == "intelligence_scan"))


def test_account_creation_triggers_autopilot_and_clear_setup_state() -> None:
    with session_scope() as session:
        owner = _owner(session)
        model = create_model_brand(session, actor=owner, display_name="Account Model")
        account = create_account(session, model_brand=model, platform="instagram", username="account_model", actor=owner)

        state = account_setup_states(session)[0]
        workflow = session.scalar(
            select(OperationsWorkflow).where(
                OperationsWorkflow.workflow_type == "account_autopilot",
                OperationsWorkflow.source_id == str(account.id),
            )
        )

        assert workflow is not None
        assert state.account_id == account.id
        assert "Needs proxy" in state.checklist
        assert "Assign the best available proxy." in state.recommended_actions


def test_placeholder_cleanup_can_complete_link_or_archive_without_deleting() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)
        model = create_model_brand(session, actor=owner, display_name="New Model 1")
        loose = create_manual_opportunity(session, actor=owner, title="Loose Opportunity")

        cleanup = render_placeholder_cleanup_page(session)
        labels = _labels(cleanup)
        assert "Complete Placeholder Model" in labels
        assert "Link First Opportunity" in labels

        completion = screen_for_page("setup:cleanup:complete_placeholder", principal, session=session, user=owner)
        assert "Model Completion Wizard" in completion.text
        assert "Edit Name" in _labels(render_model_completion_page(session, model.id))

        screen_for_page("setup:cleanup:link_unlinked_opportunity", principal, session=session, user=owner)
        session.refresh(loose)
        assert loose.model_brand_id == model.id

        second = create_manual_opportunity(session, actor=owner, title="Archive Later")
        screen_for_page("setup:cleanup:archive_unlinked_opportunity", principal, session=session, user=owner)
        session.refresh(second)
        assert second.status == "archived"
        assert session.get(Opportunity, loose.id) is not None
        assert session.get(Opportunity, second.id) is not None
