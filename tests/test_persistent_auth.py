import pytest

from app.models.audit import AuditLog
from app.models.permissions import Permission, Role
from app.services.auth import (
    DEFAULT_PERMISSION_DESCRIPTIONS,
    USER_STATUS_ACTIVE,
    USER_STATUS_DISABLED,
    USER_STATUS_PENDING,
    assign_role_to_user,
    audit_action,
    disable_user,
    get_or_create_telegram_user,
    prevent_self_promotion,
    seed_default_roles_and_permissions,
    setup_owner_if_needed,
    user_has_permission,
)
from app.services.permissions import RoleName

from tests.utils import session_scope


def test_owner_first_setup_seeds_assigns_and_audits() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(
            session,
            telegram_user_id=100,
            username="owner",
            owner_telegram_id=100,
        )

        assert owner.status == USER_STATUS_ACTIVE
        assert owner.is_owner is True
        assert {role.name for role in owner.roles} == {RoleName.OWNER.value}
        assert user_has_permission(owner, "manage_users")
        assert session.query(AuditLog).filter_by(action="owner.setup").count() == 1


def test_default_seed_is_idempotent() -> None:
    with session_scope() as session:
        seed_default_roles_and_permissions(session)
        seed_default_roles_and_permissions(session)

        assert session.query(Role).count() == len(RoleName)
        assert session.query(Permission).count() == len(DEFAULT_PERMISSION_DESCRIPTIONS)


def test_non_owner_cannot_self_promote() -> None:
    with session_scope() as session:
        user = get_or_create_telegram_user(session, telegram_user_id=200)

        with pytest.raises(PermissionError):
            prevent_self_promotion(user, user, [RoleName.OWNER.value])


def test_disabled_user_is_blocked() -> None:
    with session_scope() as session:
        seed_default_roles_and_permissions(session)
        user = get_or_create_telegram_user(session, telegram_user_id=201, owner_telegram_id=100)
        user.status = USER_STATUS_ACTIVE
        user.is_active = True
        assign_role_to_user(session, user, RoleName.ADMIN)

        disable_user(session, user)

        assert user.status == USER_STATUS_DISABLED
        assert user_has_permission(user, "manage_users") is False


def test_pending_user_is_limited() -> None:
    with session_scope() as session:
        user = get_or_create_telegram_user(session, telegram_user_id=202, owner_telegram_id=100)

        assert user.status == USER_STATUS_PENDING
        assert user_has_permission(user, "view_dashboard") is False


def test_owner_bypasses_permission_checks() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(
            session,
            telegram_user_id=100,
            username=None,
            owner_telegram_id=100,
        )

        assert user_has_permission(owner, "permission_that_does_not_exist") is True


def test_permission_allow_and_deny() -> None:
    with session_scope() as session:
        seed_default_roles_and_permissions(session)
        admin = get_or_create_telegram_user(session, telegram_user_id=203)
        viewer = get_or_create_telegram_user(session, telegram_user_id=204)
        admin.status = USER_STATUS_ACTIVE
        admin.is_active = True
        viewer.status = USER_STATUS_ACTIVE
        viewer.is_active = True
        assign_role_to_user(session, admin, RoleName.ADMIN)
        assign_role_to_user(session, viewer, RoleName.VIEWER)

        assert user_has_permission(admin, "manage_users") is True
        assert user_has_permission(viewer, "manage_users") is False


def test_restricted_access_attempt_gets_audited() -> None:
    with session_scope() as session:
        user = get_or_create_telegram_user(session, telegram_user_id=205)
        audit_action(
            session,
            actor=user,
            action="restricted_page.accessed",
            resource_type="telegram_page",
            resource_id="users",
            status="denied",
            details={"permission": "manage_users"},
        )

        log = session.query(AuditLog).one()
        assert log.actor_user_id == user.id
        assert log.status == "denied"
        assert log.details == {"permission": "manage_users"}
