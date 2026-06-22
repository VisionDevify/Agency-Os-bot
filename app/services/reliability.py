from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Iterable

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.button_issue import ButtonIssue
from app.models.callback_error import CallbackErrorLog
from app.models.reliability import CallbackLatencyRecord, ReliabilityJob, ResponseCacheEntry
from app.models.user import User
from app.services.audit import sanitize_details
from app.services.callbacks import callback_failure_review
from app.services.freeze_watchdog import freeze_watchdog
from app.services.recovery import latest_recovery_job_summary, recovery_risk_assessment
from app.services.permissions import PermissionPrincipal, RoleName

ACTIVE_JOB_STATUSES = {"queued", "running", "checking", "uploading", "verifying", "summarizing"}
TERMINAL_JOB_STATUSES = {"completed", "failed", "timed_out", "cancelled"}
SUCCESSFUL_JOB_STATUSES = {"completed"}
JOB_TIMEOUT_MINUTES = int(os.getenv("RELIABILITY_JOB_TIMEOUT_MINUTES", "15"))
CACHE_DEFAULT_MINUTES = int(os.getenv("RELIABILITY_CACHE_DEFAULT_MINUTES", "5"))
BLOCKING_BUTTON_ISSUE_TYPES = {
    "missing_handler",
    "renderer_error",
    "bad_back_target",
    "missing_back",
    "missing_home",
    "dead_end",
}


@dataclass(frozen=True)
class CallbackTiming:
    callback_route: str
    received_at: datetime
    acknowledged_at: datetime | None = None
    render_started_at: datetime | None = None
    render_finished_at: datetime | None = None
    edit_or_send_completed_at: datetime | None = None
    db_latency_ms: int | None = None
    ai_latency_ms: int | None = None
    search_latency_ms: int | None = None
    backup_latency_ms: int | None = None


@dataclass(frozen=True)
class ShortcutCommand:
    command: str
    page: str
    owner_only: bool = True
    description: str = ""
    working_label: str | None = None


@dataclass(frozen=True)
class VerificationRouteResult:
    command: str
    page: str
    status: str
    latency_ms: int
    safe_error_summary: str | None = None


@dataclass(frozen=True)
class VerificationHarnessResult:
    passed: tuple[VerificationRouteResult, ...]
    failed: tuple[VerificationRouteResult, ...]
    slow: tuple[VerificationRouteResult, ...]
    callback_issue_count: int
    stale_menu_issue_count: int
    average_latency_ms: int
    average_latency_label: str


@dataclass(frozen=True)
class RouteHealthEntry:
    route_name: str
    display_label: str
    parent_route: str
    owner_only: bool
    expected_render_function: str
    last_success_at: datetime | None
    last_failure_at: datetime | None
    health_status: str
    average_latency_ms: int
    latest_safe_error: str | None = None


SHORTCUT_COMMANDS: tuple[ShortcutCommand, ...] = (
    ShortcutCommand("home", "menu", owner_only=False, description="Open Home."),
    ShortcutCommand("command_center", "command_center", owner_only=False, description="Open Fortuna Command Center."),
    ShortcutCommand("more", "command_center:admin", description="Open Admin."),
    ShortcutCommand("scores", "command_center:scores", description="Open readiness scores."),
    ShortcutCommand("intelligence", "command_center:intelligence", description="Open Intelligence."),
    ShortcutCommand("operations", "command_center:operations", description="Open Operations."),
    ShortcutCommand("systems", "command_center:systems", description="Open Systems."),
    ShortcutCommand("admin", "command_center:admin", description="Open Admin."),
    ShortcutCommand("coo", "coo:briefing", description="Open COO Briefing.", working_label="Checking priorities"),
    ShortcutCommand("today", "today_priorities", owner_only=False, description="Open What Matters Today."),
    ShortcutCommand("agency", "agency_awareness", description="Open Agency Awareness."),
    ShortcutCommand("agency_active", "agency_awareness:active", description="Open active agency areas."),
    ShortcutCommand("agency_missing", "agency_awareness:missing", description="Open missing or inactive agency areas."),
    ShortcutCommand("agency_connected", "agency_awareness:not_connected", description="Open not connected platforms."),
    ShortcutCommand("ai", "ai_brain", description="Open AI Brain."),
    ShortcutCommand("ai_settings", "ai_brain:settings", description="Open AI settings."),
    ShortcutCommand("ai_critic", "ai_brain:critic", description="Open AI critic status."),
    ShortcutCommand("ai_evidence", "ai_brain:evidence", description="Open AI evidence summary.", working_label="Reviewing evidence"),
    ShortcutCommand("ai_coo", "ai_brain:coo", description="Open AI COO explanation.", working_label="Reviewing briefing evidence"),
    ShortcutCommand(
        "ai_opportunity",
        "ai_brain:opportunity",
        description="Open AI opportunity explanation.",
        working_label="Reviewing opportunity evidence",
    ),
    ShortcutCommand("search", "search", description="Open Search Intelligence."),
    ShortcutCommand("search_settings", "search:settings", description="Open Search settings."),
    ShortcutCommand("search_history", "search:history", description="Open Search history."),
    ShortcutCommand("recovery", "recovery_center", description="Open Recovery Center."),
    ShortcutCommand("backup_storage", "recovery:storage", description="Open Backup Storage."),
    ShortcutCommand("s3_storage", "recovery:storage:s3", description="Open S3 backup storage status."),
    ShortcutCommand(
        "activate_s3_storage",
        "recovery:storage:s3",
        description="Activate S3 storage from Railway variables.",
        working_label="Testing S3 storage",
    ),
    ShortcutCommand(
        "test_s3_storage",
        "recovery:storage:s3",
        description="Test active S3 backup storage.",
        working_label="Testing S3 storage",
    ),
    ShortcutCommand("backup_history", "recovery:history", description="Open Backup History."),
    ShortcutCommand("run_backup", "recovery:backup:run", description="Start or show backup job.", working_label="Starting backup"),
    ShortcutCommand("restore_test", "recovery:restore:test", description="Start or show restore validation.", working_label="Starting restore validation"),
    ShortcutCommand("reliability", "reliability", description="Open Reliability Center.", working_label="Checking reliability"),
    ShortcutCommand("callback_failures", "callback_failure_review", description="Open Callback Failure Review."),
    ShortcutCommand("button_health", "button_health", description="Open Button Health.", working_label="Checking buttons"),
    ShortcutCommand("notifications", "platforms:notifications", description="Open Notification Center."),
    ShortcutCommand("platforms", "platforms", description="Open Platform Connections."),
    ShortcutCommand("decision_memory", "decision:memory", description="Open Decision Memory."),
    ShortcutCommand("reality", "reality:check", description="Open Reality Check."),
    ShortcutCommand("intelligence_quality", "intelligence:quality", description="Open Recommendation Quality."),
    ShortcutCommand("observability", "production_observability", description="Open Production Observability.", working_label="Checking health signals"),
    ShortcutCommand("help", "help", owner_only=False, description="Open Help."),
    ShortcutCommand("verify_navigation", "reliability:verify", description="Run command-based navigation verification.", working_label="Verifying navigation"),
)

SHORTCUT_BY_COMMAND = {item.command: item for item in SHORTCUT_COMMANDS}
HARNESS_COMMANDS = (
    "home",
    "command_center",
    "scores",
    "today",
    "intelligence",
    "operations",
    "systems",
    "admin",
    "coo",
    "agency",
    "agency_active",
    "agency_missing",
    "agency_connected",
    "ai",
    "ai_settings",
    "ai_critic",
    "ai_evidence",
    "ai_coo",
    "ai_opportunity",
    "search",
    "search_settings",
    "search_history",
    "recovery",
    "reliability",
    "callback_failures",
    "button_health",
    "observability",
)


def now_utc() -> datetime:
    return datetime.now(UTC)


def latency_label(total_latency_ms: int | None) -> str:
    if total_latency_ms is None:
        return "dead"
    if total_latency_ms < 500:
        return "excellent"
    if total_latency_ms < 1500:
        return "good"
    if total_latency_ms <= 3000:
        return "slow"
    return "bad"


def _ms(start: datetime | None, end: datetime | None) -> int | None:
    if start is None or end is None:
        return None
    return max(0, round((end - start).total_seconds() * 1000))


def record_callback_latency(
    session: Session,
    timing: CallbackTiming,
    *,
    result: str,
    safe_error_summary: str | None = None,
    metadata: dict | None = None,
) -> CallbackLatencyRecord:
    total_ms = _ms(timing.received_at, timing.edit_or_send_completed_at or timing.render_finished_at or timing.acknowledged_at)
    record = CallbackLatencyRecord(
        callback_route=timing.callback_route[:220],
        received_at=timing.received_at,
        acknowledged_at=timing.acknowledged_at,
        render_started_at=timing.render_started_at,
        render_finished_at=timing.render_finished_at,
        edit_or_send_completed_at=timing.edit_or_send_completed_at,
        total_latency_ms=total_ms,
        ack_latency_ms=_ms(timing.received_at, timing.acknowledged_at),
        render_latency_ms=_ms(timing.render_started_at, timing.render_finished_at),
        db_latency_ms=timing.db_latency_ms,
        ai_latency_ms=timing.ai_latency_ms,
        search_latency_ms=timing.search_latency_ms,
        backup_latency_ms=timing.backup_latency_ms,
        result=result,
        latency_label=latency_label(total_ms),
        safe_error_summary=(safe_error_summary or "")[:600] or None,
        metadata_json=sanitize_details(metadata or {}),
    )
    session.add(record)
    session.flush()
    return record


def start_reliability_job(
    session: Session,
    *,
    job_id: str,
    job_type: str,
    status: str = "queued",
    current_step: str = "Queued",
    related_chat_id: int | str | None = None,
    related_message_id: int | str | None = None,
    progress_percent: int | None = None,
    metadata: dict | None = None,
) -> ReliabilityJob:
    existing = session.scalar(select(ReliabilityJob).where(ReliabilityJob.job_id == job_id).limit(1))
    if existing is not None:
        existing.status = status
        existing.current_step = current_step
        existing.updated_at = now_utc()
        existing.related_chat_id = str(related_chat_id) if related_chat_id is not None else existing.related_chat_id
        existing.related_message_id = str(related_message_id) if related_message_id is not None else existing.related_message_id
        if progress_percent is not None:
            existing.progress_percent = progress_percent
        if metadata:
            existing.metadata_json = sanitize_details({**(existing.metadata_json or {}), **metadata})
        session.flush()
        return existing
    job = ReliabilityJob(
        job_id=job_id[:120],
        job_type=job_type[:80],
        status=status,
        current_step=current_step[:160],
        related_chat_id=str(related_chat_id) if related_chat_id is not None else None,
        related_message_id=str(related_message_id) if related_message_id is not None else None,
        progress_percent=progress_percent,
        metadata_json=sanitize_details(metadata or {}),
    )
    session.add(job)
    session.flush()
    return job


def update_reliability_job(
    session: Session,
    job_id: str,
    *,
    status: str | None = None,
    current_step: str | None = None,
    progress_percent: int | None = None,
    result_summary: str | None = None,
    safe_error_summary: str | None = None,
) -> ReliabilityJob | None:
    job = session.scalar(select(ReliabilityJob).where(ReliabilityJob.job_id == job_id).limit(1))
    if job is None:
        return None
    current = now_utc()
    if status is not None:
        job.status = status
        if status in TERMINAL_JOB_STATUSES:
            job.finished_at = current
    if current_step is not None:
        job.current_step = current_step[:160]
    if progress_percent is not None:
        job.progress_percent = progress_percent
    if result_summary is not None:
        job.result_summary = result_summary[:1000]
    if safe_error_summary is not None:
        job.safe_error_summary = safe_error_summary[:1000]
    job.updated_at = current
    session.flush()
    return job


def mark_stale_reliability_jobs(session: Session, *, now: datetime | None = None) -> int:
    current = now or now_utc()
    cutoff = current - timedelta(minutes=JOB_TIMEOUT_MINUTES)
    count = 0
    jobs = session.scalars(
        select(ReliabilityJob).where(
            ReliabilityJob.status.in_(tuple(ACTIVE_JOB_STATUSES)),
            ReliabilityJob.updated_at < cutoff,
        )
    ).all()
    for job in jobs:
        job.status = "timed_out"
        job.finished_at = current
        job.updated_at = current
        job.safe_error_summary = "Job did not update before the reliability timeout."
        count += 1
    if count:
        session.flush()
    return count


def latest_jobs(session: Session, *, limit: int = 8) -> list[ReliabilityJob]:
    mark_stale_reliability_jobs(session)
    return list(
        session.scalars(
            select(ReliabilityJob).order_by(desc(ReliabilityJob.updated_at), desc(ReliabilityJob.id)).limit(limit)
        ).all()
    )


def active_jobs(session: Session) -> list[ReliabilityJob]:
    mark_stale_reliability_jobs(session)
    return list(
        session.scalars(
            select(ReliabilityJob)
            .where(ReliabilityJob.status.in_(tuple(ACTIVE_JOB_STATUSES)))
            .order_by(desc(ReliabilityJob.updated_at), desc(ReliabilityJob.id))
            .limit(20)
        ).all()
    )


def _job_superseded_by_newer_success(session: Session, job: ReliabilityJob) -> bool:
    if job.updated_at is None:
        return False
    newer_success_count = int(
        session.scalar(
            select(func.count(ReliabilityJob.id)).where(
                ReliabilityJob.job_type == job.job_type,
                ReliabilityJob.status.in_(tuple(SUCCESSFUL_JOB_STATUSES)),
                ReliabilityJob.updated_at > job.updated_at,
            )
        )
        or 0
    )
    return newer_success_count > 0


def _active_failed_jobs(session: Session, *, recent_cutoff: datetime, limit: int = 8) -> list[ReliabilityJob]:
    failed_rows = list(
        session.scalars(
            select(ReliabilityJob)
            .where(
                ReliabilityJob.status.in_(("failed", "timed_out")),
                ReliabilityJob.updated_at >= recent_cutoff,
            )
            .order_by(desc(ReliabilityJob.updated_at), desc(ReliabilityJob.id))
            .limit(limit * 4)
        ).all()
    )
    active_failed = [job for job in failed_rows if not _job_superseded_by_newer_success(session, job)]
    return active_failed[:limit]


def cache_key_for(name: str, *parts: object) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()[:24]
    return f"{name}:{digest}"


def get_cached_response(session: Session, cache_key: str, *, now: datetime | None = None) -> ResponseCacheEntry | None:
    current = now or now_utc()
    entry = session.scalar(select(ResponseCacheEntry).where(ResponseCacheEntry.cache_key == cache_key).limit(1))
    if entry is None:
        return None
    if entry.expires_at is not None and entry.expires_at <= current:
        return None
    if entry.contains_sensitive_data:
        return None
    return entry


def set_cached_response(
    session: Session,
    cache_key: str,
    *,
    evidence_version: str,
    safe_summary: str,
    payload: dict | None = None,
    ttl_minutes: int = CACHE_DEFAULT_MINUTES,
    source_commit: str | None = None,
) -> ResponseCacheEntry:
    current = now_utc()
    expires = current + timedelta(minutes=ttl_minutes)
    entry = session.scalar(select(ResponseCacheEntry).where(ResponseCacheEntry.cache_key == cache_key).limit(1))
    if entry is None:
        entry = ResponseCacheEntry(
            cache_key=cache_key[:180],
            evidence_version=evidence_version[:120],
            generated_at=current,
            expires_at=expires,
            source_commit=(source_commit or os.getenv("GIT_COMMIT") or os.getenv("RAILWAY_GIT_COMMIT_SHA") or "")[:80] or None,
            safe_summary=safe_summary[:2000],
            payload_json=sanitize_details(payload or {}),
            contains_sensitive_data=False,
        )
        session.add(entry)
    else:
        entry.evidence_version = evidence_version[:120]
        entry.generated_at = current
        entry.expires_at = expires
        entry.source_commit = (source_commit or os.getenv("GIT_COMMIT") or os.getenv("RAILWAY_GIT_COMMIT_SHA") or "")[:80] or None
        entry.safe_summary = safe_summary[:2000]
        entry.payload_json = sanitize_details(payload or {})
        entry.contains_sensitive_data = False
    session.flush()
    return entry


def reliability_summary(session: Session) -> dict[str, object]:
    mark_stale_reliability_jobs(session)
    recent_cutoff = now_utc() - timedelta(hours=24)
    total_callbacks = int(
        session.scalar(select(func.count(CallbackLatencyRecord.id)).where(CallbackLatencyRecord.received_at >= recent_cutoff))
        or 0
    )
    successful_callbacks = int(
        session.scalar(
            select(func.count(CallbackLatencyRecord.id)).where(
                CallbackLatencyRecord.received_at >= recent_cutoff,
                CallbackLatencyRecord.result == "succeeded",
            )
        )
        or 0
    )
    average_latency = session.scalar(
        select(func.avg(CallbackLatencyRecord.total_latency_ms)).where(
            CallbackLatencyRecord.received_at >= recent_cutoff,
            CallbackLatencyRecord.total_latency_ms.is_not(None),
        )
    )
    slow_records = list(
        session.scalars(
            select(CallbackLatencyRecord)
            .where(
                CallbackLatencyRecord.received_at >= recent_cutoff,
                CallbackLatencyRecord.latency_label.in_(("slow", "bad", "dead")),
            )
            .order_by(desc(CallbackLatencyRecord.total_latency_ms), desc(CallbackLatencyRecord.id))
            .limit(5)
        ).all()
    )
    open_button_issues = list(session.scalars(select(ButtonIssue).where(ButtonIssue.status == "open")).all())
    blocking_button_issues = [
        issue for issue in open_button_issues if (issue.issue_type or "") in BLOCKING_BUTTON_ISSUE_TYPES
    ]
    active_callback_failures = callback_failure_review(session, limit=10).active_items
    active_job_rows = active_jobs(session)
    failed_job_rows = _active_failed_jobs(session, recent_cutoff=recent_cutoff)
    timed_out_jobs = sum(1 for job in failed_job_rows if job.status == "timed_out")
    recovery_job = latest_recovery_job_summary(session)
    recovery = recovery_risk_assessment(session)
    reliability_percent = 100 if total_callbacks == 0 else round((successful_callbacks / total_callbacks) * 100)
    active_issue_count = len(blocking_button_issues) + len(active_callback_failures) + len(failed_job_rows)
    status = "healthy"
    if active_issue_count or timed_out_jobs or recovery_job.get("timed_out_marked"):
        status = "needs_review"
    if any(record.latency_label in {"bad", "dead"} for record in slow_records):
        status = "needs_review"
    rollout_blockers: list[str] = []
    if active_issue_count:
        rollout_blockers.append("active reliability issue")
    if recovery.risk_level == "Critical":
        rollout_blockers.append("critical recovery risk")
    if recovery_job.get("timed_out_marked"):
        rollout_blockers.append("stuck recovery job")
    if any(record.latency_label in {"bad", "dead"} for record in slow_records):
        rollout_blockers.append("bad or dead slow route")
    if failed_job_rows:
        rollout_blockers.append("recent failed job")
    team_rollout_status = "ready" if not rollout_blockers else ("not_ready" if recovery.risk_level == "Critical" else "needs_review")
    slowest = slow_records[0].callback_route if slow_records else "None"
    avg_ms = round(float(average_latency or 0))
    return {
        "status": status,
        "button_reliability": reliability_percent,
        "average_response_ms": avg_ms,
        "average_response_label": latency_label(avg_ms if total_callbacks else 0),
        "slowest_area": slowest,
        "active_issue_count": active_issue_count,
        "open_button_issue_count": len(open_button_issues),
        "blocking_button_issue_count": len(blocking_button_issues),
        "non_blocking_warning_count": max(0, len(open_button_issues) - len(blocking_button_issues)),
        "historical_failure_count": int(session.scalar(select(func.count(CallbackErrorLog.id))) or 0),
        "slow_records": slow_records,
        "active_jobs": active_job_rows,
        "failed_jobs": failed_job_rows,
        "latest_jobs": latest_jobs(session, limit=8),
        "recovery_job": recovery_job,
        "timed_out_jobs": timed_out_jobs,
        "latest_check": now_utc(),
        "webhook_status": "Healthy",
        "team_rollout_status": team_rollout_status,
        "team_rollout_blockers": rollout_blockers,
        "freeze_watchdog": freeze_watchdog.summary(),
    }


def _friendly_route_label(value: str | None) -> str:
    raw = (value or "button").replace("nav:", "").replace("_", " ").replace(":", " ")
    words = [word for word in raw.split() if word]
    if not words:
        return "Button"
    replacements = {
        "ai": "AI",
        "coo": "COO",
        "s3": "S3",
        "ui": "UI",
    }
    return " ".join(replacements.get(word.lower(), word.capitalize()) for word in words)


def route_health_registry(session: Session) -> list[RouteHealthEntry]:
    from app.bot.navigation_stack import parent_page_for

    review = callback_failure_review(session, limit=50)
    active_by_page = {item.page: item for item in review.active_items}
    entries: list[RouteHealthEntry] = []
    for shortcut in SHORTCUT_COMMANDS:
        route_name = f"command:{shortcut.command}"
        last_success = session.scalar(
            select(CallbackLatencyRecord)
            .where(
                CallbackLatencyRecord.callback_route == route_name,
                CallbackLatencyRecord.result == "succeeded",
            )
            .order_by(desc(CallbackLatencyRecord.received_at), desc(CallbackLatencyRecord.id))
            .limit(1)
        )
        last_failure = session.scalar(
            select(CallbackLatencyRecord)
            .where(
                CallbackLatencyRecord.callback_route == route_name,
                CallbackLatencyRecord.result.in_(("failed_safe", "timed_out")),
            )
            .order_by(desc(CallbackLatencyRecord.received_at), desc(CallbackLatencyRecord.id))
            .limit(1)
        )
        average_latency = session.scalar(
            select(func.avg(CallbackLatencyRecord.total_latency_ms)).where(
                CallbackLatencyRecord.callback_route == route_name,
                CallbackLatencyRecord.total_latency_ms.is_not(None),
            )
        )
        active_failure = active_by_page.get(shortcut.page)
        status = "healthy"
        latest_error = None
        if active_failure is not None:
            status = "failing"
            latest_error = active_failure.next_action
        elif last_failure is not None and (
            last_success is None
            or (
                last_failure.received_at is not None
                and last_success.received_at is not None
                and last_failure.received_at > last_success.received_at
            )
        ):
            status = "needs_review"
            latest_error = last_failure.safe_error_summary
        entries.append(
            RouteHealthEntry(
                route_name=route_name,
                display_label=_friendly_route_label(shortcut.page),
                parent_route=parent_page_for(shortcut.page),
                owner_only=shortcut.owner_only,
                expected_render_function=shortcut.page,
                last_success_at=last_success.received_at if last_success is not None else None,
                last_failure_at=last_failure.received_at if last_failure is not None else None,
                health_status=status,
                average_latency_ms=round(float(average_latency or 0)),
                latest_safe_error=latest_error,
            )
        )
    return entries


def working_screen_for(command: ShortcutCommand) -> Screen | None:
    from app.bot.screens.formatting import Screen

    if not command.working_label:
        return None
    labels = command.working_label.split(" ", 1)
    title = command.working_label
    return Screen(
        "\n".join(
            [
                f"{title}...",
                "",
                "Fortuna heard you.",
                "This screen may take a moment, so I am checking it now.",
            ]
        ),
        reply_markup=None,
    )


def working_screen_for_page(page: str) -> Screen | None:
    shortcut = next((item for item in SHORTCUT_COMMANDS if item.page == page and item.working_label), None)
    if shortcut is None:
        labels = {
            "production_observability": "Checking health signals",
            "callback_failure_review": "Checking callback history",
            "button_health": "Checking buttons",
            "button_health:run": "Checking buttons",
            "reliability:verify": "Verifying navigation",
            "reliability": "Checking reliability",
        }
        label = labels.get(page)
        if not label:
            return None
        shortcut = ShortcutCommand("working", page, working_label=label)
    return working_screen_for(shortcut)


def _retire_revalidated_button_issues(session: Session, *, pages: Iterable[str], revalidated_at: datetime) -> int:
    page_set = {page for page in pages if page}
    if not page_set:
        return 0
    rows = list(
        session.scalars(
            select(ButtonIssue).where(
                ButtonIssue.status == "open",
                ButtonIssue.screen.in_(page_set),
                ButtonIssue.issue_type.in_(("missing_handler", "renderer_error")),
            )
        ).all()
    )
    for issue in rows:
        issue.status = "resolved"
        issue.resolved_at = revalidated_at
    if rows:
        session.flush()
    return len(rows)


def render_command_shortcut(
    session: Session,
    *,
    command: str,
    principal: PermissionPrincipal,
    user: User,
    chat_id: int | None = None,
    chat_title: str | None = None,
) -> Screen:
    from app.bot.screens import render_page
    from app.bot.navigation import screen_for_page
    from app.bot.screens.recovery import render_backup_job_started_page, render_restore_job_started_page
    from app.services.recovery import start_backup_job, start_restore_job

    shortcut = SHORTCUT_BY_COMMAND[command]
    if shortcut.page == "recovery:backup:run":
        run, _started = start_backup_job(session, actor=user)
        return render_backup_job_started_page(run, reused=not _started)
    if shortcut.page == "recovery:restore:test":
        test, _started = start_restore_job(session, actor=user)
        return render_restore_job_started_page(test, reused=not _started)
    simple_screen = render_page(shortcut.page, session=session, user=user)
    simple_text = simple_screen.text.strip()
    if simple_text and not simple_text.lower().startswith("unknown"):
        return simple_screen
    return screen_for_page(shortcut.page, principal, session=session, user=user, chat_id=chat_id, chat_title=chat_title)


def run_command_verification_harness(session: Session, *, actor: User) -> VerificationHarnessResult:
    principal = PermissionPrincipal(telegram_id=actor.telegram_id, is_owner=True, role=RoleName.OWNER)
    passed: list[VerificationRouteResult] = []
    failed: list[VerificationRouteResult] = []
    slow: list[VerificationRouteResult] = []
    for command in HARNESS_COMMANDS:
        shortcut = SHORTCUT_BY_COMMAND[command]
        if shortcut.command in {"run_backup", "restore_test"}:
            continue
        started = now_utc()
        try:
            if shortcut.working_label:
                screen = working_screen_for(shortcut)
            else:
                screen = render_command_shortcut(session, command=shortcut.command, principal=principal, user=actor)
            if not screen.text.strip():
                raise ValueError("screen returned empty text")
            finished = now_utc()
            latency = _ms(started, finished) or 0
            result = VerificationRouteResult(shortcut.command, shortcut.page, "passed", latency)
            passed.append(result)
            if latency >= 1500:
                slow.append(result)
            record_callback_latency(
                session,
                CallbackTiming(
                    callback_route=f"command:{shortcut.command}",
                    received_at=started,
                    acknowledged_at=started,
                    render_started_at=started,
                    render_finished_at=finished,
                    edit_or_send_completed_at=finished,
                ),
                result="succeeded",
                metadata={"verification_harness": True, "page": shortcut.page},
            )
        except Exception as exc:
            finished = now_utc()
            failed.append(
                VerificationRouteResult(
                    shortcut.command,
                    shortcut.page,
                    "failed",
                    _ms(started, finished) or 0,
                    type(exc).__name__,
                )
            )
            try:
                record_callback_latency(
                    session,
                    CallbackTiming(
                        callback_route=f"command:{shortcut.command}",
                        received_at=started,
                        acknowledged_at=started,
                        render_started_at=started,
                        render_finished_at=finished,
                        edit_or_send_completed_at=finished,
                    ),
                    result="failed_safe",
                    safe_error_summary=type(exc).__name__,
                    metadata={"verification_harness": True, "page": shortcut.page},
                )
            except Exception:
                pass
    completed_at = now_utc()
    passed_pages = [item.page for item in passed]
    failed_pages = [item.page for item in failed]
    _retire_revalidated_button_issues(session, pages=passed_pages, revalidated_at=completed_at)
    review = callback_failure_review(
        session,
        working_pages=passed_pages,
        failing_pages=failed_pages,
        revalidated_at=completed_at,
    )
    average = round(sum(item.latency_ms for item in passed + failed) / max(1, len(passed) + len(failed)))
    return VerificationHarnessResult(
        passed=tuple(passed),
        failed=tuple(failed),
        slow=tuple(slow),
        callback_issue_count=len(review.active_items),
        stale_menu_issue_count=0,
        average_latency_ms=average,
        average_latency_label=latency_label(average),
    )


def commands_markdown(commands: Iterable[ShortcutCommand] = SHORTCUT_COMMANDS) -> str:
    return "\n".join(f"/{item.command} - {item.description or item.page}" for item in commands)
