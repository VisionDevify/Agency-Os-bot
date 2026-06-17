from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.reporting import (
    NOTIFICATION_TARGET_PURPOSES,
    NOTIFICATION_TARGET_TYPES,
    NotificationTarget,
)
from app.models.user import User
from app.services.auth import audit_action, user_has_permission
from app.services.crypto import encrypt_secret
from app.services.events import emit_event


def _require_notification_admin(session: Session, actor: User | None) -> None:
    if user_has_permission(actor, "manage_reports") or user_has_permission(actor, "manage_roles"):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="notification_target",
        status="denied",
        details={"permission": "manage_reports_or_manage_roles"},
    )
    raise PermissionError("Missing permission: manage_reports or manage_roles")


def mask_chat_id(value: str | None) -> str:
    if not value:
        return "not set"
    raw = str(value)
    if len(raw) <= 4:
        return "hidden"
    return f"{raw[:2]}...{raw[-2:]}"


def list_notification_targets(session: Session, *, include_inactive: bool = True) -> list[NotificationTarget]:
    statement = select(NotificationTarget).order_by(NotificationTarget.id)
    if not include_inactive:
        statement = statement.where(NotificationTarget.is_active.is_(True))
    return list(session.scalars(statement).all())


def get_notification_target(session: Session, target_id: int) -> NotificationTarget | None:
    return session.get(NotificationTarget, target_id)


def create_notification_target(
    session: Session,
    *,
    actor: User,
    name: str,
    target_type: str,
    purpose: str,
    telegram_chat_id: str | None = None,
) -> NotificationTarget:
    _require_notification_admin(session, actor)
    if target_type not in NOTIFICATION_TARGET_TYPES:
        raise ValueError(f"Invalid notification target type: {target_type}")
    if purpose not in NOTIFICATION_TARGET_PURPOSES:
        raise ValueError(f"Invalid notification target purpose: {purpose}")
    target = NotificationTarget(
        name=name.strip() or "Notification Target",
        target_type=target_type,
        purpose=purpose,
        telegram_chat_id=encrypt_secret(telegram_chat_id) if telegram_chat_id else None,
        is_active=True,
    )
    session.add(target)
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="notification_target.created",
        resource_type="notification_target",
        resource_id=str(target.id),
        payload={"target_type": target.target_type, "purpose": target.purpose},
    )
    return target


def create_placeholder_notification_target(session: Session, *, actor: User) -> NotificationTarget:
    next_number = session.scalar(select(func.count(NotificationTarget.id))) or 0
    return create_notification_target(
        session,
        actor=actor,
        name=f"Notification Target {next_number + 1}",
        target_type="telegram_user",
        purpose="testing",
        telegram_chat_id=None,
    )


def disable_notification_target(session: Session, target: NotificationTarget, *, actor: User) -> NotificationTarget:
    _require_notification_admin(session, actor)
    target.is_active = False
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="notification_target.disabled",
        resource_type="notification_target",
        resource_id=str(target.id),
        payload={"purpose": target.purpose},
    )
    return target


def test_notification_target(session: Session, target: NotificationTarget, *, actor: User) -> None:
    _require_notification_admin(session, actor)
    audit_action(
        session,
        actor=actor,
        action="notification_target.test_requested",
        resource_type="notification_target",
        resource_id=str(target.id),
        details={"delivery": "placeholder", "target_type": target.target_type, "purpose": target.purpose},
    )
