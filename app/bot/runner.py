import asyncio
import contextlib
import logging
import time
from datetime import UTC, datetime

from aiogram import Bot, Dispatcher
from aiogram import F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from app.bot.navigation import screen_for_page
from app.bot.menu import choice_menu
from app.bot.screens import (
    render_access_pending,
    render_account_detail_page,
    render_creator_watch_detail_page,
    render_denied,
    render_disabled,
    render_main_menu,
    render_onboarding_page,
    render_opportunity_detail_page,
    render_post_watch_detail_page,
)
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.migrations import run_migrations
from app.db.session import SessionLocal
from app.models.account import AccountAuthSession
from app.models.opportunity import CREATOR_WATCH_PRIORITIES, OPPORTUNITY_PRIORITIES, POST_WATCH_TYPES, CreatorWatch, PostWatch
from app.models.user import User
from app.services.auth import (
    USER_STATUS_DISABLED,
    USER_STATUS_DENIED,
    USER_STATUS_PENDING,
    audit_action,
    get_or_create_telegram_user,
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
    create_manual_opportunity,
    create_post_watch,
    comment_strategies_for_opportunity,
    get_opportunity,
    record_opportunity_result,
    update_creator_watch,
)
from app.services.permissions import PermissionPrincipal, RoleName, require_owner
from app.services.model_brands import get_model_brand
from app.services.heartbeats import record_heartbeat
from app.services.notifications import (
    create_delivery_attempt,
    decrypt_target_chat_id,
    get_notification_target,
    mark_delivery_failed,
    mark_delivery_sent,
    mark_delivery_skipped,
)
from app.services.team_operations import BotPollingGuard, update_user_localization

logger = logging.getLogger(__name__)
dp = Dispatcher()

PENDING_ACCOUNT_CREATES: dict[int, dict[str, int | str]] = {}
PENDING_AUTH_CODES: dict[int, int] = {}
PENDING_CREATOR_INTAKES: dict[int, dict[str, int | str | None]] = {}
PENDING_OPPORTUNITY_INTAKES: dict[int, dict[str, int | str | None]] = {}
PENDING_POST_INTAKES: dict[int, dict[str, int | str | None]] = {}
PENDING_RESULT_INTAKES: dict[int, dict[str, int | str | None]] = {}


async def _acquire_polling_guard(
    guard: BotPollingGuard,
    *,
    retry_seconds: int = 10,
    max_wait_seconds: int = 420,
) -> bool:
    if guard.acquire():
        return True

    logger.warning("Another Agency OS bot polling instance appears active; waiting for lock to clear")
    deadline = time.monotonic() + max_wait_seconds
    while time.monotonic() < deadline:
        await asyncio.sleep(retry_seconds)
        if guard.acquire():
            logger.info("Acquired Agency OS bot polling lock after waiting")
            return True
    return False


def _principal_from_user(user: User) -> PermissionPrincipal:
    role = RoleName.OWNER if user.is_owner else RoleName.VIEWER
    return PermissionPrincipal(telegram_id=user.telegram_id, is_owner=user.is_owner, role=role)


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
    parts = page.split(":")
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


def _notification_target_id_for_send_test(page: str) -> int | None:
    parts = page.split(":")
    if len(parts) >= 3 and parts[0] == "notification_target" and parts[1].isdigit() and parts[2] == "send_test":
        return int(parts[1])
    return None


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
        record_heartbeat(session, service_name="bot", status="healthy", metadata={"source": "telegram_start"})
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
            await message.answer(screen.text, reply_markup=screen.reply_markup)
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
        session.commit()
    await message.answer(screen.text, reply_markup=screen.reply_markup)


@dp.message(F.text)
async def text_input(message: Message) -> None:
    if message.from_user is None or SessionLocal is None or message.text is None:
        return

    telegram_id = message.from_user.id
    with SessionLocal() as session:
        record_heartbeat(session, service_name="bot", status="healthy", metadata={"source": "telegram_text"})
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
        await callback.answer()
        return

    page = callback.data.removeprefix("nav:") if callback.data else "menu"
    if SessionLocal is None:
        await callback.answer("Database is not configured.", show_alert=True)
        return

    with SessionLocal() as session:
        record_heartbeat(session, service_name="bot", status="healthy", metadata={"source": "telegram_callback"})
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
            await callback.message.edit_text(screen.text, reply_markup=screen.reply_markup)
            await callback.answer("Access disabled.", show_alert=True)
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
            await callback.message.edit_text(screen.text, reply_markup=screen.reply_markup)
            await callback.answer("Access denied.", show_alert=True)
            session.commit()
            return
        if user.status == USER_STATUS_PENDING:
            if page.startswith("onboarding"):
                try:
                    forced_step = _apply_onboarding_callback(session, user, page)
                    screen = render_onboarding_page(session, user, step=forced_step)
                    await callback.message.edit_text(screen.text, reply_markup=screen.reply_markup)
                    await callback.answer()
                except ValueError:
                    await callback.answer("Unable to save onboarding preference.", show_alert=True)
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
            await callback.message.edit_text(screen.text, reply_markup=screen.reply_markup)
            await callback.answer("Access pending.", show_alert=True)
            session.commit()
            return
        try:
            chat_id = callback.message.chat.id
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
            await callback.message.edit_text(screen.text, reply_markup=screen.reply_markup)
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
                    await callback.answer("Test sends require an active testing target.", show_alert=True)
                    session.commit()
                    return
                try:
                    await callback.bot.send_message(int(raw_chat_id), "Agency OS test notification.")
                    if attempt is not None:
                        mark_delivery_sent(session, attempt, actor=user)
                except Exception:
                    if attempt is not None:
                        mark_delivery_failed(session, attempt, actor=user, error_message="telegram_send_failed")
                    logger.warning("Unable to send test notification to configured target")
            await callback.answer()
            session.commit()
        except PermissionError:
            session.commit()
            await callback.answer("You do not have permission to open this page.", show_alert=True)


async def main() -> None:
    configure_logging()
    token = settings.telegram_bot_token.get_secret_value()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    guard = BotPollingGuard(settings.redis_url)
    if not await _acquire_polling_guard(guard):
        raise RuntimeError("Another Agency OS bot polling instance appears active after waiting")
    refresh_task: asyncio.Task | None = None

    main_task = asyncio.current_task()

    async def refresh_guard() -> None:
        while True:
            await asyncio.sleep(60)
            if not guard.refresh():
                logger.error("Lost Agency OS bot polling lock; stopping process to avoid duplicate polling")
                if main_task is not None:
                    main_task.cancel()
                return

    bot = Bot(token=token)
    try:
        logger.info("Starting Telegram bot")
        if SessionLocal is not None:
            run_migrations()
            with SessionLocal() as session:
                record_heartbeat(session, service_name="bot", status="healthy", metadata={"source": "startup"})
                session.commit()
        refresh_task = asyncio.create_task(refresh_guard())
        await dp.start_polling(bot)
    finally:
        if refresh_task is not None:
            refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await refresh_task
        guard.release()


if __name__ == "__main__":
    asyncio.run(main())
