from pathlib import Path

import pytest

from app.bot.screens import render_account_list_page, render_help_center_page, render_help_topic_page
from app.services.auth import setup_owner_if_needed
from app.services.setup_wizard import create_setup_model
from app.services.team_experience import team_invite_message, team_invite_packet
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Owner")


def test_account_empty_state_guides_global_and_model_contexts() -> None:
    with session_scope() as session:
        owner = _owner(session)
        model = create_setup_model(session, actor=owner, display_name="First Real Model")

        global_accounts = render_account_list_page(session)
        model_accounts = render_account_list_page(
            session,
            accounts=[],
            title=f"Accounts for {model.display_name}",
            back_to=f"model:{model.id}",
        )

        assert "Create a model first" in global_accounts.text
        assert "Add an account to this model" in model_accounts.text
        assert "Create a model first" not in model_accounts.text


def test_team_invite_packet_generation_is_safe_and_role_specific() -> None:
    packet = team_invite_packet(bot_username="@FortunaSolstice_Bot")

    assert set(packet) == {"chatter", "va", "manager"}
    for role, message in packet.items():
        assert "@FortunaSolstice_Bot" in message
        assert "/start" in message
        assert "language, country, timezone" in message
        assert "Access pending approval" in message
        assert "Do not send passwords or verification codes" in message
        assert role != "" and role in packet
    assert "My Opportunities" in packet["chatter"]
    assert "My Accounts" in packet["va"]
    assert "Team, Models, Tasks" in packet["manager"]


def test_team_invite_message_rejects_unknown_roles() -> None:
    with pytest.raises(ValueError):
        team_invite_message("owner")


def test_help_center_exposes_team_invite_packet_for_owner() -> None:
    with session_scope() as session:
        owner = _owner(session)

        center = render_help_center_page(owner)
        topic = render_help_topic_page("team_invites", owner)
        labels = [button.text for row in center.reply_markup.inline_keyboard for button in row]

        assert "Team Invite Packet" in labels
        assert "Fortuna OS invite for Chatter" in topic.text
        assert "Fortuna OS invite for Manager" in topic.text
        assert "Do not send passwords or verification codes" in topic.text


def test_activation_docs_include_invites_and_manual_notification_groups() -> None:
    invite_doc = Path("docs/team_invite_packet.md").read_text(encoding="utf-8")
    production_doc = Path("docs/production_operations.md").read_text(encoding="utf-8")
    routing_doc = Path("docs/notification_routing.md").read_text(encoding="utf-8")

    assert "Chatter Invite" in invite_doc
    assert "VA Invite" in invite_doc
    assert "Manager Invite" in invite_doc
    assert "Access pending approval" in invite_doc
    assert "Agency OS — HQ" in production_doc
    assert "Agency OS — Testing Sandbox" in production_doc
    assert "Add Current Chat As Target" in routing_doc
    assert "Testing Sandbox -> `testing`" in routing_doc
