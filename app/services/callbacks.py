from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
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
from app.services.db_safety import normalize_db_error, safe_db_side_effect
from app.services.events import emit_event
from app.services.friction import create_friction_item
from app.services.issue_lifecycle import IssueLifecycleView, IssueRevalidationEngine, IssueRevalidationResult
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
    "agency_awareness",
    "agency_awareness:active",
    "agency_awareness:missing",
    "agency_awareness:not_connected",
    "ai_brain",
    "ai_brain:critic",
    "ai_brain:details",
    "ai_brain:settings",
    "assistant_next",
    "button_health",
    "callback_failure_review",
    "callback_failure_review:problems",
    "callback_failure_review:history",
    "callback_failure_review:details",
    "coo:readiness",
    "coo:briefing",
    "command_center",
    "command_center:intelligence",
    "command_center:operations",
    "command_center:systems",
    "command_center:admin",
    "command_center:scores",
    "command_center:score:agency_os",
    "command_center:score:intelligence",
    "command_center:score:team_readiness",
    "command_center:score:revenue_intelligence",
    "command_center:score:recovery_safety",
    "command_center:score:reliability",
    "command_center:score:agency_visibility",
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
    "notification_routing",
    "notification_targets",
    "opportunities",
    "opportunities:command",
    "opportunities:creators",
    "opportunities:list",
    "opportunities:posts",
    "owner_advanced",
    "prediction:preview",
    "prediction:preview:details",
    "prediction:feedback:helpful",
    "prediction:feedback:not_helpful",
    "prediction:feedback:remind_later",
    "prediction:feedback:dismissed",
    "prediction:outcome:right",
    "prediction:outcome:wrong",
    "prediction:outcome:add_evidence",
    "prediction:outcome:still_pending",
    "platforms",
    "platforms:details",
    "platforms:instagram",
    "platforms:instagram:connection",
    "platforms:instagram:stats",
    "platforms:notifications",
    "platforms:alert_health",
    "platforms:alert_health:details",
    "platforms:alert_routing",
    "platforms:notifications:email",
    "platforms:notifications:instagram",
    "platforms:notifications:intelligence",
    "platforms:notifications:onlyfans",
    "platforms:notifications:system_alerts",
    "platforms:notifications:telegram",
    "platforms:notifications:x",
    "platforms:onlyfans",
    "platforms:onlyfans:connection",
    "platforms:onlyfans:stats",
    "platforms:x",
    "platforms:x:connection",
    "platforms:x:stats",
    "production_status",
    "production_observability",
    "recovery_center",
    "recovery:history",
    "recovery:storage",
    "recovery:storage:s3",
    "recovery:restore:test",
    "reliability",
    "reliability:details",
    "reliability:history",
    "reliability:jobs",
    "reliability:slow",
    "reliability:verify",
    "reality:check",
    "reality:check:details",
    "reality:outcomes",
    "reality:calibration",
    "reality:accuracy",
    "decision:review",
    "decision:review:details",
    "decision:timeline",
    "owner_validation:correct",
    "owner_validation:incorrect",
    "owner_validation:partially_correct",
    "owner_validation:too_early",
    "owner_validation:add_evidence",
    "evidence:notes",
    "evidence:notes:record",
    "knowledge:memory",
    "knowledge:memory:create",
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
    "search",
    "search:history",
    "search:settings",
    "setup_progress",
    "start_here",
    "today_priorities",
    "ui_self_test",
    "intelligence:quality",
    "intelligence:quality:categories",
    "intelligence:quality:details",
    "intelligence:quality:trends",
    "intelligence:quality:trends:details",
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
    lifecycle_status: str = "active"
    evidence_summary: str = "Failure is still active until revalidated."
    next_action: str = "Run Button Health."
    first_seen_at: object | None = None
    last_seen_at: object | None = None
    fixed_by_commit: str | None = None
    revalidated_at: object | None = None
    revalidated_commit: str | None = None


@dataclass(frozen=True)
class CallbackFailureReview:
    items: list[CallbackFailureReviewItem]
    active_items: list[CallbackFailureReviewItem]
    new_since_deploy_items: list[CallbackFailureReviewItem]
    validating_items: list[CallbackFailureReviewItem]
    resolved_items: list[CallbackFailureReviewItem]
    historical_items: list[CallbackFailureReviewItem]
    friction_count: int
    recommendation_count: int
    active_recommendation_count: int
    resolved_recommendation_count: int
    audit_count: int
    event_count: int
    lifecycle_summary: IssueRevalidationResult
    latest_deploy_commit: str | None = None


SECRET_PATTERNS = (
    re.compile(r"(?i)(token|secret|password|credential|database_url|redis_url)=([^\\s]+)"),
    re.compile(r"(?i)(postgres(?:ql)?|redis)://[^\\s]+"),
    re.compile(r"(?i)host\\.olympix\\.io:\\d+:[^\\s:]+:[^\\s]+"),
)


def safe_exception_message(exc: BaseException) -> str:
    if exc.__class__.__name__ == "IntegrityError":
        details = normalize_db_error(exc)
        parts = ["IntegrityError"]
        if details.get("table"):
            parts.append(f"table={details['table']}")
        if details.get("constraint"):
            parts.append(f"constraint={details['constraint']}")
        if details.get("column"):
            parts.append(f"column={details['column']}")
        return " ".join(parts)[:MAX_ERROR_LENGTH]
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
    safe_db_side_effect(
        session,
        "callback_failure.friction",
        lambda: create_friction_item(
            session,
            screen=(affected_screen or page or "unknown")[:120],
            issue=issue,
            severity="high",
            fix_recommendation="Review the callback route and renderer; keep fallback screen active until fixed.",
        ),
    )
    recommendation, _ = safe_db_side_effect(
        session,
        "callback_failure.recommendation",
        lambda: upsert_recommendation(
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
        ),
    )
    recommendation_id = getattr(recommendation, "id", None)
    safe_db_side_effect(
        session,
        "callback_failure.audit",
        lambda: audit_action(
            session,
            actor=actor,
            action="callback.failed",
            resource_type="telegram_callback",
            resource_id=(page or callback_data or "unknown")[:120],
            status="failed",
            details={
                "callback_error_log_id": error.id,
                "recommendation_id": recommendation_id,
                "exception_type": type(exc).__name__,
                "affected_screen": affected_screen or page,
            },
        ),
    )
    safe_db_side_effect(
        session,
        "callback_failure.event",
        lambda: emit_event(
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
        ),
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


def _review_item_from_error(error: CallbackErrorLog, lifecycle: IssueLifecycleView) -> CallbackFailureReviewItem:
    root_cause, recommended_fix = _classify_root_cause(error)
    return CallbackFailureReviewItem(
        error_id=error.id,
        page=error.page or "unknown",
        callback_data=error.callback_data or "unknown",
        exception_type=error.exception_type,
        root_cause=root_cause,
        recommended_fix=recommended_fix,
        created_at=error.created_at,
        lifecycle_status=lifecycle.status,
        evidence_summary=lifecycle.evidence_summary,
        next_action=lifecycle.next_action,
        first_seen_at=lifecycle.first_seen_at,
        last_seen_at=lifecycle.last_seen_at,
        fixed_by_commit=lifecycle.fixed_by_commit,
        revalidated_at=lifecycle.revalidated_at,
        revalidated_commit=lifecycle.revalidated_commit,
    )


def _datetime_after(value: object | None, boundary: datetime | None) -> bool:
    if value is None or boundary is None or not isinstance(value, datetime):
        return False
    left = value.replace(tzinfo=UTC) if value.tzinfo is None else value
    right = boundary.replace(tzinfo=UTC) if boundary.tzinfo is None else boundary
    return left > right


def _parse_iso_datetime(value: object | None) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def callback_failure_review(
    session: Session,
    *,
    limit: int = 10,
    working_pages: Iterable[str] | None = None,
    failing_pages: Iterable[str] | None = None,
    revalidated_at: datetime | None = None,
    current_commit: str | None = None,
) -> CallbackFailureReview:
    errors = recent_callback_errors(session, limit=limit)
    working_set = set(working_pages or ())
    failing_set = set(failing_pages or ())
    resolved_recommendations = list(
        session.scalars(
            select(Recommendation).where(
                Recommendation.recommendation_type == "callback_failure",
                Recommendation.entity_type == "telegram_callback",
                Recommendation.status == "resolved",
            )
        ).all()
    )
    resolved_pages = {rec.entity_id for rec in resolved_recommendations if rec.entity_id}
    working_set.update(resolved_pages)
    resolved_revalidated_at = max(
        (
            parsed
            for rec in resolved_recommendations
            if (parsed := _parse_iso_datetime((rec.metadata_json or {}).get("revalidated_at"))) is not None
        ),
        default=None,
    )
    effective_revalidated_at = revalidated_at or resolved_revalidated_at
    engine = IssueRevalidationEngine(current_commit=current_commit, revalidated_at=effective_revalidated_at)
    items: list[CallbackFailureReviewItem] = []
    lifecycle_views: list[IssueLifecycleView] = []
    for error in errors:
        lifecycle = engine.classify_callback_error(error, working_pages=working_set, failing_pages=failing_set)
        lifecycle_views.append(lifecycle)
        items.append(_review_item_from_error(error, lifecycle))
    fixed_pages = {view.source for view in lifecycle_views if view.status in {"resolved", "historical"}}
    if fixed_pages:
        engine.resolve_callback_recommendations(session, fixed_pages=fixed_pages)
    lifecycle_summary = engine.summarize(lifecycle_views)
    active_items = [item for item in items if item.lifecycle_status in {"active", "reappeared"}]
    new_since_deploy_items = [
        item
        for item in active_items
        if _datetime_after(item.created_at, effective_revalidated_at)
    ]
    validating_items = [item for item in items if item.lifecycle_status == "validating"]
    resolved_items = [item for item in items if item.lifecycle_status == "resolved"]
    historical_items = [item for item in items if item.lifecycle_status == "historical"]
    all_recommendation_count = (
        session.scalar(select(func.count(Recommendation.id)).where(Recommendation.recommendation_type == "callback_failure"))
        or 0
    )
    active_recommendation_count = (
        session.scalar(
            select(func.count(Recommendation.id)).where(
                Recommendation.recommendation_type == "callback_failure",
                Recommendation.status.in_(("open", "acknowledged")),
            )
        )
        or 0
    )
    resolved_recommendation_count = (
        session.scalar(
            select(func.count(Recommendation.id)).where(
                Recommendation.recommendation_type == "callback_failure",
                Recommendation.status == "resolved",
            )
        )
        or 0
    )
    return CallbackFailureReview(
        items=active_items,
        active_items=active_items,
        new_since_deploy_items=new_since_deploy_items,
        validating_items=validating_items,
        resolved_items=resolved_items,
        historical_items=historical_items,
        friction_count=session.scalar(select(func.count(FrictionItem.id))) or 0,
        recommendation_count=all_recommendation_count,
        active_recommendation_count=active_recommendation_count,
        resolved_recommendation_count=resolved_recommendation_count,
        audit_count=session.scalar(select(func.count(AuditLog.id)).where(AuditLog.action == "callback.failed")) or 0,
        event_count=session.scalar(select(func.count(EventLog.id)).where(EventLog.event_type == "callback.failed")) or 0,
        lifecycle_summary=lifecycle_summary,
        latest_deploy_commit=engine.current_commit,
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
        "command_center",
        "command_center:scores",
        "command_center:intelligence",
        "command_center:operations",
        "command_center:systems",
        "command_center:admin",
        "coo:briefing",
        "agency_awareness",
        "ai_brain",
        "search",
        "recovery_center",
        "reliability",
        "callback_failure_review",
        "production_observability",
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
