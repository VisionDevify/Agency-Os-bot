from sqlalchemy import select

from app.bot.screens import (
    render_account_list_page,
    render_first_day_plan_page,
    render_help_copilot_page,
    render_manager_setup_qa_page,
    render_model_detail_page,
    render_model_list_page,
    render_setup_summary_page,
)
from app.models.account import Account
from app.models.audit import AuditLog
from app.models.event_log import EventLog
from app.models.model_brand import ModelBrand, ModelBrandMember
from app.models.opportunity import CreatorWatch, Opportunity
from app.models.team_rollout import FirstDayChecklist, SetupWizardState
from app.services.auth import USER_STATUS_ACTIVE, assign_role_to_user, get_or_create_telegram_user, setup_owner_if_needed
from app.services.opportunities import help_copilot_answer
from app.services.permissions import RoleName
from app.services.setup_wizard import (
    add_setup_account,
    add_setup_creator,
    add_setup_opportunity,
    assign_setup_team_member,
    clear_demo_data,
    complete_setup_wizard,
    create_demo_seed,
    create_setup_model,
    first_day_plan,
    manager_setup_qa,
    start_setup_wizard,
    summarize_setup_state,
    update_setup_model_profile,
)
from app.services.team_operations import update_user_localization
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Owner")


def _active_user(session, telegram_id: int, display_name: str):
    user = get_or_create_telegram_user(session, telegram_user_id=telegram_id, display_name=display_name)
    user.status = USER_STATUS_ACTIVE
    user.is_active = True
    return user


def test_setup_wizard_creates_first_model_and_records_audit_event() -> None:
    with session_scope() as session:
        owner = _owner(session)
        state = start_setup_wizard(session, actor=owner)
        model = create_setup_model(
            session,
            actor=owner,
            state=state,
            display_name="Fortuna",
            stage_name="Solstice",
            country="United States",
            timezone="America/New_York",
            notes="Primary brand",
        )

        summary = summarize_setup_state(session, state)
        plan = first_day_plan(session, owner)

        assert model.country == "United States"
        assert model.timezone == "America/New_York"
        assert state.model_brand_id == model.id
        assert state.current_step == "accounts"
        assert "accounts" in summary["missing"]
        assert plan["checklist"].created_first_model is True
        assert session.scalar(select(AuditLog).where(AuditLog.action == "setup.model_created")) is not None
        assert session.scalar(select(EventLog).where(EventLog.event_type == "setup.started")) is not None


def test_model_profile_editing_updates_database_and_detail_screen() -> None:
    with session_scope() as session:
        owner = _owner(session)
        model = create_setup_model(session, actor=owner, display_name="Old Name")

        update_setup_model_profile(
            session,
            model,
            actor=owner,
            display_name="New Name",
            stage_name="New Stage",
            country="Colombia",
            timezone="America/Bogota",
            notes="Updated notes",
            internal_notes="Owner-only note",
        )
        screen = render_model_detail_page(session, model.id)

        assert model.display_name == "New Name"
        assert model.stage_name == "New Stage"
        assert model.country == "Colombia"
        assert model.timezone == "America/Bogota"
        assert model.notes == "Updated notes"
        assert "Country: Colombia" in screen.text
        assert "Timezone: America/Bogota" in screen.text
        assert session.scalar(select(AuditLog).where(AuditLog.action == "model.profile_updated")) is not None


def test_setup_flow_adds_account_team_creator_and_opportunity() -> None:
    with session_scope() as session:
        owner = _owner(session)
        chatter = _active_user(session, 1901, "Chatter One")
        assign_role_to_user(session, chatter, RoleName.CHATTER, actor=owner)
        state = start_setup_wizard(session, actor=owner)
        model = create_setup_model(session, actor=owner, state=state, display_name="Model A")

        account = add_setup_account(
            session,
            actor=owner,
            state=state,
            model=model,
            platform="instagram",
            username="model_a",
            display_name="Model A IG",
        )
        member = assign_setup_team_member(
            session,
            actor=owner,
            state=state,
            model=model,
            target_user=chatter,
            relationship_type="chatter",
        )
        creator = add_setup_creator(
            session,
            actor=owner,
            state=state,
            model=model,
            platform="x",
            username="creator_a",
            display_name="Creator A",
            niche="fitness",
            assigned_chatter_id=chatter.id,
        )
        opportunity = add_setup_opportunity(
            session,
            actor=owner,
            state=state,
            model=model,
            title="Starter opportunity",
            platform="x",
            niche="fitness",
            assigned_to_user_id=chatter.id,
        )
        complete_setup_wizard(session, state, actor=owner)

        assert account.model_brand_id == model.id
        assert member.relationship_type == "chatter"
        assert creator.assigned_model_id == model.id
        assert opportunity.assigned_to_user_id == chatter.id
        assert state.status == "completed"
        assert state.completed_at is not None
        assert session.scalar(select(AuditLog).where(AuditLog.action == "setup.account_added")) is not None
        assert session.scalar(select(AuditLog).where(AuditLog.action == "setup.team_assigned")) is not None
        assert session.scalar(select(AuditLog).where(AuditLog.action == "setup.creator_added")) is not None
        assert session.scalar(select(AuditLog).where(AuditLog.action == "setup.opportunity_created")) is not None
        assert session.scalar(select(EventLog).where(EventLog.event_type == "setup.completed")) is not None


def test_first_day_plan_and_manager_qa_show_actionable_setup_gaps() -> None:
    with session_scope() as session:
        owner = _owner(session)
        pending = get_or_create_telegram_user(session, telegram_user_id=1902, display_name="Pending Teammate")
        model = create_setup_model(session, actor=owner, display_name="Needs Team")
        add_setup_account(session, actor=owner, model=model, platform="x", username="needs_team")
        update_user_localization(session, owner, actor=owner, timezone="America/New_York")

        plan = first_day_plan(session, owner)
        qa = manager_setup_qa(session)
        first_day_screen = render_first_day_plan_page(session, owner)
        qa_screen = render_manager_setup_qa_page(session)

        assert plan["completion_score"] > 0
        assert any(item["label"] == "Assign manager" for item in plan["items"])
        assert model in qa["models_without_manager"]
        assert model in qa["models_without_chatters"]
        assert pending in qa["users_pending"]
        assert "First Day Plan" in first_day_screen.text
        assert "Manager Setup / QA" in qa_screen.text


def test_help_copilot_setup_answers_and_empty_state_guidance() -> None:
    with session_scope() as session:
        owner = _owner(session)

        first_model = help_copilot_answer(session, owner, question="How do I create the first model?")
        add_accounts = help_copilot_answer(session, owner, question="How do I add accounts?")
        edit_model = render_help_copilot_page(session, owner, question="edit_model")
        empty_models = render_model_list_page(session)
        empty_accounts = render_account_list_page(session)
        model_accounts = render_account_list_page(
            session,
            accounts=[],
            title="Accounts for Existing Model",
            back_to="model:1",
        )

        assert first_model["next_action"] == "setup:wizard:model"
        assert "Create a model first" in add_accounts["answer"]
        assert "Edit Name" in edit_model.text
        assert "No models yet. Start by creating your first model/brand" in empty_models.text
        assert "No accounts yet. Create a model first" in empty_accounts.text
        assert "Add an account to this model" in model_accounts.text


def test_role_home_visibility_and_setup_summary_are_simple() -> None:
    with session_scope() as session:
        owner = _owner(session)
        manager = _active_user(session, 1903, "Manager")
        chatter = _active_user(session, 1904, "Chatter")
        va = _active_user(session, 1905, "VA")
        assign_role_to_user(session, manager, RoleName.MANAGER, actor=owner)
        assign_role_to_user(session, chatter, RoleName.CHATTER, actor=owner)
        assign_role_to_user(session, va, RoleName.VA, actor=owner)

        from app.services.team_experience import role_home_items

        owner_labels = {label for label, _ in role_home_items(owner)}
        manager_labels = {label for label, _ in role_home_items(manager)}
        chatter_labels = {label for label, _ in role_home_items(chatter)}
        va_labels = {label for label, _ in role_home_items(va)}
        summary = render_setup_summary_page(session, owner)

        assert "Setup Agency" in owner_labels
        assert {"Team", "Models", "Tasks", "Incidents", "Opportunities", "Reports"} <= manager_labels
        assert "Automation" not in manager_labels
        assert {"My Models", "My Opportunities", "My Tasks", "Availability", "Help"} <= chatter_labels
        assert "Proxy Vault" not in chatter_labels
        assert {"My Models", "My Accounts", "My Tasks", "Availability", "Help"} <= va_labels
        assert "Setup Summary" in summary.text


def test_demo_seed_create_and_clear_marks_demo_records_only() -> None:
    with session_scope() as session:
        owner = _owner(session)
        create_demo_seed(session, actor=owner)
        create_setup_model(session, actor=owner, display_name="Real Model")

        assert session.scalar(select(ModelBrand).where(ModelBrand.is_demo.is_(True))) is not None
        assert session.scalar(select(Account).where(Account.is_demo.is_(True))) is not None
        assert session.scalar(select(CreatorWatch).where(CreatorWatch.is_demo.is_(True))) is not None
        assert session.scalar(select(Opportunity).where(Opportunity.is_demo.is_(True))) is not None

        counts = clear_demo_data(session, actor=owner)

        assert counts["models"] == 1
        assert session.scalar(select(ModelBrand).where(ModelBrand.is_demo.is_(True))) is None
        assert session.scalar(select(Account).where(Account.is_demo.is_(True))) is None
        assert session.scalar(select(CreatorWatch).where(CreatorWatch.is_demo.is_(True))) is None
        assert session.scalar(select(Opportunity).where(Opportunity.is_demo.is_(True))) is None
        assert session.scalar(select(ModelBrand).where(ModelBrand.display_name == "Real Model")) is not None
        assert session.scalar(select(AuditLog).where(AuditLog.action == "demo.created")) is not None
        assert session.scalar(select(AuditLog).where(AuditLog.action == "demo.cleared")) is not None
