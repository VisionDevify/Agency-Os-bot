from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.bot_instances import duplicate_bot_instances, polling_preflight
from app.services.crypto import decrypt_secret, encrypt_secret
from app.services.persistence import StorageStatus, storage_status


@dataclass(frozen=True)
class LiveDataSafetyCheck:
    label: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class LiveDataSafetyStatus:
    safe: bool
    checks: list[LiveDataSafetyCheck]

    @property
    def blocking_reasons(self) -> list[str]:
        return [check.detail for check in self.checks if not check.passed]


def _redis_ping() -> bool:
    if not settings.redis_url:
        return False
    try:
        from redis import Redis

        client = Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
        return bool(client.ping())
    except Exception:
        return False


def _encryption_ready() -> bool:
    if not settings.encryption_key.get_secret_value().strip():
        return False
    probe = "fortuna-live-safety-probe"
    return decrypt_secret(encrypt_secret(probe)) == probe


def live_data_safety_status(
    session: Session,
    *,
    current_instance_id: str | None = None,
    storage: StorageStatus | None = None,
    redis_ping: Callable[[], bool] | None = None,
    encryption_ready: Callable[[], bool] | None = None,
) -> LiveDataSafetyStatus:
    current_storage = storage or storage_status()
    preflight = polling_preflight(current_storage)
    duplicates = duplicate_bot_instances(session, current_instance_id=current_instance_id)
    redis_ok = (redis_ping or _redis_ping)()
    encryption_ok = (encryption_ready or _encryption_ready)()

    checks = [
        LiveDataSafetyCheck(
            "PostgreSQL durable",
            current_storage.backend == "postgresql" and current_storage.durable is True,
            "Production storage must be durable PostgreSQL.",
        ),
        LiveDataSafetyCheck(
            "Redis healthy",
            redis_ok,
            "Redis must respond before accepting live proxy credentials.",
        ),
        LiveDataSafetyCheck(
            "Encryption enabled",
            encryption_ok,
            "ENCRYPTION_KEY must be configured and working.",
        ),
        LiveDataSafetyCheck(
            "Single bot instance",
            not duplicates,
            "Only one active polling instance may be running.",
        ),
        LiveDataSafetyCheck(
            "Polling safety",
            preflight.allowed,
            preflight.reason,
        ),
        LiveDataSafetyCheck(
            "No SQLite fallback",
            current_storage.backend != "sqlite_fallback",
            "SQLite emergency storage is not allowed for real credentials.",
        ),
    ]
    return LiveDataSafetyStatus(safe=all(check.passed for check in checks), checks=checks)
