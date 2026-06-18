import re

from app.bot.navigation import screen_for_page
from app.bot.screens import (
    render_first_workspace_flow_page,
    render_placeholder_cleanup_page,
    render_proxies_home,
)
from app.services.accounts import create_account
from app.services.auth import setup_owner_if_needed
from app.services.help_brain import help_brain_answer
from app.services.model_brands import create_model_brand
from app.services.opportunities import create_manual_opportunity
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.proxies import create_olympix_proxy_from_string
from tests.utils import session_scope


PROXY_STRING = "host.olympix.io:1080:user_abcdef,type_mobile,session_bf534e5c:super-secret"


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Rex")


def _principal(owner):
    return PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)


def _button_labels(screen) -> str:
    return " ".join(button.text for row in screen.reply_markup.inline_keyboard for button in row)


def _assert_clean(text: str) -> None:
    forbidden = (
        "metadata_json",
        "source_type",
        "entity_id",
        "activation_model_missing_team",
        "encrypted_password",
        "super-secret",
        "Traceback",
        "{",
        "}",
    )
    for value in forbidden:
        assert value not in text
    assert re.search(r"\d{4}-\d{2}-\d{2}T", text) is None


def test_first_workspace_flow_guides_zero_data_owner() -> None:
    with session_scope() as session:
        owner = _owner(session)

        screen = render_first_workspace_flow_page(session, owner)
        labels = _button_labels(screen)

        assert "First Workspace Guide" in screen.text
        assert "Complete model profile: Needs Attention" in screen.text
        assert "Add first account: Waiting" in screen.text
        assert "Add proxy: Needs Attention" in screen.text
        assert "Next best action:" in screen.text
        assert "Complete model profile" in labels
        assert "Add proxy" in labels
        assert "Run Daily Cycle" in labels
        _assert_clean(screen.text)


def test_first_workspace_flow_updates_from_live_data() -> None:
    with session_scope() as session:
        owner = _owner(session)
        model = create_model_brand(
            session,
            actor=owner,
            display_name="Ashley",
            country="United States",
            timezone="America/New_York",
            primary_platform="instagram",
        )
        create_account(session, model_brand=model, platform="instagram", username="ashley", actor=owner)
        create_olympix_proxy_from_string(session, actor=owner, proxy_string=PROXY_STRING)

        screen = render_first_workspace_flow_page(session, owner)

        assert "Complete model profile: Done" in screen.text
        assert "Add first account: Done" in screen.text
        assert "Add proxy: Done" in screen.text
        assert "Assign proxy to account: Needs Attention" in screen.text
        _assert_clean(screen.text)


def test_proxy_vault_empty_state_points_to_one_paste_import() -> None:
    with session_scope() as session:
        _owner(session)
        screen = render_proxies_home(session)
        labels = _button_labels(screen)

        assert "Paste your Olympix proxy string to begin." in screen.text
        assert "Next best move: Add your first proxy." in screen.text
        assert "Paste Olympix Proxy String" in labels
        _assert_clean(screen.text)


def test_placeholder_cleanup_archives_only_safe_starter_records() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)
        model = create_model_brand(session, actor=owner, display_name="New Model 1")
        real_model = create_model_brand(session, actor=owner, display_name="Real Model")
        opportunity = create_manual_opportunity(session, actor=owner, title="Manual Opportunity 1")

        before = render_placeholder_cleanup_page(session)
        assert "Model: New Model 1" in before.text
        assert "Opportunity: Manual Opportunity 1" in before.text

        screen_for_page("setup:cleanup:archive_placeholders", principal, session=session, user=owner)
        session.refresh(model)
        session.refresh(real_model)
        session.refresh(opportunity)

        assert model.status == "archived"
        assert opportunity.status == "archived"
        assert real_model.status != "archived"


def test_help_brain_navigates_from_live_product_state() -> None:
    with session_scope() as session:
        owner = _owner(session)
        create_model_brand(session, actor=owner, display_name="New Model 1")

        next_action = help_brain_answer(session, owner, question="What is safe to do next?")
        proxy_where = help_brain_answer(session, owner, question="Where is Proxy Vault?")
        postgres = help_brain_answer(session, owner, question="Why do I need Postgres?")
        broken = help_brain_answer(session, owner, question="Why is this broken?")

        assert "safest next move" in next_action.answer
        assert next_action.next_action != "help"
        assert proxy_where.next_action == "proxies"
        assert "Owner Home" in proxy_where.answer
        assert "durable production database" in postgres.answer
        assert postgres.next_action == "production_observability"
        assert "/integrity" in broken.answer
        assert broken.next_action == "production_observability"
        _assert_clean("\n".join([next_action.answer, proxy_where.answer, postgres.answer, broken.answer]))


def test_core_product_callbacks_render_useful_non_static_pages() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)
        model = create_model_brand(session, actor=owner, display_name="New Model 1")
        account = create_account(session, model_brand=model, platform="instagram", username="ashley", actor=owner)
        proxy = create_olympix_proxy_from_string(session, actor=owner, proxy_string=PROXY_STRING)
        pages = [
            "menu",
            "start_here",
            "first_workspace",
            "setup_progress",
            "setup:wizard:start",
            "agency_activation",
            "models",
            f"model:{model.id}:complete",
            "accounts",
            f"account:{account.id}",
            "proxies",
            "proxies:add",
            "proxies:olympix:paste",
            "proxies:missing",
            f"proxy:{proxy.id}",
            f"proxy:{proxy.id}:advanced",
            f"proxy:{proxy.id}:disable",
            f"proxy:{proxy.id}:reactivate",
            "opportunities",
            "help_copilot:safe_next",
            "settings",
            "production_observability",
        ]

        for page in pages:
            screen = screen_for_page(page, principal, session=session, user=owner)
            assert screen.text.strip()
            assert screen.reply_markup is not None
            assert "Management tools will appear here" not in screen.text
            _assert_clean(screen.text)
