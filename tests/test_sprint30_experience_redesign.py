import re

from app.bot.screens import (
    render_assistant_next_page,
    render_main_menu,
    render_owner_advanced_page,
    render_proxies_home,
    render_recommendations_page,
    render_setup_progress_page,
    render_today_priorities_page,
)
from app.models.recommendation import Recommendation
from app.models.reporting import NotificationTarget
from app.services.auth import setup_owner_if_needed
from app.services.model_brands import create_model_brand
from app.services.proxies import create_proxy
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Rex")


def _button_text(screen) -> str:
    return " ".join(button.text for row in screen.reply_markup.inline_keyboard for button in row)


def _assert_no_raw_backend_text(text: str) -> None:
    forbidden = (
        "source_type",
        "entity_id",
        "metadata_json",
        "activation_model_missing_team",
        "status=open",
        "{",
        "}",
    )
    for value in forbidden:
        assert value not in text
    assert re.search(r"\d{4}-\d{2}-\d{2}T", text) is None


def test_owner_home_feels_like_a_product_dashboard() -> None:
    with session_scope() as session:
        owner = _owner(session)
        create_model_brand(session, actor=owner, display_name="New Model 1")

        screen = render_main_menu(session, owner)
        labels = _button_text(screen)

        assert "\U0001f319 Good" in screen.text
        assert "Fortuna Status:" in screen.text
        assert "Production Healthy" in screen.text
        assert "Agency Setup:" in screen.text
        assert "Today\u2019s Focus:" in screen.text
        assert "Estimated Time:" in screen.text
        assert "Continue Setup" in labels
        assert "Today\u2019s Priorities" in labels
        assert "Proxy Vault" in labels
        assert "Advanced" in labels
        assert "Intelligence" not in labels
        assert "Automation" not in labels
        _assert_no_raw_backend_text(screen.text)


def test_today_and_assistant_screens_surface_one_next_move() -> None:
    with session_scope() as session:
        owner = _owner(session)

        today = render_today_priorities_page(session, owner)
        assistant = render_assistant_next_page(session, owner)

        assert "Today's Priorities" in today.text
        assert "Top 5 Actions" in today.text
        assert "Things Fortuna Did" in today.text
        assert "Pending Approvals" in today.text
        assert "Follow-Ups" in today.text
        assert "Recommended Next Action" in today.text
        assert "What Should I Do Next?" in assistant.text
        assert "Fortuna recommends" in assistant.text
        assert "Ready when you are." in assistant.text
        _assert_no_raw_backend_text(today.text)
        _assert_no_raw_backend_text(assistant.text)


def test_setup_progress_groups_real_setup_areas() -> None:
    with session_scope() as session:
        owner = _owner(session)
        create_model_brand(
            session,
            actor=owner,
            display_name="Ashley",
            country="United States",
            timezone="America/New_York",
            primary_platform="instagram",
        )
        session.add(
            NotificationTarget(
                name="Fortuna OS Testing Sandbox",
                target_type="telegram_group",
                telegram_chat_id="***-1234",
                purpose="testing",
                is_active=True,
            )
        )
        session.flush()

        screen = render_setup_progress_page(session, owner)
        labels = _button_text(screen)

        assert "Setup Progress" in screen.text
        assert "Agency Setup:" in screen.text
        for section in ("Model Setup", "Accounts", "Team", "Creators", "Notifications", "Proxy"):
            assert section in screen.text
        assert "Fix Model Setup" in labels
        assert "View" in labels
        _assert_no_raw_backend_text(screen.text)


def test_proxy_vault_home_is_first_class_and_not_backend_like() -> None:
    with session_scope() as session:
        owner = _owner(session)
        create_proxy(
            session,
            actor=owner,
            provider="Olympix Mobile SOCKS5",
            host="host.olympix.io",
            port=1080,
            base_username="customer",
            password="secret-password",
            target_country="United States",
            target_state="Florida",
        )

        screen = render_proxies_home(session)
        labels = _button_text(screen)

        assert "\U0001f6e1 Proxy Vault" in screen.text
        assert "Total Proxies:" in screen.text
        assert "Healthy:" in screen.text
        assert "Needs Attention:" in screen.text
        assert "Missing Accounts:" in screen.text
        assert "Real Checks:" in screen.text
        assert "Add Proxy" in labels
        assert "Accounts Missing Proxy" in labels
        assert "Proxy Assignments" in labels
        assert "Advanced Tools" in labels
        assert "secret-password" not in screen.text
        _assert_no_raw_backend_text(screen.text)


def test_recommendations_are_grouped_with_human_labels() -> None:
    with session_scope() as session:
        owner = _owner(session)
        session.add_all(
            [
                Recommendation(
                    recommendation_type="activation_model_missing_team",
                    title="New Model 1 needs team",
                    description="Assign a manager or chatter so the model can be operated.",
                    severity="warning",
                ),
                Recommendation(
                    recommendation_type="activation_model_missing_accounts",
                    title="New Model 1 needs accounts",
                    description="Accounts connect the model to daily work.",
                    severity="warning",
                ),
                Recommendation(
                    recommendation_type="creator_gap",
                    title="No creators watched",
                    description="Creators give chatters a clear place to look for opportunities.",
                    severity="info",
                ),
                Recommendation(
                    recommendation_type="notification_targets_missing",
                    title="Notification targets missing",
                    description="Register Fortuna groups before routing alerts.",
                    severity="warning",
                ),
            ]
        )
        session.flush()

        screen = render_recommendations_page(session, owner)

        assert "Fortuna Recommendations" in screen.text
        assert "Recommended Next Move:" in screen.text
        assert "\U0001f7e1 Needs Setup" in screen.text
        assert "\U0001f7e1 Growth" in screen.text
        assert "\U0001f535 System" in screen.text
        assert "Why it matters:" in screen.text
        assert "View All:" in screen.text
        _assert_no_raw_backend_text(screen.text)


def test_simple_and_advanced_modes_are_separated() -> None:
    with session_scope() as session:
        owner = _owner(session)

        simple = render_main_menu(session, owner)
        advanced = render_owner_advanced_page()
        simple_labels = _button_text(simple)
        advanced_labels = _button_text(advanced)

        assert "Advanced" in simple_labels
        assert "Intelligence" not in simple_labels
        assert "Automation" not in simple_labels
        assert "Intelligence" in advanced_labels
        assert "Automation" in advanced_labels
        assert "Simple Mode" in advanced_labels
