from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.menu import callback_for, page_controls
from app.services.team_intelligence import team_intelligence_summary

from .formatting import *


def render_team_intelligence_page(session: Session, user: User | None = None, *, details: bool = False) -> Screen:
    summary = team_intelligence_summary(session)
    if not details:
        best = summary.best_chatter.display_name or summary.best_chatter.username if summary.best_chatter else None
        lines = [
            "👥 Team Intelligence",
            "",
            "Fortuna checked the team.",
            "",
            "Status",
            "Ready for routing." if summary.snapshots else "No active team data yet.",
            "",
            "✨ Next Best Move",
            summary.next_best_move,
            "",
            "What Fortuna noticed",
            f"• Best available chatter: {best or 'Not enough team data yet'}",
            f"• Overloaded users: {len(summary.overloaded_users)}",
            f"• Idle users: {len(summary.idle_users)}",
        ]
        return Screen(
            "\n".join(lines),
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🎯 Assign Work", callback_data=callback_for("opportunities:manager"))],
                    [InlineKeyboardButton(text="👥 Team Load", callback_data=callback_for("team_intelligence:details"))],
                    [InlineKeyboardButton(text="🔎 Details", callback_data=callback_for("team_intelligence:details"))],
                    [InlineKeyboardButton(text="❓ Help", callback_data=callback_for("help_copilot:team_intelligence"))],
                    *page_controls(back_to="owner_advanced"),
                ]
            ),
        )
    lines = [
        "🔎 Team Load Details",
        "",
    ]
    if not summary.snapshots:
        lines.append("No team snapshots yet.")
    for snapshot in summary.snapshots[:10]:
        member = session.get(User, snapshot.user_id)
        name = member.display_name or member.username or f"User {snapshot.user_id}" if member else f"User {snapshot.user_id}"
        lines.append(f"• {name} — {snapshot.role}")
        lines.append(f"  Workload: {snapshot.workload_score}/100 | Reliability: {snapshot.reliability_score}/100")
        lines.append(f"  Tasks done: {snapshot.tasks_completed} | Overdue: {snapshot.tasks_overdue}")
    return Screen(
        "\n".join(lines),
        InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Executive Summary", callback_data=callback_for("team_intelligence"))],
                *page_controls(back_to="team_intelligence"),
            ]
        ),
    )
