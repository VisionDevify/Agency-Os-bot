from datetime import UTC, datetime

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.reporting import (
    NOTIFICATION_DELIVERY_STATUSES,
    NOTIFICATION_TARGET_PURPOSES,
    NOTIFICATION_TARGET_TYPES,
    NotificationDeliveryAttempt,
    NotificationTarget,
)
from app.models.user import User
from app.services.audit import sanitize_details
from app.services.auth import audit_action, is_owner
from app.services.crypto import decrypt_secret, encrypt_secret
from app.services.events import emit_event
from app.services.permissions import RoleName
from app.services.recommendations import upsert_recommendation

NOTIFICATION_ROUTING_RULES: dict[str, tuple[str, ...]] = {
    "briefing.generated": ("owner", "operations"),
    "digest.generated": ("owner", "operations"),
    "digest.sent": ("owner", "operations"),
    "digest.failed": ("owner", "operations"),
    "accountability.generated": ("operations",),
    "incident.created.critical": ("owner", "incidents"),
    "incident.escalated": ("owner", "incidents"),
    "incident.resolved": ("operations",),
    "task.assigned": ("operations",),
    "task.escalated": ("operations", "owner"),
    "task.overdue_detected": ("operations",),
    "proxy.repair.failed": ("incidents", "automation_logs"),
    "proxy.repair.succeeded": ("automation_logs",),
    "deployment.event": ("testing", "owner"),
    "automation.simulated": ("automation_logs",),
    "intelligence.signal.critical": ("owner", "incidents", "operations"),
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


def _safe_error_message(error_message: str | None) -> str | None:
    if not error_message:
        return None
    lowered = error_message.lower()
    if any(marker in lowered for marker in ("token", "secret", "password", "key", "credential", "chat_id")):
        return "delivery failed; sensitive details redacted"
    return error_message[:500]


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


def create_delivery_attempt(
    session: Session,
    target: NotificationTarget,
    *,
    event_type: str,
    actor: User | None,
    status: str = "pending",
    error_message: str | None = None,
    metadata: dict | None = None,
) -> NotificationDeliveryAttempt:
    if status not in NOTIFICATION_DELIVERY_STATUSES:
        raise ValueError(f"Invalid notification delivery status: {status}")
    attempt = NotificationDeliveryAttempt(
        notification_target_id=target.id,
        event_type=event_type,
        status=status,
        error_message=_safe_error_message(error_message),
        attempted_at=_now(),
        metadata_json=sanitize_details(metadata),
    )
    session.add(attempt)
    session.flush()
    audit_action(
        session,
        actor=actor,
        action="notification.delivery_attempted",
        resource_type="notification_delivery_attempt",
        resource_id=str(attempt.id),
        details={
            "target_id": target.id,
            "event_type": event_type,
            "purpose": target.purpose,
            "target_type": target.target_type,
            "status": status,
        },
    )
    return attempt


def _failed_attempt_count(session: Session, target: NotificationTarget) -> int:
    return (
        session.scalar(
            select(func.count(NotificationDeliveryAttempt.id)).where(
                NotificationDeliveryAttempt.notification_target_id == target.id,
                NotificationDeliveryAttempt.status == "failed",
            )
        )
        or 0
    )


def _maybe_recommend_delivery_review(
    session: Session,
    target: NotificationTarget,
    *,
    actor: User | None,
) -> None:
    failed_count = _failed_attempt_count(session, target)
    if failed_count < 3:
        return
    upsert_recommendation(
        session,
        actor=actor,
        recommendation_type="notification_delivery_failures",
        title="Notification Delivery Failures",
        description=f"{target.name} has {failed_count} failed delivery attempts and needs review.",
        severity="warning",
        entity_type="notification_target",
        entity_id=target.id,
        metadata={"failed_count": failed_count, "purpose": target.purpose, "target_type": target.target_type},
    )


def mark_delivery_sent(
    session: Session,
    attempt: NotificationDeliveryAttempt,
    *,
    actor: User | None,
) -> NotificationDeliveryAttempt:
    attempt.status = "sent"
    attempt.error_message = None
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="notification.delivery_succeeded",
        resource_type="notification_delivery_attempt",
        resource_id=str(attempt.id),
        payload={"event_type": attempt.event_type, "target_id": attempt.notification_target_id},
    )
    return attempt


def mark_delivery_failed(
    session: Session,
    attempt: NotificationDeliveryAttempt,
    *,
    actor: User | None,
    error_message: str | None = None,
) -> NotificationDeliveryAttempt:
    attempt.status = "failed"
    attempt.error_message = _safe_error_message(error_message) or "delivery failed"
    session.flush()
    emit_event(
        session,
        actor=actor,
        event_name="notification.delivery_failed",
        resource_type="notification_delivery_attempt",
        resource_id=str(attempt.id),
        status="failed",
        payload={
            "event_type": attempt.event_type,
            "target_id": attempt.notification_target_id,
            "error": attempt.error_message,
        },
    )
    if attempt.target:
        _maybe_recommend_delivery_review(session, attempt.target, actor=actor)
    return attempt


def mark_delivery_skipped(
    session: Session,
    attempt: NotificationDeliveryAttempt,
    *,
    actor: User | None,
    reason: str = "skipped",
) -> NotificationDeliveryAttempt:
    attempt.status = "skipped"
    attempt.error_message = _safe_error_message(reason)
    session.flush()
    return attempt


def latest_delivery_attempts_for_target(
    session: Session,
    target: NotificationTarget,
    *,
    limit: int = 5,
) -> list[NotificationDeliveryAttempt]:
    return list(
        session.scalars(
            select(NotificationDeliveryAttempt)
            .where(NotificationDeliveryAttempt.notification_target_id == target.id)
            .order_by(desc(NotificationDeliveryAttempt.attempted_at), desc(NotificationDeliveryAttempt.id))
            .limit(limit)
        ).all()
    )


def latest_delivery_attempt(session: Session) -> NotificationDeliveryAttempt | None:
    return session.scalar(
        select(NotificationDeliveryAttempt)
        .order_by(desc(NotificationDeliveryAttempt.attempted_at), desc(NotificationDeliveryAttempt.id))
        .limit(1)
    )


def failed_delivery_count(session: Session) -> int:
    return (
        session.scalar(
            select(func.count(NotificationDeliveryAttempt.id)).where(NotificationDeliveryAttempt.status == "failed")
        )
        or 0
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
