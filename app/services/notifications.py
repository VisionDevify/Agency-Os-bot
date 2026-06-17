from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.reporting import (
    NOTIFICATION_TARGET_PURPOSES,
    NOTIFICATION_TARGET_TYPES,
    NotificationTarget,
)
from app.models.user import User
from app.services.auth import audit_action, is_owner
from app.services.crypto import decrypt_secret, encrypt_secret
from app.services.events import emit_event
from app.services.permissions import RoleName

NOTIFICATION_ROUTING_RULES: dict[str, tuple[str, ...]] = {
    "briefing.generated": ("owner", "operations"),
    "accountability.generated": ("operations",),
    "incident.created.critical": ("owner", "incidents"),
    "proxy.repair.failed": ("incidents", "automation_logs"),
    "proxy.repair.succeeded": ("automation_logs",),
    "deployment.event": ("testing", "owner"),
    "automation.simulated": ("automation_logs",),
}


def _now() -> datetime:
    return datetime.now(UTC)


def _is_owner_or_admin(actor: User | None) -> bool:
    if actor is None:
        return False
    return is_owner(actor) or any(role.name == RoleName.ADMIN.value for role in actor.roles)


def _require_notification_admin(session: Session, actor: User | None) -> None:
    if _is_owner_or_admin(actor):
        return
    audit_action(
        session,
        actor=actor,
        action="access.denied",
        resource_type="notification_target",
        status="denied",
        details={"permission": "owner_or_admin"},
    )
    raise PermissionError("Only Owner/Admin can manage notification targets")


def mask_chat_id(value: str | None) -> str:
    if not value:
        return "not set"
    raw = str(value)
    if len(raw) <= 4:
        return "hidden"
    return f"{raw[:2]}...{raw[-2:]}"


def mask_target_chat_id(target: NotificationTarget) -> str:
    return mask_chat_id(decrypt_target_chat_id(target))


def list_notification_targets(session: Session, *, include_inactive: bool = True) -> list[NotificationTarget]:
    statement = select(NotificationTarget).order_by(NotificationTarget.id)
    if not include_inactive:
        statement = statement.where(NotificationTarget.is_active.is_(True))
    return list(session.scalars(statement).all())


def get_notification_target(session: Session, target_id: int) -> NotificationTarget | None:
    return session.get(NotificationTarget, target_id)


def decrypt_target_chat_id(target: NotificationTarget) -> str | None:
    if not target.telegram_chat_id:
        return None
    return decrypt_secret(target.telegram_chat_id)


def create_notification_target(
    session: Session,
    *,
    actor: User,
    name: str,
    target_type: str,
    purpose: str,
    telegram_chat_id: str | int | None = None,
) -> NotificationTarget:
    _require_notification_admin(session, actor)
    if target_type not in NOTIFICATION_TARGET_TYPES:
        raise ValueError(f"Invalid notification target type: {target_type}")
    if purpose not in NOTIFICATION_TARGET_PURPOSES:
        raise ValueError(f"Invalid notification target purpose: {purpose}")
    raw_chat_id = str(telegram_chat_id) if telegram_chat_id is not None else None
    target = NotificationTarget(
        name=name.strip() or "Notification Target",
        target_type=target_type,
        purpose=purpose,
        telegram_chat_id=encrypt_secret(raw_chat_id) if raw_chat_id else None,
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
        payload={"target_type": target.target_type, "purpose": target.purpose, "has_chat_id": bool(raw_chat_id)},
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


def add_current_chat_as_target(
    session: Session,
    *,
    actor: User,
    chat_id: int,
    chat_title: str | None = None,
    target_type: str = "telegram_user",
    purpose: str = "testing",
) -> NotificationTarget:
    label = chat_title or f"Current Chat {str(chat_id)[-4:]}"
    return create_notification_target(
        session,
        actor=actor,
        name=label,
        target_type=target_type,
        purpose=purpose,
        telegram_chat_id=chat_id,
    )


def set_notification_target_purpose(
    session: Session,
    target: NotificationTarget,
    purpose: str,
    *,
    actor: User,
) -> NotificationTarget:
    _require_notification_admin(session, actor)
    if purpose not in NOTIFICATION_TARGET_PURPOSES:
        raise ValueError(f"Invalid notification target purpose: {purpose}")
    old_purpose = target.purpose
    target.purpose = purpose
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="notification_target.updated",
        resource_type="notification_target",
        resource_id=str(target.id),
        payload={"from": old_purpose, "to": purpose},
    )
    return target


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
    target.last_tested_at = _now()
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="notification_target.tested",
        resource_type="notification_target",
        resource_id=str(target.id),
        payload={"delivery": "placeholder", "target_type": target.target_type, "purpose": target.purpose},
    )


def target_purposes_for_event(event_type: str, *, severity: str | None = None) -> tuple[str, ...]:
    if event_type == "incident.created" and severity == "critical":
        return NOTIFICATION_ROUTING_RULES["incident.created.critical"]
    return NOTIFICATION_ROUTING_RULES.get(event_type, ())


def active_targets_for_event(
    session: Session,
    event_type: str,
    *,
    severity: str | None = None,
) -> list[NotificationTarget]:
    purposes = target_purposes_for_event(event_type, severity=severity)
    if not purposes:
        return []
    return list(
        session.scalars(
            select(NotificationTarget).where(
                NotificationTarget.is_active.is_(True),
                NotificationTarget.purpose.in_(purposes),
            )
        ).all()
    )


def build_notification_text(event_type: str, *, title: str | None = None, body: str | None = None) -> str:
    safe_title = title or event_type.replace(".", " ").title()
    safe_body = body or "Agency OS event routed safely."
    return f"Agency OS\n{safe_title}\n{safe_body}"


def record_notification_routed(
    session: Session,
    *,
    actor: User | None,
    event_type: str,
    target_count: int,
    purpose: str | None = None,
) -> None:
    emit_event(
        session,
        actor=actor,
        event_name="notification.routed",
        resource_type="notification",
        resource_id=event_type,
        payload={"target_count": target_count, "purpose": purpose},
    )
