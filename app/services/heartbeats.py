import os
from datetime import UTC, datetime

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.event_log import EventLog
from app.models.reporting import NotificationDeliveryAttempt
from app.models.system import SystemHeartbeat
from app.models.user import User
from app.services.audit import sanitize_details
from app.services.events import emit_event

DEFAULT_SERVICES = ("api", "bot", "db", "redis", "railway_deployment")


def _now() -> datetime:
    return datetime.now(UTC)


def record_heartbeat(
    session: Session,
    *,
    service_name: str,
    status: str = "healthy",
    metadata: dict | None = None,
    actor: User | None = None,
) -> SystemHeartbeat:
    heartbeat = session.scalar(select(SystemHeartbeat).where(SystemHeartbeat.service_name == service_name))
    changed = heartbeat is None or heartbeat.status != status
    safe_metadata = sanitize_details(metadata)
    if heartbeat is None:
        heartbeat = SystemHeartbeat(
            service_name=service_name,
            status=status,
            last_seen_at=_now(),
            metadata_json=safe_metadata,
        )
        session.add(heartbeat)
    else:
        heartbeat.status = status
        heartbeat.last_seen_at = _now()
        heartbeat.metadata_json = {**(heartbeat.metadata_json or {}), **safe_metadata}
    session.flush()
    if changed:
        emit_event(
            session,
            actor=actor,
            event_name="heartbeat.status_changed",
            resource_type="system_heartbeat",
            resource_id=heartbeat.service_name,
            payload={"service_name": heartbeat.service_name, "status": heartbeat.status},
        )
    return heartbeat


def ensure_default_heartbeats(session: Session) -> list[SystemHeartbeat]:
    heartbeats: list[SystemHeartbeat] = []
    for service_name in DEFAULT_SERVICES:
        heartbeat = session.scalar(select(SystemHeartbeat).where(SystemHeartbeat.service_name == service_name))
        if heartbeat is None:
            heartbeat = SystemHeartbeat(
                service_name=service_name,
                status="pending" if service_name == "railway_deployment" else "unknown",
                last_seen_at=_now(),
                metadata_json={"source": "default"},
            )
            session.add(heartbeat)
            session.flush()
        heartbeats.append(heartbeat)
    return heartbeats


def list_heartbeats(session: Session) -> list[SystemHeartbeat]:
    ensure_default_heartbeats(session)
    return list(session.scalars(select(SystemHeartbeat).order_by(SystemHeartbeat.service_name)).all())


def latest_event_logged(session: Session) -> EventLog | None:
    return session.scalar(select(EventLog).order_by(desc(EventLog.created_at), desc(EventLog.id)).limit(1))


def detect_environment() -> str:
    if os.getenv("RAILWAY_ENVIRONMENT") or os.getenv("RAILWAY_PROJECT_ID"):
        return "railway"
    if os.getenv("DATABASE_URL") or os.getenv("REDIS_URL"):
        return "local"
    return "unknown"


def _latest_delivery_attempt(session: Session) -> NotificationDeliveryAttempt | None:
    return session.scalar(
        select(NotificationDeliveryAttempt)
        .order_by(desc(NotificationDeliveryAttempt.attempted_at), desc(NotificationDeliveryAttempt.id))
        .limit(1)
    )


def system_status_summary(session: Session) -> dict:
    heartbeats = {heartbeat.service_name: heartbeat for heartbeat in list_heartbeats(session)}
    railway = heartbeats.get("railway_deployment")
    bot = heartbeats.get("bot")
    api = heartbeats.get("api")
    db = heartbeats.get("db")
    redis = heartbeats.get("redis")
    latest_event = latest_event_logged(session)
    latest_delivery = _latest_delivery_attempt(session)
    failed_notifications = (
        session.scalar(
            select(func.count(NotificationDeliveryAttempt.id)).where(NotificationDeliveryAttempt.status == "failed")
        )
        or 0
    )
    last_heartbeat_at = max(
        (heartbeat.last_seen_at for heartbeat in heartbeats.values() if heartbeat.last_seen_at),
        default=None,
    )
    railway_metadata = railway.metadata_json or {} if railway else {}
    return {
        "environment": detect_environment(),
        "production_status": railway.status if railway else "pending",
        "last_deployment_status": railway_metadata.get("deployment_status", railway.status) if railway else "pending",
        "last_deployment_time": railway_metadata.get("last_deployment_time"),
        "railway_deployment_status": railway.status if railway else "pending",
        "bot_status": bot.status if bot else "unknown",
        "bot_last_seen_at": bot.last_seen_at if bot else None,
        "api_status": api.status if api else "unknown",
        "db_status": db.status if db else "unknown",
        "redis_status": redis.status if redis else "unknown",
        "last_heartbeat_at": last_heartbeat_at,
        "last_delivery_attempt_id": latest_delivery.id if latest_delivery else None,
        "last_delivery_status": latest_delivery.status if latest_delivery else "none",
        "last_delivery_event_type": latest_delivery.event_type if latest_delivery else "none",
        "last_delivery_attempted_at": latest_delivery.attempted_at if latest_delivery else None,
        "failed_notification_count": failed_notifications,
        "latest_event_type": latest_event.event_type if latest_event else "none",
        "latest_event_at": latest_event.created_at if latest_event else None,
    }
