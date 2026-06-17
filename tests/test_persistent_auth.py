import pytest

from app.models.audit import AuditLog
from app.models.permissions import Permission, Role
from app.services.auth import (
    DEFAULT_PERMISSION_DESCRIPTIONS,
    USER_STATUS_ACTIVE,
    USER_STATUS_DENIED,
    USER_STATUS_DISABLED,
    USER_STATUS_PENDING,
    add_permission_to_role,
    assign_role_to_user,
    audit_action,
    approve_user,
    delete_role,
    deny_user,
    disable_user,
    get_or_create_telegram_user,
    prevent_self_promotion,
    reactivate_user,
    remove_permission_from_role,
    remove_role_from_user,
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
            display_name="Owner Display",
            username="owner",
            owner_telegram_id=100,
        )

        assert owner.status == USER_STATUS_ACTIVE
        assert owner.is_owner is True
        assert owner.display_name == "Owner Display"
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
        user = get_or_create_telegram_user(
            session,
            telegram_user_id=202,
            display_name="Pending User",
            username="pending",
            owner_telegram_id=100,
        )

        assert user.status == USER_STATUS_PENDING
        assert user.display_name == "Pending User"
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


def test_owner_can_approve_user() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=100, owner_telegram_id=100)
        pending = get_or_create_telegram_user(session, telegram_user_id=300)

        approve_user(session, pending, actor=owner)

        assert pending.status == USER_STATUS_ACTIVE
        assert pending.is_active is True
        assert session.query(AuditLog).filter_by(action="user.approved").count() == 1


def test_admin_with_manage_users_can_approve_user() -> None:
    with session_scope() as session:
        seed_default_roles_and_permissions(session)
        admin = get_or_create_telegram_user(session, telegram_user_id=301)
        admin.status = USER_STATUS_ACTIVE
        admin.is_active = True
        assign_role_to_user(session, admin, RoleName.ADMIN)
        pending = get_or_create_telegram_user(session, telegram_user_id=302)

        approve_user(session, pending, actor=admin)

        assert pending.status == USER_STATUS_ACTIVE


def test_user_without_manage_users_cannot_approve() -> None:
    with session_scope() as session:
        seed_default_roles_and_permissions(session)
        viewer = get_or_create_telegram_user(session, telegram_user_id=303)
        viewer.status = USER_STATUS_ACTIVE
        viewer.is_active = True
        assign_role_to_user(session, viewer, RoleName.VIEWER)
        pending = get_or_create_telegram_user(session, telegram_user_id=304)

        with pytest.raises(PermissionError):
            approve_user(session, pending, actor=viewer)


def test_owner_role_cannot_be_deleted() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=100, owner_telegram_id=100)
        owner_role = session.query(Role).filter_by(name=RoleName.OWNER.value).one()

        with pytest.raises(PermissionError):
            delete_role(session, owner_role, actor=owner)


def test_final_owner_cannot_be_removed() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=100, owner_telegram_id=100)

        with pytest.raises(PermissionError):
            remove_role_from_user(session, owner, RoleName.OWNER, actor=owner)


def test_owner_role_cannot_be_assigned_by_non_owner() -> None:
    with session_scope() as session:
        seed_default_roles_and_permissions(session)
        admin = get_or_create_telegram_user(session, telegram_user_id=305)
        admin.status = USER_STATUS_ACTIVE
        admin.is_active = True
        assign_role_to_user(session, admin, RoleName.ADMIN)
        target = get_or_create_telegram_user(session, telegram_user_id=306)

        with pytest.raises(PermissionError):
            assign_role_to_user(session, target, RoleName.OWNER, actor=admin)


def test_permission_add_remove_works() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=100, owner_telegram_id=100)
        role = session.query(Role).filter_by(name=RoleName.VIEWER.value).one()
        role.permissions.clear()
        session.flush()

        add_permission_to_role(session, role, "view_dashboard", actor=owner)
        assert "view_dashboard" in {permission.key for permission in role.permissions}

        remove_permission_from_role(session, role, "view_dashboard", actor=owner)
        assert "view_dashboard" not in {permission.key for permission in role.permissions}


def test_admin_actions_create_audit_logs() -> None:
    with session_scope() as session:
        owner = setup_owner_if_needed(session, telegram_user_id=100, owner_telegram_id=100)
        target = get_or_create_telegram_user(session, telegram_user_id=307)
        approve_user(session, target, actor=owner)
        assign_role_to_user(session, target, RoleName.VIEWER, actor=owner)
        remove_role_from_user(session, target, RoleName.VIEWER, actor=owner)
        disable_user(session, target, actor=owner)
        reactivate_user(session, target, actor=owner)
        deny_user(session, target, actor=owner)
        role = session.query(Role).filter_by(name=RoleName.VIEWER.value).one()
        add_permission_to_role(session, role, "view_audit_logs", actor=owner)
        remove_permission_from_role(session, role, "view_audit_logs", actor=owner)

        actions = {row.action for row in session.query(AuditLog).all()}

        assert {
            "user.approved",
            "user.disabled",
            "user.reactivated",
            "user.denied",
            "role.assigned",
            "role.removed",
            "role_permission.added",
            "role_permission.removed",
        }.issubset(actions)
