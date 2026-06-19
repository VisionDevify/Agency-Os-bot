from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.menu import callback_for, page_controls
from app.services.opportunity_prediction import best_opportunity_prediction, latest_prediction_for, predict_opportunity

from .formatting import *


def _best_opportunity_menu(opportunity_id: int | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if opportunity_id is not None:
        rows.extend(
            [
                [InlineKeyboardButton(text="👀 Review", callback_data=callback_for(f"opportunity:{opportunity_id}"))],
                [InlineKeyboardButton(text="✍️ Comment Ideas", callback_data=callback_for(f"opportunity:{opportunity_id}:strategies"))],
                [InlineKeyboardButton(text="📌 Assign", callback_data=callback_for(f"opportunity:{opportunity_id}:assign"))],
                [InlineKeyboardButton(text="❌ Skip", callback_data=callback_for(f"opportunity:{opportunity_id}:status"))],
                [InlineKeyboardButton(text="🔎 Details", callback_data=callback_for(f"opportunity_prediction:{opportunity_id}:details"))],
            ]
        )
    rows.extend(page_controls(back_to="opportunities"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def render_best_opportunity_page(session: Session, user: User | None = None, *, details: bool = False) -> Screen:
    result = best_opportunity_prediction(session, actor=user)
    if result is None:
        lines = [
            "🎯 Best Opportunity",
            "",
            "Fortuna does not see an active opportunity yet.",
            "",
            "✨ Next Best Move",
            "Add a creator, paste a public post, or create a manual opportunity.",
        ]
        return Screen("\n".join(lines), _best_opportunity_menu())
    opportunity = result.opportunity
    prediction = result.prediction
    if not details:
        lines = [
            "🎯 Best Opportunity",
            "",
            "Fortuna found one opportunity worth reviewing first.",
            "",
            "🔥 Why this one",
            prediction.reasoning_summary.split(".")[0] + ".",
            "",
            "✨ Suggested Move",
            "Assign it for manual review.",
            "",
            f"Opportunity: {opportunity.title}",
            f"Suggested angle: {prediction.recommended_angle or 'curiosity'}",
            f"Confidence: {prediction.confidence_score}/100",
            "",
            "No auto-posting. Human review only.",
        ]
        return Screen("\n".join(lines), _best_opportunity_menu(opportunity.id))
    lines = [
        "🔎 Opportunity Prediction Details",
        "",
        f"Opportunity: {opportunity.title}",
        f"Predicted Quality: {prediction.predicted_quality}/100",
        f"Confidence: {prediction.confidence_score}/100",
        f"Recommended Angle: {prediction.recommended_angle or 'curiosity'}",
        f"Recommended Chatter ID: {prediction.recommended_chatter_id or 'None'}",
        "",
        "Reasoning:",
        prediction.reasoning_summary,
        "",
        "Safety:",
        prediction.risk_notes or "Human review only.",
    ]
    return Screen("\n".join(lines), _best_opportunity_menu(opportunity.id))


def render_opportunity_prediction_detail_page(session: Session, opportunity_id: int) -> Screen:
    opportunity = session.get(Opportunity, opportunity_id)
    if opportunity is None:
        return Screen("Opportunity not found.", page_menu(back_to="opportunities"))
    prediction = latest_prediction_for(session, opportunity_id) or predict_opportunity(session, opportunity)
    lines = [
        "🔎 Opportunity Prediction Details",
        "",
        f"Opportunity: {opportunity.title}",
        f"Predicted Quality: {prediction.predicted_quality}/100",
        f"Confidence: {prediction.confidence_score}/100",
        f"Recommended Angle: {prediction.recommended_angle or 'curiosity'}",
        "",
        "Why:",
        prediction.reasoning_summary,
        "",
        "Safety:",
        prediction.risk_notes or "Human review only.",
    ]
    return Screen("\n".join(lines), _best_opportunity_menu(opportunity.id))
