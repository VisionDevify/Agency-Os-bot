from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat import BOT_MESSAGE_TYPES, BotChatMessage, ChatCleanupPreference
from app.models.user import User

TEMPORARY_NAVIGATION = "temporary_navigation"
PERSISTENT_ALERT = "persistent_alert"
PERSISTENT_REPORT = "persistent_report"
PERSISTENT_APPROVAL = "persistent_approval"
PERSISTENT_EXPORT = "persistent_export"
ERROR_FALLBACK = "error_fallback"

PERSISTENT_MESSAGE_TYPES = {
    PERSISTENT_ALERT,
    PERSISTENT_REPORT,
    PERSISTENT_APPROVAL,
    PERSISTENT_EXPORT,
    ERROR_FALLBACK,
}


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


def track_bot_message(
    session: Session,
    *,
    chat_id: int,
    user: User | None,
    message_id: int,
    message_type: str = TEMPORARY_NAVIGATION,
    page: str | None = None,
) -> BotChatMessage:
    if message_type not in BOT_MESSAGE_TYPES:
        raise ValueError("Unsupported bot message type.")

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
            message_type=message_type,
            page=page,
            is_active=True,
        )
        session.add(record)
    else:
        record.user_id = user.id if user is not None else record.user_id
        record.message_type = message_type
        record.page = page
        record.is_active = True
        record.deleted_at = None
        record.delete_error = None
    session.flush()
    return record


def temporary_navigation_messages(
    session: Session,
    *,
    chat_id: int,
    user: User,
    limit: int = 25,
) -> list[BotChatMessage]:
    return list(
        session.scalars(
            select(BotChatMessage)
            .where(
                BotChatMessage.chat_id == chat_id,
                BotChatMessage.user_id == user.id,
                BotChatMessage.message_type == TEMPORARY_NAVIGATION,
                BotChatMessage.is_active.is_(True),
                BotChatMessage.deleted_at.is_(None),
            )
            .order_by(BotChatMessage.created_at.desc(), BotChatMessage.id.desc())
            .limit(limit)
        ).all()
    )


def mark_message_deleted(record: BotChatMessage) -> None:
    record.is_active = False
    record.delete_attempted_at = datetime.now(UTC)
    record.deleted_at = record.delete_attempted_at
    record.delete_error = None


def mark_message_delete_failed(record: BotChatMessage, *, reason: str = "telegram_delete_failed") -> None:
    record.delete_attempted_at = datetime.now(UTC)
    record.delete_error = reason[:160]
