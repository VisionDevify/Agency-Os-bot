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
STALE_MENU_RESPONSE = "That menu is no longer active. Opening the latest screen..."

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
    total_candidates: int
    remaining_count: int
    concurrency_reuse_count: int
    stale_callback_count: int
    multiple_active_count: int
    status: str
    evidence: str
    next_action: str

    @property
    def old_menu_risk(self) -> bool:
        return self.status in {"needs_review", "needs_attention", "critical"}

    @property
    def label(self) -> str:
        return {
            "healthy": "Healthy",
            "needs_review": "Needs Review",
            "needs_attention": "Needs Attention",
            "critical": "Critical",
        }[self.status]


@dataclass(frozen=True)
class CallbackNavigationState:
    classification: str
    active_message_id: int | None
    active_navigation_version: int | None
    callback_message_id: int
    callback_label: str | None
    evidence: str

    @property
    def is_stale(self) -> bool:
        return self.classification in {"stale_old_menu", "unknown_untracked"}

    @property
    def is_current(self) -> bool:
        return self.classification == "current"


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


def active_navigation_message_count(session: Session, *, chat_id: int | None = None) -> int:
    conditions = [
        BotChatMessage.active_navigation.is_(True),
        BotChatMessage.message_label == TEMPORARY_NAVIGATION,
        BotChatMessage.deletion_status == "active",
    ]
    if chat_id is not None:
        conditions.append(BotChatMessage.chat_id == chat_id)
    return session.scalar(select(func.count(BotChatMessage.id)).where(*conditions)) or 0


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
    return classify_navigation_callback(
        session,
        chat_id=chat_id,
        user=user,
        message_id=message_id,
    ).is_stale


def classify_navigation_callback(
    session: Session,
    *,
    chat_id: int,
    user: User,
    message_id: int,
) -> CallbackNavigationState:
    current = current_active_navigation_message(session, chat_id=chat_id, user=user)
    callback_record = session.scalar(
        select(BotChatMessage).where(BotChatMessage.chat_id == chat_id, BotChatMessage.message_id == message_id)
    )
    if callback_record is not None and is_persistent_label(callback_record.message_label):
        return CallbackNavigationState(
            classification="persistent_action",
            active_message_id=current.message_id if current else None,
            active_navigation_version=current.navigation_version if current else None,
            callback_message_id=message_id,
            callback_label=callback_record.message_label,
            evidence="Callback belongs to a persistent message, so cleanup does not invalidate it.",
        )
    if current is None:
        return CallbackNavigationState(
            classification="unknown_untracked",
            active_message_id=None,
            active_navigation_version=None,
            callback_message_id=message_id,
            callback_label=callback_record.message_label if callback_record else None,
            evidence="No active navigation message is currently tracked for this chat.",
        )
    if callback_record is None:
        classification = "current" if current.message_id == message_id else "unknown_untracked"
        evidence = (
            "Callback message matches the active message but has no tracking row."
            if classification == "current"
            else "Callback came from an untracked message while a newer active message exists."
        )
        return CallbackNavigationState(
            classification=classification,
            active_message_id=current.message_id,
            active_navigation_version=current.navigation_version,
            callback_message_id=message_id,
            callback_label=None,
            evidence=evidence,
        )
    if not callback_record.active_navigation:
        return CallbackNavigationState(
            classification="stale_old_menu",
            active_message_id=current.message_id,
            active_navigation_version=current.navigation_version,
            callback_message_id=message_id,
            callback_label=callback_record.message_label,
            evidence="Callback message is tracked as inactive navigation.",
        )
    if callback_record.navigation_version != current.navigation_version:
        return CallbackNavigationState(
            classification="stale_old_menu",
            active_message_id=current.message_id,
            active_navigation_version=current.navigation_version,
            callback_message_id=message_id,
            callback_label=callback_record.message_label,
            evidence="Callback navigation version is older than the active session.",
        )
    if callback_record.message_id != current.message_id:
        return CallbackNavigationState(
            classification="stale_old_menu",
            active_message_id=current.message_id,
            active_navigation_version=current.navigation_version,
            callback_message_id=message_id,
            callback_label=callback_record.message_label,
            evidence="Callback message is not the active navigation message.",
        )
    return CallbackNavigationState(
        classification="current",
        active_message_id=current.message_id,
        active_navigation_version=current.navigation_version,
        callback_message_id=message_id,
        callback_label=callback_record.message_label,
        evidence="Callback belongs to the active navigation message.",
    )


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
    total_candidates: int | None = None,
) -> None:
    run.attempted_count = attempted_count
    run.deleted_count = deleted_count
    run.failed_count = failed_count
    if total_candidates is not None:
        run.total_candidates = total_candidates
    run.preserved_count = (
        session.scalar(
            select(func.count(BotChatMessage.id)).where(
                BotChatMessage.chat_id == run.chat_id,
                BotChatMessage.message_label.in_(PRESERVED_MESSAGE_LABELS),
            )
        )
        or 0
    )
    run.remaining_count = (
        session.scalar(
            select(func.count(BotChatMessage.id)).where(
                BotChatMessage.chat_id == run.chat_id,
                BotChatMessage.message_label.in_(TEMPORARY_MESSAGE_LABELS),
                ~BotChatMessage.deletion_status.in_(TERMINAL_DELETION_STATUSES),
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
    active_groups = session.execute(
        select(BotChatMessage.chat_id, BotChatMessage.user_id, func.count(BotChatMessage.id))
        .where(
            BotChatMessage.message_label == TEMPORARY_NAVIGATION,
            BotChatMessage.active_navigation.is_(True),
            BotChatMessage.deletion_status == "active",
        )
        .group_by(BotChatMessage.chat_id, BotChatMessage.user_id)
    ).all()
    multiple_active_count = sum(max(0, int(count) - 1) for _chat_id, _user_id, count in active_groups)
    remaining_count = (
        session.scalar(
            select(func.count(BotChatMessage.id)).where(
                BotChatMessage.message_label.in_(TEMPORARY_MESSAGE_LABELS),
                ~BotChatMessage.deletion_status.in_(TERMINAL_DELETION_STATUSES),
                BotChatMessage.active_navigation.is_(False),
            )
        )
        or 0
    )
    failed_count = latest.failed_count if latest else 0
    if multiple_active_count:
        status = "needs_attention"
        evidence = f"{multiple_active_count} extra active navigation message(s) are tracked. Active screen safety needs review."
        next_action = "Run Chat Cleanup."
    elif failed_count >= 3:
        status = "needs_review"
        evidence = f"{failed_count} recent cleanup deletion failure(s) were recorded. Active screens still render, but old menus may remain visible."
        next_action = "Open Chat Cleanup settings."
    elif remaining_count:
        status = "healthy"
        evidence = (
            f"{remaining_count} old temporary menu message(s) remain tracked for cleanup. "
            "They are inactive, ignored if clicked, and shown in Details only."
        )
        next_action = "No action needed. Telegram may prevent deletion of older messages."
    else:
        status = "healthy"
        evidence = "One active Telegram screen is tracked. Old menus are ignored."
        next_action = "No cleanup action needed."
    return CleanupMetrics(
        latest_cleanup_at=latest.completed_at if latest and latest.completed_at else None,
        attempted_count=latest.attempted_count if latest else 0,
        deleted_count=latest.deleted_count if latest else 0,
        preserved_count=latest.preserved_count if latest else 0,
        failed_count=failed_count,
        total_candidates=latest.total_candidates if latest else remaining_count,
        remaining_count=max(latest.remaining_count, remaining_count) if latest else remaining_count,
        concurrency_reuse_count=latest.concurrency_reuse_count if latest else 0,
        stale_callback_count=stale_count,
        multiple_active_count=multiple_active_count,
        status=status,
        evidence=evidence,
        next_action=next_action,
    )
