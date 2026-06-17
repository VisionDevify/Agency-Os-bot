from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models.audit import AuditLog
from app.models.permissions import Permission, Role
from app.models.user import User
from app.services.audit import sanitize_details
from app.services.permissions import ROLE_PERMISSIONS, RoleName

USER_STATUS_ACTIVE = "active"
USER_STATUS_PENDING = "pending"
USER_STATUS_DISABLED = "disabled"

DEFAULT_PERMISSION_DESCRIPTIONS: dict[str, str] = {
    "view_dashboard": "View the main dashboard.",
    "manage_users": "Create, update, disable, and inspect users.",
    "manage_roles": "Manage roles and role permissions.",
    "manage_accounts": "Manage accounts.",
    "manage_proxies": "Manage proxies.",
    "manage_tasks": "Manage tasks.",
    "manage_incidents": "Manage incidents.",
    "manage_reports": "Manage reports.",
    "manage_automations": "Manage automations.",
    "view_audit_logs": "View recent audit logs.",
    "approve_content": "Approve content.",
    "upload_content": "Upload content.",
    "view_credentials": "View credential metadata.",
    "rotate_proxy": "Rotate proxy/session placeholders.",
    "resolve_incidents": "Resolve incidents.",
    "view_chatter_dashboard": "View chatter dashboard.",
    "manage_chatter_team": "Manage chatter team.",
}


def _role_permissions(role_name: RoleName) -> set[str]:
    permissions = set(ROLE_PERMISSIONS[role_name])
    permissions.discard("*")
    if role_name is RoleName.OWNER:
        permissions.update(DEFAULT_PERMISSION_DESCRIPTIONS)
    return permissions


def seed_default_roles_and_permissions(session: Session) -> None:
    permissions: dict[str, Permission] = {}
    for key, description in DEFAULT_PERMISSION_DESCRIPTIONS.items():
        permission = session.scalar(select(Permission).where(Permission.key == key))
        if permission is None:
            permission = Permission(key=key, description=description)
            session.add(permission)
        else:
            permission.description = permission.description or description
        permissions[key] = permission

    session.flush()

    for role_name in RoleName:
        role = session.scalar(select(Role).where(Role.name == role_name.value))
        if role is None:
            role = Role(name=role_name.value, description=f"{role_name.value} role")
            session.add(role)
            session.flush()
        existing_keys = {permission.key for permission in role.permissions}
        for key in _role_permissions(role_name):
            if key not in existing_keys:
                role.permissions.append(permissions[key])


def get_user_by_telegram_id(session: Session, telegram_user_id: int) -> User | None:
    return session.scalar(
        select(User)
        .where(User.telegram_id == telegram_user_id)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )


def get_or_create_telegram_user(
    session: Session,
    *,
    telegram_user_id: int,
    username: str | None = None,
    owner_telegram_id: int | None = None,
) -> User:
    user = get_user_by_telegram_id(session, telegram_user_id)
    owner_match = owner_telegram_id is not None and telegram_user_id == owner_telegram_id

    if user is None:
        user = User(
            telegram_id=telegram_user_id,
            username=username,
            is_owner=owner_match,
            is_active=owner_match,
            status=USER_STATUS_ACTIVE if owner_match else USER_STATUS_PENDING,
        )
        session.add(user)
        session.flush()
    else:
        user.username = username or user.username
        if owner_match:
            user.is_owner = True
            user.is_active = True
            user.status = USER_STATUS_ACTIVE

    return user


def assign_role_to_user(session: Session, user: User, role_name: RoleName | str) -> None:
    role_value = role_name.value if isinstance(role_name, RoleName) else role_name
    role = session.scalar(select(Role).where(Role.name == role_value))
    if role is None:
        raise ValueError(f"Role does not exist: {role_value}")
    if role not in user.roles:
        user.roles.append(role)
        if role.name == RoleName.OWNER.value:
            user.is_owner = True
            user.is_active = True
            user.status = USER_STATUS_ACTIVE


def is_owner(user: User | None) -> bool:
    if user is None:
        return False
    return user.is_owner or any(role.name == RoleName.OWNER.value for role in user.roles)


def user_has_permission(user: User | None, permission_key: str) -> bool:
    if user is None or user.status != USER_STATUS_ACTIVE or not user.is_active:
        return False
    if is_owner(user):
        return True
    return any(permission.key == permission_key for role in user.roles for permission in role.permissions)


def require_permission(user: User, permission_key: str) -> None:
    if not user_has_permission(user, permission_key):
        raise PermissionError(f"Missing permission: {permission_key}")


def disable_user(session: Session, user: User, *, actor: User | None = None) -> None:
    if is_owner(user):
        raise PermissionError("Owner user cannot be disabled")
    user.is_active = False
    user.status = USER_STATUS_DISABLED
    audit_action(
        session,
        actor=actor,
        action="user.disabled",
        resource_type="user",
        resource_id=str(user.id),
        status="success",
        details={"telegram_id": user.telegram_id},
    )


def audit_action(
    session: Session,
    *,
    actor: User | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    status: str = "success",
    details: dict | None = None,
) -> AuditLog:
    log = AuditLog(
        actor_user_id=actor.id if actor else None,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        details=sanitize_details(details),
    )
    session.add(log)
    session.flush()
    return log


def setup_owner_if_needed(
    session: Session,
    *,
    telegram_user_id: int,
    username: str | None = None,
    owner_telegram_id: int | None = None,
) -> User:
    if owner_telegram_id is None or telegram_user_id != owner_telegram_id:
        raise PermissionError("Only OWNER_TELEGRAM_ID can perform owner setup")

    seed_default_roles_and_permissions(session)
    user = get_or_create_telegram_user(
        session,
        telegram_user_id=telegram_user_id,
        username=username,
        owner_telegram_id=owner_telegram_id,
    )
    assign_role_to_user(session, user, RoleName.OWNER)
    audit_action(
        session,
        actor=user,
        action="owner.setup",
        resource_type="user",
        resource_id=str(user.id),
        details={"telegram_id": telegram_user_id},
    )
    return user


def prevent_self_promotion(actor: User, target: User, roles: Iterable[str]) -> None:
    if actor.id == target.id and not is_owner(actor) and RoleName.OWNER.value in set(roles):
        raise PermissionError("Non-owner users cannot self-promote")
