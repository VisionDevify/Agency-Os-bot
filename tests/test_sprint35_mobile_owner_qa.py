import pytest

from app.bot.navigation import screen_for_page
from app.services.auth import setup_owner_if_needed
from app.services.friction import create_friction_item
from app.services.permissions import PermissionPrincipal, RoleName
from tests.utils import session_scope


def _owner(session):
    return setup_owner_if_needed(session, telegram_user_id=1, owner_telegram_id=1, display_name="Rex")


def _principal(owner):
    return PermissionPrincipal(telegram_id=owner.telegram_id, is_owner=True, role=RoleName.OWNER)


def test_friction_item_creation() -> None:
    with session_scope() as session:
        item = create_friction_item(
            session,
            screen="Proxy Vault",
            issue="Owner cannot tell whether real checks will use bandwidth.",
            severity="high",
            fix_recommendation="Show simulated mode, last checked time, and a one-tap on-demand check.",
        )

        assert item.id is not None
        assert item.screen == "Proxy Vault"
        assert item.severity == "high"
        assert "bandwidth" in item.issue


def test_friction_item_rejects_unknown_severity() -> None:
    with session_scope() as session:
        with pytest.raises(ValueError):
            create_friction_item(
                session,
                screen="Home",
                issue="Invalid severity should not be persisted.",
                severity="panic",
                fix_recommendation="Use low, medium, high, or critical.",
            )


def test_owner_daily_surfaces_have_next_actions() -> None:
    with session_scope() as session:
        owner = _owner(session)
        principal = _principal(owner)
        for page in ("menu", "start_here", "today", "setup_progress", "proxies", "opportunities", "help"):
            screen = screen_for_page(page, principal, session=session, user=owner)
            text = screen.text.casefold()

            assert screen.reply_markup is not None
            assert "traceback" not in text
            assert "metadata_json" not in text
            assert "source_type" not in text
            assert "next" in text or "start" in text or "nothing urgent" in text or "ask fortuna" in text
