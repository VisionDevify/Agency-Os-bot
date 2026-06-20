from __future__ import annotations

import os
from typing import Any

from app.core.config import settings

_SENSITIVE_MARKERS = (
    "secret",
    "token",
    "password",
    "passwd",
    "database_url",
    "redis_url",
    "telegram_bot_token",
    "app_secret_key",
    "encryption_key",
    "private_key",
)


def safe_metadata_value(value: Any, *, default: str = "unknown") -> str:
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    lowered = text.casefold()
    if "\n" in text or "\r" in text or "://" in text or "=" in text:
        return default
    if any(marker in lowered for marker in _SENSITIVE_MARKERS):
        return default
    return text[:96]


def safe_build_metadata(*, environment: str | None = None, alembic_revision: str | None = None) -> dict[str, str]:
    return {
        "app_name": safe_metadata_value(settings.app_display_name),
        "environment": safe_metadata_value(environment or settings.environment),
        "git_commit": safe_metadata_value(
            settings.git_commit or os.environ.get("RAILWAY_GIT_COMMIT_SHA")
        ),
        "build_version": safe_metadata_value(settings.app_version),
        "deployed_at": safe_metadata_value(settings.deployed_at),
        "alembic_revision": safe_metadata_value(alembic_revision),
    }
