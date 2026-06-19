from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from app.core.config import settings
from app.services.build_metadata import safe_build_metadata

PRODUCTION_ENV_VALUES = {"production", "prod", "railway"}
SQLITE_SCHEMES = {"sqlite", "sqlite+pysqlite", "sqlite+aiosqlite"}
POSTGRES_SCHEMES = {"postgres", "postgresql", "postgresql+psycopg", "postgresql+psycopg2", "postgresql+asyncpg"}


@dataclass(frozen=True)
class StorageStatus:
    backend: str
    display_backend: str
    scheme: str
    environment: str
    is_production: bool
    durable: bool | None
    sqlite_fallback_allowed: bool
    risk: str
    warning: str | None
    file_location: str

    @property
    def is_sqlite(self) -> bool:
        return self.scheme in SQLITE_SCHEMES

    @property
    def is_postgresql(self) -> bool:
        return self.scheme in POSTGRES_SCHEMES


def runtime_environment(environ: dict[str, str] | None = None, configured: str | None = None) -> str:
    env = environ if environ is not None else os.environ
    explicit = (configured or settings.environment or env.get("APP_ENV") or env.get("ENVIRONMENT") or "").strip().lower()
    if explicit in PRODUCTION_ENV_VALUES:
        return "production"
    if env.get("RAILWAY_ENVIRONMENT") or env.get("RAILWAY_PROJECT_ID") or env.get("RAILWAY_SERVICE_ID"):
        return "railway"
    if explicit:
        return explicit
    return "local"


def is_production_environment(environment: str) -> bool:
    return environment in {"production", "railway"}


def database_scheme(database_url: str | None = None) -> str:
    value = (database_url if database_url is not None else settings.database_url).strip()
    if not value:
        return "unconfigured"
    if "://" not in value:
        return value.split(":", 1)[0].lower()
    return urlsplit(value).scheme.lower()


def sqlite_location_label(database_url: str | None = None) -> str:
    value = (database_url if database_url is not None else settings.database_url).strip()
    if not value or not database_scheme(value).startswith("sqlite"):
        return "Not applicable"
    if "/tmp/" in value.replace("\\", "/"):
        return "Railway/container temporary filesystem"
    if ":memory:" in value:
        return "In-memory SQLite"
    return "Local container filesystem"


def storage_status(
    *,
    database_url: str | None = None,
    allow_sqlite_fallback: bool | None = None,
    environment: str | None = None,
    environ: dict[str, str] | None = None,
) -> StorageStatus:
    url = settings.database_url if database_url is None else database_url
    env_name = environment or runtime_environment(environ)
    is_prod = is_production_environment(env_name)
    allow = settings.allow_sqlite_fallback if allow_sqlite_fallback is None else allow_sqlite_fallback
    scheme = database_scheme(url)

    if scheme in POSTGRES_SCHEMES:
        return StorageStatus(
            backend="postgresql",
            display_backend="PostgreSQL",
            scheme=scheme,
            environment=env_name,
            is_production=is_prod,
            durable=True,
            sqlite_fallback_allowed=allow,
            risk="ready",
            warning=None,
            file_location="Not applicable",
        )

    if scheme in SQLITE_SCHEMES:
        if is_prod and not allow:
            risk = "unsafe"
            warning = "sqlite_fallback_blocked"
        elif is_prod:
            risk = "degraded"
            warning = "production_persistence_degraded"
        else:
            risk = "local"
            warning = "local_sqlite"
        return StorageStatus(
            backend="sqlite_fallback",
            display_backend="SQLite Emergency",
            scheme=scheme,
            environment=env_name,
            is_production=is_prod,
            durable=False,
            sqlite_fallback_allowed=allow,
            risk=risk,
            warning=warning,
            file_location=sqlite_location_label(url),
        )

    if scheme == "unconfigured":
        return StorageStatus(
            backend="unconfigured",
            display_backend="Unconfigured",
            scheme=scheme,
            environment=env_name,
            is_production=is_prod,
            durable=False,
            sqlite_fallback_allowed=allow,
            risk="unsafe" if is_prod else "degraded",
            warning="database_url_missing",
            file_location="Not applicable",
        )

    return StorageStatus(
        backend="other",
        display_backend=scheme,
        scheme=scheme,
        environment=env_name,
        is_production=is_prod,
        durable=None,
        sqlite_fallback_allowed=allow,
        risk="degraded",
        warning="unknown_database_backend",
        file_location="Not applicable",
    )


def enforce_sqlite_fallback_policy(status: StorageStatus | None = None) -> None:
    current = status or storage_status()
    if current.backend == "sqlite_fallback" and current.is_production and not current.sqlite_fallback_allowed:
        raise RuntimeError(
            "SQLite fallback is blocked in production. Configure PostgreSQL, or set "
            "ALLOW_SQLITE_FALLBACK=true only for an explicit emergency mode."
        )


def health_payload(
    *,
    storage: StorageStatus | None = None,
    db_connected: bool,
    redis_status: str,
    alembic_revision: str | None = None,
) -> dict[str, object]:
    current = storage or storage_status()
    warnings: list[str] = []
    overall = "ok"

    if db_connected:
        db_status = "healthy"
    else:
        db_status = "unhealthy"
        overall = "degraded"
        warnings.append("database_unavailable")

    if current.backend == "sqlite_fallback" and current.is_production:
        db_status = "degraded" if db_connected else "unhealthy"
        overall = "degraded"
        warnings.append(current.warning or "production_persistence_degraded")
    elif current.backend in {"unconfigured", "other"}:
        db_status = "degraded" if db_connected else "unhealthy"
        overall = "degraded"
        if current.warning:
            warnings.append(current.warning)

    if current.is_production and redis_status != "healthy":
        overall = "degraded"
        warnings.append("redis_unavailable")

    payload: dict[str, object] = {
        **safe_build_metadata(environment=current.environment, alembic_revision=alembic_revision),
        "status": overall,
        "api": "healthy",
        "db": db_status,
        "db_backend": current.backend,
        "db_driver": current.scheme,
        "db_durable": current.durable,
        "redis": redis_status,
    }
    if current.warning:
        payload["storage_warning"] = current.warning
    if warnings:
        payload["warning"] = ",".join(sorted(set(warnings)))
    return payload
