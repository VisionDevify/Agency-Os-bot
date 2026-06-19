from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.models.user import User


SECTION_EMOJIS = {
    "automation": "🤖",
    "details": "🔎",
    "help": "❓",
    "home": "🌙",
    "learning": "🧠",
    "opportunities": "🎯",
    "proxy": "🛡",
    "reports": "📊",
    "setup": "🧩",
    "team": "👥",
    "alerts": "🚨",
    "success": "✅",
    "next": "✨",
    "owner": "👑",
}

HEALTH_EMOJIS = {
    "healthy": "🟢",
    "ok": "🟢",
    "warning": "🟡",
    "needs_attention": "🟡",
    "critical": "🔴",
    "failed": "🔴",
    "paused": "💤",
}


@dataclass(frozen=True)
class Greeting:
    emoji: str
    text: str
    hour: int


def user_timezone(user: User | None) -> ZoneInfo:
    timezone = user.timezone if user and user.timezone and user.timezone != "UTC" else "America/New_York"
    try:
        return ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo("America/New_York")


def local_now(user: User | None, now: datetime | None = None) -> datetime:
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(user_timezone(user))


def display_name(user: User | None) -> str:
    if user is None:
        return "there"
    return user.display_name or user.username or "there"


def dynamic_greeting(user: User | None, now: datetime | None = None) -> Greeting:
    current = local_now(user, now)
    hour = current.hour
    if 5 <= hour < 12:
        return Greeting("🌅", f"Good Morning, {display_name(user)}", hour)
    if 12 <= hour < 17:
        return Greeting("☀️", f"Good Afternoon, {display_name(user)}", hour)
    if 17 <= hour < 21:
        return Greeting("🌇", f"Good Evening, {display_name(user)}", hour)
    return Greeting("🌙", f"Good Night, {display_name(user)}", hour)


def health_emoji(status: str | None) -> str:
    return HEALTH_EMOJIS.get((status or "").strip().casefold(), "🟡")


def section_emoji(section: str) -> str:
    return SECTION_EMOJIS.get(section.strip().casefold(), "✨")


def status_label(healthy: bool, *, warning_text: str = "Needs attention") -> str:
    return "Everything is running smoothly." if healthy else warning_text


def next_action_phrase(action: str | None) -> str:
    value = (action or "").strip()
    return value or "Nothing urgent here."


def simple_block(title: str, body: str | list[str], *, emoji: str | None = None) -> list[str]:
    lines = [f"{emoji + ' ' if emoji else ''}{title}"]
    if isinstance(body, list):
        lines.extend(body or ["Nothing urgent here."])
    else:
        lines.append(body)
    return lines


def screen_lines(
    *,
    header: str,
    status: str,
    noticed: list[str] | None,
    next_move: str,
    header_emoji: str = "🌙",
    status_kind: str = "healthy",
) -> list[str]:
    noticed_lines = [f"• {item}" for item in (noticed or ["Nothing urgent here."])]
    return [
        f"{header_emoji} {header}",
        "",
        f"{health_emoji(status_kind)} Status",
        status,
        "",
        "🎯 What Fortuna Noticed",
        *noticed_lines,
        "",
        "✨ Next Best Move",
        next_action_phrase(next_move),
    ]
