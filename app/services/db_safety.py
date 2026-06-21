from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Callable, TypeVar

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.services.audit import sanitize_details

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass(frozen=True)
class SideEffectResult:
    name: str
    ok: bool
    safe_error_summary: str | None = None
    table: str | None = None
    constraint: str | None = None
    column: str | None = None


def normalize_db_error(exc: BaseException) -> dict[str, str | None]:
    """Return safe, non-secret database error metadata for diagnostics."""
    message = f"{getattr(exc, 'orig', '')} {exc}"
    summary = message.replace("\n", " ").replace("\r", " ")
    constraint = None
    table = None
    column = None
    match = re.search(r'violates check constraint "([^"]+)"', summary)
    if match:
        constraint = match.group(1)
    match = re.search(r'duplicate key value violates unique constraint "([^"]+)"', summary)
    if match:
        constraint = match.group(1)
    match = re.search(r'null value in column "([^"]+)" of relation "([^"]+)"', summary)
    if match:
        column = match.group(1)
        table = match.group(2)
    match = re.search(r"INSERT INTO ([a-zA-Z0-9_]+)", summary)
    if match:
        table = table or match.group(1)
    safe = sanitize_details({"summary": summary[:500], "table": table, "constraint": constraint, "column": column})
    return {
        "summary": str(safe.get("summary") or type(exc).__name__)[:500],
        "table": table,
        "constraint": constraint,
        "column": column,
    }


def safe_db_side_effect(session: Session, name: str, fn: Callable[[], T]) -> tuple[T | None, SideEffectResult]:
    """Run a best-effort DB side effect inside a savepoint.

    Callback screens must still render when audit, event, memory, AI-audit, or
    friction writes fail. This helper keeps those writes out of the critical
    render path and rolls back only the side effect.
    """
    nested = None
    try:
        nested = session.begin_nested()
        value = fn()
        session.flush()
        nested.commit()
        return value, SideEffectResult(name=name, ok=True)
    except (IntegrityError, SQLAlchemyError) as exc:
        if nested is not None:
            try:
                nested.rollback()
            except Exception:
                session.rollback()
        details = normalize_db_error(exc)
        logger.warning(
            "Database side effect failed: %s table=%s constraint=%s column=%s",
            name,
            details.get("table"),
            details.get("constraint"),
            details.get("column"),
        )
        return None, SideEffectResult(
            name=name,
            ok=False,
            safe_error_summary=details.get("summary"),
            table=details.get("table"),
            constraint=details.get("constraint"),
            column=details.get("column"),
        )
    except Exception as exc:
        if nested is not None:
            try:
                nested.rollback()
            except Exception:
                session.rollback()
        logger.warning("Non-critical DB side effect failed: %s: %s", name, type(exc).__name__)
        return None, SideEffectResult(name=name, ok=False, safe_error_summary=type(exc).__name__)
