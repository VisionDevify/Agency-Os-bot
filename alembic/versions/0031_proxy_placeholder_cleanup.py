"""proxy placeholder cleanup

Revision ID: 0031_proxy_placeholder_cleanup
Revises: 0030_notification_routing_mode
Create Date: 2026-06-19
"""

from __future__ import annotations

import json
from typing import Any

from alembic import op
from sqlalchemy import text


revision: str = "0031_proxy_placeholder_cleanup"
down_revision: str | None = "0030_notification_routing_mode"
branch_labels: str | None = None
depends_on: str | None = None


PLACEHOLDER_PROVIDERS = {"placeholder", "fake", "demo", "test"}
PLACEHOLDER_PORTS = set(range(8000, 8010))


def _metadata(value: Any) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _is_truthy(value: Any) -> bool:
    return str(value).casefold() in {"1", "true", "yes", "on"}


def _is_placeholder(row: dict) -> bool:
    metadata = _metadata(row.get("metadata_json"))
    provider = (row.get("provider") or "").casefold()
    host = (row.get("host") or "").casefold()
    name = (row.get("name") or "").casefold()
    if _is_truthy(metadata.get("is_demo")) or _is_truthy(metadata.get("is_placeholder")) or _is_truthy(metadata.get("placeholder")):
        return True
    if provider in PLACEHOLDER_PROVIDERS or any(marker in provider for marker in ("placeholder", "demo", "fake", "test")):
        return True
    if "placeholder" in host or host.endswith(".local"):
        return True
    if "placeholder" in name:
        return True
    if (row.get("port") in PLACEHOLDER_PORTS) and (
        host.startswith("proxy-") or "placeholder" in name or provider in {"provider", "placeholder"}
    ):
        return True
    required = (
        row.get("host"),
        row.get("port"),
        row.get("base_username"),
        row.get("session_suffix"),
        row.get("encrypted_password"),
    )
    return any(value in (None, "", 0) for value in required)


def _count(conn, query: str, proxy_id: int) -> int:
    return int(conn.execute(text(query), {"id": proxy_id}).scalar() or 0)


def _insert_audit(conn, *, action: str, proxy_id: int, provider: str) -> None:
    conn.execute(
        text(
            """
            insert into audit_logs (actor_user_id, action, resource_type, resource_id, status, details)
            values (null, :action, 'proxy', :resource_id, 'success', :details)
            """
        ),
        {
            "action": action,
            "resource_id": str(proxy_id),
            "details": json.dumps({"provider": provider, "source": "0031_proxy_placeholder_cleanup"}),
        },
    )


def upgrade() -> None:
    conn = op.get_bind()
    rows = [dict(row) for row in conn.execute(text("select * from proxies")).mappings().all()]
    archived = 0
    deleted = 0
    for row in rows:
        if not _is_placeholder(row):
            continue
        proxy_id = int(row["id"])
        assigned = _count(conn, "select count(*) from accounts where assigned_proxy_id = :id and status != 'archived'", proxy_id)
        rotations = _count(conn, "select count(*) from proxy_rotation_history where proxy_id = :id", proxy_id)
        checks = _count(conn, "select count(*) from proxy_health_check_results where proxy_id = :id", proxy_id)
        if assigned == 0 and rotations == 0 and checks == 0:
            _insert_audit(conn, action="proxy.placeholder.removed", proxy_id=proxy_id, provider=row.get("provider") or "unknown")
            conn.execute(text("delete from proxies where id = :id"), {"id": proxy_id})
            deleted += 1
            continue
        metadata = _metadata(row.get("metadata_json"))
        metadata["archived"] = True
        metadata["is_placeholder"] = True
        metadata["archive_reason"] = "placeholder_cleanup_migration"
        conn.execute(
            text("update proxies set status = 'disabled', metadata_json = :metadata where id = :id"),
            {"id": proxy_id, "metadata": json.dumps(metadata)},
        )
        _insert_audit(conn, action="proxy.placeholder.archived", proxy_id=proxy_id, provider=row.get("provider") or "unknown")
        archived += 1
    if archived or deleted:
        conn.execute(
            text(
                """
                insert into event_logs (event_type, actor_user_id, entity_type, entity_id, metadata_json)
                values ('proxy.placeholder.hidden', null, 'proxy', null, :metadata)
                """
            ),
            {"metadata": json.dumps({"archived": archived, "deleted": deleted, "source": revision})},
        )


def downgrade() -> None:
    # Data cleanup is intentionally not reversible.
    pass
