from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.system import SystemHeartbeat
from app.services.heartbeats import record_heartbeat
from app.services.persistence import StorageStatus, storage_status

BOT_INSTANCE_PREFIX = "bot_instance:"
_GENERATED_INSTANCE_ID: str | None = None


@dataclass(frozen=True)
class PollingPreflight:
    allowed: bool
    status: str
    reason: str


def bot_instance_id() -> str:
    global _GENERATED_INSTANCE_ID
    configured = (settings.bot_instance_id or "").strip()
    if configured:
        return configured
    if _GENERATED_INSTANCE_ID is None:
        _GENERATED_INSTANCE_ID = f"bot-{uuid4().hex[:12]}"
    return _GENERATED_INSTANCE_ID


def mask_instance_id(instance_id: str | None) -> str:
    if not instance_id:
        return "unknown"
    if len(instance_id) <= 8:
        return f"{instance_id[:2]}••{instance_id[-2:]}"
    return f"{instance_id[:4]}••••{instance_id[-4:]}"


def bot_instance_service_name(instance_id: str | None = None) -> str:
    return f"{BOT_INSTANCE_PREFIX}{instance_id or bot_instance_id()}"


def polling_preflight(storage: StorageStatus | None = None) -> PollingPreflight:
    current = storage or storage_status()
    if not settings.bot_primary_instance:
        return PollingPreflight(False, "blocked", "BOT_PRIMARY_INSTANCE is false; this process must not poll Telegram.")
    if current.is_production and not settings.redis_url and not settings.allow_polling_without_redis:
        return PollingPreflight(
            False,
            "blocked",
            "Redis is required for production polling. Set REDIS_URL or explicitly enable emergency polling override.",
        )
    return PollingPreflight(True, "ready", "Polling preflight passed.")


def record_bot_instance_heartbeat(
    session: Session,
    *,
    instance_id: str | None = None,
    status: str = "healthy",
    metadata: dict | None = None,
) -> SystemHeartbeat:
    identifier = instance_id or bot_instance_id()
    safe_metadata = {
        "instance_id_masked": mask_instance_id(identifier),
        "primary": str(settings.bot_primary_instance),
        **(metadata or {}),
    }
    return record_heartbeat(
        session,
        service_name=bot_instance_service_name(identifier),
        status=status,
        metadata=safe_metadata,
    )


def active_bot_instance_heartbeats(
    session: Session,
    *,
    active_seconds: int | None = None,
) -> list[SystemHeartbeat]:
    cutoff = datetime.now(UTC) - timedelta(seconds=active_seconds or settings.bot_instance_active_seconds)
    rows = session.scalars(
        select(SystemHeartbeat)
        .where(SystemHeartbeat.service_name.like(f"{BOT_INSTANCE_PREFIX}%"))
        .where(SystemHeartbeat.last_seen_at >= cutoff)
        .where(SystemHeartbeat.status.in_(("healthy", "running", "degraded")))
        .order_by(SystemHeartbeat.last_seen_at.desc())
    ).all()
    return list(rows)


def duplicate_bot_instances(session: Session, *, current_instance_id: str | None = None) -> list[SystemHeartbeat]:
    current_service = bot_instance_service_name(current_instance_id)
    return [
        heartbeat
        for heartbeat in active_bot_instance_heartbeats(session)
        if heartbeat.service_name != current_service
    ]


def bot_instance_diagnostics(session: Session, *, current_instance_id: str | None = None) -> dict[str, object]:
    identifier = current_instance_id or bot_instance_id()
    current = storage_status()
    active = active_bot_instance_heartbeats(session)
    duplicates = duplicate_bot_instances(session, current_instance_id=identifier)
    bot_heartbeat = session.scalar(select(SystemHeartbeat).where(SystemHeartbeat.service_name == "bot"))
    metadata = bot_heartbeat.metadata_json if bot_heartbeat else {}
    preflight = polling_preflight(current)
    redis_configured = bool(settings.redis_url)
    duplicate_count = len(duplicates)
    if not preflight.allowed:
        risk = "blocked"
    elif duplicate_count:
        risk = "warning"
    elif current.is_production and not redis_configured:
        risk = "unsafe"
    else:
        risk = "ready"
    return {
        "instance_id_masked": mask_instance_id(identifier),
        "primary_polling_enabled": settings.bot_primary_instance,
        "preflight_allowed": preflight.allowed,
        "preflight_status": preflight.status,
        "preflight_reason": preflight.reason,
        "redis_configured": redis_configured,
        "redis_lock_status": metadata.get("redis_lock_status", "unknown"),
        "polling_guard": metadata.get("polling_guard", "unknown"),
        "last_update_at": metadata.get("last_telegram_update_at", "Unknown"),
        "last_polling_loop_at": metadata.get("last_polling_loop_at", "Unknown"),
        "db_backend": current.backend,
        "db_durable": current.durable,
        "environment": current.environment,
        "active_instance_count": len(active),
        "duplicate_instance_count": duplicate_count,
        "multiple_active_instances": duplicate_count > 0,
        "risk": risk,
    }
