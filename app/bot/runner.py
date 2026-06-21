import asyncio
import contextlib
import logging
import os
import time
from datetime import UTC, datetime

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramConflictError
from aiogram import F
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.bot.navigation import screen_for_page
from app.bot.menu import choice_menu
from app.bot.screens import (
    render_access_pending,
    render_account_detail_page,
    render_creator_watch_detail_page,
    render_creator_post_alert_detail_page,
    render_denied,
    render_disabled,
    render_main_menu,
    render_model_detail_page,
    render_onboarding_page,
    render_opportunity_detail_page,
    render_post_watch_detail_page,
    render_own_post_alert_detail_page,
    render_proxy_detail_page,
    render_proxy_import_success_page,
    render_problem_report_saved_page,
    render_botstatus_page,
    render_backup_job_started_page,
    render_callback_error_page,
    render_callback_failure_review_page,
    render_debug_last_error_page,
    render_integrity_page,
    render_restore_job_started_page,
    render_ui_self_test_page,
)
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.models.account import AccountAuthSession
from app.models.button_issue import ButtonIssue
from app.models.opportunity import CREATOR_WATCH_PRIORITIES, OPPORTUNITY_PRIORITIES, POST_WATCH_TYPES, CreatorWatch, PostWatch
from app.models.recovery import BackupRun, RestoreTestRun
from app.models.reporting import NotificationDeliveryAttempt
from app.models.user import User
from app.services.auth import (
    USER_STATUS_DISABLED,
    USER_STATUS_DENIED,
    USER_STATUS_PENDING,
    audit_action,
    get_or_create_telegram_user,
    get_user_by_id,
    mask_telegram_id,
    setup_owner_if_needed,
)
from app.services.accounts import (
    create_account,
    get_account,
    latest_waiting_auth_session,
    submit_verification_code,
)
from app.services.opportunities import (
    create_creator_watch,
    create_creator_post_alert,
    create_manual_opportunity,
    create_own_post_alert,
    create_post_watch,
    comment_strategies_for_opportunity,
    get_opportunity,
    record_opportunity_result,
    update_creator_watch,
)
from app.services.permissions import PermissionPrincipal, RoleName, require_owner
from app.services.proxies import (
    ProxyStringParseError,
    create_proxy,
    create_olympix_proxy_from_string,
    get_proxy,
    update_proxy_location_target,
)
from app.services.model_brands import get_model_brand
from app.services.setup_wizard import (
    add_setup_account,
    add_setup_creator,
    add_setup_opportunity,
    create_setup_model,
    latest_setup_state,
    start_setup_wizard,
    update_setup_model_profile,
)
from app.services.heartbeats import record_heartbeat
from app.services.bot_instances import (
    bot_instance_id,
    clear_polling_conflict_metadata,
    duplicate_bot_instances,
    mask_instance_id,
    polling_preflight,
    polling_owner_metadata,
    record_polling_conflict,
    record_bot_instance_heartbeat,
    telegram_polling_lock_key,
)
from app.services.persistence import storage_status
from app.services.notifications import (
    create_delivery_attempt,
    decrypt_target_chat_id,
    get_notification_target,
    mark_delivery_failed,
    mark_delivery_sent,
    mark_delivery_skipped,
)
from app.services.callbacks import log_callback_failure
from app.services.callback_protection import (
    CallbackLockManager,
    RedisIdempotencyStore,
    SafeRenderResult,
    callback_fingerprint,
    classify_telegram_error,
)
from app.services.recovery import run_backup, run_restore_test, start_backup_job, start_restore_job
from app.services.chat_cleanup import (
    TEMPORARY_ERROR,
    TEMPORARY_NAVIGATION,
    TEMPORARY_STATUS,
    chat_cleanup_enabled,
    classify_navigation_callback,
    classify_delete_exception,
    complete_cleanup_run,
    current_active_navigation_message,
    mark_cleanup_started,
    mark_message_delete_failed,
    mark_message_deleted,
    reset_navigation_session,
    reuse_cleanup_run,
    start_cleanup_run,
    temporary_cleanup_messages,
    track_bot_message,
)
from app.services.friction import report_problem
from app.services.live_safety import live_data_safety_status
from app.services.team_operations import BotPollingGuard, update_user_localization

logger = logging.getLogger(__name__)
dp = Dispatcher()
CURRENT_BOT_INSTANCE_ID = bot_instance_id()
CALLBACK_LOCKS = CallbackLockManager(settings.redis_url)
CALLBACK_IDEMPOTENCY = RedisIdempotencyStore(settings.redis_url)
NAVIGATION_IDEMPOTENCY_TTL_SECONDS = 2
TELEGRAM_PENDING_WATCHDOG_INTERVAL_SECONDS = float(os.getenv("TELEGRAM_PENDING_WATCHDOG_INTERVAL_SECONDS", "20"))
TELEGRAM_PENDING_WATCHDOG_LIMIT = int(os.getenv("TELEGRAM_PENDING_WATCHDOG_LIMIT", "3"))
TELEGRAM_PENDING_WATCHDOG_API_TIMEOUT_SECONDS = float(os.getenv("TELEGRAM_PENDING_WATCHDOG_API_TIMEOUT_SECONDS", "10"))
LAST_TELEGRAM_UPDATE_MONOTONIC = time.monotonic()

PENDING_ACCOUNT_CREATES: dict[int, dict[str, int | str]] = {}
PENDING_AUTH_CODES: dict[int, int] = {}
PENDING_CREATOR_INTAKES: dict[int, dict[str, int | str | None]] = {}
PENDING_CREATOR_ALERTS: dict[int, dict[str, int | str | None]] = {}
PENDING_OPPORTUNITY_INTAKES: dict[int, dict[str, int | str | None]] = {}
PENDING_POST_INTAKES: dict[int, dict[str, int | str | None]] = {}
PENDING_OWN_POST_ALERTS: dict[int, dict[str, int | str | None]] = {}
PENDING_RESULT_INTAKES: dict[int, dict[str, int | str | None]] = {}


def _bypass_navigation_duplicate_guard(page: str) -> bool:
    normalized = (page or "menu").strip()
    if normalized in {"menu", "home", "help", "help_copilot"}:
        return True
    if normalized.startswith(("help:", "help_from:", "help_copilot:", "help_copilot_from:")):
        return True
    if "refresh" in normalized:
        return True
    return False


async def _mark_navigation_callback_if_new(
    callback: CallbackQuery,
    *,
    session,
    user: User,
    chat_id: int,
    page: str,
) -> bool:
    if _bypass_navigation_duplicate_guard(page):
        return True
    current = current_active_navigation_message(session, chat_id=chat_id, user=user)
    active_navigation_version = str(current.navigation_version) if current is not None else ""
    fingerprint = callback_fingerprint(callback, active_navigation_version=active_navigation_version)
    return await CALLBACK_IDEMPOTENCY.mark_callback_seen(
        fingerprint=fingerprint,
        ttl_seconds=NAVIGATION_IDEMPOTENCY_TTL_SECONDS,
    )
PENDING_SETUP_WIZARDS: dict[int, dict[str, int | str | None]] = {}
PENDING_MODEL_EDITS: dict[int, dict[str, int | str | None]] = {}
PENDING_PROXY_WIZARDS: dict[int, dict[str, str]] = {}
PENDING_PROXY_LOCATION_EDITS: dict[int, int] = {}
PENDING_PROBLEM_REPORTS: dict[int, dict[str, int | str | None]] = {}


def _mark_backup_job_failed(run_identifier: str, error_summary: str) -> None:
    if SessionLocal is None:
        return
    with SessionLocal() as session:
        run = session.scalar(select(BackupRun).where(BackupRun.run_identifier == run_identifier))
        if run is not None and run.status in {"pending", "running"}:
            run.status = "failed"
            run.finished_at = datetime.now(UTC)
            run.error_summary = error_summary
            run.result_summary = "Backup did not finish with verified artifact evidence."
            session.commit()


def _mark_restore_job_failed(run_identifier: str, error_summary: str) -> None:
    if SessionLocal is None:
        return
    with SessionLocal() as session:
        run = session.scalar(select(RestoreTestRun).where(RestoreTestRun.run_identifier == run_identifier))
        if run is not None and run.status in {"pending", "running"}:
            run.status = "failed"
            run.finished_at = datetime.now(UTC)
            run.error_summary = error_summary
            run.result_summary = "Restore validation did not finish with verified evidence."
            run.checksum_verified = False
            run.decrypt_verified = False
            run.full_restore_performed = False
            session.commit()


def _execute_backup_job_sync(run_identifier: str, actor_id: int | None, backup_type: str = "manual") -> None:
    if SessionLocal is None:
        return
    with SessionLocal() as session:
        actor = session.get(User, actor_id) if actor_id is not None else None
        run_backup(session, actor=actor, backup_type=backup_type, run_identifier=run_identifier)
        session.commit()


def _execute_restore_job_sync(run_identifier: str, actor_id: int | None) -> None:
    if SessionLocal is None:
        return
    with SessionLocal() as session:
        actor = session.get(User, actor_id) if actor_id is not None else None
        run_restore_test(session, actor=actor, run_identifier=run_identifier)
        session.commit()


async def _run_backup_job_background(run_identifier: str, actor_id: int | None, backup_type: str = "manual") -> None:
    try:
        await asyncio.to_thread(_execute_backup_job_sync, run_identifier, actor_id, backup_type)
    except Exception as exc:
        logger.exception("Recovery backup background job failed safely")
        await asyncio.to_thread(
            _mark_backup_job_failed,
            run_identifier,
            f"Backup failed safely: {type(exc).__name__}.",
        )


async def _run_restore_job_background(run_identifier: str, actor_id: int | None) -> None:
    try:
        await asyncio.to_thread(_execute_restore_job_sync, run_identifier, actor_id)
    except Exception as exc:
        logger.exception("Recovery restore background job failed safely")
        await asyncio.to_thread(
            _mark_restore_job_failed,
            run_identifier,
            f"Restore validation failed safely: {type(exc).__name__}.",
        )


class _PollingConflictLogHandler(logging.Handler):
    """Capture aiogram getUpdates conflicts that are logged and retried internally."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self._last_recorded_at = 0.0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
        except Exception:
            message = ""
        if "terminated by other getUpdates request" not in message and "TelegramConflictError" not in message:
            return
        now = time.monotonic()
        if now - self._last_recorded_at < 60:
            return
        self._last_recorded_at = now
        if SessionLocal is None:
            return
        with contextlib.suppress(Exception):
            with SessionLocal() as session:
                record_polling_conflict(
                    session,
                    instance_id=CURRENT_BOT_INSTANCE_ID,
                    source="aiogram_polling_log",
                    conflict_source="telegram_getupdates",
                    polling_lock_owner=mask_instance_id(CURRENT_BOT_INSTANCE_ID),
                )
                session.commit()


async def _acquire_polling_guard(
    guard: BotPollingGuard,
    *,
    retry_seconds: int = 10,
    max_wait_seconds: int = 420,
    operation_timeout_seconds: int = 5,
) -> bool:
    try:
        acquired = await asyncio.wait_for(asyncio.to_thread(guard.acquire), timeout=operation_timeout_seconds)
    except Exception:
        logger.warning("Unable to acquire Fortuna OS bot polling lock", exc_info=True)
        acquired = False
    if acquired:
        return True

    logger.warning("Another Fortuna OS bot polling instance appears active; waiting for lock to clear")
    deadline = time.monotonic() + max_wait_seconds
    while time.monotonic() < deadline:
        await asyncio.sleep(retry_seconds)
        try:
            acquired = await asyncio.wait_for(asyncio.to_thread(guard.acquire), timeout=operation_timeout_seconds)
        except Exception:
            logger.warning("Unable to acquire Fortuna OS bot polling lock while waiting", exc_info=True)
            acquired = False
        if acquired:
            logger.info("Acquired Fortuna OS bot polling lock after waiting")
            return True
    return False


async def _idle_without_polling(reason: str, *, status: str = "blocked") -> None:
    logger.error("Fortuna OS bot worker is not polling: %s", reason)
    while True:
        if SessionLocal is not None:
            with contextlib.suppress(Exception):
                with SessionLocal() as session:
                    _record_bot_heartbeat(
                        session,
                        status=status,
                        source="polling_disabled",
                        polling_allowed="False",
                        polling_active="False",
                        polling_block_reason=reason,
                    )
                    session.commit()
        await asyncio.sleep(300)


def _principal_from_user(user: User) -> PermissionPrincipal:
    role = RoleName.OWNER if user.is_owner else RoleName.VIEWER
    return PermissionPrincipal(telegram_id=user.telegram_id, is_owner=user.is_owner, role=role)


def _bot_heartbeat_metadata(source: str, **extra: str) -> dict[str, str]:
    now = datetime.now(UTC).isoformat()
    storage = storage_status()
    has_redis = bool(settings.redis_url)
    owner_metadata = polling_owner_metadata(
        instance_id=CURRENT_BOT_INSTANCE_ID,
        polling_allowed=True,
        polling_active=source in {"startup", "polling_loop"} or source.startswith("telegram_"),
        polling_lock_owner=mask_instance_id(CURRENT_BOT_INSTANCE_ID) if has_redis else "not_configured",
        source=source,
    )
    metadata = {
        **owner_metadata,
        "source": source,
        "instance_id_masked": mask_instance_id(CURRENT_BOT_INSTANCE_ID),
        "service_role": "worker",
        "primary_polling_enabled": str(settings.bot_primary_instance),
        "allow_polling_without_redis": str(settings.allow_polling_without_redis),
        "db_backend": storage.backend,
        "db_driver": storage.scheme,
        "db_durable": str(storage.durable),
        "storage_warning": storage.warning or "",
        "polling_guard": "redis_lock" if has_redis else "disabled_no_redis",
        "redis_lock_status": "held" if has_redis else "not_configured",
    }
    if source.startswith("telegram_"):
        metadata = clear_polling_conflict_metadata(metadata)
    if source == "startup":
        metadata["bot_started_at"] = now
    elif source == "polling_loop":
        metadata["last_polling_loop_at"] = now
    elif source.startswith("telegram_"):
        metadata["last_telegram_update_at"] = now
    metadata.update(extra)
    return metadata


def _record_bot_heartbeat(session, *, status: str = "healthy", source: str, **extra: str) -> None:
    global LAST_TELEGRAM_UPDATE_MONOTONIC
    if source.startswith("telegram_"):
        LAST_TELEGRAM_UPDATE_MONOTONIC = time.monotonic()
    metadata = _bot_heartbeat_metadata(source, **extra)
    record_heartbeat(session, service_name="bot", status=status, metadata=metadata)
    record_bot_instance_heartbeat(
        session,
        instance_id=CURRENT_BOT_INSTANCE_ID,
        status=status,
        metadata=metadata,
    )


async def _watch_telegram_pending_updates(
    bot: Bot,
    *,
    interval_seconds: float = TELEGRAM_PENDING_WATCHDOG_INTERVAL_SECONDS,
    consecutive_limit: int = TELEGRAM_PENDING_WATCHDOG_LIMIT,
    api_timeout_seconds: float = TELEGRAM_PENDING_WATCHDOG_API_TIMEOUT_SECONDS,
    exit_process: bool = True,
    max_checks: int | None = None,
) -> None:
    """Exit the worker if Telegram queues updates while no handler consumes them.

    Railway can keep a long-polling worker marked online even when the poll loop is
    wedged. Telegram's safe webhook-info endpoint exposes pending update count
    without consuming updates, so this watchdog can detect that state and let the
    platform restart the single primary worker.
    """
    pending_streak = 0
    last_update_marker = LAST_TELEGRAM_UPDATE_MONOTONIC
    checks = 0
    while True:
        await asyncio.sleep(interval_seconds)
        checks += 1
        try:
            info = await asyncio.wait_for(bot.get_webhook_info(), timeout=api_timeout_seconds)
            pending_count = int(getattr(info, "pending_update_count", 0) or 0)
        except Exception:
            logger.warning("Unable to check Telegram pending update count", exc_info=True)
            if max_checks is not None and checks >= max_checks:
                return
            continue

        current_update_marker = LAST_TELEGRAM_UPDATE_MONOTONIC
        if current_update_marker > last_update_marker:
            pending_streak = 0
            last_update_marker = current_update_marker

        if pending_count <= 0:
            pending_streak = 0
            if max_checks is not None and checks >= max_checks:
                return
            continue

        pending_streak += 1
        logger.warning(
            "Telegram pending updates remain queued while worker is polling",
            extra={"telegram_pending_updates": pending_count, "pending_watchdog_streak": pending_streak},
        )
        if pending_streak < consecutive_limit:
            if max_checks is not None and checks >= max_checks:
                return
            continue

        logger.error(
            "Telegram polling appears wedged; restarting worker to recover update consumption",
            extra={"telegram_pending_updates": pending_count, "pending_watchdog_streak": pending_streak},
        )
        if SessionLocal is not None:
            with contextlib.suppress(Exception):
                with SessionLocal() as session:
                    _record_bot_heartbeat(
                        session,
                        status="critical",
                        source="pending_watchdog",
                        telegram_pending_updates=str(pending_count),
                        pending_watchdog_streak=str(pending_streak),
                    )
                    session.commit()
        if exit_process:
            os._exit(1)
        return


def _username_from_message_user(user) -> str | None:
    return user.username if user and user.username else None


def _display_name_from_message_user(user) -> str | None:
    if user is None:
        return None
    parts = [getattr(user, "first_name", None), getattr(user, "last_name", None)]
    return " ".join(part for part in parts if part) or getattr(user, "username", None)


def _parse_account_input(text: str) -> tuple[str, str | None]:
    if "|" in text:
        username, display_name = [part.strip() for part in text.split("|", 1)]
        return username.lstrip("@"), display_name or None
    clean = text.strip().lstrip("@")
    return clean, clean


def _clean_optional_text(text: str) -> str | None:
    value = text.strip()
    if not value or value.lower() in {"skip", "none", "no", "n/a"}:
        return None
    return value


def _parse_optional_int(text: str) -> int | None:
    value = _clean_optional_text(text)
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return max(0, parsed)


def _parse_pipe_parts(text: str, length: int) -> list[str | None]:
    parts = [part.strip() for part in text.split("|")]
    while len(parts) < length:
        parts.append("")
    return [_clean_optional_text(part) for part in parts[:length]]


def _priority_markup(prefix: str) -> object:
    return choice_menu(
        [(priority.title(), f"nav:{prefix}:{priority}") for priority in OPPORTUNITY_PRIORITIES],
        back_to="opportunities",
    )


def _creator_priority_markup() -> object:
    return choice_menu(
        [(priority.title(), f"nav:opportunities:creators:add:priority:{priority}") for priority in CREATOR_WATCH_PRIORITIES],
        back_to="opportunities:creators:add",
    )


def _post_type_markup() -> object:
    return choice_menu(
        [(post_type.title(), f"nav:opportunities:posts:add:type:{post_type}") for post_type in POST_WATCH_TYPES],
        back_to="opportunities:posts:add",
    )


def _set_pending_callback_state(telegram_id: int, page: str, session, user: User) -> None:
    PENDING_ACCOUNT_CREATES.pop(telegram_id, None)
    PENDING_AUTH_CODES.pop(telegram_id, None)
    PENDING_PROBLEM_REPORTS.pop(telegram_id, None)
    PENDING_CREATOR_ALERTS.pop(telegram_id, None)
    PENDING_OWN_POST_ALERTS.pop(telegram_id, None)
    parts = page.split(":")
    if page == "settings:report_problem:start":
        PENDING_PROBLEM_REPORTS[telegram_id] = {"mode": "manual"}
        return
    if page.startswith("callback_error:report"):
        callback_error_id = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else None
        PENDING_PROBLEM_REPORTS[telegram_id] = {
            "mode": "callback",
            "callback_error_log_id": callback_error_id,
            "screen": "Callback fallback",
        }
        return
    if page == "proxies:olympix:paste":
        PENDING_PROXY_WIZARDS[telegram_id] = {"provider": "Olympix", "mode": "paste"}
        return
    if page == "proxies:olympix:manual":
        PENDING_PROXY_WIZARDS[telegram_id] = {"provider": "Olympix Mobile SOCKS5", "mode": "manual"}
        return
    if len(parts) >= 3 and parts[0] == "proxy" and parts[1].isdigit() and parts[2] == "location":
        PENDING_PROXY_LOCATION_EDITS[telegram_id] = int(parts[1])
        return
    if page == "setup:wizard:model":
        PENDING_SETUP_WIZARDS[telegram_id] = {"step": "model"}
        return
    if page.startswith("setup:wizard:accounts:platform:"):
        PENDING_SETUP_WIZARDS[telegram_id] = {"step": "account", "platform": parts[-1]}
        return
    if page == "setup:wizard:creators":
        PENDING_SETUP_WIZARDS[telegram_id] = {"step": "creator"}
        return
    if page == "setup:wizard:opportunities":
        PENDING_SETUP_WIZARDS[telegram_id] = {"step": "opportunity"}
        return
    if len(parts) >= 4 and parts[0] == "model" and parts[1].isdigit() and parts[2] == "edit":
        PENDING_MODEL_EDITS[telegram_id] = {"model_id": int(parts[1]), "field": parts[3]}
        return
    if len(parts) >= 6 and parts[:3] == ["accounts", "add", "model"] and parts[3].isdigit() and parts[4] == "platform":
        PENDING_ACCOUNT_CREATES[telegram_id] = {"model_id": int(parts[3]), "platform": parts[5]}
        return
    if (
        len(parts) >= 4
        and parts[0] == "account"
        and parts[1].isdigit()
        and parts[2] == "auth"
        and parts[3] in {"start", "enter"}
    ):
        account = get_account(session, int(parts[1]))
        if account is None:
            return
        auth_session = latest_waiting_auth_session(session, account.id)
        if auth_session is not None:
            PENDING_AUTH_CODES[telegram_id] = auth_session.id
    if page == "opportunities:creators:add":
        PENDING_CREATOR_INTAKES[telegram_id] = {"step": "platform"}
        return
    if page.startswith("opportunities:creators:add:"):
        data = PENDING_CREATOR_INTAKES.setdefault(telegram_id, {})
        if len(parts) >= 5 and parts[3] == "platform":
            data.clear()
            data.update({"step": "username", "platform": parts[4]})
            return
        if len(parts) >= 5 and parts[3] == "priority":
            data.update({"step": "model", "priority": parts[4]})
            return
        if len(parts) >= 5 and parts[3] == "model":
            data.update({"step": "chatter", "assigned_model_id": None if parts[4] == "skip" else int(parts[4])})
            return
        if len(parts) >= 5 and parts[3] == "chatter":
            data.update({"step": "notes", "assigned_chatter_id": None if parts[4] == "skip" else int(parts[4])})
            return
    if page == "opportunities:add":
        PENDING_OPPORTUNITY_INTAKES[telegram_id] = {"step": "source"}
        return
    if page.startswith("opportunities:add:"):
        data = PENDING_OPPORTUNITY_INTAKES.setdefault(telegram_id, {})
        if "platform" in parts:
            data["platform"] = parts[-1]
            data["step"] = "title"
            return
        if len(parts) >= 4 and parts[2] == "source":
            data.clear()
            data["source_type"] = parts[3]
            data["source_reference_id"] = int(parts[4]) if len(parts) >= 5 and parts[4].isdigit() else None
            data["step"] = "platform"
            return
        if len(parts) >= 4 and parts[2] == "priority":
            data.update({"step": "model", "priority": parts[3]})
            return
        if len(parts) >= 4 and parts[2] == "model":
            data.update({"step": "chatter", "model_brand_id": None if parts[3] == "skip" else int(parts[3])})
            return
        if len(parts) >= 4 and parts[2] == "chatter":
            data.update({"step": "notes", "assigned_to_user_id": None if parts[3] == "skip" else int(parts[3])})
            return
    if page == "opportunities:posts:add":
        PENDING_POST_INTAKES[telegram_id] = {"step": "model"}
        return
    if page.startswith("opportunities:posts:add:"):
        data = PENDING_POST_INTAKES.setdefault(telegram_id, {})
        if len(parts) >= 5 and parts[3] == "model":
            data.clear()
            data.update({"step": "platform", "model_brand_id": int(parts[4])})
            return
        if "platform" in parts:
            data.update({"step": "post_reference", "platform": parts[-1]})
            return
        if len(parts) >= 5 and parts[3] == "type":
            data.update({"step": "attention", "post_type": parts[4]})
            return
        if len(parts) >= 5 and parts[3] == "attention":
            data.update({"step": "chatter", "attention_level": parts[4]})
            return
        if len(parts) >= 5 and parts[3] == "chatter":
            data.update({"step": "notes", "assigned_chatter_id": None if parts[4] == "skip" else int(parts[4])})
            return
    if len(parts) >= 4 and parts[0] == "opportunity" and parts[1].isdigit() and parts[2] == "result":
        PENDING_RESULT_INTAKES[telegram_id] = {
            "step": "notes",
            "opportunity_id": int(parts[1]),
            "status": parts[3],
        }
    if len(parts) >= 3 and parts[0] == "creator" and parts[1].isdigit() and parts[2] == "niche":
        PENDING_CREATOR_INTAKES[telegram_id] = {"step": "edit_niche", "creator_id": int(parts[1])}
    if len(parts) >= 3 and parts[0] == "creator" and parts[1].isdigit() and parts[2] == "alert":
        PENDING_CREATOR_ALERTS[telegram_id] = {"creator_id": int(parts[1])}
    if len(parts) >= 3 and parts[0] == "post" and parts[1].isdigit() and parts[2] == "alert":
        PENDING_OWN_POST_ALERTS[telegram_id] = {"post_id": int(parts[1])}


def _notification_target_id_for_send_test(page: str) -> int | None:
    parts = page.split(":")
    if len(parts) >= 3 and parts[0] == "notification_target" and parts[1].isdigit() and parts[2] == "send_test":
        return int(parts[1])
    return None


async def _send_pending_routing_smoke_tests(bot: Bot, session, actor: User) -> None:
    attempts = list(
        session.scalars(
            select(NotificationDeliveryAttempt)
            .where(
                NotificationDeliveryAttempt.event_type == "notification.routing_smoke_test",
                NotificationDeliveryAttempt.status == "pending",
            )
            .order_by(NotificationDeliveryAttempt.id)
            .limit(5)
        ).all()
    )
    for attempt in attempts:
        target = attempt.target
        raw_chat_id = decrypt_target_chat_id(target) if target else None
        if target is None or not target.is_active or target.purpose != "testing" or raw_chat_id is None:
            mark_delivery_skipped(session, attempt, actor=actor, reason="test target not eligible")
            continue
        try:
            await bot.send_message(int(raw_chat_id), "Fortuna OS routing smoke test: Testing Sandbox target is active.")
            mark_delivery_sent(session, attempt, actor=actor)
        except Exception:
            mark_delivery_failed(session, attempt, actor=actor, error_message="telegram_send_failed")
            logger.warning("Unable to send routing smoke test to configured testing target")


async def _cleanup_navigation_messages_on_start(
    bot: Bot,
    session,
    *,
    user: User,
    chat_id: int,
    cleanup_limit: int | None = 60,
    time_budget_seconds: float = 3.0,
) -> int:
    cleanup_lock = await CALLBACK_LOCKS.acquire_cleanup_lock(chat_id=chat_id, ttl_seconds=10)
    if cleanup_lock is None:
        run = reuse_cleanup_run(session, chat_id=chat_id, user=user)
        session.flush()
        logger.info("Reusing active Fortuna chat cleanup batch %s", run.cleanup_run_id)
        return reset_navigation_session(session, chat_id=chat_id, user=None)

    try:
        if not chat_cleanup_enabled(session, user=user, chat_id=chat_id):
            return reset_navigation_session(session, chat_id=chat_id, user=None)

        run = start_cleanup_run(session, chat_id=chat_id, user=user)
        all_candidates = temporary_cleanup_messages(session, chat_id=chat_id, limit=None)
        total_candidates = len(all_candidates)
        navigation_version = reset_navigation_session(session, chat_id=chat_id, user=None)
        session.flush()
        attempted = 0
        deleted = 0
        failed = 0
        deadline = time.monotonic() + max(0.5, float(time_budget_seconds))
        candidates = all_candidates if cleanup_limit is None else all_candidates[: max(0, int(cleanup_limit))]
        for record in candidates:
            if attempted > 0 and time.monotonic() >= deadline:
                logger.info("Stopping foreground chat cleanup early to keep /start responsive")
                break
            attempted += 1
            mark_cleanup_started(record, run)
            try:
                await bot.delete_message(chat_id, record.message_id)
                mark_message_deleted(record, run=run)
                deleted += 1
            except Exception as exc:
                status = classify_delete_exception(exc)
                mark_message_delete_failed(record, reason=status, run=run)
                if status not in {"already_missing"}:
                    failed += 1
                logger.info("Unable to delete old Fortuna temporary message: %s", status)
        complete_cleanup_run(
            session,
            run,
            attempted_count=attempted,
            deleted_count=deleted,
            failed_count=failed,
            total_candidates=total_candidates,
        )
        return navigation_version
    finally:
        await CALLBACK_LOCKS.release(cleanup_lock)


async def _send_tracked_navigation_message(
    message: Message,
    session,
    *,
    user: User,
    screen,
    page: str,
    navigation_version: int | None = None,
) -> None:
    sent = await message.answer(screen.text, reply_markup=screen.reply_markup)
    track_bot_message(
        session,
        chat_id=sent.chat.id,
        user=user,
        message_id=sent.message_id,
        message_label=TEMPORARY_NAVIGATION,
        screen=page,
        active_navigation=True,
        navigation_version=navigation_version,
    )


async def _send_tracked_temporary_message(
    message: Message,
    session,
    *,
    user: User | None,
    text: str,
    reply_markup=None,
    screen: str | None = None,
    message_label: str = TEMPORARY_STATUS,
) -> Message:
    sent = await message.answer(text, reply_markup=reply_markup)
    track_bot_message(
        session,
        chat_id=sent.chat.id,
        user=user,
        message_id=sent.message_id,
        message_label=message_label,
        screen=screen,
        active_navigation=False,
    )
    return sent


def _callback_error_text(exc: BaseException) -> str:
    return str(exc).casefold()


def _is_harmless_callback_edit_race(exc: BaseException) -> bool:
    return classify_telegram_error(exc) == "harmless_duplicate"


async def _safe_callback_answer(
    callback: CallbackQuery,
    text: str | None = None,
    *,
    show_alert: bool = False,
) -> None:
    with contextlib.suppress(Exception):
        await callback.answer(text, show_alert=show_alert)


def _record_callback_button_issue(
    session,
    *,
    page: str | None,
    callback_data: str | None,
    issue_type: str,
    severity: str,
    evidence_summary: str,
    recommended_fix: str,
) -> None:
    if session is None:
        return
    screen = (page or "unknown")[:160]
    existing = session.scalar(
        select(ButtonIssue).where(
            ButtonIssue.screen == screen,
            ButtonIssue.callback_data == (callback_data or "")[:260],
            ButtonIssue.issue_type == issue_type,
            ButtonIssue.status == "open",
        )
    )
    if existing is not None:
        existing.severity = severity
        existing.evidence_summary = evidence_summary
        existing.recommended_fix = recommended_fix
        return
    session.add(
        ButtonIssue(
            screen=screen,
            button_label=None,
            callback_data=(callback_data or "")[:260] or None,
            issue_type=issue_type,
            severity=severity,
            evidence_summary=evidence_summary,
            recommended_fix=recommended_fix,
        )
    )
    session.flush()


async def _edit_or_send_callback_screen(
    callback: CallbackQuery,
    screen,
    *,
    session=None,
    user: User | None = None,
    page: str | None = None,
    message_label: str = TEMPORARY_NAVIGATION,
) -> SafeRenderResult:
    if callback.message is None:
        return SafeRenderResult(success=False, outcome="missing_callback_message")
    chat_id = callback.message.chat.id
    message_id = callback.message.message_id
    edit_lock = await CALLBACK_LOCKS.acquire_message_edit_lock(
        chat_id=chat_id,
        message_id=message_id,
        ttl_seconds=5,
    )
    if edit_lock is None:
        await _safe_callback_answer(callback, "One moment - Fortuna is already updating that.")
        return SafeRenderResult(success=False, message_id=message_id, outcome="message_edit_locked")
    try:
        await callback.message.edit_text(screen.text, reply_markup=screen.reply_markup)
        if session is not None:
            track_bot_message(
                session,
                chat_id=chat_id,
                user=user,
                message_id=message_id,
                message_label=message_label,
                screen=page,
                active_navigation=message_label == TEMPORARY_NAVIGATION,
            )
        return SafeRenderResult(success=True, edited=True, message_id=message_id, outcome="edited")
    except Exception as exc:
        error_class = classify_telegram_error(exc)
        if error_class == "harmless_duplicate":
            logger.info("Ignoring harmless Telegram callback edit race for page %s", page)
            return SafeRenderResult(success=True, message_id=message_id, outcome="message_not_modified")
        logger.warning("Unable to edit callback message; sending fallback screen", exc_info=True)
        try:
            sent = await callback.message.answer(screen.text, reply_markup=screen.reply_markup)
            if session is not None:
                track_bot_message(
                    session,
                    chat_id=sent.chat.id,
                    user=user,
                    message_id=sent.message_id,
                    message_label=message_label,
                    screen=page,
                    active_navigation=message_label == TEMPORARY_NAVIGATION,
                )
            return SafeRenderResult(
                success=True,
                sent_new_message=True,
                message_id=sent.message_id,
                outcome=f"fallback_sent_after_{error_class}",
            )
        except Exception:
            logger.exception("Unable to send callback fallback screen")
            _record_callback_button_issue(
                session,
                page=page,
                callback_data=getattr(callback, "data", None),
                issue_type="renderer_error",
                severity="high",
                evidence_summary=f"{page or 'unknown'} could not edit or send a fallback screen.",
                recommended_fix="Inspect Telegram edit/send errors and ensure the callback renders a safe screen.",
            )
            await _safe_callback_answer(
                callback,
                "Fortuna had trouble updating that message. Use /start to refresh.",
                show_alert=True,
            )
            return SafeRenderResult(success=False, message_id=message_id, outcome=f"fallback_failed_after_{error_class}")
    finally:
        await CALLBACK_LOCKS.release(edit_lock)


async def _handle_callback_failure(
    callback: CallbackQuery,
    session,
    *,
    user: User | None,
    page: str,
    exc: BaseException,
) -> None:
    logger.error("Fortuna callback failed for page %s", page, exc_info=(type(exc), exc, exc.__traceback__))
    error_id: int | None = None
    actor = user
    try:
        session.rollback()
        if user is not None and user.id is not None:
            actor = session.get(User, user.id)
        error = log_callback_failure(
            session,
            actor=actor,
            callback_data=callback.data,
            page=page,
            exc=exc,
            affected_screen=page,
        )
        error_id = error.id
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Unable to persist callback failure log")
    fallback = render_callback_error_page(page, error_id=error_id)
    await _edit_or_send_callback_screen(
        callback,
        fallback,
        session=session,
        user=actor,
        page=page,
        message_label=TEMPORARY_ERROR,
    )
    with contextlib.suppress(Exception):
        await callback.answer("Fortuna logged the problem.", show_alert=True)


def _apply_onboarding_callback(session, user: User, page: str) -> str | None:
    parts = page.split(":")
    if len(parts) < 2 or parts[0] != "onboarding":
        return None
    if parts[1] == "reset" and len(parts) >= 3:
        return parts[2]
    if len(parts) < 3:
        return None
    action = parts[1]
    value = ":".join(parts[2:])
    if action == "language":
        update_user_localization(session, user, actor=user, language=value, require_admin=False)
        return None
    if action == "country":
        update_user_localization(session, user, actor=user, country=value, require_admin=False)
        return None
    if action == "timezone":
        update_user_localization(session, user, actor=user, timezone=value, require_admin=False)
        return None
    if action == "time_format":
        update_user_localization(session, user, actor=user, time_format=value, require_admin=False)
        return None
    return None


@dp.message(CommandStart())
async def start(message: Message) -> None:
    if message.from_user is None or SessionLocal is None:
        await message.answer("Access pending owner approval.")
        return

    with SessionLocal() as session:
        telegram_id = message.from_user.id
        _record_bot_heartbeat(session, status="healthy", source="telegram_start")
        if telegram_id == settings.owner_telegram_id:
            user = setup_owner_if_needed(
                session,
                telegram_user_id=telegram_id,
                display_name=_display_name_from_message_user(message.from_user),
                username=_username_from_message_user(message.from_user),
                owner_telegram_id=settings.owner_telegram_id,
            )
            user.last_seen = datetime.now(UTC)
            session.commit()
            principal = _principal_from_user(user)
            require_owner(principal, settings.owner_telegram_id)
            screen = render_main_menu(session=session, user=user)
            navigation_version = await _cleanup_navigation_messages_on_start(
                message.bot,
                session,
                user=user,
                chat_id=message.chat.id,
            )
            await _send_tracked_navigation_message(
                message,
                session,
                user=user,
                screen=screen,
                page="menu",
                navigation_version=navigation_version,
            )
            session.commit()
            return

        user = get_or_create_telegram_user(
            session,
            telegram_user_id=telegram_id,
            display_name=_display_name_from_message_user(message.from_user),
            username=_username_from_message_user(message.from_user),
            owner_telegram_id=settings.owner_telegram_id,
        )
        user.last_seen = datetime.now(UTC)
        if user.status == USER_STATUS_DISABLED:
            screen = render_disabled()
        elif user.status == USER_STATUS_DENIED:
            screen = render_denied()
        elif user.status == USER_STATUS_PENDING:
            screen = render_onboarding_page(session, user)
        else:
            screen = render_main_menu(session=session, user=user)
        navigation_version = await _cleanup_navigation_messages_on_start(
            message.bot,
            session,
            user=user,
            chat_id=message.chat.id,
        )
        await _send_tracked_navigation_message(
            message,
            session,
            user=user,
            screen=screen,
            page="menu",
            navigation_version=navigation_version,
        )
        session.commit()


@dp.message(Command("clean"))
async def clean_chat(message: Message) -> None:
    if message.from_user is None or SessionLocal is None:
        await message.answer("Chat cleanup is unavailable.")
        return

    with SessionLocal() as session:
        telegram_id = message.from_user.id
        _record_bot_heartbeat(session, status="healthy", source="telegram_clean")
        user = get_or_create_telegram_user(
            session,
            telegram_user_id=telegram_id,
            display_name=_display_name_from_message_user(message.from_user),
            username=_username_from_message_user(message.from_user),
            owner_telegram_id=settings.owner_telegram_id,
        )
        user.last_seen = datetime.now(UTC)
        if not user.is_owner:
            await message.answer("Chat cleanup is owner-only.")
            session.commit()
            return
        screen = render_main_menu(session=session, user=user)
        navigation_version = await _cleanup_navigation_messages_on_start(
            message.bot,
            session,
            user=user,
            chat_id=message.chat.id,
        )
        await _send_tracked_navigation_message(
            message,
            session,
            user=user,
            screen=screen,
            page="menu",
            navigation_version=navigation_version,
        )
        session.commit()


@dp.message(Command("selftest"))
async def selftest(message: Message) -> None:
    if message.from_user is None or SessionLocal is None:
        await message.answer("Self-test is owner-only.")
        return

    with SessionLocal() as session:
        telegram_id = message.from_user.id
        _record_bot_heartbeat(session, status="healthy", source="telegram_selftest")
        user = get_or_create_telegram_user(
            session,
            telegram_user_id=telegram_id,
            display_name=_display_name_from_message_user(message.from_user),
            username=_username_from_message_user(message.from_user),
            owner_telegram_id=settings.owner_telegram_id,
        )
        if not user.is_owner:
            audit_action(
                session,
                actor=user,
                action="access.denied",
                resource_type="ui_self_test",
                status="denied",
                details={"permission": "owner"},
            )
            session.commit()
            await message.answer("UI Self-Test is owner-only.")
            return
        screen = render_ui_self_test_page(session, user, run_now=True)
        await _send_tracked_temporary_message(
            message,
            session,
            user=user,
            text=screen.text,
            reply_markup=screen.reply_markup,
            screen="selftest",
        )
        session.commit()


@dp.message(Command("integrity"))
async def integrity(message: Message) -> None:
    if message.from_user is None or SessionLocal is None:
        await message.answer("Integrity check is owner-only.")
        return

    with SessionLocal() as session:
        telegram_id = message.from_user.id
        _record_bot_heartbeat(session, status="healthy", source="telegram_integrity")
        user = get_or_create_telegram_user(
            session,
            telegram_user_id=telegram_id,
            display_name=_display_name_from_message_user(message.from_user),
            username=_username_from_message_user(message.from_user),
            owner_telegram_id=settings.owner_telegram_id,
        )
        if not user.is_owner:
            audit_action(
                session,
                actor=user,
                action="access.denied",
                resource_type="integrity_check",
                status="denied",
                details={"permission": "owner"},
            )
            session.commit()
            await message.answer("Integrity check is owner-only.")
            return
        screen = render_integrity_page(session, user)
        await _send_tracked_temporary_message(
            message,
            session,
            user=user,
            text=screen.text,
            reply_markup=screen.reply_markup,
            screen="integrity",
        )
        session.commit()


@dp.message(Command("botstatus"))
async def botstatus(message: Message) -> None:
    if message.from_user is None or SessionLocal is None:
        await message.answer("Bot status is owner-only.")
        return

    with SessionLocal() as session:
        telegram_id = message.from_user.id
        _record_bot_heartbeat(session, status="healthy", source="telegram_botstatus")
        user = get_or_create_telegram_user(
            session,
            telegram_user_id=telegram_id,
            display_name=_display_name_from_message_user(message.from_user),
            username=_username_from_message_user(message.from_user),
            owner_telegram_id=settings.owner_telegram_id,
        )
        if not user.is_owner:
            audit_action(
                session,
                actor=user,
                action="access.denied",
                resource_type="bot_status",
                status="denied",
                details={"permission": "owner"},
            )
            session.commit()
            await message.answer("Bot status is owner-only.")
            return
        screen = render_botstatus_page(session, user, current_instance_id=CURRENT_BOT_INSTANCE_ID)
        await _send_tracked_temporary_message(
            message,
            session,
            user=user,
            text=screen.text,
            reply_markup=screen.reply_markup,
            screen="botstatus",
        )
        session.commit()


@dp.message(Command("debug_last_error"))
async def debug_last_error(message: Message) -> None:
    if message.from_user is None or SessionLocal is None:
        await message.answer("Debug last error is owner-only.")
        return

    with SessionLocal() as session:
        telegram_id = message.from_user.id
        _record_bot_heartbeat(session, status="healthy", source="telegram_debug_last_error")
        user = get_or_create_telegram_user(
            session,
            telegram_user_id=telegram_id,
            display_name=_display_name_from_message_user(message.from_user),
            username=_username_from_message_user(message.from_user),
            owner_telegram_id=settings.owner_telegram_id,
        )
        if not user.is_owner:
            audit_action(
                session,
                actor=user,
                action="access.denied",
                resource_type="callback_error_log",
                status="denied",
                details={"permission": "owner"},
            )
            session.commit()
            await message.answer("Debug last error is owner-only.")
            return
        screen = render_debug_last_error_page(session, user)
        await _send_tracked_temporary_message(
            message,
            session,
            user=user,
            text=screen.text,
            reply_markup=screen.reply_markup,
            screen="debug_last_error",
        )
        session.commit()


@dp.message(Command("callback_failures"))
async def callback_failures(message: Message) -> None:
    if message.from_user is None or SessionLocal is None:
        await message.answer("Callback failure review is owner-only.")
        return

    with SessionLocal() as session:
        telegram_id = message.from_user.id
        _record_bot_heartbeat(session, status="healthy", source="telegram_callback_failures")
        user = get_or_create_telegram_user(
            session,
            telegram_user_id=telegram_id,
            display_name=_display_name_from_message_user(message.from_user),
            username=_username_from_message_user(message.from_user),
            owner_telegram_id=settings.owner_telegram_id,
        )
        if not user.is_owner:
            audit_action(
                session,
                actor=user,
                action="access.denied",
                resource_type="callback_failure_review",
                status="denied",
                details={"permission": "owner"},
            )
            session.commit()
            await message.answer("Callback failure review is owner-only.")
            return
        screen = render_callback_failure_review_page(session, user)
        await _send_tracked_temporary_message(
            message,
            session,
            user=user,
            text=screen.text,
            reply_markup=screen.reply_markup,
            screen="callback_failure_review",
        )
        session.commit()


@dp.message(F.text)
async def text_input(message: Message) -> None:
    if message.from_user is None or SessionLocal is None or message.text is None:
        return

    telegram_id = message.from_user.id
    with SessionLocal() as session:
        _record_bot_heartbeat(session, status="healthy", source="telegram_text")
        user = get_or_create_telegram_user(
            session,
            telegram_user_id=telegram_id,
            display_name=_display_name_from_message_user(message.from_user),
            username=_username_from_message_user(message.from_user),
            owner_telegram_id=settings.owner_telegram_id,
        )
        if user.status in {USER_STATUS_DISABLED, USER_STATUS_DENIED, USER_STATUS_PENDING}:
            session.commit()
            return

        pending_model_edit = PENDING_MODEL_EDITS.pop(telegram_id, None)
        if pending_model_edit is not None:
            model = get_model_brand(session, int(pending_model_edit["model_id"]))
            field = str(pending_model_edit["field"])
            value = _clean_optional_text(message.text)
            if model is None:
                await message.answer("Model not found.")
                session.commit()
                return
            if value is None:
                screen = render_model_detail_page(session, model.id)
                await message.answer("No change made.")
                await message.answer(screen.text, reply_markup=screen.reply_markup)
                session.commit()
                return
            allowed_fields = {
                "display_name",
                "stage_name",
                "country",
                "timezone",
                "primary_platform",
                "notes",
                "internal_notes",
            }
            if field not in allowed_fields:
                await message.answer("That model field cannot be edited from Telegram.")
                session.commit()
                return
            try:
                update_setup_model_profile(session, model, actor=user, **{field: value})
            except (PermissionError, ValueError):
                await message.answer("Unable to update model.")
                session.commit()
                return
            screen = render_model_detail_page(session, model.id)
            await message.answer("Model updated.")
            await message.answer(screen.text, reply_markup=screen.reply_markup)
            session.commit()
            return

        pending_proxy_location = PENDING_PROXY_LOCATION_EDITS.pop(telegram_id, None)
        if pending_proxy_location is not None:
            proxy = get_proxy(session, int(pending_proxy_location))
            country, state, city = _parse_pipe_parts(message.text, 3)
            if proxy is None:
                await message.answer("Proxy not found.")
                session.commit()
                return
            if not country or not state:
                PENDING_PROXY_LOCATION_EDITS[telegram_id] = int(pending_proxy_location)
                await message.answer("Please send: Country | State | City\nCity is optional.")
                session.commit()
                return
            try:
                update_proxy_location_target(
                    session,
                    proxy,
                    actor=user,
                    target_country=country,
                    target_state=state,
                    target_city=city,
                )
            except (PermissionError, ValueError):
                await message.answer("Unable to update proxy location.")
                session.commit()
                return
            screen = render_proxy_detail_page(session, proxy.id)
            await message.answer("Proxy location updated.")
            await message.answer(screen.text, reply_markup=screen.reply_markup)
            session.commit()
            return

        pending_report = PENDING_PROBLEM_REPORTS.pop(telegram_id, None)
        if pending_report is not None:
            if pending_report.get("mode") == "manual":
                screen, issue, severity, notes = _parse_pipe_parts(message.text, 4)
                severity = (severity or "medium").lower()
                if not screen or not issue:
                    await message.answer("Please send: Screen | what happened | severity | notes")
                    PENDING_PROBLEM_REPORTS[telegram_id] = pending_report
                    session.commit()
                    return
            else:
                screen = str(pending_report.get("screen") or "Callback fallback")
                issue = "Owner added notes after callback fallback."
                severity = "high"
                notes = _clean_optional_text(message.text)
            try:
                report_problem(
                    session,
                    actor=user,
                    screen=screen,
                    issue=issue,
                    severity=severity,
                    notes=notes,
                    callback_error_log_id=(
                        int(pending_report["callback_error_log_id"])
                        if pending_report.get("callback_error_log_id") is not None
                        else None
                    ),
                )
            except ValueError:
                await message.answer("Severity must be low, medium, high, or critical.")
                PENDING_PROBLEM_REPORTS[telegram_id] = pending_report
                session.commit()
                return
            screen_obj = render_problem_report_saved_page()
            await message.answer(screen_obj.text, reply_markup=screen_obj.reply_markup)
            session.commit()
            return

        pending_proxy = PENDING_PROXY_WIZARDS.get(telegram_id)
        if pending_proxy is not None:
            safety = live_data_safety_status(session, current_instance_id=CURRENT_BOT_INSTANCE_ID)
            if not safety.safe:
                PENDING_PROXY_WIZARDS.pop(telegram_id, None)
                with contextlib.suppress(Exception):
                    await message.delete()
                await message.answer(
                    "Proxy credential entry is blocked right now.\n\n"
                    "Fortuna needs durable PostgreSQL, healthy Redis, working encryption, and one bot instance "
                    "before accepting real proxy secrets. Run /integrity and /botstatus, then try again."
                )
                session.commit()
                return
            if pending_proxy.get("mode") == "paste":
                with contextlib.suppress(Exception):
                    await message.delete()
                try:
                    proxy = create_olympix_proxy_from_string(
                        session,
                        actor=user,
                        proxy_string=message.text,
                    )
                except (PermissionError, ProxyStringParseError, ValueError):
                    await message.answer(
                        "That proxy string did not work. Please send it as:\n"
                        "host:port:username:password\n\n"
                        "The username must include ,session_."
                    )
                    session.commit()
                    return
                PENDING_PROXY_WIZARDS.pop(telegram_id, None)
                screen = render_proxy_import_success_page(session, proxy.id)
                await message.answer(screen.text, reply_markup=screen.reply_markup)
                session.commit()
                return

            with contextlib.suppress(Exception):
                await message.delete()
            base_username, password, target_country, target_state, target_city = _parse_pipe_parts(message.text, 5)
            if not base_username or not password or not target_country or not target_state:
                await message.answer(
                    "Please send: base username | password | target country | target state | target city"
                )
                session.commit()
                return
            try:
                proxy = create_proxy(
                    session,
                    actor=user,
                    provider=str(pending_proxy.get("provider") or "Olympix Mobile SOCKS5"),
                    host="host.olympix.io",
                    port=1080,
                    base_username=base_username,
                    password=password,
                    target_country=target_country,
                    target_state=target_state,
                    target_city=target_city,
                )
                password = ""
            except (PermissionError, ValueError):
                password = ""
                await message.answer("Unable to save proxy. Check permissions and required fields.")
                session.commit()
                return
            PENDING_PROXY_WIZARDS.pop(telegram_id, None)
            screen = render_proxy_detail_page(session, proxy.id)
            await message.answer("Proxy saved. Password encrypted and hidden.")
            await message.answer(screen.text, reply_markup=screen.reply_markup)
            session.commit()
            return

        pending_setup = PENDING_SETUP_WIZARDS.get(telegram_id)
        if pending_setup is not None:
            step = str(pending_setup.get("step") or "")
            state = latest_setup_state(session, user) or start_setup_wizard(session, actor=user)
            if step == "model":
                display_name, stage_name, country, timezone, notes = _parse_pipe_parts(message.text, 5)
                if not display_name:
                    await message.answer("Please send at least a display name.")
                    session.commit()
                    return
                try:
                    model = create_setup_model(
                        session,
                        actor=user,
                        state=state,
                        display_name=display_name,
                        stage_name=stage_name,
                        country=country,
                        timezone=timezone,
                        notes=notes,
                    )
                except (PermissionError, ValueError):
                    await message.answer("Unable to create model.")
                    session.commit()
                    return
                PENDING_SETUP_WIZARDS.pop(telegram_id, None)
                screen = render_model_detail_page(session, model.id)
                await message.answer("First model created.")
                await message.answer(screen.text, reply_markup=screen.reply_markup)
                session.commit()
                return
            if step == "account":
                model = state.model_brand
                if model is None:
                    await message.answer("Create a model first, then add accounts.")
                    PENDING_SETUP_WIZARDS.pop(telegram_id, None)
                    session.commit()
                    return
                username, display_name, account_url, notes = _parse_pipe_parts(message.text, 4)
                if not username:
                    await message.answer("Please send at least an account username.")
                    session.commit()
                    return
                try:
                    account = add_setup_account(
                        session,
                        actor=user,
                        state=state,
                        model=model,
                        platform=str(pending_setup.get("platform") or "other"),
                        username=username.lstrip("@"),
                        display_name=display_name,
                        account_url=account_url,
                        notes=notes,
                    )
                except (PermissionError, ValueError):
                    await message.answer("Unable to add account.")
                    session.commit()
                    return
                PENDING_SETUP_WIZARDS.pop(telegram_id, None)
                screen = render_account_detail_page(session, account.id)
                await message.answer("Account added.")
                await message.answer(screen.text, reply_markup=screen.reply_markup)
                session.commit()
                return
            if step == "creator":
                model = state.model_brand
                if model is None:
                    await message.answer("Create a model first, then add creators.")
                    PENDING_SETUP_WIZARDS.pop(telegram_id, None)
                    session.commit()
                    return
                platform, username, display_name, niche, priority = _parse_pipe_parts(message.text, 5)
                if not platform or not username or not display_name:
                    await message.answer("Please send platform, username, and display name.")
                    session.commit()
                    return
                try:
                    creator = add_setup_creator(
                        session,
                        actor=user,
                        state=state,
                        model=model,
                        platform=platform.lower(),
                        username=username.lstrip("@"),
                        display_name=display_name,
                        niche=niche,
                        priority=(priority or "normal").lower(),
                    )
                except (PermissionError, ValueError):
                    await message.answer("Unable to add creator.")
                    session.commit()
                    return
                PENDING_SETUP_WIZARDS.pop(telegram_id, None)
                screen = render_creator_watch_detail_page(session, creator.id)
                await message.answer("Creator starter added.")
                await message.answer(screen.text, reply_markup=screen.reply_markup)
                session.commit()
                return
            if step == "opportunity":
                model = state.model_brand
                if model is None:
                    await message.answer("Create a model first, then add opportunities.")
                    PENDING_SETUP_WIZARDS.pop(telegram_id, None)
                    session.commit()
                    return
                title, platform, niche, assigned_user_id = _parse_pipe_parts(message.text, 4)
                if not title:
                    await message.answer("Please send at least an opportunity title.")
                    session.commit()
                    return
                assigned_id = int(assigned_user_id) if assigned_user_id and assigned_user_id.isdigit() else None
                if assigned_id is not None and get_user_by_id(session, assigned_id) is None:
                    assigned_id = None
                try:
                    opportunity = add_setup_opportunity(
                        session,
                        actor=user,
                        state=state,
                        model=model,
                        title=title,
                        platform=(platform or "x").lower(),
                        niche=niche,
                        assigned_to_user_id=assigned_id,
                    )
                except (PermissionError, ValueError):
                    await message.answer("Unable to create opportunity.")
                    session.commit()
                    return
                PENDING_SETUP_WIZARDS.pop(telegram_id, None)
                screen = render_opportunity_detail_page(session, opportunity.id)
                await message.answer("Starter opportunity created.")
                await message.answer(screen.text, reply_markup=screen.reply_markup)
                session.commit()
                return

        pending_account = PENDING_ACCOUNT_CREATES.pop(telegram_id, None)
        if pending_account is not None:
            username, display_name = _parse_account_input(message.text)
            model_brand = get_model_brand(session, int(pending_account["model_id"]))
            if model_brand is None:
                await message.answer("Model not found. Start Add Account again.")
                session.commit()
                return
            try:
                account = create_account(
                    session,
                    model_brand=model_brand,
                    platform=str(pending_account["platform"]),
                    username=username,
                    display_name=display_name,
                    actor=user,
                )
            except (PermissionError, ValueError):
                await message.answer("Unable to create account.")
                session.commit()
                return
            screen = render_account_detail_page(session, account.id)
            await message.answer(screen.text, reply_markup=screen.reply_markup)
            session.commit()
            return

        pending_auth_session_id = PENDING_AUTH_CODES.pop(telegram_id, None)
        if pending_auth_session_id is not None:
            auth_session = session.get(AccountAuthSession, pending_auth_session_id)
            if auth_session is None:
                await message.answer("Auth session expired or not found.")
                session.commit()
                return
            submitted_code = message.text.strip()
            try:
                submit_verification_code(
                    session,
                    auth_session,
                    code=submitted_code,
                    code_type="authenticator",
                    actor=user,
                )
                submitted_code = ""
                try:
                    await message.delete()
                except Exception:
                    logger.warning("Unable to delete verification code message")
                account_id = auth_session.account_id
                screen = render_account_detail_page(session, account_id)
                await message.answer("Verification code received securely.")
                await message.answer(screen.text, reply_markup=screen.reply_markup)
            except (PermissionError, ValueError):
                submitted_code = ""
                await message.answer("Unable to submit verification code.")
            session.commit()
            return

        pending_creator_alert = PENDING_CREATOR_ALERTS.pop(telegram_id, None)
        if pending_creator_alert is not None:
            creator = session.get(CreatorWatch, int(pending_creator_alert["creator_id"]))
            reference, notes = _parse_pipe_parts(message.text, 2)
            if creator is None:
                await message.answer("Creator not found.")
                session.commit()
                return
            if not reference:
                PENDING_CREATOR_ALERTS[telegram_id] = pending_creator_alert
                await message.answer("Please send the creator post URL or reference.")
                session.commit()
                return
            try:
                alert = create_creator_post_alert(
                    session,
                    creator,
                    actor=user,
                    post_reference=reference,
                    notes=notes,
                )
            except (PermissionError, ValueError):
                await message.answer("Unable to create creator alert.")
                session.commit()
                return
            screen = render_creator_post_alert_detail_page(session, alert.id)
            await message.answer("Creator alert created. Fortuna routed it for human review.")
            await message.answer(screen.text, reply_markup=screen.reply_markup)
            session.commit()
            return

        pending_own_post_alert = PENDING_OWN_POST_ALERTS.pop(telegram_id, None)
        if pending_own_post_alert is not None:
            post = session.get(PostWatch, int(pending_own_post_alert["post_id"]))
            reference, notes = _parse_pipe_parts(message.text, 2)
            if post is None:
                await message.answer("Post watch item not found.")
                session.commit()
                return
            if not reference or reference.lower() == "same":
                reference = post.post_reference
            try:
                alert = create_own_post_alert(
                    session,
                    post,
                    actor=user,
                    post_reference=reference,
                    notes=notes,
                )
            except (PermissionError, ValueError):
                await message.answer("Unable to create own post alert.")
                session.commit()
                return
            screen = render_own_post_alert_detail_page(session, alert.id)
            await message.answer("Own post alert created. Fortuna routed it for human review.")
            await message.answer(screen.text, reply_markup=screen.reply_markup)
            session.commit()
            return

        pending_creator = PENDING_CREATOR_INTAKES.get(telegram_id)
        if pending_creator is not None:
            step = str(pending_creator.get("step") or "")
            value = message.text.strip()
            if step == "edit_niche":
                creator = session.get(CreatorWatch, int(pending_creator["creator_id"]))
                if creator is None:
                    await message.answer("Creator not found.")
                    PENDING_CREATOR_INTAKES.pop(telegram_id, None)
                    session.commit()
                    return
                try:
                    update_creator_watch(session, creator, actor=user, niche=_clean_optional_text(value) or "")
                except (PermissionError, ValueError):
                    await message.answer("Unable to update creator niche.")
                    session.commit()
                    return
                PENDING_CREATOR_INTAKES.pop(telegram_id, None)
                screen = render_creator_watch_detail_page(session, creator.id)
                await message.answer("Creator niche updated.")
                await message.answer(screen.text, reply_markup=screen.reply_markup)
                session.commit()
                return
            if step == "username":
                pending_creator["creator_username"] = value.lstrip("@")
                pending_creator["step"] = "display_name"
                await message.answer("Send the creator display name.")
                session.commit()
                return
            if step == "display_name":
                pending_creator["display_name"] = value
                pending_creator["creator_name"] = value
                pending_creator["step"] = "niche"
                await message.answer("Send the niche, like fitness, lifestyle, gaming, or skip.")
                session.commit()
                return
            if step == "niche":
                pending_creator["niche"] = _clean_optional_text(value)
                pending_creator["step"] = "priority"
                await message.answer("Choose priority.", reply_markup=_creator_priority_markup())
                session.commit()
                return
            if step == "notes":
                notes = _clean_optional_text(value)
                try:
                    creator = create_creator_watch(
                        session,
                        actor=user,
                        platform=str(pending_creator["platform"]),
                        creator_name=str(pending_creator.get("creator_name") or pending_creator.get("display_name") or "Creator"),
                        display_name=str(pending_creator.get("display_name") or pending_creator.get("creator_name") or "Creator"),
                        creator_username=str(pending_creator.get("creator_username") or "unknown"),
                        niche=pending_creator.get("niche") if isinstance(pending_creator.get("niche"), str) else None,
                        priority=str(pending_creator.get("priority") or "normal"),
                        assigned_model_id=(
                            int(pending_creator["assigned_model_id"])
                            if pending_creator.get("assigned_model_id") is not None
                            else None
                        ),
                        assigned_chatter_id=(
                            int(pending_creator["assigned_chatter_id"])
                            if pending_creator.get("assigned_chatter_id") is not None
                            else None
                        ),
                        notes=notes,
                    )
                except (PermissionError, ValueError):
                    await message.answer("Unable to create creator watch item.")
                    session.commit()
                    return
                PENDING_CREATOR_INTAKES.pop(telegram_id, None)
                screen = render_creator_watch_detail_page(session, creator.id)
                await message.answer("Creator created.")
                await message.answer(screen.text, reply_markup=screen.reply_markup)
                session.commit()
                return

        pending_opportunity = PENDING_OPPORTUNITY_INTAKES.get(telegram_id)
        if pending_opportunity is not None:
            step = str(pending_opportunity.get("step") or "")
            value = message.text.strip()
            if step == "title":
                pending_opportunity["title"] = value
                pending_opportunity["step"] = "url"
                await message.answer("Send URL/reference, or type skip.")
                session.commit()
                return
            if step == "url":
                pending_opportunity["url"] = _clean_optional_text(value)
                pending_opportunity["step"] = "niche"
                await message.answer("Send niche, or type skip.")
                session.commit()
                return
            if step == "niche":
                pending_opportunity["niche"] = _clean_optional_text(value)
                pending_opportunity["step"] = "priority"
                await message.answer("Choose priority.", reply_markup=_priority_markup("opportunities:add:priority"))
                session.commit()
                return
            if step == "notes":
                notes = _clean_optional_text(value)
                source_type = str(pending_opportunity.get("source_type") or "manual")
                source_reference_id = (
                    int(pending_opportunity["source_reference_id"])
                    if pending_opportunity.get("source_reference_id") is not None
                    else None
                )
                model_brand_id = (
                    int(pending_opportunity["model_brand_id"])
                    if pending_opportunity.get("model_brand_id") is not None
                    else None
                )
                assigned_to_user_id = (
                    int(pending_opportunity["assigned_to_user_id"])
                    if pending_opportunity.get("assigned_to_user_id") is not None
                    else None
                )
                if source_type == "creator_watch" and source_reference_id is not None:
                    creator = session.get(CreatorWatch, source_reference_id)
                    if creator is not None:
                        model_brand_id = model_brand_id or creator.assigned_model_id
                        assigned_to_user_id = assigned_to_user_id or creator.assigned_chatter_id
                        pending_opportunity["niche"] = pending_opportunity.get("niche") or creator.niche
                if source_type == "own_post" and source_reference_id is not None:
                    post = session.get(PostWatch, source_reference_id)
                    if post is not None:
                        model_brand_id = model_brand_id or post.model_brand_id
                        assigned_to_user_id = assigned_to_user_id or post.assigned_chatter_id
                try:
                    opportunity = create_manual_opportunity(
                        session,
                        actor=user,
                        title=str(pending_opportunity.get("title") or "Manual Opportunity"),
                        platform=str(pending_opportunity.get("platform") or "x"),
                        url=pending_opportunity.get("url") if isinstance(pending_opportunity.get("url"), str) else None,
                        niche=pending_opportunity.get("niche") if isinstance(pending_opportunity.get("niche"), str) else None,
                        model_brand_id=model_brand_id,
                        priority=str(pending_opportunity.get("priority") or "normal"),
                        assigned_to_user_id=assigned_to_user_id,
                        source_type=source_type,
                        source_reference_id=source_reference_id,
                        reason=notes or "Created from guided Telegram intake.",
                        suggested_angle="Review suggested strategies and perform any platform action manually.",
                    )
                    comment_strategies_for_opportunity(session, opportunity, actor=user)
                except (PermissionError, ValueError):
                    await message.answer("Unable to create opportunity.")
                    session.commit()
                    return
                PENDING_OPPORTUNITY_INTAKES.pop(telegram_id, None)
                screen = render_opportunity_detail_page(session, opportunity.id)
                await message.answer("Opportunity created.")
                await message.answer(screen.text, reply_markup=screen.reply_markup)
                session.commit()
                return

        pending_post = PENDING_POST_INTAKES.get(telegram_id)
        if pending_post is not None:
            step = str(pending_post.get("step") or "")
            value = message.text.strip()
            if step == "post_reference":
                pending_post["post_reference"] = value
                pending_post["step"] = "post_type"
                await message.answer("Choose post type.", reply_markup=_post_type_markup())
                session.commit()
                return
            if step == "notes":
                notes = _clean_optional_text(value)
                model_brand = get_model_brand(session, int(pending_post["model_brand_id"]))
                if model_brand is None:
                    await message.answer("Model not found. Start Own Post Watch again.")
                    PENDING_POST_INTAKES.pop(telegram_id, None)
                    session.commit()
                    return
                try:
                    post = create_post_watch(
                        session,
                        actor=user,
                        model_brand=model_brand,
                        platform=str(pending_post.get("platform") or "instagram"),
                        post_reference=str(pending_post.get("post_reference") or "manual-reference"),
                        post_type=str(pending_post.get("post_type") or "other"),
                        attention_level=str(pending_post.get("attention_level") or "monitor"),
                        assigned_chatter_id=(
                            int(pending_post["assigned_chatter_id"])
                            if pending_post.get("assigned_chatter_id") is not None
                            else None
                        ),
                        status="attention_needed" if pending_post.get("attention_level") == "urgent" else "recent",
                        notes=notes,
                    )
                except (PermissionError, ValueError):
                    await message.answer("Unable to create own post watch item.")
                    session.commit()
                    return
                PENDING_POST_INTAKES.pop(telegram_id, None)
                screen = render_post_watch_detail_page(session, post.id)
                await message.answer("Own post watch item created.")
                await message.answer(screen.text, reply_markup=screen.reply_markup)
                session.commit()
                return

        pending_result = PENDING_RESULT_INTAKES.get(telegram_id)
        if pending_result is not None:
            step = str(pending_result.get("step") or "")
            value = message.text.strip()
            if step == "notes":
                pending_result["notes"] = _clean_optional_text(value)
                pending_result["step"] = "clicks"
                await message.answer("Enter clicks as a number, or type skip.")
                session.commit()
                return
            if step == "clicks":
                pending_result["clicks"] = _parse_optional_int(value)
                pending_result["step"] = "conversions"
                await message.answer("Enter conversions as a number, or type skip.")
                session.commit()
                return
            if step == "conversions":
                pending_result["conversions"] = _parse_optional_int(value)
                opportunity = get_opportunity(session, int(pending_result["opportunity_id"]))
                if opportunity is None:
                    await message.answer("Opportunity not found.")
                    PENDING_RESULT_INTAKES.pop(telegram_id, None)
                    session.commit()
                    return
                try:
                    record_opportunity_result(
                        session,
                        opportunity,
                        actor=user,
                        status=str(pending_result.get("status") or "posted"),
                        clicks=pending_result.get("clicks") if isinstance(pending_result.get("clicks"), int) else None,
                        conversions=(
                            pending_result.get("conversions")
                            if isinstance(pending_result.get("conversions"), int)
                            else None
                        ),
                        reason=pending_result.get("notes") if isinstance(pending_result.get("notes"), str) else None,
                        notes=pending_result.get("notes") if isinstance(pending_result.get("notes"), str) else None,
                    )
                except (PermissionError, ValueError):
                    await message.answer("Unable to record result.")
                    session.commit()
                    return
                PENDING_RESULT_INTAKES.pop(telegram_id, None)
                screen = render_opportunity_detail_page(session, opportunity.id)
                await message.answer("Result recorded.")
                await message.answer(screen.text, reply_markup=screen.reply_markup)
                session.commit()
                return


@dp.callback_query(F.data.startswith("nav:"))
async def navigate(callback: CallbackQuery) -> None:
    if callback.message is None:
        await _safe_callback_answer(callback)
        return

    page = callback.data.removeprefix("nav:") if callback.data else "menu"
    if SessionLocal is None:
        await _safe_callback_answer(callback, "Database is not configured.", show_alert=True)
        return

    chat_id = callback.message.chat.id
    user_id = callback.from_user.id
    callback_lock = await CALLBACK_LOCKS.acquire_callback_lock(
        chat_id=chat_id,
        user_id=user_id,
        ttl_seconds=5,
    )
    if callback_lock is None:
        await _safe_callback_answer(callback, "One moment - Fortuna is already opening that.")
        return
    try:
        await _navigate_locked(callback, page)
    finally:
        await CALLBACK_LOCKS.release(callback_lock)


async def _navigate_locked(callback: CallbackQuery, page: str) -> None:
    with SessionLocal() as session:
        user: User | None = None
        try:
            _record_bot_heartbeat(session, status="healthy", source="telegram_callback")
            user = get_or_create_telegram_user(
                session,
                telegram_user_id=callback.from_user.id,
                display_name=_display_name_from_message_user(callback.from_user),
                username=_username_from_message_user(callback.from_user),
                owner_telegram_id=settings.owner_telegram_id,
            )
            user.last_seen = datetime.now(UTC)
            principal = _principal_from_user(user)
            if user.status == USER_STATUS_DISABLED:
                audit_action(
                    session,
                    actor=user,
                    action="access.denied",
                    resource_type="telegram_page",
                    resource_id=page,
                    status="denied",
                    details={"reason": "disabled", "telegram_id_masked": mask_telegram_id(user.telegram_id)},
                )
                screen = render_disabled()
                await _edit_or_send_callback_screen(
                    callback,
                    screen,
                    session=session,
                    user=user,
                    page=page,
                )
                await _safe_callback_answer(callback, "Access disabled.", show_alert=True)
                session.commit()
                return
            if user.status == USER_STATUS_DENIED:
                audit_action(
                    session,
                    actor=user,
                    action="access.denied",
                    resource_type="telegram_page",
                    resource_id=page,
                    status="denied",
                    details={"reason": "denied", "telegram_id_masked": mask_telegram_id(user.telegram_id)},
                )
                screen = render_denied()
                await _edit_or_send_callback_screen(
                    callback,
                    screen,
                    session=session,
                    user=user,
                    page=page,
                )
                await _safe_callback_answer(callback, "Access denied.", show_alert=True)
                session.commit()
                return
            if user.status == USER_STATUS_PENDING:
                if page.startswith("onboarding"):
                    try:
                        forced_step = _apply_onboarding_callback(session, user, page)
                        screen = render_onboarding_page(session, user, step=forced_step)
                        await _edit_or_send_callback_screen(
                            callback,
                            screen,
                            session=session,
                            user=user,
                            page=page,
                        )
                        await _safe_callback_answer(callback)
                    except ValueError:
                        await _safe_callback_answer(callback, "Unable to save onboarding preference.", show_alert=True)
                    session.commit()
                    return
                audit_action(
                    session,
                    actor=user,
                    action="access.denied",
                    resource_type="telegram_page",
                    resource_id=page,
                    status="denied",
                    details={"reason": "pending", "telegram_id_masked": mask_telegram_id(user.telegram_id)},
                )
                screen = render_access_pending()
                await _edit_or_send_callback_screen(
                    callback,
                    screen,
                    session=session,
                    user=user,
                    page=page,
                )
                await _safe_callback_answer(callback, "Access pending.", show_alert=True)
                session.commit()
                return
            chat_id = callback.message.chat.id
            navigation_state = classify_navigation_callback(
                session,
                chat_id=chat_id,
                user=user,
                message_id=callback.message.message_id,
            )
            if navigation_state.is_stale:
                screen = render_main_menu(session=session, user=user)
                navigation_version = reset_navigation_session(session, chat_id=chat_id, user=user)
                try:
                    sent = await callback.message.answer(screen.text, reply_markup=screen.reply_markup)
                    track_bot_message(
                        session,
                        chat_id=sent.chat.id,
                        user=user,
                        message_id=sent.message_id,
                        message_label=TEMPORARY_NAVIGATION,
                        screen="menu",
                        active_navigation=True,
                        navigation_version=navigation_version,
                    )
                except Exception:
                    logger.exception("Unable to send fresh Home for stale callback")
                    _record_callback_button_issue(
                        session,
                        page=page,
                        callback_data=callback.data,
                        issue_type="dead_end",
                        severity="medium",
                        evidence_summary="A stale menu callback could not open a fresh Home screen.",
                        recommended_fix="Inspect Telegram send permissions and stale callback handling.",
                    )
                await _safe_callback_answer(callback, "That menu is old. I opened a fresh Home for you.")
                session.commit()
                return
            if page == "settings:chat_cleanup:clean":
                navigation_version = await _cleanup_navigation_messages_on_start(
                    callback.bot,
                    session,
                    user=user,
                    chat_id=chat_id,
                )
                screen = render_main_menu(session=session, user=user)
                sent = await callback.message.answer(screen.text, reply_markup=screen.reply_markup)
                track_bot_message(
                    session,
                    chat_id=sent.chat.id,
                    user=user,
                    message_id=sent.message_id,
                    message_label=TEMPORARY_NAVIGATION,
                    screen="menu",
                    active_navigation=True,
                    navigation_version=navigation_version,
                )
                await _safe_callback_answer(callback, "Cleaned old menus where Telegram allowed it.")
                session.commit()
                return
            if not await _mark_navigation_callback_if_new(
                callback,
                session=session,
                user=user,
                chat_id=chat_id,
                page=page,
            ):
                await _safe_callback_answer(callback, "One moment.")
                session.commit()
                return
            if page == "recovery:backup:run":
                run, started = start_backup_job(session, actor=user)
                screen = render_backup_job_started_page(run, reused=not started)
                run_identifier = run.run_identifier
                actor_id = user.id
                session.commit()
                if started:
                    asyncio.create_task(_run_backup_job_background(run_identifier, actor_id))
                await _edit_or_send_callback_screen(
                    callback,
                    screen,
                    session=session,
                    user=user,
                    page=page,
                )
                await _safe_callback_answer(callback, "Backup started." if started else "Backup is already running.")
                session.commit()
                return
            if page == "recovery:restore:test":
                test, started = start_restore_job(session, actor=user)
                screen = render_restore_job_started_page(test, reused=not started)
                run_identifier = test.run_identifier
                actor_id = user.id
                session.commit()
                if started:
                    asyncio.create_task(_run_restore_job_background(run_identifier, actor_id))
                await _edit_or_send_callback_screen(
                    callback,
                    screen,
                    session=session,
                    user=user,
                    page=page,
                )
                await _safe_callback_answer(
                    callback,
                    "Restore validation started." if started else "Restore validation is already running.",
                )
                session.commit()
                return
            chat_title = getattr(callback.message.chat, "title", None)
            screen = screen_for_page(
                page,
                principal,
                session=session,
                user=user,
                chat_id=chat_id,
                chat_title=chat_title,
            )
            _set_pending_callback_state(callback.from_user.id, page, session, user)
            await _edit_or_send_callback_screen(
                callback,
                screen,
                session=session,
                user=user,
                page=page,
            )
            target_id = _notification_target_id_for_send_test(page)
            if target_id is not None:
                target = get_notification_target(session, target_id)
                raw_chat_id = decrypt_target_chat_id(target) if target else None
                attempt = None
                if target is not None:
                    attempt = create_delivery_attempt(
                        session,
                        target,
                        event_type="notification.test",
                        actor=user,
                        metadata={"source": "telegram_test"},
                    )
                if target is None or not target.is_active or target.purpose != "testing" or raw_chat_id is None:
                    if attempt is not None:
                        mark_delivery_skipped(session, attempt, actor=user, reason="test target not eligible")
                    await _safe_callback_answer(callback, "Test sends require an active testing target.", show_alert=True)
                    session.commit()
                    return
                try:
                    await callback.bot.send_message(int(raw_chat_id), "Fortuna OS test notification.")
                    if attempt is not None:
                        mark_delivery_sent(session, attempt, actor=user)
                except Exception:
                    if attempt is not None:
                        mark_delivery_failed(session, attempt, actor=user, error_message="telegram_send_failed")
                    logger.warning("Unable to send test notification to configured target")
            if page == "notification_targets:routing_test":
                await _send_pending_routing_smoke_tests(callback.bot, session, user)
            await _safe_callback_answer(callback)
            session.commit()
        except PermissionError:
            session.commit()
            await _safe_callback_answer(callback, "You do not have permission to open this page.", show_alert=True)
        except Exception as exc:
            await _handle_callback_failure(callback, session, user=user, page=page, exc=exc)


async def main() -> None:
    configure_logging()
    token = settings.telegram_bot_token.get_secret_value()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    preflight = polling_preflight()
    if not preflight.allowed:
        logger.error("Fortuna OS bot polling blocked: %s", preflight.reason)
        if SessionLocal is not None:
            with contextlib.suppress(Exception):
                with SessionLocal() as session:
                    _record_bot_heartbeat(
                        session,
                        status="blocked",
                        source="startup_blocked",
                        polling_allowed="False",
                        polling_active="False",
                        polling_block_reason=preflight.reason,
                    )
                    session.commit()
        await _idle_without_polling(preflight.reason)
        return

    lock_key = telegram_polling_lock_key(token)
    guard = BotPollingGuard(
        settings.redis_url,
        key=lock_key,
        owner_id=mask_instance_id(CURRENT_BOT_INSTANCE_ID),
    )
    if not await _acquire_polling_guard(guard):
        lock_owner = guard.current_owner() or "unknown"
        reason = "Another Fortuna OS bot polling instance owns the Redis polling lock."
        if SessionLocal is not None:
            with contextlib.suppress(Exception):
                with SessionLocal() as session:
                    record_polling_conflict(
                        session,
                        instance_id=CURRENT_BOT_INSTANCE_ID,
                        reason=reason,
                        source="redis_polling_lock",
                        conflict_source="redis_lock_owner",
                        polling_lock_owner=lock_owner,
                    )
                    session.commit()
        await _idle_without_polling(reason, status="critical")
        return
    refresh_task: asyncio.Task | None = None
    pending_watchdog_task: asyncio.Task | None = None
    conflict_handler = _PollingConflictLogHandler()
    logging.getLogger("aiogram").addHandler(conflict_handler)

    async def refresh_guard() -> None:
        while True:
            await asyncio.sleep(60)
            try:
                refreshed = await asyncio.wait_for(asyncio.to_thread(guard.refresh), timeout=5)
            except Exception:
                logger.error("Unable to refresh Fortuna OS bot polling lock", exc_info=True)
                refreshed = False
            if not refreshed:
                logger.error("Lost Fortuna OS bot polling lock; stopping process to avoid duplicate polling")
                # If long polling hangs during cancellation, Railway can show the worker as online
                # while Telegram updates are no longer consumed. Exiting immediately is safer: the
                # platform restarts the single primary worker, and the Redis lock prevents duplicate
                # pollers from surviving together.
                os._exit(1)
            if SessionLocal is not None:
                try:
                    with SessionLocal() as session:
                        _record_bot_heartbeat(session, status="healthy", source="polling_loop")
                        session.commit()
                except Exception:
                    logger.warning("Unable to record bot polling heartbeat", exc_info=True)

    bot = Bot(token=token)
    try:
        logger.info("Starting Telegram bot")
        if SessionLocal is not None:
            with SessionLocal() as session:
                duplicates = duplicate_bot_instances(session, current_instance_id=CURRENT_BOT_INSTANCE_ID)
                if duplicates:
                    logger.warning("Found %s other active Fortuna OS bot instance heartbeat(s)", len(duplicates))
                _record_bot_heartbeat(
                    session,
                    status="healthy",
                    source="startup",
                    duplicate_instance_count=str(len(duplicates)),
                )
                session.commit()
        refresh_task = asyncio.create_task(refresh_guard())
        pending_watchdog_task = asyncio.create_task(_watch_telegram_pending_updates(bot))
        await dp.start_polling(
            bot,
            polling_timeout=20,
            allowed_updates=dp.resolve_used_update_types(),
        )
    except TelegramConflictError:
        reason = "Another process is using the same Telegram bot token."
        if SessionLocal is not None:
            with contextlib.suppress(Exception):
                with SessionLocal() as session:
                    record_polling_conflict(
                        session,
                        instance_id=CURRENT_BOT_INSTANCE_ID,
                        reason=reason,
                        source="telegram_conflict_exception",
                        conflict_source="telegram_getupdates",
                        polling_lock_owner=mask_instance_id(CURRENT_BOT_INSTANCE_ID),
                    )
                    session.commit()
        await _idle_without_polling(reason, status="critical")
    finally:
        logging.getLogger("aiogram").removeHandler(conflict_handler)
        if refresh_task is not None:
            refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await refresh_task
        if pending_watchdog_task is not None:
            pending_watchdog_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pending_watchdog_task
        guard.release()


if __name__ == "__main__":
    asyncio.run(main())
