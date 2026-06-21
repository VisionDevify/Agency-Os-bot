from __future__ import annotations


ROOT_SCREEN = "menu"

ROOT_LEVEL_SCREENS = {
    "menu",
    "start_here",
    "today_priorities",
    "setup_progress",
    "proxies",
    "opportunities",
    "help",
    "owner_advanced",
}

MORE_CHILDREN = {
    "intelligence",
    "automations",
    "reports",
    "settings",
    "production_observability",
    "users",
    "executive_mode",
    "coo",
    "coo:briefing",
    "recovery_center",
    "team_intelligence",
    "platforms",
    "search",
    "ai_brain",
    "agency_awareness",
    "reliability",
}


def parent_page_for(page: str | None) -> str:
    current = page or ROOT_SCREEN
    if current in ROOT_LEVEL_SCREENS:
        return ROOT_SCREEN
    if current.startswith("help_from:"):
        body = current.removeprefix("help_from:")
        return body.split(":topic:", 1)[0] if body else "help"
    if current.startswith("help_copilot_from:"):
        body = current.removeprefix("help_copilot_from:")
        return body.split(":question:", 1)[0] if body else "help"
    if current == "help_copilot":
        return "help"
    if current.startswith("help:") or current.startswith("help_copilot:"):
        return "help"
    if current in {"ui_self_test", "ui_self_test:run", "ui_self_test:details"}:
        return "settings"
    if current in {"callback_failure_review", "debug_last_error", "production_status"}:
        return "settings"
    if current in {"models:list", "models:dashboard", "models:search"}:
        return "models"
    if current == "first_workspace":
        return "start_here"
    if current == "coo:readiness":
        return "agency_activation"
    if current in {"coo", "coo:briefing"}:
        return "owner_advanced"
    if current in {"coo:briefing:details", "decision:top", "decision:details"} or current.startswith("decision:memory"):
        return "coo:briefing"
    if current == "intelligence:quality":
        return "coo:briefing"
    if current == "intelligence:quality:details":
        return "intelligence:quality"
    if current == "intelligence:quality:trends":
        return "intelligence:quality"
    if current == "intelligence:quality:trends:details":
        return "intelligence:quality:trends"
    if current == "intelligence:quality:categories":
        return "intelligence:quality:trends"
    if current.startswith("prediction:"):
        return "intelligence:quality:trends"
    if current == "reality:check":
        return "intelligence:quality"
    if current.startswith("reality:"):
        return "reality:check"
    if current in {"decision:review", "decision:timeline", "knowledge:memory"}:
        return "reality:check"
    if current == "decision:review:details":
        return "decision:review"
    if current.startswith("owner_validation:"):
        return "decision:review"
    if current == "evidence:notes":
        return "decision:review"
    if current.startswith("evidence:notes:"):
        return "evidence:notes"
    if current.startswith("knowledge:memory:"):
        return "knowledge:memory"
    if current.startswith("coo:"):
        return "coo"
    if current in MORE_CHILDREN:
        return "owner_advanced"
    if current.startswith("intelligence:trends"):
        return "intelligence"
    if current.startswith("intelligence:learning:"):
        return "intelligence:learning"
    if current.startswith("intelligence:"):
        return "intelligence"
    if current.startswith("proxy:"):
        parts = current.split(":")
        if len(parts) >= 3 and parts[2] == "manage":
            return f"proxy:{parts[1]}"
        if len(parts) >= 4 and parts[2] in {"rotate_preview", "archive_confirm", "delete_confirm"}:
            return f"proxy:{parts[1]}:manage"
        if len(parts) >= 3:
            return f"proxy:{parts[1]}"
        return "proxies:list"
    if current.startswith("proxies:"):
        return "proxies"
    if current.startswith("setup:wizard:model") or current.startswith("model:"):
        return "setup_progress"
    if current.startswith("accounts:") or current.startswith("account:"):
        return "setup_progress" if "add" in current else "accounts"
    if current.startswith("opportunities:") or current.startswith("opportunity:"):
        return "opportunities"
    if current.startswith("opportunity_prediction:"):
        return "opportunities"
    if current.startswith("recovery:"):
        return "recovery_center"
    if current.startswith("platforms:notifications:"):
        return "platforms:notifications"
    if current.startswith("platforms:alert_"):
        return "platforms:notifications"
    if current.startswith("platforms:"):
        return "platforms"
    if current in {"search:details", "search:run", "search:opportunity", "search:platform_signals", "search:coo_context", "search:history", "search:settings"}:
        return "search"
    if current == "search:history:rerun" or current.startswith("search:results"):
        return "search:history"
    if current in {"ai_brain:details", "ai_brain:settings", "ai_brain:critic", "ai_brain:evidence", "ai_brain:search", "ai_brain:coo", "ai_brain:opportunity"}:
        return "ai_brain"
    if current.startswith("agency_awareness:"):
        return "agency_awareness"
    if current.startswith("reliability:"):
        return "reliability"
    if current.startswith("team_intelligence:"):
        return "team_intelligence"
    if current.startswith("notification_") or current.startswith("notification:"):
        return "settings"
    if current in {"integrity", "integrity:details", "bot_status", "bot_instance_status"}:
        return "production_observability"
    return ROOT_SCREEN


def root_page_for(page: str | None) -> str:
    current = page or ROOT_SCREEN
    if current == ROOT_SCREEN:
        return ROOT_SCREEN
    if current.startswith("settings:chat_cleanup"):
        return "settings"
    if current in MORE_CHILDREN or current.startswith(("coo", "decision", "intelligence", "automations", "reports", "settings", "recovery", "team_intelligence", "platforms", "search", "ai_brain", "agency_awareness", "reliability")):
        return "owner_advanced"
    if current.startswith(("proxy:", "proxies:")):
        return "proxies"
    if current.startswith(("help_from:", "help_copilot_from:")):
        return parent_page_for(current)
    if current.startswith(("setup:", "model:", "account:", "accounts:")):
        return "setup_progress"
    return ROOT_SCREEN
