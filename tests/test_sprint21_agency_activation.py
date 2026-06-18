from sqlalchemy import func, select

from app.bot.screens import (
    render_account_setup_state_page,
    render_agency_activation_page,
    render_activation_section_page,
    render_model_completion_page,
    render_olympix_proxy_wizard_page,
)
from app.models.account import Account
from app.models.audit import AuditLog
from app.models.event_log import EventLog
from app.models.recommendation import Recommendation
from app.models.task import Task
from app.models.team_rollout import AgencyActivationState
from app.services.agency_activation import (
    account_setup_states,
    build_activation_report,
    run_activation_scan,
)
from app.services.auth import setup_owner_if_needed
from app.services.opportunities import help_copilot_answer
from app.services.setup_wizard import create_setup_model, update_setup_model_profile
from app.services.team_experience import role_home_items
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Owner")


def test_agency_readiness_scoring_detects_setup_gaps() -> None:
    with session_scope() as session:
        owner = _owner(session)
        model = create_setup_model(session, actor=owner, display_name="New Model 1")

        report = build_activation_report(session)
        screen = render_agency_activation_page(session)
        section_screen = render_activation_section_page(session, "models")

        codes = {blocker["code"] for blocker in report["blockers"]}
        assert report["readiness_score"] < 60
        assert "model.missing_country" in codes
        assert "model.missing_timezone" in codes
        assert "model.missing_platform" in codes
        assert "model.missing_accounts" in codes
        assert "model.missing_team" in codes
        assert "model.missing_creators" in codes
        assert "notifications.missing_targets" in codes
        assert "Agency Readiness:" in screen.text
        assert "Top Blockers:" in screen.text
        assert any(
            button.callback_data == f"nav:model:{model.id}:complete"
            for row in section_screen.reply_markup.inline_keyboard
            for button in row
        )


def test_activation_scan_persists_state_recommendations_tasks_and_avoids_duplicates() -> None:
    with session_scope() as session:
        owner = _owner(session)
        create_setup_model(session, actor=owner, display_name="Activation Model")

        state = run_activation_scan(session, actor=owner)
        first_task_count = session.scalar(select(func.count(Task.id)).where(Task.title.like("Setup:%")))

        run_activation_scan(session, actor=owner)
        second_task_count = session.scalar(select(func.count(Task.id)).where(Task.title.like("Setup:%")))

        assert state.readiness_score < 60
        assert session.scalar(select(AgencyActivationState)) is not None
        assert session.scalar(select(Recommendation).where(Recommendation.recommendation_type.like("activation_%"))) is not None
        assert session.scalar(select(EventLog).where(EventLog.event_type == "agency_activation.scanned")) is not None
        assert session.scalar(select(AuditLog).where(AuditLog.action == "agency_activation.scanned")) is not None
        assert first_task_count == second_task_count
        assert first_task_count and first_task_count > 0


def test_model_completion_wizard_and_primary_platform_edit() -> None:
    with session_scope() as session:
        owner = _owner(session)
        model = create_setup_model(session, actor=owner, display_name="Completion Model")

        update_setup_model_profile(session, model, actor=owner, primary_platform="instagram")
        screen = render_model_completion_page(session, model.id)

        assert model.primary_platform == "instagram"
        assert "Model Completion Wizard" in screen.text
        assert "Primary Platform: Done (instagram)" in screen.text
        assert "Edit Primary Platform" in str(screen.reply_markup.inline_keyboard)


def test_account_setup_state_flags_missing_proxy_and_auth() -> None:
    with session_scope() as session:
        owner = _owner(session)
        model = create_setup_model(session, actor=owner, display_name="Account State Model")
        account = Account(
            model_brand_id=model.id,
            platform="instagram",
            username="state_model",
            display_name="State Model",
            status="healthy",
            auth_status="not_connected",
        )
        session.add(account)
        session.flush()

        states = account_setup_states(session)
        screen = render_account_setup_state_page(session)

        assert len(states) == 1
        assert states[0].status == "Needs Proxy"
        assert "Needs proxy" in states[0].checklist
        assert "Auth: not connected" in states[0].checklist
        assert "Account Setup State" in screen.text
        assert "Assign the best available proxy" in screen.text


def test_proxy_wizard_copy_masks_secret_guidance_and_has_no_raw_json() -> None:
    screen = render_olympix_proxy_wizard_page()

    assert "host.olympix.io" in screen.text
    assert "1080" in screen.text
    assert "password is never shown" in screen.text
    assert "{" not in screen.text
    assert "}" not in screen.text


def test_help_copilot_answers_activation_questions_from_live_state() -> None:
    with session_scope() as session:
        owner = _owner(session)
        create_setup_model(session, actor=owner, display_name="Low Readiness Model")

        answer = help_copilot_answer(session, owner, question="What's stopping my agency from being ready?")
        next_answer = help_copilot_answer(session, owner, question="What should I do next?")

        assert answer["next_action"] == "agency_activation"
        assert "Agency readiness" in answer["answer"]
        assert "main blockers" in answer["answer"]
        assert next_answer["next_action"] == "agency_activation"


def test_owner_home_includes_agency_activation() -> None:
    with session_scope() as session:
        owner = _owner(session)
        labels = {label for label, _ in role_home_items(owner)}

        assert "Agency Activation" in labels
