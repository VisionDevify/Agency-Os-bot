from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.models.chat import (
    DELETION_STATUSES,
    MESSAGE_LABELS,
    PERSISTENT_ALERT,
    PERSISTENT_APPROVAL,
    PERSISTENT_DELIVERY,
    PERSISTENT_EXPORT,
    PERSISTENT_INCIDENT,
    PERSISTENT_MESSAGE_LABELS,
    PERSISTENT_REPORT,
    PRESERVED_MESSAGE_LABELS,
    TEMPORARY_ERROR,
    TEMPORARY_HELP,
    TEMPORARY_MESSAGE_LABELS,
    TEMPORARY_NAVIGATION,
    TEMPORARY_STATUS,
    TERMINAL_DELETION_STATUSES,
    UNKNOWN_PRESERVE,
    BotChatMessage,
    ChatCleanupPreference,
    ChatCleanupRun,
)
from app.models.user import User

CANONICAL_MESSAGE_LABELS = MESSAGE_LABELS

LEGACY_LABEL_MAP = {
    "error_fallback": TEMPORARY_ERROR,
    "temporary_navigation": TEMPORARY_NAVIGATION,
    "persistent_alert": PERSISTENT_ALERT,
    "persistent_report": PERSISTENT_REPORT,
    "persistent_export": PERSISTENT_EXPORT,
    "persistent_approval": PERSISTENT_APPROVAL,
}


@dataclass(frozen=True)
class CleanupMetrics:
    latest_cleanup_at: datetime | None
    attempted_count: int
    deleted_count: int
    preserved_count: int
    failed_count: int
    concurrency_reuse_count: int
    stale_callback_count: int


def normalize_message_label(label: str | None) -> str:
    clean = (label or "").strip()
    if clean in MESSAGE_LABELS:
        return clean
    return LEGACY_LABEL_MAP.get(clean, UNKNOWN_PRESERVE)


def is_temporary_label(label: str | None) -> bool:
    return normalize_message_label(label) in TEMPORARY_MESSAGE_LABELS


def is_persistent_label(label: str | None) -> bool:
    return normalize_message_label(label) in PRESERVED_MESSAGE_LABELS


def get_or_create_chat_cleanup_preference(
    session: Session,
    *,
    user: User,
    chat_id: int,
) -> ChatCleanupPreference:
    preference = session.scalar(
        select(ChatCleanupPreference).where(
            ChatCleanupPreference.user_id == user.id,
            ChatCleanupPreference.chat_id == chat_id,
        )
    )
    if preference is None:
        preference = ChatCleanupPreference(user_id=user.id, chat_id=chat_id, clean_on_start=True)
        session.add(preference)
        session.flush()
    return preference


def chat_cleanup_enabled(session: Session, *, user: User, chat_id: int) -> bool:
    return get_or_create_chat_cleanup_preference(session, user=user, chat_id=chat_id).clean_on_start


def set_chat_cleanup_enabled(
    session: Session,
    *,
    user: User,
    chat_id: int,
    enabled: bool,
) -> ChatCleanupPreference:
    preference = get_or_create_chat_cleanup_preference(session, user=user, chat_id=chat_id)
    preference.clean_on_start = enabled
    return preference


def toggle_chat_cleanup(session: Session, *, user: User, chat_id: int) -> ChatCleanupPreference:
    preference = get_or_create_chat_cleanup_preference(session, user=user, chat_id=chat_id)
    preference.clean_on_start = not preference.clean_on_start
    return preference


def current_active_navigation_message(
    session: Session,
    *,
    chat_id: int,
    user: User | None,
) -> BotChatMessage | None:
    base_conditions = [
        BotChatMessage.chat_id == chat_id,
        BotChatMessage.active_navigation.is_(True),
        BotChatMessage.message_label == TEMPORARY_NAVIGATION,
        BotChatMessage.deletion_status == "active",
    ]
    if user is not None:
        user_current = session.scalar(
            select(BotChatMessage)
            .where(*base_conditions, BotChatMessage.user_id == user.id)
            .order_by(desc(BotChatMessage.navigation_version), desc(BotChatMessage.updated_at), desc(BotChatMessage.id))
            .limit(1)
        )
        if user_current is not None:
            return user_current
    return session.scalar(
        select(BotChatMessage)
        .where(*base_conditions)
        .order_by(desc(BotChatMessage.navigation_version), desc(BotChatMessage.updated_at), desc(BotChatMessage.id))
        .limit(1)
    )


def next_navigation_version(session: Session, *, chat_id: int, user: User | None) -> int:
    conditions = [BotChatMessage.chat_id == chat_id]
    if user is not None:
        conditions.append(BotChatMessage.user_id == user.id)
    current_max = session.scalar(select(func.max(BotChatMessage.navigation_version)).where(*conditions)) or 0
    return int(current_max) + 1


def clear_active_navigation(session: Session, *, chat_id: int, user: User | None = None) -> None:
    conditions = [BotChatMessage.chat_id == chat_id, BotChatMessage.active_navigation.is_(True)]
    if user is not None:
        conditions.append(BotChatMessage.user_id == user.id)
    for record in session.scalars(select(BotChatMessage).where(*conditions)).all():
        record.active_navigation = False


def reset_navigation_session(session: Session, *, chat_id: int, user: User | None = None) -> int:
    clear_active_navigation(session, chat_id=chat_id, user=user)
    return next_navigation_version(session, chat_id=chat_id, user=user)


def track_bot_message(
    session: Session,
    *,
    chat_id: int,
    user: User | None,
    message_id: int,
    message_label: str = TEMPORARY_NAVIGATION,
    screen: str | None = None,
    active_navigation: bool | None = None,
    navigation_version: int | None = None,
) -> BotChatMessage:
    label = normalize_message_label(message_label)
    if active_navigation is None:
        active_navigation = label == TEMPORARY_NAVIGATION
    if active_navigation:
        current = current_active_navigation_message(session, chat_id=chat_id, user=user)
        navigation_version = navigation_version or (current.navigation_version if current else None)
        if navigation_version is None:
            navigation_version = next_navigation_version(session, chat_id=chat_id, user=user)
        clear_active_navigation(session, chat_id=chat_id, user=user)
    else:
        navigation_version = navigation_version or 0

    record = session.scalar(
        select(BotChatMessage).where(
            BotChatMessage.chat_id == chat_id,
            BotChatMessage.message_id == message_id,
        )
    )
    if record is None:
        record = BotChatMessage(
            chat_id=chat_id,
            user_id=user.id if user is not None else None,
            message_id=message_id,
            message_label=label,
            screen=screen,
            active_navigation=bool(active_navigation),
            deletion_status="active" if label not in PRESERVED_MESSAGE_LABELS else "preserved",
            navigation_version=int(navigation_version),
        )
        session.add(record)
    else:
        record.user_id = user.id if user is not None else record.user_id
        record.message_label = label
        record.screen = screen
        record.active_navigation = bool(active_navigation)
        record.deletion_status = "active" if label not in PRESERVED_MESSAGE_LABELS else "preserved"
        record.cleanup_completed_at = None
        record.navigation_version = int(navigation_version)
    session.flush()
    return record


def temporary_cleanup_messages(
    session: Session,
    *,
    chat_id: int,
    limit: int | None = None,
) -> list[BotChatMessage]:
    statement = (
        select(BotChatMessage)
        .where(
            BotChatMessage.chat_id == chat_id,
            BotChatMessage.message_label.in_(TEMPORARY_MESSAGE_LABELS),
            ~BotChatMessage.deletion_status.in_(TERMINAL_DELETION_STATUSES),
        )
        .order_by(BotChatMessage.created_at.desc(), BotChatMessage.id.desc())
    )
    if limit is not None:
        statement = statement.limit(limit)
    return list(session.scalars(statement).all())


def temporary_navigation_messages(
    session: Session,
    *,
    chat_id: int,
    user: User | None = None,
    limit: int | None = 100,
) -> list[BotChatMessage]:
    conditions = [
        BotChatMessage.chat_id == chat_id,
        BotChatMessage.message_label.in_(TEMPORARY_MESSAGE_LABELS),
        ~BotChatMessage.deletion_status.in_(TERMINAL_DELETION_STATUSES),
    ]
    if user is not None:
        conditions.append(BotChatMessage.user_id == user.id)
    statement = select(BotChatMessage).where(*conditions).order_by(BotChatMessage.created_at.desc(), BotChatMessage.id.desc())
    if limit is not None:
        statement = statement.limit(limit)
    return list(session.scalars(statement).all())


def current_temporary_navigation_message(
    session: Session,
    *,
    chat_id: int,
    user: User,
) -> BotChatMessage | None:
    return current_active_navigation_message(session, chat_id=chat_id, user=user)


def is_stale_navigation_callback(
    session: Session,
    *,
    chat_id: int,
    user: User,
    message_id: int,
) -> bool:
    current = current_active_navigation_message(session, chat_id=chat_id, user=user)
    if current is None:
        return False
    callback_record = session.scalar(
        select(BotChatMessage).where(BotChatMessage.chat_id == chat_id, BotChatMessage.message_id == message_id)
    )
    if callback_record is None:
        return current.message_id != message_id
    if not callback_record.active_navigation:
        return True
    if callback_record.navigation_version != current.navigation_version:
        return True
    return callback_record.message_id != current.message_id


def start_cleanup_run(session: Session, *, chat_id: int, user: User | None) -> ChatCleanupRun:
    now = datetime.now(UTC)
    run = ChatCleanupRun(
        cleanup_run_id=str(uuid4()),
        chat_id=chat_id,
        user_id=user.id if user is not None else None,
        status="running",
        started_at=now,
    )
    session.add(run)
    session.flush()
    return run


def latest_running_cleanup_run(session: Session, *, chat_id: int) -> ChatCleanupRun | None:
    return session.scalar(
        select(ChatCleanupRun)
        .where(ChatCleanupRun.chat_id == chat_id, ChatCleanupRun.status == "running")
        .order_by(desc(ChatCleanupRun.started_at), desc(ChatCleanupRun.id))
        .limit(1)
    )


def reuse_cleanup_run(session: Session, *, chat_id: int, user: User | None) -> ChatCleanupRun:
    run = latest_running_cleanup_run(session, chat_id=chat_id)
    if run is None:
        run = start_cleanup_run(session, chat_id=chat_id, user=user)
        run.status = "reused"
    run.concurrency_reuse_count += 1
    return run


def mark_cleanup_started(record: BotChatMessage, run: ChatCleanupRun) -> None:
    now = datetime.now(UTC)
    record.deletion_status = "cleanup_started"
    record.cleanup_batch_id = run.cleanup_run_id
    record.cleanup_run_id = run.cleanup_run_id
    record.cleanup_started_at = now


def mark_message_deleted(record: BotChatMessage, *, run: ChatCleanupRun | None = None) -> None:
    record.active_navigation = False
    record.deletion_status = "deleted"
    record.cleanup_completed_at = datetime.now(UTC)
    if run is not None:
        record.cleanup_batch_id = run.cleanup_run_id
        record.cleanup_run_id = run.cleanup_run_id


def mark_message_delete_failed(
    record: BotChatMessage,
    *,
    reason: str = "failed",
    run: ChatCleanupRun | None = None,
) -> None:
    status = reason if reason in DELETION_STATUSES else "failed"
    record.active_navigation = False
    record.deletion_status = status
    record.cleanup_completed_at = datetime.now(UTC)
    if run is not None:
        record.cleanup_batch_id = run.cleanup_run_id
        record.cleanup_run_id = run.cleanup_run_id


def complete_cleanup_run(
    session: Session,
    run: ChatCleanupRun,
    *,
    attempted_count: int,
    deleted_count: int,
    failed_count: int,
) -> None:
    run.attempted_count = attempted_count
    run.deleted_count = deleted_count
    run.failed_count = failed_count
    run.preserved_count = (
        session.scalar(
            select(func.count(BotChatMessage.id)).where(
                BotChatMessage.chat_id == run.chat_id,
                BotChatMessage.message_label.in_(PRESERVED_MESSAGE_LABELS),
            )
        )
        or 0
    )
    run.status = "completed"
    run.completed_at = datetime.now(UTC)


def classify_delete_exception(exc: BaseException) -> str:
    text = str(exc).casefold()
    if "not found" in text or "message to delete not found" in text:
        return "already_missing"
    if "too old" in text:
        return "too_old"
    if "can't be deleted" in text or "cannot be deleted" in text or "forbidden" in text:
        return "forbidden"
    return "failed"


def chat_cleanup_metrics(session: Session) -> CleanupMetrics:
    latest = session.scalar(select(ChatCleanupRun).order_by(desc(ChatCleanupRun.started_at), desc(ChatCleanupRun.id)).limit(1))
    stale_count = (
        session.scalar(
            select(func.count(BotChatMessage.id)).where(
                BotChatMessage.message_label == TEMPORARY_NAVIGATION,
                BotChatMessage.active_navigation.is_(False),
                ~BotChatMessage.deletion_status.in_(TERMINAL_DELETION_STATUSES),
            )
        )
        or 0
    )
    return CleanupMetrics(
        latest_cleanup_at=latest.completed_at if latest and latest.completed_at else None,
        attempted_count=latest.attempted_count if latest else 0,
        deleted_count=latest.deleted_count if latest else 0,
        preserved_count=latest.preserved_count if latest else 0,
        failed_count=latest.failed_count if latest else 0,
        concurrency_reuse_count=latest.concurrency_reuse_count if latest else 0,
        stale_callback_count=stale_count,
    )
