from datetime import UTC, datetime
import re

from app.bot.screens import (
    render_account_detail_page,
    render_assistant_next_page,
    render_main_menu,
    render_olympix_proxy_wizard_page,
    render_production_observability_page,
    render_proxies_home,
    render_proxy_detail_page,
    render_recommendations_page,
    render_setup_progress_page,
    render_start_here_page,
    render_today_priorities_page,
)
from app.models.recommendation import Recommendation
from app.services.accounts import create_account
from app.services.auth import setup_owner_if_needed
from app.services.crypto import decrypt_secret
from app.services.help_brain import help_brain_answer
from app.services.model_brands import create_model_brand
from app.services.proxies import create_proxy
from app.services.team_operations import format_user_datetime
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Rex")


def _button_text(screen) -> str:
    return " ".join(
        button.text
        for row in screen.reply_markup.inline_keyboard
        for button in row
    )


def test_owner_home_is_simple_and_advanced_menu_exists() -> None:
    with session_scope() as session:
        owner = _owner(session)
        screen = render_main_menu(session, owner)
        labels = _button_text(screen)

        assert "Status" in screen.text
        assert "Today\u2019s Focus:" in screen.text
        assert "Continue" in labels
        assert "Today\u2019s Priorities" in labels
        assert "Proxy Vault" in labels
        assert "More" in labels
        assert "Automation" not in labels

        start = render_start_here_page(session, owner)
        assert "Top Setup Steps" in start.text
        assert "Continue Setup" in _button_text(start)

        today = render_today_priorities_page(session, owner)
        assert "Today's Priorities" in today.text
        assert "Things Fortuna Did" in today.text

        setup = render_setup_progress_page(session, owner)
        assert "Setup" in setup.text
        assert "Model Setup" in setup.text

        assistant = render_assistant_next_page(session, owner)
        assert "What Should I Do Next?" in assistant.text
        assert "Fortuna recommends" in assistant.text


def test_recommendations_are_grouped_and_hide_raw_types() -> None:
    with session_scope() as session:
        owner = _owner(session)
        session.add(
            Recommendation(
                recommendation_type="activation_model_missing_team",
                title="New Model 1 needs team",
                description="Assign a manager or chatter so the model can be operated.",
                severity="warning",
                entity_type="model_brand",
                entity_id="1",
            )
        )
        session.add(
            Recommendation(
                recommendation_type="activation_notification_targets_missing",
                title="Notification targets missing",
                description="Register Fortuna groups before routing alerts.",
                severity="warning",
            )
        )
        session.flush()

        screen = render_recommendations_page(session, owner)

        assert "Start Here" in screen.text
        assert "Why" in screen.text
        assert "Later" in screen.text
        assert "activation_model_missing_team" not in screen.text
        assert "Type:" not in screen.text


def test_user_datetime_defaults_to_new_york_style() -> None:
    with session_scope() as session:
        owner = _owner(session)
        owner.timezone = "UTC"
        rendered = format_user_datetime(owner, datetime(2026, 6, 18, 10, 13, tzinfo=UTC))

        assert rendered == "Jun 18, 6:13 AM EST"
        assert re.search(r"\d{4}-\d{2}-\d{2}T", rendered) is None


def test_proxy_vault_and_detail_are_clean_and_secret_safe() -> None:
    with session_scope() as session:
        owner = _owner(session)
        proxy = create_proxy(
            session,
            actor=owner,
            provider="Olympix Mobile SOCKS5",
            host="host.olympix.io",
            port=1080,
            base_username="customer",
            password="super-secret",
            target_country="United States",
            target_state="Florida",
            target_city="Miami",
        )
        assert decrypt_secret(proxy.encrypted_password) == "super-secret"

        home = render_proxies_home(session)
        detail = render_proxy_detail_page(session, proxy.id)

        assert "Status" in home.text
        assert "What Needs Attention" in home.text
        assert "View Proxies" in _button_text(home)
        assert "More Details" in _button_text(home)
        assert "Olympix Mobile Proxy" in detail.text
        assert "Connection:" in detail.text
        assert "Real Check: Off" in detail.text
        assert "super-secret" not in detail.text
        assert "metadata_json" not in detail.text
        assert "{" not in detail.text
        assert re.search(r"\d{4}-\d{2}-\d{2}T", detail.text) is None


def test_olympix_wizard_and_account_missing_proxy_guidance() -> None:
    with session_scope() as session:
        owner = _owner(session)
        model = create_model_brand(session, actor=owner, display_name="Model")
        account = create_account(session, model_brand=model, platform="instagram", username="creator", actor=owner)

        wizard = render_olympix_proxy_wizard_page()
        detail = render_account_detail_page(session, account.id)

        assert "Step 1: Host" in wizard.text
        assert "Paste the part before ,session_" in wizard.text
        assert "Password is encrypted and never shown again." in wizard.text
        assert "This account needs a proxy." in detail.text
        assert "Add your first proxy" in detail.text


def test_help_brain_new_ui_answers_and_observability_time() -> None:
    with session_scope() as session:
        owner = _owner(session)
        crowded = help_brain_answer(session, owner, question="Why does this screen look crowded?")
        simulated = help_brain_answer(session, owner, question="What does simulated proxy check mean?")
        advanced = help_brain_answer(session, owner, question="How do I switch to Advanced Mode?")

        assert "Simple Mode" in crowded.answer
        assert "Real checks stay off" in simulated.answer
        assert advanced.next_action == "owner_advanced"

        observability = render_production_observability_page(session, owner)
        assert "Production Observability" in observability.text
        assert re.search(r"\d{4}-\d{2}-\d{2}T", observability.text) is None
