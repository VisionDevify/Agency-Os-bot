import re

from sqlalchemy import select

from app.bot.navigation import screen_for_page
from app.bot.screens import (
    render_proxies_home,
    render_proxy_delete_confirm_page,
    render_proxy_list_page,
    render_proxy_manage_page,
    render_proxy_rotation_preview_page,
)
from app.models.proxy import Proxy
from app.services.accounts import create_account
from app.services.auth import setup_owner_if_needed
from app.services.model_brands import create_model_brand
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.proxies import (
    archive_proxy,
    cleanup_placeholder_proxies,
    create_olympix_proxy_from_string,
    create_proxy,
    list_placeholder_proxies,
    list_proxies,
)
from tests.utils import session_scope


PROXY_STRING = "host.olympix.io:1080:user_abcdef,type_mobile,session_bf534e5c:super-secret"


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Rex")


def _principal(owner):
    return PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)


def _button_labels(screen) -> str:
    return " ".join(button.text for row in screen.reply_markup.inline_keyboard for button in row)


def _assert_proxy_screen_clean(text: str) -> None:
    forbidden = (
        "super-secret",
        "encrypted_password",
        "metadata_json",
        "placeholder proxy-1.local",
        "placeholder proxy-2.local",
        "placeholder proxy-3.local",
        "placeholder proxy-4.local",
        "placeholder proxy-5.local",
        "{",
        "}",
        "Traceback",
    )
    for value in forbidden:
        assert value not in text
    assert re.search(r"\d{4}-\d{2}-\d{2}T", text) is None


def _create_placeholder(session, owner, index: int) -> Proxy:
    return create_proxy(
        session,
        actor=owner,
        provider="placeholder",
        host=f"placeholder proxy-{index}.local",
        port=7999 + index,
        base_username=f"proxy_user_{index}",
        password="placeholder-password",
    )


def test_placeholder_proxies_are_hidden_from_normal_proxy_vault() -> None:
    with session_scope() as session:
        owner = _owner(session)
        for index in range(1, 6):
            _create_placeholder(session, owner, index)

        home = render_proxies_home(session)
        listing = render_proxy_list_page(session)

        assert list_proxies(session) == []
        assert "No real proxies saved yet." in home.text
        assert "Paste your Olympix proxy string." in home.text
        assert "Healthy 100/100" not in listing.text
        _assert_proxy_screen_clean(home.text)
        _assert_proxy_screen_clean(listing.text)


def test_placeholder_cleanup_deletes_unassigned_and_archives_assigned() -> None:
    with session_scope() as session:
        owner = _owner(session)
        model = create_model_brand(session, actor=owner, display_name="Proxy Model")
        account = create_account(session, model_brand=model, platform="instagram", username="creator", actor=owner)
        assigned_placeholder = _create_placeholder(session, owner, 1)
        unassigned_placeholder = _create_placeholder(session, owner, 2)
        account.assigned_proxy_id = assigned_placeholder.id
        session.flush()

        result = cleanup_placeholder_proxies(session, actor=owner)
        session.flush()

        assert result["hidden"] == 2
        assert result["archived"] == 1
        assert result["deleted"] == 1
        assert session.get(Proxy, unassigned_placeholder.id) is None
        session.refresh(assigned_placeholder)
        assert assigned_placeholder.metadata_json["archived"] is True
        assert list_proxies(session) == []
        assert list_placeholder_proxies(session, include_archived=False) == []


def test_proxy_manage_archive_delete_and_empty_state_flows() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)
        proxy = create_olympix_proxy_from_string(session, actor=owner, proxy_string=PROXY_STRING)

        manage = render_proxy_manage_page(session, proxy.id)
        labels = _button_labels(manage)

        assert "Manage Proxy" in manage.text
        assert "Choose what you want to do." in manage.text
        assert "Assign to Account" in labels
        assert "Archive Proxy" in labels
        assert "Delete Proxy" in labels
        _assert_proxy_screen_clean(manage.text)

        archive_result = screen_for_page(f"proxy:{proxy.id}:archive", principal, session=session, user=owner)
        assert "Proxy archived" in archive_result.text
        assert list_proxies(session) == []

        empty = render_proxies_home(session)
        assert "No real proxies saved yet." in empty.text
        assert "Paste your Olympix proxy string." in empty.text


def test_delete_blocks_assigned_proxy_and_allows_unassigned_proxy() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)
        model = create_model_brand(session, actor=owner, display_name="Proxy Model")
        account = create_account(session, model_brand=model, platform="instagram", username="creator", actor=owner)
        assigned = create_olympix_proxy_from_string(session, actor=owner, proxy_string=PROXY_STRING)
        account.assigned_proxy_id = assigned.id
        session.flush()

        blocked = render_proxy_delete_confirm_page(session, assigned.id)
        assert "assigned to 1 active account" in blocked.text
        assert "Confirm Delete" not in _button_labels(blocked)
        assert "Archive Instead" in _button_labels(blocked)

        unassigned = create_olympix_proxy_from_string(
            session,
            actor=owner,
            proxy_string="host.olympix.io:1080:user_other,type_mobile,session_aa11bb22:super-secret",
        )
        confirm = render_proxy_delete_confirm_page(session, unassigned.id)
        assert "Confirm Delete" in _button_labels(confirm)

        result = screen_for_page(f"proxy:{unassigned.id}:delete", principal, session=session, user=owner)
        assert "Proxy deleted" in result.text
        assert session.get(Proxy, unassigned.id) is None


def test_rotation_preview_and_no_rollback_are_simple_and_safe() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)
        proxy = create_olympix_proxy_from_string(session, actor=owner, proxy_string=PROXY_STRING)

        preview = render_proxy_rotation_preview_page(session, proxy.id)
        assert "Rotate Proxy" in preview.text
        assert "fresh session/IP" in preview.text
        assert "Current session:" in preview.text
        assert "Confirm Rotate" in _button_labels(preview)
        _assert_proxy_screen_clean(preview.text)

        no_rollback = screen_for_page(f"proxy:{proxy.id}:rollback", principal, session=session, user=owner)
        assert "No previous session saved yet." in no_rollback.text


def test_proxy_callbacks_cover_real_state_without_raw_output() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)
        proxy = create_olympix_proxy_from_string(session, actor=owner, proxy_string=PROXY_STRING)
        pages = [
            "proxies",
            "proxies:list",
            "proxies:advanced",
            "proxies:rotation_help",
            "proxies:cleanup_placeholders",
            f"proxy:{proxy.id}",
            f"proxy:{proxy.id}:manage",
            f"proxy:{proxy.id}:assign",
            f"proxy:{proxy.id}:remove",
            f"proxy:{proxy.id}:rotate_preview",
            f"proxy:{proxy.id}:archive_confirm",
            f"proxy:{proxy.id}:delete_confirm",
        ]

        for page in pages:
            screen = screen_for_page(page, principal, session=session, user=owner)
            assert screen.text.strip()
            assert screen.reply_markup is not None
            _assert_proxy_screen_clean(screen.text)
