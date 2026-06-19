import re

from app.bot.screens import (
    render_assistant_next_page,
    render_help_copilot_page,
    render_main_menu,
    render_setup_progress_page,
)
from app.models.friction import FrictionItem
from app.models.opportunity import Opportunity
from app.services.auth import USER_STATUS_ACTIVE, assign_role_to_user, get_or_create_telegram_user, setup_owner_if_needed
from app.services.friction import create_friction_item
from app.services.model_brands import create_model_brand
from app.services.permissions import RoleName
from app.services.productization import best_next_action, friction_burndown, setup_steps, visible_button_count
from app.services.team_experience import role_home_items
from tests.utils import session_scope


SNAKE_CASE = re.compile(r"\b[a-z]+_[a-z0-9_]+\b")
RAW_TERMS = (
    "source_type",
    "entity_id",
    "metadata_json",
    "callback",
    "renderer",
    "status=open",
)


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Rex")


def _active_user(session, telegram_id: int, display_name: str):
    user = get_or_create_telegram_user(session, telegram_user_id=telegram_id, display_name=display_name)
    user.status = USER_STATUS_ACTIVE
    user.is_active = True
    return user


def _labels(screen) -> list[str]:
    return [button.text for row in screen.reply_markup.inline_keyboard for button in row]


def _assert_product_copy(text: str) -> None:
    assert not SNAKE_CASE.search(text)
    lowered = text.casefold()
    for term in RAW_TERMS:
        assert term not in lowered


def test_role_homes_are_simplified_for_team_mode() -> None:
    with session_scope() as session:
        owner = _owner(session)
        manager = _active_user(session, 4201, "Manager")
        chatter = _active_user(session, 4202, "Chatter")
        va = _active_user(session, 4203, "VA")
        assign_role_to_user(session, manager, RoleName.MANAGER, actor=owner)
        assign_role_to_user(session, chatter, RoleName.CHATTER, actor=owner)
        assign_role_to_user(session, va, RoleName.VA, actor=owner)

        assert role_home_items(manager) == [
            ("Team", "availability:team"),
            ("Assignments", "manager_queue"),
            ("Alerts", "notification_group_pilot"),
            ("Help", "help"),
        ]
        assert role_home_items(chatter) == [
            ("My Work", "my_work"),
            ("Opportunities", "my_opportunities"),
            ("Alerts", "opportunities"),
            ("Help", "help"),
        ]
        assert role_home_items(va) == [
            ("Tasks", "tasks:my"),
            ("Assignments", "my_work"),
            ("Help", "help"),
        ]


def test_home_and_setup_follow_three_layer_product_model() -> None:
    with session_scope() as session:
        owner = _owner(session)
        home = render_main_menu(session, owner)
        setup = render_setup_progress_page(session, owner)
        assistant = render_assistant_next_page(session, owner)

        assert "Status" in home.text
        assert "Next Best Move" in home.text
        assert "Estimated Time" in home.text
        assert "Setup Steps:" in setup.text
        assert "Next Best Move:" in setup.text
        assert "Why:" in setup.text
        assert "Fortuna recommends:" in assistant.text
        assert "Estimated time:" in assistant.text
        assert visible_button_count(_labels(home)) <= 6
        assert visible_button_count(_labels(setup)) <= 6
        _assert_product_copy(home.text)
        _assert_product_copy(setup.text)
        _assert_product_copy(assistant.text)


def test_setup_progression_uses_single_guided_path() -> None:
    with session_scope() as session:
        owner = _owner(session)
        create_model_brand(session, actor=owner, display_name="Ashley")

        steps = setup_steps(session)
        labels = [step.label for step in steps]
        screen = render_setup_progress_page(session, owner)
        buttons = _labels(screen)

        assert labels == [
            "Model",
            "Account",
            "Proxy",
            "Team",
            "Creators",
            "Opportunities",
            "Alerts",
            "Daily Cycle",
        ]
        assert buttons[0].startswith("Continue:")
        assert "More Details" in buttons
        assert sum(1 for label in buttons if label.startswith("Continue:")) == 1


def test_what_should_i_do_next_returns_one_action_for_owner_and_chatter() -> None:
    with session_scope() as session:
        owner = _owner(session)
        chatter = _active_user(session, 4204, "Chatter")
        assign_role_to_user(session, chatter, RoleName.CHATTER, actor=owner)
        opportunity = Opportunity(
            platform="x",
            title="Review creator post",
            niche="fitness",
            status="assigned",
            assigned_to_user_id=chatter.id,
        )
        session.add(opportunity)
        session.flush()

        owner_action = best_next_action(session, owner)
        chatter_action = best_next_action(session, chatter)
        chatter_screen = render_main_menu(session, chatter)

        assert owner_action.title
        assert chatter_action.title == "Review My Opportunities"
        assert chatter_action.action_page == "my_opportunities"
        assert "Next best move:" in chatter_screen.text
        assert "Review My Opportunities" in chatter_screen.text


def test_help_brain_gives_direct_navigation_guidance() -> None:
    with session_scope() as session:
        owner = _owner(session)

        next_screen = render_help_copilot_page(session, owner, question="next")
        explain_screen = render_help_copilot_page(session, owner, question="where")

        assert "Your next best move is" in next_screen.text
        assert "Next Button" in next_screen.text
        assert "one path" in explain_screen.text or "What Should I Do Next" in explain_screen.text
        assert visible_button_count(_labels(render_help_copilot_page(session, owner))) <= 6


def test_friction_burndown_prioritizes_high_medium_low() -> None:
    with session_scope() as session:
        create_friction_item(
            session,
            screen="Proxy Vault",
            issue="Owner could not find paste flow.",
            severity="high",
            fix_recommendation="Make Paste Proxy primary.",
        )
        create_friction_item(
            session,
            screen="Help",
            issue="Too many help options.",
            severity="medium",
            fix_recommendation="Reduce visible prompts.",
        )
        create_friction_item(
            session,
            screen="Today",
            issue="Minor copy polish.",
            severity="low",
            fix_recommendation="Simplify wording.",
        )

        grouped = friction_burndown(session)

        assert grouped["high"][0].screen == "Proxy Vault"
        assert grouped["medium"][0].screen == "Help"
        assert grouped["low"][0].screen == "Today"
        assert session.query(FrictionItem).count() == 3
