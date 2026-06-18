from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterable

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog
from app.models.callback_error import CallbackErrorLog
from app.models.event_log import EventLog
from app.models.friction import FrictionItem
from app.models.recommendation import Recommendation
from app.models.user import User
from app.services.audit import sanitize_details
from app.services.auth import audit_action
from app.services.events import emit_event
from app.services.friction import create_friction_item
from app.services.recommendations import upsert_recommendation
from app.services.permissions import PermissionPrincipal, RoleName


MAX_ERROR_LENGTH = 600
MAX_CALLBACKS_CHECKED = 80
SAFE_SMOKE_PAGES = {
    "accounts",
    "accounts:attention",
    "accounts:by_model",
    "accounts:by_platform",
    "accounts:list",
    "agency_activation",
    "assistant_next",
    "callback_failure_review",
    "coo:readiness",
    "debug_last_error",
    "first_workspace",
    "help",
    "help_copilot",
    "menu",
    "models",
    "models:dashboard",
    "models:list",
    "notification_group_pilot",
    "notification_group_setup",
    "notification_targets",
    "opportunities",
    "opportunities:command",
    "opportunities:creators",
    "opportunities:list",
    "opportunities:posts",
    "owner_advanced",
    "production_status",
    "proxies",
    "proxies:add",
    "proxies:advanced",
    "proxies:entry_check",
    "proxies:list",
    "proxies:missing",
    "proxies:olympix",
    "proxies:olympix:manual",
    "proxies:olympix:paste",
    "proxies:real_check_pilot",
    "settings",
    "setup_progress",
    "start_here",
    "today_priorities",
    "ui_self_test",
}


@dataclass(frozen=True)
class CallbackHealthFailure:
    page: str
    exception_type: str
    message: str


@dataclass
class CallbackHealthReport:
    working: list[str] = field(default_factory=list)
    failing: list[CallbackHealthFailure] = field(default_factory=list)
    untested: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.working) + len(self.failing) + len(self.untested)

    @property
    def score(self) -> int:
        tested = len(self.working) + len(self.failing)
        if tested == 0:
            return 0
        return round((len(self.working) / tested) * 100)


@dataclass(frozen=True)
class CallbackFailureReviewItem:
    error_id: int
    page: str
    callback_data: str
    exception_type: str
    root_cause: str
    recommended_fix: str
    created_at: object


@dataclass(frozen=True)
class CallbackFailureReview:
    items: list[CallbackFailureReviewItem]
    friction_count: int
    recommendation_count: int
    audit_count: int
    event_count: int


SECRET_PATTERNS = (
    re.compile(r"(?i)(token|secret|password|credential|database_url|redis_url)=([^\\s]+)"),
    re.compile(r"(?i)(postgres(?:ql)?|redis)://[^\\s]+"),
    re.compile(r"(?i)host\\.olympix\\.io:\\d+:[^\\s:]+:[^\\s]+"),
)


def safe_exception_message(exc: BaseException) -> str:
    raw = str(exc).strip() or type(exc).__name__
    for pattern in SECRET_PATTERNS:
        raw = pattern.sub(lambda match: f"{match.group(1)}=[redacted]" if match.lastindex else "[redacted]", raw)
    raw = raw.replace("\n", " ").replace("\r", " ")
    return raw[:MAX_ERROR_LENGTH]


def callback_page(callback_data: str | None) -> str | None:
    if not callback_data:
        return None
    return callback_data.removeprefix("nav:") if callback_data.startswith("nav:") else callback_data


def log_callback_failure(
    session: Session,
    *,
    actor: User | None,
    callback_data: str | None,
    page: str | None,
    exc: BaseException,
    affected_screen: str | None = None,
) -> CallbackErrorLog:
    safe_message = safe_exception_message(exc)
    error = CallbackErrorLog(
        telegram_user_id=actor.telegram_id if actor else None,
        user_id=actor.id if actor else None,
        callback_data=(callback_data or "")[:260] or None,
        page=(page or "")[:220] or None,
        affected_screen=(affected_screen or page or "unknown")[:220],
        exception_type=type(exc).__name__[:120],
        error_message=safe_message,
    )
    session.add(error)
    session.flush()
    issue = f"Button failed on {page or 'unknown'}: {type(exc).__name__}."
    create_friction_item(
        session,
        screen=(affected_screen or page or "unknown")[:120],
        issue=issue,
        severity="high",
        fix_recommendation="Review the callback route and renderer; keep fallback screen active until fixed.",
    )
    recommendation = upsert_recommendation(
        session,
        actor=actor,
        recommendation_type="callback_failure",
        title="Button Needs Repair",
        description=f"Fortuna caught a failing button for {page or 'unknown'} and kept the bot alive.",
        severity="warning",
        entity_type="telegram_callback",
        entity_id=(page or callback_data or "unknown")[:120],
        metadata={
            "callback_error_log_id": error.id,
            "exception_type": type(exc).__name__,
            "affected_screen": affected_screen or page,
        },
    )
    audit_action(
        session,
        actor=actor,
        action="callback.failed",
        resource_type="telegram_callback",
        resource_id=(page or callback_data or "unknown")[:120],
        status="failed",
        details={
            "callback_error_log_id": error.id,
            "recommendation_id": recommendation.id,
            "exception_type": type(exc).__name__,
            "affected_screen": affected_screen or page,
        },
    )
    emit_event(
        session,
        actor=actor,
        event_name="callback.failed",
        resource_type="telegram_callback",
        resource_id=(page or callback_data or "unknown")[:120],
        status="failed",
        payload={
            "callback_error_log_id": error.id,
            "exception_type": type(exc).__name__,
            "affected_screen": affected_screen or page,
        },
    )
    return error


def latest_callback_error(session: Session) -> CallbackErrorLog | None:
    return session.scalar(
        select(CallbackErrorLog)
        .order_by(desc(CallbackErrorLog.created_at), desc(CallbackErrorLog.id))
        .limit(1)
    )


def recent_callback_errors(session: Session, *, limit: int = 10) -> list[CallbackErrorLog]:
    return list(
        session.scalars(
            select(CallbackErrorLog)
            .order_by(desc(CallbackErrorLog.created_at), desc(CallbackErrorLog.id))
            .limit(limit)
        ).all()
    )


def _classify_root_cause(error: CallbackErrorLog) -> tuple[str, str]:
    exception = error.exception_type
    page = error.page or "unknown"
    message = error.error_message.casefold()
    if exception == "PermissionError":
        return (
            "Permission route blocked the callback.",
            "Confirm the button is hidden from users without access or that the permission message is clear.",
        )
    if exception in {"ValueError", "TypeError", "IndexError", "KeyError"}:
        return (
            "Callback payload or renderer input was malformed.",
            f"Add a regression test for `{page}` and make the renderer handle missing or invalid data.",
        )
    if "database" in message or "integrity" in message or exception.endswith("Error") and "sql" in message:
        return (
            "Database action failed while loading the button.",
            "Check the service action, constraints, and transaction rollback path for this callback.",
        )
    if "telegram" in message or "message" in message and "edit" in message:
        return (
            "Telegram message update failed.",
            "Keep the edit-or-send fallback active and inspect whether the screen text/markup is too large or stale.",
        )
    if page.startswith("proxy"):
        return (
            "Proxy screen or proxy action failed.",
            "Review the proxy route, ensure secrets stay masked, and add a focused proxy callback regression test.",
        )
    return (
        "Renderer or action raised an unexpected exception.",
        f"Reproduce `{page}` through `screen_for_page`, fix the failing route, and add a regression test.",
    )


def callback_failure_review(session: Session, *, limit: int = 10) -> CallbackFailureReview:
    errors = recent_callback_errors(session, limit=limit)
    items: list[CallbackFailureReviewItem] = []
    for error in errors:
        root_cause, recommended_fix = _classify_root_cause(error)
        items.append(
            CallbackFailureReviewItem(
                error_id=error.id,
                page=error.page or "unknown",
                callback_data=error.callback_data or "unknown",
                exception_type=error.exception_type,
                root_cause=root_cause,
                recommended_fix=recommended_fix,
                created_at=error.created_at,
            )
        )
    return CallbackFailureReview(
        items=items,
        friction_count=session.scalar(select(func.count(FrictionItem.id))) or 0,
        recommendation_count=session.scalar(
            select(func.count(Recommendation.id)).where(Recommendation.recommendation_type == "callback_failure")
        )
        or 0,
        audit_count=session.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "callback.failed")) or 0,
        event_count=session.scalar(select(func.count(EventLog.id)).where(EventLog.event_type == "callback.failed")) or 0,
    )


def _callbacks_from_markup(markup) -> Iterable[str]:
    if markup is None:
        return ()
    callbacks: list[str] = []
    for row in getattr(markup, "inline_keyboard", []) or []:
        for button in row:
            data = getattr(button, "callback_data", None)
            if data:
                callbacks.append(str(data))
    return callbacks


def _is_mutating_or_unsafe_page(page: str) -> bool:
    if page not in SAFE_SMOKE_PAGES:
        return True
    parts = page.split(":")
    unsafe_tokens = {
        "approve",
        "archive",
        "assign",
        "assign_best",
        "block",
        "clear",
        "complete",
        "connected",
        "create",
        "daily_cycle",
        "deny",
        "disable",
        "enable_real",
        "finish",
        "generate",
        "needs_login",
        "not_needed",
        "pause",
        "reactivate",
        "reject",
        "remove",
        "request_approval",
        "resolve",
        "resume",
        "retire",
        "rollback",
        "rotate",
        "rotate_until_match",
        "run",
        "run_due",
        "run_now",
        "scan",
        "send_hq",
        "send_ops",
        "send_owner",
        "send_test",
        "set",
        "simulate",
        "start",
        "toggle",
    }
    if any(part in unsafe_tokens for part in parts):
        return True
    if page in {
        "automations:templates",
        "automations:create",
        "demo:create",
        "demo:clear",
        "models:create",
        "notification_targets:add",
        "notification_targets:add_current",
        "notification_targets:routing_test",
        "setup:cleanup:archive_placeholders",
        "ui_self_test:run",
    }:
        return True
    if page.startswith("proxy:") and any(part in {"check", "rotated", "rollback_result"} for part in parts):
        return True
    if page.startswith("opportunity:") and any(part in {"strategies", "result"} for part in parts):
        return True
    if page.startswith("help_feedback:"):
        return True
    return False


def run_callback_health_smoke_test(session: Session, *, actor: User) -> CallbackHealthReport:
    from app.bot.navigation import screen_for_page

    principal = PermissionPrincipal(telegram_id=actor.telegram_id, is_owner=True, role=RoleName.OWNER)
    queue: list[str] = [
        "menu",
        "start_here",
        "today_priorities",
        "setup_progress",
        "first_workspace",
        "models",
        "accounts",
        "proxies",
        "opportunities",
        "help",
        "settings",
        "owner_advanced",
    ]
    seen: set[str] = set()
    report = CallbackHealthReport()

    while queue and len(seen) < MAX_CALLBACKS_CHECKED:
        page = queue.pop(0)
        if page in seen:
            continue
        seen.add(page)
        if _is_mutating_or_unsafe_page(page):
            report.untested.append(page)
            continue
        try:
            screen = screen_for_page(page, principal, session=session, user=actor)
            if not getattr(screen, "text", "").strip():
                raise ValueError("screen returned empty text")
            if getattr(screen, "reply_markup", None) is None:
                raise ValueError("screen returned no buttons")
            report.working.append(page)
            for callback in _callbacks_from_markup(screen.reply_markup):
                if not callback.startswith("nav:"):
                    report.untested.append(callback)
                    continue
                target = callback_page(callback)
                if target and target not in SAFE_SMOKE_PAGES:
                    if target not in report.untested:
                        report.untested.append(target)
                    continue
                if target and target not in seen and target not in queue:
                    queue.append(target)
        except Exception as exc:
            report.failing.append(
                CallbackHealthFailure(
                    page=page,
                    exception_type=type(exc).__name__,
                    message=safe_exception_message(exc),
                )
            )
            log_callback_failure(
                session,
                actor=actor,
                callback_data=f"nav:{page}",
                page=page,
                exc=exc,
                affected_screen=page,
            )

    return report
