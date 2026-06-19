from dataclasses import dataclass
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
    "briefing.generated": ("hq", "ops"),
    "digest.generated": ("hq", "ops"),
    "digest.sent": ("hq", "ops"),
    "digest.failed": ("hq", "ops"),
    "accountability.generated": ("ops",),
    "incident.created.critical": ("hq", "ops"),
    "incident.escalated": ("hq", "ops"),
    "incident.resolved": ("ops",),
    "task.assigned": ("ops",),
    "task.escalated": ("ops", "hq"),
    "task.overdue_detected": ("ops",),
    "proxy.repair.failed": ("hq", "ops"),
    "proxy.repair.succeeded": ("ops",),
    "deployment.event": ("hq",),
    "automation.simulated": ("ops",),
    "intelligence.signal.critical": ("hq", "ops"),
    "creator_watch.created": ("ops",),
    "creator.created": ("ops",),
    "creator.assigned": ("ops",),
    "creator.post_alert": ("alerts",),
    "own_post.alert": ("alerts",),
    "opportunity.assigned": ("ops",),
    "opportunity.high_priority": ("alerts", "hq"),
    "opportunity.created": ("ops",),
    "opportunity.result_recorded": ("ops",),
    "post_watch.created": ("ops",),
    "opportunity.digest": ("ops",),
}

PURPOSE_LABELS: dict[str, str] = {
    "hq": "Fortuna HQ",
    "ops": "Fortuna Ops",
    "alerts": "Fortuna Alerts",
}

PURPOSE_ALIASES: dict[str, tuple[str, ...]] = {
    "hq": ("hq", "owner", "incidents", "testing"),
    "ops": ("ops", "operations", "automation_logs"),
    "alerts": ("alerts",),
    "owner": ("hq", "owner"),
    "operations": ("ops", "operations"),
    "incidents": ("hq", "incidents"),
    "automation_logs": ("ops", "automation_logs"),
    "testing": ("hq", "testing"),
}


@dataclass(frozen=True)
class NotificationPurposeStatus:
    purpose: str
    label: str
    configured: bool
    active_count: int
    last_delivery_status: str
    last_delivery_at: datetime | None


@dataclass(frozen=True)
class RoutingSmokeTestResult:
    would_send: tuple[str, ...]
    actual_sends: tuple[str, ...]
    skipped: tuple[str, ...]
    failures: tuple[str, ...]


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


def canonical_purpose(purpose: str) -> str:
    if purpose in {"hq", "ops", "alerts"}:
        return purpose
    return {
        "owner": "hq",
        "incidents": "hq",
        "testing": "hq",
        "operations": "ops",
        "automation_logs": "ops",
    }.get(purpose, purpose)


def purpose_aliases(purpose: str) -> tuple[str, ...]:
    return PURPOSE_ALIASES.get(purpose, (purpose,))


def expanded_purpose_set(purposes: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    expanded: list[str] = []
    for purpose in purposes:
        for alias in purpose_aliases(purpose):
            if alias not in expanded:
                expanded.append(alias)
    return tuple(expanded)


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
        purpose="hq",
        telegram_chat_id=None,
    )


def add_current_chat_as_target(
    session: Session,
    *,
    actor: User,
    chat_id: int,
    chat_title: str | None = None,
    target_type: str = "telegram_user",
    purpose: str = "hq",
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
    from app.services.learning import capture_notification_delivery

    capture_notification_delivery(session, attempt, actor=actor)
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
    from app.services.learning import capture_notification_delivery

    capture_notification_delivery(session, attempt, actor=actor)
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


def active_targets_for_purposes(session: Session, purposes: tuple[str, ...] | list[str]) -> list[NotificationTarget]:
    expanded = expanded_purpose_set(tuple(purposes))
    if not expanded:
        return []
    return list(
        session.scalars(
            select(NotificationTarget).where(
                NotificationTarget.is_active.is_(True),
                NotificationTarget.purpose.in_(expanded),
            )
        ).all()
    )


def active_targets_for_event(
    session: Session,
    event_type: str,
    *,
    severity: str | None = None,
) -> list[NotificationTarget]:
    purposes = target_purposes_for_event(event_type, severity=severity)
    if not purposes:
        return []
    return active_targets_for_purposes(session, purposes)


def build_notification_text(event_type: str, *, title: str | None = None, body: str | None = None) -> str:
    safe_title = title or event_type.replace(".", " ").title()
    safe_body = body or "Fortuna OS event routed safely."
    return f"Fortuna OS\n{safe_title}\n{safe_body}"


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


def notification_group_setup_status(session: Session) -> list[NotificationPurposeStatus]:
    rows: list[NotificationPurposeStatus] = []
    for purpose, label in PURPOSE_LABELS.items():
        aliases = purpose_aliases(purpose)
        targets = list(
            session.scalars(
                select(NotificationTarget).where(
                    NotificationTarget.is_active.is_(True),
                    NotificationTarget.purpose.in_(aliases),
                )
            ).all()
        )
        latest = session.scalar(
            select(NotificationDeliveryAttempt)
            .join(NotificationTarget)
            .where(NotificationTarget.purpose.in_(aliases))
            .order_by(desc(NotificationDeliveryAttempt.attempted_at), desc(NotificationDeliveryAttempt.id))
            .limit(1)
        )
        rows.append(
            NotificationPurposeStatus(
                purpose=purpose,
                label=label,
                configured=bool(targets),
                active_count=len(targets),
                last_delivery_status=latest.status if latest else "none",
                last_delivery_at=latest.attempted_at if latest else None,
            )
        )
    return rows


def run_notification_routing_smoke_test(
    session: Session,
    *,
    actor: User,
    send_testing: bool = True,
) -> RoutingSmokeTestResult:
    _require_notification_admin(session, actor)
    would_send: list[str] = []
    actual_sends: list[str] = []
    skipped: list[str] = []
    failures: list[str] = []

    for purpose, label in PURPOSE_LABELS.items():
        aliases = purpose_aliases(purpose)
        targets = list(
            session.scalars(
                select(NotificationTarget).where(
                    NotificationTarget.is_active.is_(True),
                    NotificationTarget.purpose.in_(aliases),
                )
            ).all()
        )
        if not targets:
            skipped.append(f"{label}: no active target")
            continue
        would_send.append(label)
        for target in targets:
            if target.purpose == "testing" and send_testing:
                create_delivery_attempt(
                    session,
                    target,
                    event_type="notification.routing_smoke_test",
                    actor=actor,
                    status="pending",
                    metadata={"purpose": purpose, "target_purpose": target.purpose, "smoke_test": True},
                )
                actual_sends.append(label)
            else:
                create_delivery_attempt(
                    session,
                    target,
                    event_type="notification.routing_smoke_test",
                    actor=actor,
                    status="skipped",
                    error_message="simulation only; no send without owner confirmation",
                    metadata={"purpose": purpose, "target_purpose": target.purpose, "smoke_test": True, "simulated": True},
                )
                skipped.append(f"{label}: simulated only")

    emit_event(
        session,
        actor=actor,
        event_name="notification.routing_smoke_test",
        resource_type="notification",
        resource_id="routing_smoke_test",
        payload={
            "would_send_count": len(would_send),
            "actual_send_count": len(actual_sends),
            "skipped_count": len(skipped),
            "failure_count": len(failures),
        },
    )
    return RoutingSmokeTestResult(
        would_send=tuple(would_send),
        actual_sends=tuple(actual_sends),
        skipped=tuple(skipped),
        failures=tuple(failures),
    )
