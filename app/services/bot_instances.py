from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.event_log import EventLog
from app.models.system import SystemHeartbeat
from app.services.events import emit_event
from app.services.heartbeats import record_heartbeat
from app.services.persistence import StorageStatus, storage_status
from app.services.recommendations import upsert_recommendation

BOT_INSTANCE_PREFIX = "bot_instance:"
POLLING_CONFLICT_EVENT = "telegram.polling_conflict_detected"
POLLING_CONFLICT_RECOMMENDATION_TYPE = "bot_polling_conflict"
_GENERATED_INSTANCE_ID: str | None = None
MIN_BOT_INSTANCE_ACTIVE_SECONDS = 60


@dataclass(frozen=True)
class PollingPreflight:
    allowed: bool
    status: str
    reason: str


@dataclass(frozen=True)
class BotInstanceHeartbeatClassification:
    active_pollers: list[SystemHeartbeat]
    non_polling: list[SystemHeartbeat]
    stale: list[SystemHeartbeat]


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


def telegram_polling_lock_key(bot_token: str | None = None) -> str:
    """Return a token-scoped Redis owner key without exposing the token."""
    token = (bot_token or "").strip()
    if token:
        identifier = hashlib.sha256(token.encode("utf-8")).hexdigest()[:16]
    else:
        identifier = "unknown"
    return f"telegram_polling_owner:{identifier}"


def _service_role() -> str:
    for key in ("FORTUNA_RUNTIME_ROLE", "FORTUNA_SERVICE_ROLE", "SERVICE_ROLE", "PROCESS_TYPE"):
        value = os.getenv(key)
        if value:
            return value.strip().lower().replace(" ", "_")
    service_name = (
        os.getenv("RAILWAY_SERVICE_NAME")
        or os.getenv("RAILWAY_SERVICE_SLUG")
        or os.getenv("RAILWAY_SERVICE")
        or ""
    ).strip().lower()
    if "worker" in service_name or "telegram" in service_name:
        return "worker"
    if "api" in service_name or "web" in service_name:
        return "api"
    return "combined" if not any(key.startswith("RAILWAY_") for key in os.environ) else "api"


def polling_owner_metadata(
    *,
    instance_id: str | None = None,
    polling_allowed: bool,
    polling_active: bool,
    polling_lock_owner: str | None = None,
    source: str = "startup",
) -> dict[str, str]:
    identifier = instance_id or bot_instance_id()
    storage = storage_status()
    return {
        "source": source,
        "instance_id_masked": mask_instance_id(identifier),
        "service_role": _service_role(),
        "environment": storage.environment,
        "process_id": str(os.getpid()),
        "started_at": datetime.now(UTC).isoformat(),
        "polling_allowed": str(polling_allowed),
        "polling_active": str(polling_active),
        "polling_lock_owner": polling_lock_owner or "unknown",
        "deployment_commit": settings.git_commit or "unknown",
        "service_name": os.getenv("RAILWAY_SERVICE_NAME") or os.getenv("RAILWAY_SERVICE_SLUG") or "unknown",
    }


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


def record_polling_conflict(
    session: Session,
    *,
    instance_id: str | None = None,
    reason: str = "Another process is using the same Telegram bot token.",
    source: str = "telegram_conflict",
    conflict_source: str = "unknown",
    polling_lock_owner: str | None = None,
) -> None:
    identifier = instance_id or bot_instance_id()
    now = datetime.now(UTC).isoformat()
    metadata = {
        **polling_owner_metadata(
            instance_id=identifier,
            polling_allowed=True,
            polling_active=False,
            polling_lock_owner=polling_lock_owner,
            source=source,
        ),
        "latest_polling_conflict_at": now,
        "latest_polling_conflict_reason": reason,
        "latest_polling_conflict_source": conflict_source,
        "polling_conflict_active": "true",
    }
    record_heartbeat(session, service_name="bot", status="critical", metadata=metadata)
    record_bot_instance_heartbeat(session, instance_id=identifier, status="critical", metadata=metadata)
    emit_event(
        session,
        actor=None,
        event_name=POLLING_CONFLICT_EVENT,
        resource_type="telegram_bot",
        resource_id="polling",
        status="failed",
        payload={
            "reason": reason,
            "source": source,
            "conflict_source": conflict_source,
            "instance_id_masked": mask_instance_id(identifier),
        },
    )
    upsert_recommendation(
        session,
        actor=None,
        recommendation_type=POLLING_CONFLICT_RECOMMENDATION_TYPE,
        title="Stop duplicate Telegram poller",
        description=(
            "Another process is using the same Telegram bot token. Stop the duplicate worker "
            "or rotate the bot token before relying on Telegram updates."
        ),
        severity="critical",
        entity_type="telegram_bot",
        entity_id="polling",
        metadata={"source": source, "conflict_source": conflict_source, "detected_at": now},
    )


def clear_polling_conflict_metadata(metadata: dict | None) -> dict:
    safe = dict(metadata or {})
    safe["polling_conflict_active"] = "false"
    safe["latest_polling_conflict_reason"] = "None"
    return safe


def _metadata_bool(metadata: dict | None, key: str, *, default: bool = False) -> bool:
    value = (metadata or {}).get(key)
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().casefold() in {"1", "true", "yes", "y", "on"}


def _instance_role(metadata: dict | None) -> str:
    return str((metadata or {}).get("service_role") or "").strip().casefold().replace(" ", "_")


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _active_window_seconds(active_seconds: int | None = None) -> int:
    configured = active_seconds if active_seconds is not None else settings.bot_instance_active_seconds
    return max(int(configured or 0), MIN_BOT_INSTANCE_ACTIVE_SECONDS)


def _is_polling_worker_heartbeat(heartbeat: SystemHeartbeat) -> bool:
    metadata = heartbeat.metadata_json or {}
    role = _instance_role(metadata)
    if role in {"api", "web", "api_only", "web_only"}:
        return False
    if not _metadata_bool(metadata, "primary", default=False):
        return False
    if not _metadata_bool(metadata, "polling_allowed", default=False):
        return False
    if not _metadata_bool(metadata, "polling_active", default=False):
        return False
    return True


def classify_bot_instance_heartbeats(
    session: Session,
    *,
    active_seconds: int | None = None,
    mark_stale: bool = True,
) -> BotInstanceHeartbeatClassification:
    window_seconds = _active_window_seconds(active_seconds)
    cutoff = datetime.now(UTC) - timedelta(seconds=window_seconds)
    rows = list(
        session.scalars(
            select(SystemHeartbeat)
            .where(SystemHeartbeat.service_name.like(f"{BOT_INSTANCE_PREFIX}%"))
            .order_by(SystemHeartbeat.last_seen_at.desc())
        ).all()
    )
    active_pollers: list[SystemHeartbeat] = []
    non_polling: list[SystemHeartbeat] = []
    stale: list[SystemHeartbeat] = []
    for heartbeat in rows:
        if _as_utc(heartbeat.last_seen_at) < cutoff or heartbeat.status == "stale":
            stale.append(heartbeat)
            if mark_stale and heartbeat.status in {"healthy", "running", "degraded"}:
                metadata = dict(heartbeat.metadata_json or {})
                metadata["heartbeat_state"] = "stale"
                metadata["stale_after_seconds"] = str(window_seconds)
                heartbeat.status = "stale"
                heartbeat.metadata_json = metadata
            continue
        if heartbeat.status not in {"healthy", "running", "degraded"}:
            non_polling.append(heartbeat)
            continue
        if _is_polling_worker_heartbeat(heartbeat):
            active_pollers.append(heartbeat)
        else:
            non_polling.append(heartbeat)
    if mark_stale:
        session.flush()
    return BotInstanceHeartbeatClassification(
        active_pollers=active_pollers,
        non_polling=non_polling,
        stale=stale,
    )


def active_bot_instance_heartbeats(
    session: Session,
    *,
    active_seconds: int | None = None,
) -> list[SystemHeartbeat]:
    return classify_bot_instance_heartbeats(session, active_seconds=active_seconds).active_pollers


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
    classified = classify_bot_instance_heartbeats(session)
    active = classified.active_pollers
    if current_instance_id is None:
        # API-side diagnostics do not own a polling instance id. In that context, one active
        # bot heartbeat is exactly what we want; only additional active heartbeats are duplicates.
        duplicates = active[1:]
    else:
        duplicates = duplicate_bot_instances(session, current_instance_id=identifier)
    bot_heartbeat = session.scalar(select(SystemHeartbeat).where(SystemHeartbeat.service_name == "bot"))
    metadata = bot_heartbeat.metadata_json if bot_heartbeat else {}
    latest_conflict = session.scalar(
        select(EventLog).where(EventLog.event_type == POLLING_CONFLICT_EVENT).order_by(desc(EventLog.created_at))
    )
    preflight = polling_preflight(current)
    redis_configured = bool(settings.redis_url)
    conflict_active = str(metadata.get("polling_conflict_active", "false")).lower() == "true"
    webhook_delivery_active = (
        str(metadata.get("telegram_delivery_mode", "")).strip().casefold() == "webhook"
        and str(metadata.get("webhook_active", "false")).strip().casefold() == "true"
    )
    active_for_status = [] if webhook_delivery_active else active
    duplicate_count = 0 if webhook_delivery_active else len(duplicates)
    if conflict_active:
        risk = "critical"
    elif not preflight.allowed:
        risk = "blocked"
    elif not active_for_status and not webhook_delivery_active:
        risk = "no_active_polling_owner"
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
        "polling_allowed": metadata.get("polling_allowed", str(preflight.allowed)),
        "polling_active": metadata.get("polling_active", "unknown"),
        "polling_lock_owner": metadata.get("polling_lock_owner", "unknown"),
        "telegram_delivery_mode": metadata.get("telegram_delivery_mode", "polling"),
        "webhook_delivery_active": webhook_delivery_active,
        "service_role": metadata.get("service_role", "unknown"),
        "process_id": metadata.get("process_id", "unknown"),
        "deployment_commit": metadata.get("deployment_commit", settings.git_commit or "unknown"),
        "service_name": metadata.get("service_name", "unknown"),
        "polling_conflict_active": conflict_active,
        "latest_conflict_at": metadata.get(
            "latest_polling_conflict_at",
            latest_conflict.created_at.isoformat() if latest_conflict and latest_conflict.created_at else "None",
        ),
        "latest_conflict_reason": metadata.get("latest_polling_conflict_reason", "None"),
        "latest_conflict_source": metadata.get("latest_polling_conflict_source", "unknown"),
        "db_backend": current.backend,
        "db_durable": current.durable,
        "environment": current.environment,
        "active_instance_count": len(active_for_status),
        "duplicate_instance_count": duplicate_count,
        "non_polling_instance_count": len(classified.non_polling),
        "stale_instance_count": len(classified.stale),
        "active_polling_owners": [
            mask_instance_id(heartbeat.service_name.removeprefix(BOT_INSTANCE_PREFIX))
            for heartbeat in active_for_status
        ],
        "non_polling_instances": [
            {
                "instance": mask_instance_id(heartbeat.service_name.removeprefix(BOT_INSTANCE_PREFIX)),
                "role": _instance_role(heartbeat.metadata_json),
                "polling_active": str((heartbeat.metadata_json or {}).get("polling_active", "unknown")),
                "polling_allowed": str((heartbeat.metadata_json or {}).get("polling_allowed", "unknown")),
                "primary": str((heartbeat.metadata_json or {}).get("primary", "unknown")),
                "last_seen_at": heartbeat.last_seen_at.isoformat() if heartbeat.last_seen_at else "unknown",
            }
            for heartbeat in classified.non_polling[:5]
        ],
        "stale_instances": [
            {
                "instance": mask_instance_id(heartbeat.service_name.removeprefix(BOT_INSTANCE_PREFIX)),
                "role": _instance_role(heartbeat.metadata_json),
                "last_seen_at": heartbeat.last_seen_at.isoformat() if heartbeat.last_seen_at else "unknown",
            }
            for heartbeat in classified.stale[:5]
        ],
        "multiple_active_instances": duplicate_count > 0,
        "risk": risk,
    }
