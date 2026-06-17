import pytest

from app.services.permissions import PermissionPrincipal, can, require_owner, require_permission


def test_owner_has_all_permissions() -> None:
    principal = PermissionPrincipal(telegram_id=1, is_owner=True)

    assert can(principal, "users.manage")


def test_permission_required_for_non_owner() -> None:
    principal = PermissionPrincipal(telegram_id=2, permissions=frozenset({"reports.read"}))

    assert can(principal, "reports.read")
    with pytest.raises(PermissionError):
        require_permission(principal, "users.manage")


def test_owner_only_setup_checks_configured_owner_id() -> None:
    principal = PermissionPrincipal(telegram_id=123)

    require_owner(principal, owner_telegram_id=123)
    with pytest.raises(PermissionError):
        require_owner(principal, owner_telegram_id=456)
