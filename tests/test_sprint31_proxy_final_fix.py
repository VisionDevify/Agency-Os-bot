import pytest

from app.bot.navigation import screen_for_page
from app.bot.screens import (
    render_olympix_proxy_paste_page,
    render_olympix_proxy_wizard_page,
    render_proxy_detail_page,
    render_proxy_import_success_page,
)
from app.models.proxy import ProxyRotationHistory
from app.services.accounts import create_account
from app.services.agency_activation import account_setup_states
from app.services.auth import setup_owner_if_needed
from app.services.crypto import decrypt_secret
from app.services.help_brain import help_brain_answer
from app.services.model_brands import create_model_brand
from app.services.permissions import PermissionPrincipal, RoleName
from app.services.proxies import (
    ProxyStringParseError,
    assign_proxy_to_account,
    create_olympix_proxy_from_string,
    parse_olympix_proxy_string,
    rollback_session,
    rotate_olympix_session,
)
from tests.utils import session_scope


PROXY_STRING = "host.olympix.io:1080:user_abcdef,type_mobile,session_bf534e5c:super-secret"


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Rex")


def _principal(owner):
    return PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)


def test_parse_full_olympix_proxy_string() -> None:
    parsed = parse_olympix_proxy_string(PROXY_STRING)

    assert parsed.host == "host.olympix.io"
    assert parsed.port == 1080
    assert parsed.full_username == "user_abcdef,type_mobile,session_bf534e5c"
    assert parsed.base_username == "user_abcdef,type_mobile"
    assert parsed.session_suffix == "bf534e5c"
    assert parsed.password == "super-secret"


def test_invalid_proxy_string_rejected_cleanly() -> None:
    with pytest.raises(ProxyStringParseError, match="Expected host:port:username:password"):
        parse_olympix_proxy_string("host.olympix.io:1080:missing-password")

    with pytest.raises(ProxyStringParseError, match="session_"):
        parse_olympix_proxy_string("host.olympix.io:1080:user_abcdef,type_mobile:secret")


def test_one_paste_import_encrypts_password_and_renders_masked_summary() -> None:
    with session_scope() as session:
        owner = _owner(session)

        proxy = create_olympix_proxy_from_string(session, actor=owner, proxy_string=PROXY_STRING)
        detail = render_proxy_detail_page(session, proxy.id)
        imported = render_proxy_import_success_page(session, proxy.id)

        assert proxy.provider == "Olympix"
        assert proxy.metadata_json["proxy_type"] == "SOCKS5 Mobile"
        assert proxy.base_username == "user_abcdef,type_mobile"
        assert proxy.session_suffix == "bf534e5c"
        assert proxy.generated_username == "user_abcdef,type_mobile,session_bf534e5c"
        assert proxy.encrypted_password != "super-secret"
        assert decrypt_secret(proxy.encrypted_password) == "super-secret"
        assert "Password: Encrypted" in imported.text
        assert "User: user_••••••" in imported.text
        assert "Session: ••••4e5c" in imported.text
        assert "super-secret" not in detail.text
        assert "super-secret" not in imported.text
        assert "user_abcdef,type_mobile,session_bf534e5c" not in detail.text
        assert "bf534e5c" not in detail.text
        assert "encrypted_password" not in detail.text
        assert "{" not in detail.text


def test_olympix_rotation_changes_suffix_and_rollback_restores_it() -> None:
    with session_scope() as session:
        owner = _owner(session)
        proxy = create_olympix_proxy_from_string(session, actor=owner, proxy_string=PROXY_STRING)
        original = proxy.session_suffix

        history = rotate_olympix_session(session, proxy, actor=owner)

        assert history.status == "succeeded"
        assert proxy.previous_session_suffix == original
        assert proxy.session_suffix != original
        assert len(proxy.session_suffix) == len(original)
        assert proxy.generated_username == f"user_abcdef,type_mobile,session_{proxy.session_suffix}"

        rollback = rollback_session(session, proxy, actor=owner)

        assert rollback.status == "rolled_back"
        assert proxy.session_suffix == original
        assert proxy.generated_username == f"user_abcdef,type_mobile,session_{original}"
        assert session.query(ProxyRotationHistory).count() == 2


def test_assign_proxy_updates_account_setup_state() -> None:
    with session_scope() as session:
        owner = _owner(session)
        model = create_model_brand(session, actor=owner, display_name="Proxy Model")
        account = create_account(session, model_brand=model, platform="instagram", username="creator", actor=owner)
        proxy = create_olympix_proxy_from_string(session, actor=owner, proxy_string=PROXY_STRING)

        before = account_setup_states(session)[0]
        assert "Needs proxy" in before.checklist

        assign_proxy_to_account(session, proxy, account, actor=owner)

        after = account_setup_states(session)[0]
        assert account.assigned_proxy_id == proxy.id
        assert "Proxy assigned" in after.checklist
        assert "Needs proxy" not in after.checklist


def test_proxy_callback_routes_do_not_dead_end_or_leak_secrets() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)
        model = create_model_brand(session, actor=owner, display_name="Callback Model")
        account = create_account(session, model_brand=model, platform="instagram", username="callback", actor=owner)
        proxy = create_olympix_proxy_from_string(session, actor=owner, proxy_string=PROXY_STRING)

        pages = [
            "proxies",
            "proxies:add",
            "proxies:olympix",
            "proxies:olympix:paste",
            "proxies:olympix:manual",
            "proxies:list",
            "proxies:missing",
            "proxies:dashboard",
            "proxies:advanced",
            "proxies:entry_check",
            "proxies:real_check_pilot",
            f"proxy:{proxy.id}",
            f"proxy:{proxy.id}:assign",
            f"proxy:{proxy.id}:remove",
            f"proxy:{proxy.id}:accounts",
            f"proxy:{proxy.id}:history",
            f"proxy:{proxy.id}:audit",
            f"proxy:{proxy.id}:rotate_preview",
            f"proxy:{proxy.id}:location",
            f"proxy:{proxy.id}:advanced",
            f"proxy:{proxy.id}:check:simulated",
            f"proxy:{proxy.id}:rotate",
            f"proxy:{proxy.id}:rollback",
            f"account:{account.id}:proxy:assign_best",
        ]

        for page in pages:
            screen = screen_for_page(page, principal, session=session, user=owner)
            assert screen.text
            assert screen.reply_markup is not None
            assert "super-secret" not in screen.text
            assert "encrypted_password" not in screen.text
            assert "metadata_json" not in screen.text


def test_proxy_setup_screens_explain_one_paste_and_manual_paths() -> None:
    paste = render_olympix_proxy_paste_page()
    manual = render_olympix_proxy_wizard_page()

    assert "Paste Olympix Proxy" in paste.text
    assert "host:port:username:password" in paste.text
    assert "password is encrypted" in paste.text.casefold()
    assert "Step 1: Host" in manual.text
    assert "Paste the part before ,session_" in manual.text


def test_help_brain_proxy_answers_are_simple_and_safe() -> None:
    with session_scope() as session:
        owner = _owner(session)
        questions = [
            "How do I add my Olympix proxy?",
            "Can I paste the full proxy string?",
            "What is the session suffix?",
            "How does rotation work?",
            "How do I assign proxy to account?",
            "Why is real check off?",
            "Why can't I see the proxy password?",
        ]

        answers = [help_brain_answer(session, owner, question=question).answer for question in questions]

        joined = "\n".join(answers)
        assert "Paste Full Proxy String" in joined
        assert "session suffix" in joined
        assert "Assign Best Proxy" in joined
        assert "off by default" in joined
        assert "encrypted" in joined
        assert "super-secret" not in joined
        assert "encrypted_password" not in joined
