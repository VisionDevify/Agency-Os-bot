from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

MENU_ITEMS: tuple[tuple[str, str], ...] = (
    ("Dashboard", "dashboard"),
    ("Models", "models"),
    ("Users", "users"),
    ("Roles", "roles"),
    ("Accounts", "accounts"),
    ("Proxies", "proxies"),
    ("Tasks", "tasks"),
    ("Incidents", "incidents"),
    ("Reports", "reports"),
    ("Intelligence", "intelligence"),
    ("Opportunities", "opportunities"),
    ("Automations", "automations"),
    ("Settings", "settings"),
)


def callback_for(page: str) -> str:
    return f"nav:{page}"


def main_menu(items: tuple[tuple[str, str], ...] | list[tuple[str, str]] | None = None) -> InlineKeyboardMarkup:
    menu_items = tuple(items or MENU_ITEMS)
    rows: list[list[InlineKeyboardButton]] = []
    for index in range(0, len(menu_items), 2):
        rows.append(
            [
                InlineKeyboardButton(text=label, callback_data=callback_for(page))
                for label, page in menu_items[index : index + 2]
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def role_home_menu(items: list[tuple[str, str]] | tuple[tuple[str, str], ...]) -> InlineKeyboardMarkup:
    return main_menu(items)


def owner_simple_home_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👑 Today", callback_data=callback_for("today_priorities"))],
            [
                InlineKeyboardButton(text="🧠 Intelligence", callback_data=callback_for("command_center:intelligence")),
                InlineKeyboardButton(text="🎯 Operations", callback_data=callback_for("command_center:operations")),
            ],
            [
                InlineKeyboardButton(text="🛡 Systems", callback_data=callback_for("command_center:systems")),
                InlineKeyboardButton(text="⚙️ Admin", callback_data=callback_for("command_center:admin")),
            ],
            [
                InlineKeyboardButton(text="📈 Scores", callback_data=callback_for("command_center:scores")),
                InlineKeyboardButton(text="🔄 Refresh", callback_data=callback_for("command_center")),
            ],
        ]
    )


def owner_advanced_home_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Intelligence", callback_data=callback_for("intelligence")),
                InlineKeyboardButton(text="Automation", callback_data=callback_for("automations")),
            ],
            [
                InlineKeyboardButton(text="Reports", callback_data=callback_for("reports")),
                InlineKeyboardButton(text="Settings", callback_data=callback_for("settings")),
            ],
            [
                InlineKeyboardButton(text="Health", callback_data=callback_for("production_observability")),
                InlineKeyboardButton(text="Owner Tools", callback_data=callback_for("users")),
            ],
            [
                InlineKeyboardButton(text="Recovery Center", callback_data=callback_for("recovery_center")),
                InlineKeyboardButton(text="Team Intelligence", callback_data=callback_for("team_intelligence")),
            ],
            [InlineKeyboardButton(text="👑 COO Briefing", callback_data=callback_for("coo:briefing"))],
            [InlineKeyboardButton(text="🔌 Platform Connections", callback_data=callback_for("platforms"))],
            [InlineKeyboardButton(text="🔎 Search Intelligence", callback_data=callback_for("search"))],
            [InlineKeyboardButton(text="🧠 AI Brain", callback_data=callback_for("ai_brain"))],
            [InlineKeyboardButton(text="🧭 Agency Awareness", callback_data=callback_for("agency_awareness"))],
            [InlineKeyboardButton(text="🛡 Reliability Center", callback_data=callback_for("reliability"))],
            [InlineKeyboardButton(text="Simple Mode", callback_data=callback_for("menu"))],
            *page_controls(back_to="menu"),
        ]
    )


def start_here_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Continue Setup", callback_data=callback_for("first_workspace"))],
            [InlineKeyboardButton(text="Fix Top Blocker", callback_data=callback_for("agency_activation"))],
            [InlineKeyboardButton(text="View Progress", callback_data=callback_for("coo:readiness"))],
            [InlineKeyboardButton(text="Ask Fortuna", callback_data=callback_for("help_copilot:finish_setup"))],
            *page_controls(back_to="menu"),
        ]
    )


def today_priorities_menu(action_buttons: list[tuple[str, str]] | None = None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="👑 COO Briefing", callback_data=callback_for("coo:briefing"))]]
    rows.append([InlineKeyboardButton(text="🎯 Top Priority", callback_data=callback_for("decision:top"))])
    for label, page in (action_buttons or [])[:4]:
        rows.append([InlineKeyboardButton(text=label, callback_data=callback_for(page))])
    rows.extend(
        [
            [
                InlineKeyboardButton(text="🔔 Notifications", callback_data=callback_for("platforms:notifications")),
                InlineKeyboardButton(text="🛡 Recovery", callback_data=callback_for("recovery_center")),
            ],
            [
                InlineKeyboardButton(text="📱 Platforms", callback_data=callback_for("platforms")),
                InlineKeyboardButton(text="🧭 Agency", callback_data=callback_for("agency_awareness")),
            ],
            *page_controls(back_to="menu"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def setup_progress_menu(rows_data: list[tuple[str, str, str]] | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    next_row = (rows_data or [("Setup", "first_workspace", "first_workspace")])[0]
    label, fix_page, _view_page = next_row
    rows.append([InlineKeyboardButton(text=f"Continue: {label}", callback_data=callback_for(fix_page))])
    rows.append([InlineKeyboardButton(text="First Workspace Guide", callback_data=callback_for("first_workspace"))])
    rows.append([InlineKeyboardButton(text="What Should I Do Next?", callback_data=callback_for("assistant_next"))])
    rows.append([InlineKeyboardButton(text="More Details", callback_data=callback_for("coo:readiness"))])
    rows.extend(page_controls(back_to="menu"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def first_workspace_menu(action_buttons: list[tuple[str, str]] | None = None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback_for(page))] for label, page in (action_buttons or [])[:8]]
    rows.extend(
        [
            [InlineKeyboardButton(text="Run Daily Cycle", callback_data=callback_for("automations:daily_autopilot:run"))],
            [
                InlineKeyboardButton(text="Setup Progress", callback_data=callback_for("setup_progress")),
                InlineKeyboardButton(text="Ask Fortuna", callback_data=callback_for("help_copilot:next")),
            ],
            *page_controls(back_to="start_here"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def assistant_next_menu(target_page: str = "setup_progress") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Do This Now", callback_data=callback_for(target_page))],
            [
                InlineKeyboardButton(text="Today", callback_data=callback_for("today_priorities")),
                InlineKeyboardButton(text="Help", callback_data=callback_for("help_copilot:next_action")),
            ],
            *page_controls(back_to="menu"),
        ]
    )


def page_controls(*, back_to: str = "menu", include_refresh: bool = False) -> list[list[InlineKeyboardButton]]:
    rows: list[list[InlineKeyboardButton]] = []
    if include_refresh:
        rows.append([InlineKeyboardButton(text="Refresh", callback_data="nav:dashboard:refresh")])
    rows.append(
        [
            InlineKeyboardButton(text="Back", callback_data=callback_for(back_to)),
            InlineKeyboardButton(text="Main Menu", callback_data=callback_for("menu")),
        ]
    )
    return rows


def dashboard_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Refresh", callback_data="nav:dashboard:refresh")],
            [
                InlineKeyboardButton(text="View Tasks", callback_data=callback_for("tasks")),
                InlineKeyboardButton(text="View Incidents", callback_data=callback_for("incidents")),
            ],
            [
                InlineKeyboardButton(text="Back", callback_data=callback_for("menu")),
                InlineKeyboardButton(text="Main Menu", callback_data=callback_for("menu")),
            ],
        ]
    )


def personalized_dashboard_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Today", callback_data=callback_for("daily_experience"))],
            [
                InlineKeyboardButton(text="My Tasks", callback_data=callback_for("tasks:my")),
                InlineKeyboardButton(text="Availability", callback_data=callback_for("availability")),
            ],
            [
                InlineKeyboardButton(text="Performance", callback_data=callback_for("performance")),
                InlineKeyboardButton(text="Help", callback_data=callback_for("help")),
            ],
            *page_controls(back_to="menu"),
        ]
    )


def daily_experience_menu(quick_actions: list[tuple[str, str]] | None = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=callback_for(page))]
        for label, page in (quick_actions or [])[:4]
    ]
    rows.extend(page_controls(back_to="menu"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def performance_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="My Tasks", callback_data=callback_for("tasks:my")),
                InlineKeyboardButton(text="Availability", callback_data=callback_for("availability")),
            ],
            *page_controls(back_to="menu"),
        ]
    )


def help_center_menu(topic_buttons: list[tuple[str, str]] | None = None, *, back_to: str = "menu", ask_page: str = "help_copilot") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in (topic_buttons or [])]
    rows.append([InlineKeyboardButton(text="How Fortuna OS Is Organized", callback_data=callback_for("structure"))])
    rows.append([InlineKeyboardButton(text="Ask Fortuna", callback_data=callback_for(ask_page))])
    rows.extend(page_controls(back_to=back_to))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def structure_map_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Setup Fortuna", callback_data=callback_for("setup:wizard"))],
            [InlineKeyboardButton(text="First Day Plan", callback_data=callback_for("first_day_plan"))],
            *page_controls(back_to="help"),
        ]
    )


def setup_wizard_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Fortuna Activation", callback_data=callback_for("agency_activation"))],
            [InlineKeyboardButton(text="First Workspace Guide", callback_data=callback_for("first_workspace"))],
            [InlineKeyboardButton(text="Start Setup Wizard", callback_data=callback_for("setup:wizard:start"))],
            [InlineKeyboardButton(text="Create First Model", callback_data=callback_for("setup:wizard:model"))],
            [InlineKeyboardButton(text="Add Accounts", callback_data=callback_for("setup:wizard:accounts"))],
            [InlineKeyboardButton(text="Assign Team", callback_data=callback_for("setup:wizard:team"))],
            [InlineKeyboardButton(text="Add Creators", callback_data=callback_for("setup:wizard:creators"))],
            [InlineKeyboardButton(text="Create Opportunities", callback_data=callback_for("setup:wizard:opportunities"))],
            [InlineKeyboardButton(text="Review Setup Summary", callback_data=callback_for("setup:wizard:summary"))],
            [
                InlineKeyboardButton(text="Demo Seed Mode", callback_data=callback_for("demo")),
                InlineKeyboardButton(text="Cleanup", callback_data=callback_for("setup:cleanup")),
            ],
            [
                InlineKeyboardButton(text="Structure Map", callback_data=callback_for("structure")),
            ],
            *page_controls(back_to="menu"),
        ]
    )


def agency_activation_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Today Top 5", callback_data=callback_for("coo:top5"))],
            [InlineKeyboardButton(text="Readiness V2", callback_data=callback_for("coo:readiness"))],
            [InlineKeyboardButton(text="Owner Daily Checklist", callback_data=callback_for("owner_daily_checklist"))],
            [InlineKeyboardButton(text="Run Activation Scan", callback_data=callback_for("agency_activation:scan"))],
            [InlineKeyboardButton(text="Run Daily Cycle", callback_data=callback_for("agency_activation:daily_cycle"))],
            [InlineKeyboardButton(text="Daily Autopilot", callback_data=callback_for("automations:daily_autopilot"))],
            [
                InlineKeyboardButton(text="Fix Models", callback_data=callback_for("agency_activation:models")),
                InlineKeyboardButton(text="Fix Accounts", callback_data=callback_for("agency_activation:accounts")),
            ],
            [
                InlineKeyboardButton(text="Fix Team", callback_data=callback_for("agency_activation:team")),
                InlineKeyboardButton(text="Fix Creators", callback_data=callback_for("agency_activation:creators")),
            ],
            [
                InlineKeyboardButton(text="Fix Notifications", callback_data=callback_for("notification_targets")),
                InlineKeyboardButton(text="Proxy Setup Check", callback_data=callback_for("proxies:entry_check")),
            ],
            [
                InlineKeyboardButton(text="Invite Team", callback_data=callback_for("team_onboarding_activation")),
                InlineKeyboardButton(text="What Fortuna Did", callback_data=callback_for("fortuna_action_log")),
            ],
            [InlineKeyboardButton(text="Ask Help Copilot", callback_data=callback_for("help_copilot:activation"))],
            *page_controls(back_to="menu"),
        ]
    )


def activation_section_menu(section: str) -> InlineKeyboardMarkup:
    destinations = {
        "models": "models",
        "accounts": "accounts",
        "team": "manager_qa",
        "creators": "opportunities:creators",
        "opportunities": "opportunities:command",
        "notifications": "notification_targets",
    }
    rows: list[list[InlineKeyboardButton]] = []
    target = destinations.get(section)
    if target is not None:
        rows.append([InlineKeyboardButton(text="Open Fix Screen", callback_data=callback_for(target))])
    rows.append([InlineKeyboardButton(text="Run Activation Scan", callback_data=callback_for("agency_activation:scan"))])
    rows.extend(page_controls(back_to="agency_activation"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def activation_blocker_detail_menu(section: str, index: int, action_page: str | None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if action_page:
        rows.append([InlineKeyboardButton(text="Fix Now", callback_data=callback_for(f"agency_activation:blocker:{section}:{index}:fix"))])
    rows.append([InlineKeyboardButton(text="Explain", callback_data=callback_for(f"agency_activation:blocker:{section}:{index}:explain"))])
    rows.append(
        [
            InlineKeyboardButton(text="Skip for Later", callback_data=callback_for(f"agency_activation:blocker:{section}:{index}:skip")),
            InlineKeyboardButton(
                text="Mark Not Needed",
                callback_data=callback_for(f"agency_activation:blocker:{section}:{index}:not_needed"),
            ),
        ]
    )
    rows.extend(page_controls(back_to=f"agency_activation:{section}"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def coo_dashboard_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Run COO Scan", callback_data=callback_for("coo:scan"))],
            [
                InlineKeyboardButton(text="Today Top 5", callback_data=callback_for("coo:top5")),
                InlineKeyboardButton(text="COO Briefing", callback_data=callback_for("coo:briefing")),
            ],
            [
                InlineKeyboardButton(text="Readiness V2", callback_data=callback_for("coo:readiness")),
                InlineKeyboardButton(text="Load Balancer", callback_data=callback_for("coo:load")),
            ],
            [
                InlineKeyboardButton(text="Manager Queue", callback_data=callback_for("manager_queue")),
                InlineKeyboardButton(text="What Fortuna Did", callback_data=callback_for("fortuna_action_log")),
            ],
            *page_controls(back_to="menu"),
        ]
    )


def top5_actions_menu(action_buttons: list[tuple[str, str]] | None = None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="Refresh Top 5", callback_data=callback_for("coo:scan"))]]
    for label, page in action_buttons or []:
        rows.append([InlineKeyboardButton(text=label, callback_data=callback_for(page))])
    rows.extend(page_controls(back_to="coo"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def coo_briefing_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh", callback_data=callback_for("coo:briefing"))],
            [InlineKeyboardButton(text="🎯 Top Priority", callback_data=callback_for("decision:top"))],
            [
                InlineKeyboardButton(text="🛡 Recovery", callback_data=callback_for("recovery_center")),
                InlineKeyboardButton(text="📱 Platforms", callback_data=callback_for("platforms")),
            ],
            [
                InlineKeyboardButton(text="🔔 Notifications", callback_data=callback_for("platforms:notifications")),
                InlineKeyboardButton(text="🔎 Details", callback_data=callback_for("coo:briefing:details")),
            ],
            [InlineKeyboardButton(text="🧠 Decision Memory", callback_data=callback_for("decision:memory"))],
            [
                InlineKeyboardButton(text="🧠 Intelligence Quality", callback_data=callback_for("intelligence:quality")),
                InlineKeyboardButton(text="🔮 Prediction Preview", callback_data=callback_for("prediction:preview")),
            ],
            [InlineKeyboardButton(text="🧠 AI Brain", callback_data=callback_for("ai_brain"))],
            [InlineKeyboardButton(text="🧭 Agency Awareness", callback_data=callback_for("agency_awareness"))],
            *page_controls(back_to="owner_advanced"),
        ]
    )


def decision_top_priority_menu(action_page: str | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if action_page:
        rows.append([InlineKeyboardButton(text="✨ Do This Next", callback_data=callback_for(action_page))])
    rows.append([InlineKeyboardButton(text="🔎 Decision Details", callback_data=callback_for("decision:details"))])
    rows.append(
        [
            InlineKeyboardButton(text="✅ Helpful", callback_data=callback_for("decision:feedback:helpful")),
            InlineKeyboardButton(text="👎 Not Helpful", callback_data=callback_for("decision:feedback:not_helpful")),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="🕒 Remind Later", callback_data=callback_for("decision:feedback:remind_later")),
            InlineKeyboardButton(text="❌ Dismiss", callback_data=callback_for("decision:feedback:dismissed")),
        ]
    )
    rows.append([InlineKeyboardButton(text="👑 COO Briefing", callback_data=callback_for("coo:briefing"))])
    rows.extend(page_controls(back_to="coo:briefing"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def decision_details_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Helpful", callback_data=callback_for("decision:feedback:helpful")),
                InlineKeyboardButton(text="👎 Not Helpful", callback_data=callback_for("decision:feedback:not_helpful")),
            ],
            [
                InlineKeyboardButton(text="🕒 Remind Later", callback_data=callback_for("decision:feedback:remind_later")),
                InlineKeyboardButton(text="❌ Dismiss", callback_data=callback_for("decision:feedback:dismissed")),
            ],
            [InlineKeyboardButton(text="🧠 Learn From This", callback_data=callback_for("decision:feedback:learn_from_this"))],
            [InlineKeyboardButton(text="🧠 AI Explanation", callback_data=callback_for("ai_brain:coo"))],
            [InlineKeyboardButton(text="🧠 Decision Memory", callback_data=callback_for("decision:memory"))],
            [InlineKeyboardButton(text="🔄 Refresh", callback_data=callback_for("coo:briefing"))],
            [InlineKeyboardButton(text="🎯 Top Priority", callback_data=callback_for("decision:top"))],
            *page_controls(back_to="coo:briefing"),
        ]
    )


def decision_memory_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🎯 Active Decisions", callback_data=callback_for("decision:memory:active")),
                InlineKeyboardButton(text="✅ Resolved", callback_data=callback_for("decision:memory:resolved")),
            ],
            [
                InlineKeyboardButton(text="🕒 Waiting", callback_data=callback_for("decision:memory:waiting")),
                InlineKeyboardButton(text="❌ Dismissed", callback_data=callback_for("decision:memory:dismissed")),
            ],
            [InlineKeyboardButton(text="🔎 Details", callback_data=callback_for("decision:memory:details"))],
            [InlineKeyboardButton(text="🧠 Intelligence Quality", callback_data=callback_for("intelligence:quality"))],
            *page_controls(back_to="coo:briefing"),
        ]
    )


def intelligence_quality_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧪 Reality Check", callback_data=callback_for("reality:check"))],
            [InlineKeyboardButton(text="🔄 Refresh", callback_data=callback_for("intelligence:quality"))],
            [
                InlineKeyboardButton(text="📈 Decision Trends", callback_data=callback_for("intelligence:quality:trends")),
                InlineKeyboardButton(text="🔮 Prediction Preview", callback_data=callback_for("prediction:preview")),
            ],
            [InlineKeyboardButton(text="🔎 Details", callback_data=callback_for("intelligence:quality:details"))],
            [
                InlineKeyboardButton(text="👑 COO Briefing", callback_data=callback_for("coo:briefing")),
                InlineKeyboardButton(text="🧠 Decision Memory", callback_data=callback_for("decision:memory")),
            ],
            *page_controls(back_to="coo:briefing"),
        ]
    )


def decision_quality_trends_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧪 Reality Check", callback_data=callback_for("reality:check"))],
            [InlineKeyboardButton(text="🔄 Refresh", callback_data=callback_for("intelligence:quality:trends"))],
            [
                InlineKeyboardButton(text="📊 Category Trends", callback_data=callback_for("intelligence:quality:categories")),
                InlineKeyboardButton(text="🧠 What Fortuna Learned", callback_data=callback_for("decision:memory")),
            ],
            [InlineKeyboardButton(text="🔮 Prediction Preview", callback_data=callback_for("prediction:preview"))],
            [InlineKeyboardButton(text="🔎 Details", callback_data=callback_for("intelligence:quality:trends:details"))],
            *page_controls(back_to="intelligence:quality"),
        ]
    )


def category_trends_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh", callback_data=callback_for("intelligence:quality:categories"))],
            [InlineKeyboardButton(text="🔮 Prediction Preview", callback_data=callback_for("prediction:preview"))],
            *page_controls(back_to="intelligence:quality:trends"),
        ]
    )


def prediction_preview_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ This Was Right", callback_data=callback_for("prediction:outcome:right")),
                InlineKeyboardButton(text="❌ This Was Wrong", callback_data=callback_for("prediction:outcome:wrong")),
            ],
            [
                InlineKeyboardButton(text="🧾 Add Evidence", callback_data=callback_for("prediction:outcome:add_evidence")),
                InlineKeyboardButton(text="🕒 Still Pending", callback_data=callback_for("prediction:outcome:still_pending")),
            ],
            [InlineKeyboardButton(text="🔄 Refresh", callback_data=callback_for("prediction:preview"))],
            [InlineKeyboardButton(text="🧠 Why Fortuna Thinks This", callback_data=callback_for("prediction:preview:details"))],
            [
                InlineKeyboardButton(text="✅ Helpful", callback_data=callback_for("prediction:feedback:helpful")),
                InlineKeyboardButton(text="👎 Not Helpful", callback_data=callback_for("prediction:feedback:not_helpful")),
            ],
            [
                InlineKeyboardButton(text="🕒 Remind Later", callback_data=callback_for("prediction:feedback:remind_later")),
                InlineKeyboardButton(text="❌ Dismiss", callback_data=callback_for("prediction:feedback:dismissed")),
            ],
            *page_controls(back_to="intelligence:quality:trends"),
        ]
    )


def reality_check_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh", callback_data=callback_for("reality:check"))],
            [
                InlineKeyboardButton(text="🔍 Decision Review", callback_data=callback_for("decision:review")),
                InlineKeyboardButton(text="📝 Evidence Notes", callback_data=callback_for("evidence:notes")),
            ],
            [
                InlineKeyboardButton(text="🔮 Prediction Outcomes", callback_data=callback_for("reality:outcomes")),
                InlineKeyboardButton(text="📊 Calibration", callback_data=callback_for("reality:calibration")),
            ],
            [
                InlineKeyboardButton(text="🎯 Accuracy by Category", callback_data=callback_for("reality:accuracy")),
                InlineKeyboardButton(text="📚 Knowledge Memory", callback_data=callback_for("knowledge:memory")),
            ],
            [InlineKeyboardButton(text="🕒 Decision Timeline", callback_data=callback_for("decision:timeline"))],
            [InlineKeyboardButton(text="🔎 Details", callback_data=callback_for("reality:check:details"))],
            *page_controls(back_to="intelligence:quality"),
        ]
    )


def prediction_outcomes_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh", callback_data=callback_for("reality:outcomes"))],
            [InlineKeyboardButton(text="📊 Calibration", callback_data=callback_for("reality:calibration"))],
            *page_controls(back_to="reality:check"),
        ]
    )


def calibration_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh", callback_data=callback_for("reality:calibration"))],
            [InlineKeyboardButton(text="🎯 Accuracy by Category", callback_data=callback_for("reality:accuracy"))],
            *page_controls(back_to="reality:check"),
        ]
    )


def accuracy_by_category_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh", callback_data=callback_for("reality:accuracy"))],
            [InlineKeyboardButton(text="📊 Calibration", callback_data=callback_for("reality:calibration"))],
            *page_controls(back_to="reality:check"),
        ]
    )


def decision_review_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Correct", callback_data=callback_for("owner_validation:correct")),
                InlineKeyboardButton(text="❌ Incorrect", callback_data=callback_for("owner_validation:incorrect")),
            ],
            [
                InlineKeyboardButton(text="🟡 Partially Correct", callback_data=callback_for("owner_validation:partially_correct")),
                InlineKeyboardButton(text="⏳ Too Early", callback_data=callback_for("owner_validation:too_early")),
            ],
            [InlineKeyboardButton(text="🧾 Add Evidence", callback_data=callback_for("owner_validation:add_evidence"))],
            [
                InlineKeyboardButton(text="📝 Evidence Notes", callback_data=callback_for("evidence:notes")),
                InlineKeyboardButton(text="🕒 Timeline", callback_data=callback_for("decision:timeline")),
            ],
            [InlineKeyboardButton(text="🔎 Details", callback_data=callback_for("decision:review:details"))],
            [InlineKeyboardButton(text="🏠 Home", callback_data=callback_for("menu"))],
            *page_controls(back_to="reality:check"),
        ]
    )


def decision_review_details_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Home", callback_data=callback_for("menu"))],
            *page_controls(back_to="decision:review"),
        ]
    )


def owner_validation_result_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Decision Review", callback_data=callback_for("decision:review"))],
            [InlineKeyboardButton(text="🏠 Home", callback_data=callback_for("menu"))],
            *page_controls(back_to="decision:review"),
        ]
    )


def evidence_notes_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📝 Record Outcome Note", callback_data=callback_for("evidence:notes:record"))],
            [
                InlineKeyboardButton(text="🔍 Decision Review", callback_data=callback_for("decision:review")),
                InlineKeyboardButton(text="📚 Knowledge Memory", callback_data=callback_for("knowledge:memory")),
            ],
            [InlineKeyboardButton(text="🏠 Home", callback_data=callback_for("menu"))],
            *page_controls(back_to="decision:review"),
        ]
    )


def evidence_note_recorded_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📚 Knowledge Memory", callback_data=callback_for("knowledge:memory"))],
            [InlineKeyboardButton(text="🏠 Home", callback_data=callback_for("menu"))],
            *page_controls(back_to="evidence:notes"),
        ]
    )


def knowledge_memory_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧠 Save Lesson", callback_data=callback_for("knowledge:memory:create"))],
            [InlineKeyboardButton(text="🕒 Decision Timeline", callback_data=callback_for("decision:timeline"))],
            [InlineKeyboardButton(text="🏠 Home", callback_data=callback_for("menu"))],
            *page_controls(back_to="reality:check"),
        ]
    )


def decision_timeline_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🔍 Decision Review", callback_data=callback_for("decision:review")),
                InlineKeyboardButton(text="📝 Evidence Notes", callback_data=callback_for("evidence:notes")),
            ],
            [InlineKeyboardButton(text="🏠 Home", callback_data=callback_for("menu"))],
            *page_controls(back_to="reality:check"),
        ]
    )


def manager_queue_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Refresh Queue", callback_data=callback_for("manager_queue"))],
            [
                InlineKeyboardButton(text="Tasks", callback_data=callback_for("tasks")),
                InlineKeyboardButton(text="Incidents", callback_data=callback_for("incidents")),
            ],
            [InlineKeyboardButton(text="Opportunities", callback_data=callback_for("opportunities:manager"))],
            *page_controls(back_to="coo"),
        ]
    )


def my_work_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="My Tasks", callback_data=callback_for("tasks:my")),
                InlineKeyboardButton(text="My Opportunities", callback_data=callback_for("my_opportunities")),
            ],
            [InlineKeyboardButton(text="Availability", callback_data=callback_for("availability"))],
            *page_controls(back_to="menu"),
        ]
    )


def readiness_v2_menu(action_buttons: list[tuple[str, str]] | None = None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="Run COO Scan", callback_data=callback_for("coo:scan"))]]
    for label, page in action_buttons or []:
        rows.append([InlineKeyboardButton(text=label, callback_data=callback_for(page))])
    rows.extend(page_controls(back_to="agency_activation"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def executive_mode_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Top Priorities", callback_data=callback_for("coo:top5")),
                InlineKeyboardButton(text="COO Briefing", callback_data=callback_for("coo:briefing")),
            ],
            [
                InlineKeyboardButton(text="Readiness", callback_data=callback_for("coo:readiness")),
                InlineKeyboardButton(text="What Fortuna Did", callback_data=callback_for("fortuna_action_log")),
            ],
            [
                InlineKeyboardButton(text="Critical Issues", callback_data=callback_for("incidents:critical")),
                InlineKeyboardButton(text="Recommendations", callback_data=callback_for("reports:executive:recommendations")),
            ],
            *page_controls(back_to="menu"),
        ]
    )


def model_completion_menu(model_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Edit Name", callback_data=f"nav:model:{model_id}:edit:display_name"),
                InlineKeyboardButton(text="Edit Stage Name", callback_data=f"nav:model:{model_id}:edit:stage_name"),
            ],
            [
                InlineKeyboardButton(text="Edit Country", callback_data=f"nav:model:{model_id}:edit:country"),
                InlineKeyboardButton(text="Edit Timezone", callback_data=f"nav:model:{model_id}:edit:timezone"),
            ],
            [
                InlineKeyboardButton(text="Edit Primary Platform", callback_data=f"nav:model:{model_id}:edit:primary_platform"),
                InlineKeyboardButton(text="Edit Notes", callback_data=f"nav:model:{model_id}:edit:notes"),
            ],
            [
                InlineKeyboardButton(text="Manage Team", callback_data=callback_for(f"model:{model_id}:team")),
                InlineKeyboardButton(text="Manage Accounts", callback_data=callback_for(f"model:{model_id}:accounts")),
            ],
            [
                InlineKeyboardButton(text="Manage Creators", callback_data=callback_for("opportunities:creators")),
                InlineKeyboardButton(text="Manage Opportunities", callback_data=callback_for("opportunities:command")),
            ],
            [InlineKeyboardButton(text="Ask Help Copilot", callback_data=callback_for("help_copilot:finish_setup"))],
            *page_controls(back_to="agency_activation:models"),
        ]
    )


def account_setup_state_menu(account_buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in account_buttons]
    rows.append([InlineKeyboardButton(text="Add Account", callback_data=callback_for("accounts:add"))])
    rows.extend(page_controls(back_to="agency_activation"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def setup_finish_menu(model_id: int | None = None) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Finish Setup", callback_data=callback_for("setup:wizard:finish"))],
        [
            InlineKeyboardButton(text="Add More Accounts", callback_data=callback_for("setup:wizard:accounts")),
            InlineKeyboardButton(text="Add Team", callback_data=callback_for("setup:wizard:team")),
        ],
        [
            InlineKeyboardButton(text="Add Creators", callback_data=callback_for("setup:wizard:creators")),
            InlineKeyboardButton(text="Create Opportunities", callback_data=callback_for("setup:wizard:opportunities")),
        ],
    ]
    if model_id is not None:
        rows.append([InlineKeyboardButton(text="Go To Model Dashboard", callback_data=callback_for(f"model:{model_id}"))])
    rows.extend(page_controls(back_to="setup:wizard"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def first_day_plan_menu(items: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=("Done: " if item["done"] else "Do: ") + item["label"], callback_data=callback_for(item["page"]))]
        for item in items
    ]
    rows.extend(page_controls(back_to="menu"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def manager_setup_qa_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Assign Manager", callback_data=callback_for("models:list")),
                InlineKeyboardButton(text="Assign Chatter", callback_data=callback_for("models:list")),
            ],
            [
                InlineKeyboardButton(text="Assign Opportunity", callback_data=callback_for("opportunities:manager")),
                InlineKeyboardButton(text="Approve User", callback_data=callback_for("users:pending")),
            ],
            [
                InlineKeyboardButton(text="Send Help Prompt", callback_data=callback_for("help_copilot:where_start")),
                InlineKeyboardButton(text="Mark Onboarded", callback_data=callback_for("team_qa")),
            ],
            *page_controls(back_to="menu"),
        ]
    )


def demo_seed_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Create Demo Model", callback_data=callback_for("demo:create"))],
            [InlineKeyboardButton(text="Create Demo Accounts", callback_data=callback_for("demo:create"))],
            [InlineKeyboardButton(text="Create Demo Creator", callback_data=callback_for("demo:create"))],
            [InlineKeyboardButton(text="Create Demo Opportunity", callback_data=callback_for("demo:create"))],
            [InlineKeyboardButton(text="Clear Demo Data", callback_data=callback_for("demo:clear"))],
            *page_controls(back_to="setup:wizard"),
        ]
    )


def notification_digest_mode_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Bundle Updates", callback_data=callback_for("notification_digest:generate"))],
            [InlineKeyboardButton(text="Refresh", callback_data=callback_for("notification_digest"))],
            *page_controls(back_to="settings"),
        ]
    )


def team_qa_menu(user_buttons: list[tuple[str, str]] | None = None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in (user_buttons or [])]
    rows.extend(page_controls(back_to="users"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def team_qa_detail_menu(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Role Assigned", callback_data=f"nav:team_qa:{user_id}:role_assigned"),
                InlineKeyboardButton(text="Timezone Confirmed", callback_data=f"nav:team_qa:{user_id}:timezone_confirmed"),
            ],
            [
                InlineKeyboardButton(text="Availability Set", callback_data=f"nav:team_qa:{user_id}:availability_configured"),
                InlineKeyboardButton(text="Help Viewed", callback_data=f"nav:team_qa:{user_id}:help_center_viewed"),
            ],
            [InlineKeyboardButton(text="Mark Onboarded", callback_data=f"nav:team_qa:{user_id}:onboarded")],
            *page_controls(back_to="team_qa"),
        ]
    )


def search_center_menu(*, configured: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🔍 Run Search", callback_data=callback_for("search:run"))],
        [
            InlineKeyboardButton(text="🎯 Opportunity Research", callback_data=callback_for("search:opportunity")),
            InlineKeyboardButton(text="📱 Platform Signals", callback_data=callback_for("search:platform_signals")),
        ],
        [InlineKeyboardButton(text="🧠 COO Context", callback_data=callback_for("search:coo_context"))],
        [
            InlineKeyboardButton(text="📚 Search History", callback_data=callback_for("search:history")),
            InlineKeyboardButton(text="⚙️ Search Settings", callback_data=callback_for("search:settings")),
        ],
        [InlineKeyboardButton(text="🔎 Details", callback_data=callback_for("search:details"))],
    ]
    if not configured:
        rows.insert(1, [InlineKeyboardButton(text="⚙️ Setup Tavily", callback_data=callback_for("search:settings"))])
    rows.extend(page_controls(back_to="owner_advanced"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def search_history_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Re-run Latest", callback_data=callback_for("search:history:rerun"))],
            [InlineKeyboardButton(text="🔎 View Results", callback_data=callback_for("search:results"))],
            [InlineKeyboardButton(text="🧾 Attach Evidence", callback_data=callback_for("search:results:attach"))],
            *page_controls(back_to="search"),
        ]
    )


def search_results_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🧾 Attach as Evidence", callback_data=callback_for("search:results:attach"))],
            [
                InlineKeyboardButton(text="🎯 Create Opportunity", callback_data=callback_for("search:results:opportunity")),
                InlineKeyboardButton(text="🔔 Notification Watch", callback_data=callback_for("search:results:notification")),
            ],
            [InlineKeyboardButton(text="🧠 AI Summary", callback_data=callback_for("ai_brain:search"))],
            [InlineKeyboardButton(text="❌ Ignore", callback_data=callback_for("search:results:ignore"))],
            *page_controls(back_to="search:history"),
        ]
    )


def search_settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh", callback_data=callback_for("search:settings"))],
            [InlineKeyboardButton(text="🔎 Search Intelligence", callback_data=callback_for("search"))],
            *page_controls(back_to="search"),
        ]
    )


def ai_brain_menu(*, configured: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="👑 AI COO Briefing", callback_data=callback_for("ai_brain:coo"))],
        [InlineKeyboardButton(text="🔎 AI Evidence Summary", callback_data=callback_for("ai_brain:evidence"))],
        [InlineKeyboardButton(text="🔎 AI Search Summary", callback_data=callback_for("ai_brain:search"))],
        [InlineKeyboardButton(text="🎯 AI Opportunity Explanation", callback_data=callback_for("ai_brain:opportunity"))],
        [
            InlineKeyboardButton(text="🧪 AI Critic Status", callback_data=callback_for("ai_brain:critic")),
            InlineKeyboardButton(text="⚙️ AI Settings", callback_data=callback_for("ai_brain:settings")),
        ],
        [InlineKeyboardButton(text="🔎 Details", callback_data=callback_for("ai_brain:details"))],
    ]
    if not configured:
        rows.insert(1, [InlineKeyboardButton(text="⚙️ Setup OpenAI", callback_data=callback_for("ai_brain:settings"))])
    rows.extend(page_controls(back_to="owner_advanced"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def ai_settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh", callback_data=callback_for("ai_brain:settings"))],
            [InlineKeyboardButton(text="🧠 AI Brain", callback_data=callback_for("ai_brain"))],
            *page_controls(back_to="ai_brain"),
        ]
    )


def ai_critic_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh", callback_data=callback_for("ai_brain:critic"))],
            [InlineKeyboardButton(text="⚙️ AI Settings", callback_data=callback_for("ai_brain:settings"))],
            *page_controls(back_to="ai_brain"),
        ]
    )


def scheduled_automations_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Daily Autopilot", callback_data=callback_for("automations:daily_autopilot"))],
            [InlineKeyboardButton(text="Run Due Safe Automations", callback_data=callback_for("automations:scheduled:run_due"))],
            [InlineKeyboardButton(text="Automation Health", callback_data=callback_for("automations:health"))],
            *page_controls(back_to="automations"),
        ]
    )


def daily_autopilot_menu(enabled: bool) -> InlineKeyboardMarkup:
    toggle_label = "Disable Daily Autopilot" if enabled else "Enable Daily Autopilot"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_label, callback_data=callback_for("automations:daily_autopilot:toggle"))],
            [InlineKeyboardButton(text="Run Now", callback_data=callback_for("automations:daily_autopilot:run"))],
            [InlineKeyboardButton(text="Automation Health", callback_data=callback_for("automations:health"))],
            *page_controls(back_to="automations"),
        ]
    )


def owner_daily_checklist_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Fix Top Blocker", callback_data=callback_for("owner_daily_checklist:fix_top"))],
            [InlineKeyboardButton(text="Run Daily Cycle", callback_data=callback_for("owner_daily_checklist:run_daily_cycle"))],
            [
                InlineKeyboardButton(text="View Approvals", callback_data=callback_for("automations:approvals")),
                InlineKeyboardButton(text="View Readiness", callback_data=callback_for("agency_activation")),
            ],
            [InlineKeyboardButton(text="View Opportunities", callback_data=callback_for("opportunities:command"))],
            *page_controls(back_to="menu"),
        ]
    )


def team_onboarding_activation_menu(has_pending: bool) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="Invite Team", callback_data=callback_for("team_onboarding_activation"))]]
    if has_pending:
        rows.append([InlineKeyboardButton(text="Approve Users", callback_data=callback_for("users:pending"))])
        rows.append([InlineKeyboardButton(text="Assign Role After Approval", callback_data=callback_for("users"))])
    rows.append([InlineKeyboardButton(text="Team Activation QA", callback_data=callback_for("team_activation"))])
    rows.extend(page_controls(back_to="agency_activation"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def fortuna_action_log_menu(window: str = "today") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Today", callback_data=callback_for("fortuna_action_log:today")),
                InlineKeyboardButton(text="7 Days", callback_data=callback_for("fortuna_action_log:7d")),
                InlineKeyboardButton(text="All", callback_data=callback_for("fortuna_action_log:all")),
            ],
            *page_controls(back_to="agency_activation"),
        ]
    )


def proxy_entry_check_menu(needs_setup: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if needs_setup:
        rows.append([InlineKeyboardButton(text="Open Olympix Wizard", callback_data=callback_for("proxies:olympix"))])
    rows.append([InlineKeyboardButton(text="Accounts Missing Proxy", callback_data=callback_for("proxies:missing"))])
    rows.append([InlineKeyboardButton(text="View Proxies", callback_data=callback_for("proxies:list"))])
    rows.extend(page_controls(back_to="proxies"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def page_menu(back_to: str = "menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=page_controls(back_to=back_to))


def choice_menu(choices: list[tuple[str, str]], *, back_to: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in choices]
    rows.extend(page_controls(back_to=back_to))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def users_menu(user_buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="Pending Users", callback_data=callback_for("users:pending"))]]
    rows.extend(
        [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in user_buttons]
    )
    rows.extend(page_controls(back_to="owner_advanced"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def accounts_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="View Accounts", callback_data=callback_for("accounts:list"))],
            [InlineKeyboardButton(text="Add Account", callback_data=callback_for("accounts:add"))],
            [InlineKeyboardButton(text="Accounts by Model", callback_data=callback_for("accounts:by_model"))],
            [InlineKeyboardButton(text="Accounts by Platform", callback_data=callback_for("accounts:by_platform"))],
            [InlineKeyboardButton(text="Accounts Needing Attention", callback_data=callback_for("accounts:attention"))],
            *page_controls(back_to="menu"),
        ]
    )


def account_list_menu(account_buttons: list[tuple[str, str]], *, back_to: str = "accounts") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in account_buttons]
    rows.extend(page_controls(back_to=back_to))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def account_model_choice_menu(model_buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in model_buttons]
    rows.extend(page_controls(back_to="accounts"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def account_platform_menu(model_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Instagram", callback_data=f"nav:accounts:add:model:{model_id}:platform:instagram")],
            [InlineKeyboardButton(text="X", callback_data=f"nav:accounts:add:model:{model_id}:platform:x")],
            [InlineKeyboardButton(text="OnlyFans", callback_data=f"nav:accounts:add:model:{model_id}:platform:onlyfans")],
            [InlineKeyboardButton(text="Email", callback_data=f"nav:accounts:add:model:{model_id}:platform:email")],
            [InlineKeyboardButton(text="Other", callback_data=f"nav:accounts:add:model:{model_id}:platform:other")],
            *page_controls(back_to="accounts:add"),
        ]
    )


def platform_filter_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Instagram", callback_data="nav:accounts:platform:instagram")],
            [InlineKeyboardButton(text="X", callback_data="nav:accounts:platform:x")],
            [InlineKeyboardButton(text="OnlyFans", callback_data="nav:accounts:platform:onlyfans")],
            [InlineKeyboardButton(text="Email", callback_data="nav:accounts:platform:email")],
            [InlineKeyboardButton(text="Other", callback_data="nav:accounts:platform:other")],
            *page_controls(back_to="accounts"),
        ]
    )


def account_detail_menu(account_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Start Login/Auth Session", callback_data=f"nav:account:{account_id}:auth:start")],
            [InlineKeyboardButton(text="Enter 2FA Code", callback_data=f"nav:account:{account_id}:auth:enter")],
            [
                InlineKeyboardButton(text="Mark Connected", callback_data=f"nav:account:{account_id}:auth:connected"),
                InlineKeyboardButton(text="Mark Needs Login", callback_data=f"nav:account:{account_id}:auth:needs_login"),
            ],
            [
                InlineKeyboardButton(text="Disable Account", callback_data=f"nav:account:{account_id}:disable"),
                InlineKeyboardButton(text="Archive Account", callback_data=f"nav:account:{account_id}:archive"),
            ],
            [
                InlineKeyboardButton(text="Assign Best Proxy", callback_data=f"nav:account:{account_id}:proxy:assign_best"),
                InlineKeyboardButton(text="Choose Proxy", callback_data=f"nav:account:{account_id}:proxy:assign"),
            ],
            [
                InlineKeyboardButton(text="Remove Proxy", callback_data=f"nav:account:{account_id}:proxy:remove"),
                InlineKeyboardButton(text="Add Proxy First", callback_data=callback_for("proxies:add")),
            ],
            [InlineKeyboardButton(text="View Audit History", callback_data=f"nav:account:{account_id}:audit")],
            *page_controls(back_to="accounts:list"),
        ]
    )


def proxies_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Paste Proxy", callback_data=callback_for("proxies:olympix:paste"))],
            [InlineKeyboardButton(text="View Proxies", callback_data=callback_for("proxies:list"))],
            [InlineKeyboardButton(text="How Rotation Works", callback_data=callback_for("proxies:rotation_help"))],
            [InlineKeyboardButton(text="Help", callback_data=callback_for("help_copilot:add_proxy"))],
            [InlineKeyboardButton(text="More Details", callback_data=callback_for("proxies:advanced"))],
            *page_controls(back_to="menu"),
        ]
    )


def proxy_add_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Paste Full Proxy String", callback_data=callback_for("proxies:olympix:paste"))],
            [InlineKeyboardButton(text="Add Olympix Proxy", callback_data=callback_for("proxies:olympix"))],
            [InlineKeyboardButton(text="Manual Step-by-Step Setup", callback_data=callback_for("proxies:olympix:manual"))],
            [InlineKeyboardButton(text="View Proxies", callback_data=callback_for("proxies:list"))],
            *page_controls(back_to="proxies"),
        ]
    )


def proxies_advanced_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Clean Placeholder Proxies", callback_data=callback_for("proxies:cleanup_placeholders"))],
            [InlineKeyboardButton(text="Simulation Mode", callback_data=callback_for("proxies:simulation"))],
            [InlineKeyboardButton(text="Infrastructure Dashboard", callback_data=callback_for("proxies:dashboard"))],
            [InlineKeyboardButton(text="Real Check Pilot", callback_data=callback_for("proxies:real_check_pilot"))],
            [InlineKeyboardButton(text="Proxy Setup Check", callback_data=callback_for("proxies:entry_check"))],
            *page_controls(back_to="proxies"),
        ]
    )


def tasks_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="View Tasks", callback_data=callback_for("tasks:list"))],
            [InlineKeyboardButton(text="Create Task", callback_data=callback_for("tasks:create"))],
            [
                InlineKeyboardButton(text="My Tasks", callback_data=callback_for("tasks:my")),
                InlineKeyboardButton(text="Team Tasks", callback_data=callback_for("tasks:team")),
            ],
            [
                InlineKeyboardButton(text="Overdue Tasks", callback_data=callback_for("tasks:overdue")),
                InlineKeyboardButton(text="Blocked Tasks", callback_data=callback_for("tasks:blocked")),
            ],
            [InlineKeyboardButton(text="Escalated Tasks", callback_data=callback_for("tasks:escalated"))],
            *page_controls(back_to="menu"),
        ]
    )


def task_list_menu(task_buttons: list[tuple[str, str]], *, back_to: str = "tasks") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in task_buttons]
    rows.extend(page_controls(back_to=back_to))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def task_detail_menu(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Start", callback_data=f"nav:task:{task_id}:start"),
                InlineKeyboardButton(text="Block", callback_data=f"nav:task:{task_id}:block"),
            ],
            [
                InlineKeyboardButton(text="Complete Task", callback_data=f"nav:task:{task_id}:complete"),
                InlineKeyboardButton(text="Archive Task", callback_data=f"nav:task:{task_id}:archive"),
            ],
            [
                InlineKeyboardButton(text="Reassign Task", callback_data=f"nav:task:{task_id}:assign"),
                InlineKeyboardButton(text="Escalate Task", callback_data=f"nav:task:{task_id}:escalate"),
            ],
            *page_controls(back_to="tasks:list"),
        ]
    )


def task_user_choice_menu(task_id: int, user_buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in user_buttons]
    rows.extend(page_controls(back_to=f"task:{task_id}"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def incidents_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Open Incidents", callback_data=callback_for("incidents:list"))],
            [InlineKeyboardButton(text="Create Incident", callback_data=callback_for("incidents:create"))],
            [
                InlineKeyboardButton(text="My Incidents", callback_data=callback_for("incidents:my")),
                InlineKeyboardButton(text="Critical Incidents", callback_data=callback_for("incidents:critical")),
            ],
            *page_controls(back_to="menu"),
        ]
    )


def incident_list_menu(incident_buttons: list[tuple[str, str]], *, back_to: str = "incidents") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in incident_buttons]
    rows.extend(page_controls(back_to=back_to))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def incident_detail_menu(incident_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Assign Incident", callback_data=f"nav:incident:{incident_id}:assign")],
            [
                InlineKeyboardButton(text="Investigate", callback_data=f"nav:incident:{incident_id}:investigate"),
                InlineKeyboardButton(text="Escalate Incident", callback_data=f"nav:incident:{incident_id}:escalate"),
                InlineKeyboardButton(text="Resolve Incident", callback_data=f"nav:incident:{incident_id}:resolve"),
            ],
            [
                InlineKeyboardButton(text="View Timeline", callback_data=f"nav:incident:{incident_id}:timeline"),
                InlineKeyboardButton(text="Archive Incident", callback_data=f"nav:incident:{incident_id}:archive"),
            ],
            *page_controls(back_to="incidents:list"),
        ]
    )


def incident_user_choice_menu(incident_id: int, user_buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in user_buttons]
    rows.extend(page_controls(back_to=f"incident:{incident_id}"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reports_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Daily Briefing", callback_data=callback_for("reports:daily"))],
            [InlineKeyboardButton(text="Daily Digest", callback_data=callback_for("reports:digest"))],
            [InlineKeyboardButton(text="Team Accountability", callback_data=callback_for("reports:accountability"))],
            [InlineKeyboardButton(text="Executive Intelligence Briefing", callback_data=callback_for("reports:intelligence"))],
            [InlineKeyboardButton(text="Workload Intelligence", callback_data=callback_for("reports:workload"))],
            [InlineKeyboardButton(text="Executive Dashboard", callback_data=callback_for("reports:executive"))],
            [InlineKeyboardButton(text="Manager Command View", callback_data=callback_for("reports:manager"))],
            [InlineKeyboardButton(text="Operations Dashboard", callback_data=callback_for("reports:operations"))],
            [
                InlineKeyboardButton(text="Chatter Dashboard", callback_data=callback_for("reports:chatter")),
                InlineKeyboardButton(text="VA Dashboard", callback_data=callback_for("reports:va")),
            ],
            *page_controls(back_to="owner_advanced"),
        ]
    )


def briefing_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Generate Today's Briefing", callback_data=callback_for("reports:daily:generate")),
            ],
            [
                InlineKeyboardButton(text="View Latest Briefing", callback_data=callback_for("reports:daily:latest")),
                InlineKeyboardButton(text="Refresh", callback_data=callback_for("reports:daily")),
            ],
            [
                InlineKeyboardButton(text="Send to Owner", callback_data=callback_for("reports:daily:send_owner")),
                InlineKeyboardButton(text="Send to Operations Group", callback_data=callback_for("reports:daily:send_ops")),
            ],
            *page_controls(back_to="reports"),
        ]
    )


def daily_digest_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Generate Digest", callback_data=callback_for("reports:digest:generate"))],
            [InlineKeyboardButton(text="Preview Digest", callback_data=callback_for("reports:digest:preview"))],
            [
                InlineKeyboardButton(text="Send to HQ", callback_data=callback_for("reports:digest:send_hq")),
                InlineKeyboardButton(text="Send to Operations", callback_data=callback_for("reports:digest:send_ops")),
            ],
            [InlineKeyboardButton(text="Schedule Digest", callback_data=callback_for("reports:digest:schedule"))],
            [InlineKeyboardButton(text="Delivery History", callback_data=callback_for("reports:digest:history"))],
            *page_controls(back_to="reports"),
        ]
    )


def executive_dashboard_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Recommendations", callback_data=callback_for("reports:executive:recommendations"))],
            [InlineKeyboardButton(text="Intelligence Briefing", callback_data=callback_for("reports:intelligence"))],
            [InlineKeyboardButton(text="Signals / Patterns", callback_data=callback_for("intelligence"))],
            [
                InlineKeyboardButton(text="Daily Briefing", callback_data=callback_for("reports:daily:latest")),
                InlineKeyboardButton(text="Accountability", callback_data=callback_for("reports:accountability")),
            ],
            [
                InlineKeyboardButton(text="Infrastructure", callback_data=callback_for("proxies:dashboard")),
                InlineKeyboardButton(text="Incidents", callback_data=callback_for("incidents")),
            ],
            [
                InlineKeyboardButton(text="Automations", callback_data=callback_for("automations")),
                InlineKeyboardButton(text="Automation Health", callback_data=callback_for("automations:health")),
            ],
            [InlineKeyboardButton(text="Bot Status", callback_data=callback_for("bot_status"))],
            [InlineKeyboardButton(text="Refresh", callback_data=callback_for("reports:executive"))],
            *page_controls(back_to="reports"),
        ]
    )


def recommendations_menu(recommendation_buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in recommendation_buttons]
    rows.append([InlineKeyboardButton(text="Refresh Recommendations", callback_data=callback_for("reports:executive:recommendations"))])
    rows.extend(page_controls(back_to="reports:executive"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def recommendation_detail_menu(recommendation_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Acknowledge", callback_data=f"nav:recommendation:{recommendation_id}:acknowledge"),
                InlineKeyboardButton(text="Dismiss", callback_data=f"nav:recommendation:{recommendation_id}:dismiss"),
            ],
            [InlineKeyboardButton(text="Mark Resolved", callback_data=f"nav:recommendation:{recommendation_id}:resolve")],
            [InlineKeyboardButton(text="Jump to Related Entity", callback_data=f"nav:recommendation:{recommendation_id}:jump")],
            [InlineKeyboardButton(text="Why am I seeing this?", callback_data=f"nav:recommendation:{recommendation_id}:why")],
            [
                InlineKeyboardButton(text="Useful", callback_data=f"nav:recommendation:{recommendation_id}:feedback:useful"),
                InlineKeyboardButton(text="Not Useful", callback_data=f"nav:recommendation:{recommendation_id}:feedback:not_useful"),
            ],
            [
                InlineKeyboardButton(text="Wrong", callback_data=f"nav:recommendation:{recommendation_id}:feedback:wrong"),
                InlineKeyboardButton(text="Needs Review", callback_data=f"nav:recommendation:{recommendation_id}:feedback:needs_review"),
            ],
            [
                InlineKeyboardButton(
                    text="Create Draft Automation",
                    callback_data=f"nav:recommendation:{recommendation_id}:create_automation",
                )
            ],
            *page_controls(back_to="reports:executive:recommendations"),
        ]
    )


def intelligence_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="View Priorities", callback_data=callback_for("reports:executive:recommendations"))],
            [InlineKeyboardButton(text="View Trends", callback_data=callback_for("intelligence:trends"))],
            [InlineKeyboardButton(text="🧠 Intelligence Quality", callback_data=callback_for("intelligence:quality"))],
            [InlineKeyboardButton(text="🔎 Search Intelligence", callback_data=callback_for("search"))],
            [InlineKeyboardButton(text="Ask Fortuna", callback_data=callback_for("help_copilot:next"))],
            [InlineKeyboardButton(text="More Details", callback_data=callback_for("intelligence:details"))],
            *page_controls(back_to="owner_advanced"),
        ]
    )


def trends_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Fix Setup", callback_data=callback_for("first_workspace"))],
            [InlineKeyboardButton(text="More Details", callback_data=callback_for("intelligence:trends:details"))],
            *page_controls(back_to="intelligence"),
        ]
    )


def intelligence_details_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Intelligence Briefing", callback_data=callback_for("reports:intelligence"))],
            [InlineKeyboardButton(text="Run Analysis", callback_data=callback_for("intelligence:runs"))],
            [
                InlineKeyboardButton(text="Things To Watch", callback_data=callback_for("intelligence:signals")),
                InlineKeyboardButton(text="Recurring Problems", callback_data=callback_for("intelligence:patterns")),
            ],
            [
                InlineKeyboardButton(text="Trends", callback_data=callback_for("intelligence:trends")),
                InlineKeyboardButton(text="Workload", callback_data=callback_for("reports:workload")),
            ],
            [
                InlineKeyboardButton(text="Recommendations", callback_data=callback_for("reports:executive:recommendations")),
                InlineKeyboardButton(text="Opportunities", callback_data=callback_for("opportunities")),
            ],
            [InlineKeyboardButton(text="Learning Center", callback_data=callback_for("intelligence:learning"))],
            [InlineKeyboardButton(text="Production Status", callback_data=callback_for("production_status"))],
            *page_controls(back_to="intelligence"),
        ]
    )


def intelligence_run_menu(run_buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in run_buttons]
    rows.extend(
        [
            [InlineKeyboardButton(text="Run Full Intelligence Scan", callback_data=callback_for("intelligence:run:full"))],
            [InlineKeyboardButton(text="Run Pattern Detection", callback_data=callback_for("intelligence:run:pattern_detection"))],
            [InlineKeyboardButton(text="Run Trend Analysis", callback_data=callback_for("intelligence:run:trend_analysis"))],
            [InlineKeyboardButton(text="Run Workload Analysis", callback_data=callback_for("intelligence:run:workload_analysis"))],
            [InlineKeyboardButton(text="Run Recommendations", callback_data=callback_for("intelligence:run:recommendation_generation"))],
            [InlineKeyboardButton(text="Run Opportunity Scoring", callback_data=callback_for("intelligence:run:opportunity_scoring"))],
        ]
    )
    rows.extend(page_controls(back_to="intelligence"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def intelligence_briefing_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Generate Intelligence Briefing", callback_data=callback_for("reports:intelligence:generate"))],
            [InlineKeyboardButton(text="View Latest", callback_data=callback_for("reports:intelligence:latest"))],
            [
                InlineKeyboardButton(text="Things To Watch", callback_data=callback_for("intelligence:signals")),
                InlineKeyboardButton(text="Recurring Problems", callback_data=callback_for("intelligence:patterns")),
            ],
            [
                InlineKeyboardButton(text="View Trends", callback_data=callback_for("intelligence:trends")),
                InlineKeyboardButton(text="View Workload", callback_data=callback_for("reports:workload")),
            ],
            [InlineKeyboardButton(text="Executive Memory Briefing", callback_data=callback_for("intelligence:learning:briefing"))],
            [InlineKeyboardButton(text="Send to HQ", callback_data=callback_for("reports:intelligence:send_hq"))],
            *page_controls(back_to="reports"),
        ]
    )


def learning_center_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="View Lessons", callback_data=callback_for("intelligence:learning:outcome_memory"))],
            [InlineKeyboardButton(text="Playbooks", callback_data=callback_for("intelligence:learning:playbooks"))],
            [InlineKeyboardButton(text="More Details", callback_data=callback_for("intelligence:learning:details"))],
            *page_controls(back_to="intelligence"),
        ]
    )


def learning_details_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Recommended Playbooks", callback_data=callback_for("intelligence:learning:recommended"))],
            [
                InlineKeyboardButton(text="What We've Learned", callback_data=callback_for("intelligence:learning:outcome_memory")),
                InlineKeyboardButton(text="Confidence Changes", callback_data=callback_for("intelligence:learning:confidence")),
            ],
            [
                InlineKeyboardButton(text="Automation Learning", callback_data=callback_for("intelligence:learning:automation")),
                InlineKeyboardButton(text="Opportunity Learning", callback_data=callback_for("intelligence:learning:opportunity")),
            ],
            [InlineKeyboardButton(text="Executive Memory Briefing", callback_data=callback_for("intelligence:learning:briefing"))],
            *page_controls(back_to="intelligence:learning"),
        ]
    )


def learning_playbooks_menu(playbook_buttons: list[tuple[str, str]], *, back_to: str = "intelligence:learning") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in playbook_buttons]
    rows.append([InlineKeyboardButton(text="Recommended Playbooks", callback_data=callback_for("intelligence:learning:recommended"))])
    rows.extend(page_controls(back_to=back_to))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def playbook_detail_menu(playbook_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Suggest Playbook", callback_data=f"nav:playbook:{playbook_id}:suggest")],
            [InlineKeyboardButton(text="Playbook History", callback_data=f"nav:playbook:{playbook_id}:history")],
            [
                InlineKeyboardButton(text="Useful", callback_data=f"nav:playbook:{playbook_id}:feedback:useful"),
                InlineKeyboardButton(text="Not Useful", callback_data=f"nav:playbook:{playbook_id}:feedback:not_useful"),
            ],
            [
                InlineKeyboardButton(text="Wrong", callback_data=f"nav:playbook:{playbook_id}:feedback:wrong"),
                InlineKeyboardButton(text="Needs Review", callback_data=f"nav:playbook:{playbook_id}:feedback:needs_review"),
            ],
            *page_controls(back_to="intelligence:learning:playbooks"),
        ]
    )


def opportunities_menu(opportunity_buttons: list[tuple[str, str]] | None = None, *, back_to: str = "menu") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in (opportunity_buttons or [])]
    rows.extend(
        [
            [InlineKeyboardButton(text="Command Center", callback_data=callback_for("opportunities:command"))],
            [
                InlineKeyboardButton(text="Creator Watchlist", callback_data=callback_for("opportunities:creators")),
                InlineKeyboardButton(text="Own Post Watch", callback_data=callback_for("opportunities:posts")),
            ],
            [InlineKeyboardButton(text="View Opportunities", callback_data=callback_for("opportunities:list"))],
            [InlineKeyboardButton(text="Add Opportunity", callback_data=callback_for("opportunities:add"))],
            [
                InlineKeyboardButton(text="Discovery Mode", callback_data=callback_for("opportunities:discovery")),
                InlineKeyboardButton(text="Opportunity Intelligence", callback_data=callback_for("opportunities:score")),
            ],
            [
                InlineKeyboardButton(text="Comment Profiles", callback_data=callback_for("opportunities:profiles")),
                InlineKeyboardButton(text="Comment Review", callback_data=callback_for("opportunities:comments")),
            ],
            [InlineKeyboardButton(text="Best Opportunity", callback_data=callback_for("opportunities:best"))],
            [
                InlineKeyboardButton(text="Opportunity Results", callback_data=callback_for("opportunities:results")),
                InlineKeyboardButton(text="Manager View", callback_data=callback_for("opportunities:manager")),
            ],
        ]
    )
    rows.extend(page_controls(back_to=back_to))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def opportunity_detail_menu(opportunity_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Assign Chatter", callback_data=f"nav:opportunity:{opportunity_id}:assign")],
            [InlineKeyboardButton(text="Change Status", callback_data=f"nav:opportunity:{opportunity_id}:status")],
            [InlineKeyboardButton(text="Generate Strategies", callback_data=f"nav:opportunity:{opportunity_id}:strategies:regenerate")],
            [InlineKeyboardButton(text="Record Result", callback_data=f"nav:opportunity:{opportunity_id}:record_result")],
            [InlineKeyboardButton(text="Create Task", callback_data=f"nav:opportunity:{opportunity_id}:create_task")],
            [
                InlineKeyboardButton(text="View Learning", callback_data=callback_for("opportunities:learning")),
                InlineKeyboardButton(text="Explain This Screen", callback_data=callback_for("help_copilot:screen:opportunity_detail")),
            ],
            *page_controls(back_to="opportunities:list"),
        ]
    )


def creator_watch_menu(creator_buttons: list[tuple[str, str]] | None = None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in (creator_buttons or [])]
    rows.extend(
        [
            [InlineKeyboardButton(text="Add Creator", callback_data=callback_for("opportunities:creators:add"))],
            [InlineKeyboardButton(text="View Watchlist", callback_data=callback_for("opportunities:creators"))],
            *page_controls(back_to="opportunities"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def creator_watch_detail_menu(creator_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Edit Priority", callback_data=f"nav:creator:{creator_id}:priority"),
                InlineKeyboardButton(text="Edit Niche", callback_data=f"nav:creator:{creator_id}:niche"),
            ],
            [
                InlineKeyboardButton(text="Assign Model", callback_data=f"nav:creator:{creator_id}:assign_model"),
                InlineKeyboardButton(text="Assign Chatter", callback_data=f"nav:creator:{creator_id}:assign_chatter"),
            ],
            [InlineKeyboardButton(text="New Post Alert", callback_data=f"nav:creator:{creator_id}:alert")],
            [InlineKeyboardButton(text="Create Opportunity", callback_data=f"nav:creator:{creator_id}:opportunity")],
            [
                InlineKeyboardButton(text="Disable", callback_data=f"nav:creator:{creator_id}:disable"),
                InlineKeyboardButton(text="Archive", callback_data=f"nav:creator:{creator_id}:archive"),
            ],
            [InlineKeyboardButton(text="Explain This Screen", callback_data=callback_for("help_copilot:screen:creator_detail"))],
            *page_controls(back_to="opportunities:creators"),
        ]
    )


def post_watch_menu(post_buttons: list[tuple[str, str]] | None = None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in (post_buttons or [])]
    rows.extend(
        [
            [InlineKeyboardButton(text="Recent Posts", callback_data=callback_for("opportunities:posts"))],
            [InlineKeyboardButton(text="Attention Needed", callback_data=callback_for("opportunities:posts:attention"))],
            [InlineKeyboardButton(text="Add Own Post", callback_data=callback_for("opportunities:posts:add"))],
            *page_controls(back_to="opportunities"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def post_watch_detail_menu(post_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Create Opportunity From Post", callback_data=f"nav:post:{post_id}:opportunity")],
            [InlineKeyboardButton(text="New Own Post Alert", callback_data=f"nav:post:{post_id}:alert")],
            [InlineKeyboardButton(text="Assign Chatter", callback_data=f"nav:post:{post_id}:assign_chatter")],
            [InlineKeyboardButton(text="Mark Monitored", callback_data=f"nav:post:{post_id}:status:recent")],
            [InlineKeyboardButton(text="Record Result", callback_data=f"nav:post:{post_id}:record_result")],
            [InlineKeyboardButton(text="Explain This Screen", callback_data=callback_for("help_copilot:screen:post_watch"))],
            *page_controls(back_to="opportunities:posts"),
        ]
    )


def opportunity_command_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Add Opportunity", callback_data=callback_for("opportunities:add"))],
            [InlineKeyboardButton(text="Top Opportunities", callback_data=callback_for("opportunities:list"))],
            [InlineKeyboardButton(text="Creator Watchlist", callback_data=callback_for("opportunities:creators"))],
            [InlineKeyboardButton(text="Own Post Watch", callback_data=callback_for("opportunities:posts"))],
            [InlineKeyboardButton(text="Opportunity Results", callback_data=callback_for("opportunities:results"))],
            *page_controls(back_to="opportunities"),
        ]
    )


def chatter_workspace_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="My Opportunities", callback_data=callback_for("my_opportunities")),
                InlineKeyboardButton(text="My Models", callback_data=callback_for("my_models")),
            ],
            [
                InlineKeyboardButton(text="My Tasks", callback_data=callback_for("tasks:my")),
                InlineKeyboardButton(text="Availability", callback_data=callback_for("availability")),
            ],
            [
                InlineKeyboardButton(text="Performance", callback_data=callback_for("performance")),
                InlineKeyboardButton(text="Explain This Screen", callback_data=callback_for("help_copilot:screen:chatter_workspace")),
            ],
            *page_controls(back_to="menu"),
        ]
    )


def help_copilot_menu(*, back_to: str = "help", prefix: str = "help_copilot") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="What should I do next?", callback_data=callback_for(f"{prefix}:question:next"))],
            [InlineKeyboardButton(text="How do I finish setup?", callback_data=callback_for(f"{prefix}:question:finish_setup"))],
            [InlineKeyboardButton(text="Help me add a proxy", callback_data=callback_for(f"{prefix}:question:add_proxy"))],
            [InlineKeyboardButton(text="Explain this screen", callback_data=callback_for(f"{prefix}:question:where"))],
            [InlineKeyboardButton(text="I'm stuck", callback_data=callback_for(f"{prefix}:question:why_broken"))],
            *page_controls(back_to=back_to),
        ]
    )


def help_feedback_menu(log_id: int | None, *, next_action: str | None = None, back_to: str = "help_copilot") -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if next_action:
        rows.append([InlineKeyboardButton(text="Open Next Step", callback_data=callback_for(next_action))])
    if log_id is not None:
        rows.append(
            [
                InlineKeyboardButton(text="Helpful", callback_data=callback_for(f"help_feedback:{log_id}:helpful")),
                InlineKeyboardButton(text="Not Helpful", callback_data=callback_for(f"help_feedback:{log_id}:not_helpful")),
            ]
        )
        rows.append([InlineKeyboardButton(text="Still Confused", callback_data=callback_for(f"help_feedback:{log_id}:still_confused"))])
    rows.extend(page_controls(back_to=back_to))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def team_activation_menu(user_buttons: list[tuple[str, str]] | None = None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in (user_buttons or [])]
    rows.extend(page_controls(back_to="menu"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def operations_dashboard_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="View Tasks", callback_data=callback_for("tasks")),
                InlineKeyboardButton(text="View Incidents", callback_data=callback_for("incidents")),
            ],
            [InlineKeyboardButton(text="View Accounts Needing Attention", callback_data=callback_for("accounts:attention"))],
            [InlineKeyboardButton(text="View Proxies Needing Attention", callback_data=callback_for("proxies:dashboard"))],
            *page_controls(back_to="reports"),
        ]
    )


def manager_command_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Assign Task", callback_data=callback_for("tasks:create")),
                InlineKeyboardButton(text="View Overdue", callback_data=callback_for("tasks:overdue")),
            ],
            [
                InlineKeyboardButton(text="View Incidents", callback_data=callback_for("incidents:list")),
                InlineKeyboardButton(text="Team Availability", callback_data=callback_for("availability:team")),
            ],
            [InlineKeyboardButton(text="Generate Daily Digest", callback_data=callback_for("reports:digest:generate"))],
            *page_controls(back_to="reports"),
        ]
    )


def automations_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Daily Autopilot", callback_data=callback_for("automations:daily_autopilot"))],
            [InlineKeyboardButton(text="Safe Automations", callback_data=callback_for("automations:templates"))],
            [InlineKeyboardButton(text="Run History", callback_data=callback_for("automations:runs"))],
            [InlineKeyboardButton(text="More Details", callback_data=callback_for("automations:rules"))],
            *page_controls(back_to="owner_advanced"),
        ]
    )


def automation_rules_menu(rule_buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in rule_buttons]
    rows.append([InlineKeyboardButton(text="Built-In Templates", callback_data=callback_for("automations:templates"))])
    rows.append([InlineKeyboardButton(text="Create Rule", callback_data=callback_for("automations:create"))])
    rows.extend(page_controls(back_to="automations"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def automation_rule_detail_menu(rule_id: int, status: str) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Run Simulation", callback_data=f"nav:automation:{rule_id}:simulate")],
        [
            InlineKeyboardButton(text="Impact Preview", callback_data=f"nav:automation:{rule_id}:simulations"),
            InlineKeyboardButton(text="View Rollback Plan", callback_data=f"nav:automation:{rule_id}:rollback"),
        ],
        [
            InlineKeyboardButton(text="Request Approval", callback_data=f"nav:automation:{rule_id}:request_approval"),
            InlineKeyboardButton(text="Run Now", callback_data=f"nav:automation:{rule_id}:run_now"),
        ],
    ]
    if status == "active":
        rows.append([InlineKeyboardButton(text="Pause Rule", callback_data=f"nav:automation:{rule_id}:pause")])
    elif status == "paused":
        rows.append([InlineKeyboardButton(text="Resume Rule", callback_data=f"nav:automation:{rule_id}:resume")])
    elif status == "approved":
        rows.append([InlineKeyboardButton(text="Activate Rule", callback_data=f"nav:automation:{rule_id}:activate")])
    rows.append([InlineKeyboardButton(text="Retire Rule", callback_data=f"nav:automation:{rule_id}:retire")])
    rows.append([InlineKeyboardButton(text="Run History", callback_data=f"nav:automation:{rule_id}:runs")])
    rows.extend(page_controls(back_to="automations:rules"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def automation_templates_menu(template_buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in template_buttons]
    rows.append([InlineKeyboardButton(text="Refresh Templates", callback_data=callback_for("automations:templates"))])
    rows.extend(page_controls(back_to="automations"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def simulation_runs_menu(run_buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in run_buttons]
    rows.append([InlineKeyboardButton(text="Run Proxy Repair Simulation", callback_data=callback_for("automations:simulate:proxy_repair"))])
    rows.append([InlineKeyboardButton(text="Run Daily Briefing Simulation", callback_data=callback_for("automations:simulate:daily_briefing"))])
    rows.extend(page_controls(back_to="automations"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def simulation_run_detail_menu(run_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="View Affected Entities", callback_data=f"nav:simulation:{run_id}:affected")],
            [
                InlineKeyboardButton(text="Approve Simulation", callback_data=f"nav:simulation:{run_id}:approve"),
                InlineKeyboardButton(text="Reject Simulation", callback_data=f"nav:simulation:{run_id}:reject"),
            ],
            *page_controls(back_to="automations:simulations"),
        ]
    )


def automation_approvals_menu(approval_buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in approval_buttons]
    rows.extend(page_controls(back_to="automations"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def automation_approval_detail_menu(approval_id: int, rule_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Approve", callback_data=f"nav:approval:{approval_id}:approve"),
                InlineKeyboardButton(text="Reject", callback_data=f"nav:approval:{approval_id}:reject"),
            ],
            [InlineKeyboardButton(text="View Rule", callback_data=f"nav:automation:{rule_id}")],
            [InlineKeyboardButton(text="View Rollback Plan", callback_data=f"nav:automation:{rule_id}:rollback")],
            *page_controls(back_to="automations:approvals"),
        ]
    )


def automation_runs_menu(run_buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in run_buttons]
    rows.extend(page_controls(back_to="automations"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def automation_run_detail_menu(run_id: int, step_buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in step_buttons]
    rows.extend(page_controls(back_to="automations:runs"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def proxy_list_menu(proxy_buttons: list[tuple[str, str]], *, back_to: str = "proxies") -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in proxy_buttons]
    rows.append([InlineKeyboardButton(text="Add Another", callback_data=callback_for("proxies:olympix:paste"))])
    rows.extend(page_controls(back_to=back_to))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def proxy_detail_menu(proxy_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Assign Account", callback_data=f"nav:proxy:{proxy_id}:assign")],
            [InlineKeyboardButton(text="Test Proxy", callback_data=f"nav:proxy:{proxy_id}:check:simulated")],
            [InlineKeyboardButton(text="Rotate Session", callback_data=f"nav:proxy:{proxy_id}:rotate_preview")],
            [InlineKeyboardButton(text="Set Location", callback_data=f"nav:proxy:{proxy_id}:location")],
            [InlineKeyboardButton(text="History", callback_data=f"nav:proxy:{proxy_id}:history")],
            [InlineKeyboardButton(text="Advanced", callback_data=f"nav:proxy:{proxy_id}:advanced")],
            *page_controls(back_to="proxies:list"),
        ]
    )


def proxy_manage_menu(proxy_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Assign to Account", callback_data=f"nav:proxy:{proxy_id}:assign")],
            [InlineKeyboardButton(text="Rotate Session", callback_data=f"nav:proxy:{proxy_id}:rotate_preview")],
            [InlineKeyboardButton(text="Rollback Last Rotation", callback_data=f"nav:proxy:{proxy_id}:rollback")],
            [InlineKeyboardButton(text="Set Location", callback_data=f"nav:proxy:{proxy_id}:location")],
            [InlineKeyboardButton(text="Run Check", callback_data=f"nav:proxy:{proxy_id}:check:simulated")],
            [InlineKeyboardButton(text="Remove From Account", callback_data=f"nav:proxy:{proxy_id}:remove")],
            [InlineKeyboardButton(text="Archive Proxy", callback_data=f"nav:proxy:{proxy_id}:archive_confirm")],
            [InlineKeyboardButton(text="Delete Proxy", callback_data=f"nav:proxy:{proxy_id}:delete_confirm")],
            [InlineKeyboardButton(text="Technical Details", callback_data=f"nav:proxy:{proxy_id}")],
            *page_controls(back_to=f"proxy:{proxy_id}"),
        ]
    )


def proxy_detail_advanced_menu(proxy_id: int, *, real_enabled: bool) -> InlineKeyboardMarkup:
    real_toggle = (
        InlineKeyboardButton(text="Disable Real Checks", callback_data=f"nav:proxy:{proxy_id}:disable_real")
        if real_enabled
        else InlineKeyboardButton(text="Enable Real Checks", callback_data=f"nav:proxy:{proxy_id}:enable_real")
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [real_toggle],
            [InlineKeyboardButton(text="Run Real Check", callback_data=f"nav:proxy:{proxy_id}:check:real")],
            [InlineKeyboardButton(text="Rotate Until Match", callback_data=f"nav:proxy:{proxy_id}:rotate_until_match")],
            [InlineKeyboardButton(text="Rollback Last Rotation", callback_data=f"nav:proxy:{proxy_id}:rollback")],
            [InlineKeyboardButton(text="Disable Proxy", callback_data=f"nav:proxy:{proxy_id}:disable")],
            [InlineKeyboardButton(text="Reactivate Proxy", callback_data=f"nav:proxy:{proxy_id}:reactivate")],
            [
                InlineKeyboardButton(text="Assigned Accounts", callback_data=f"nav:proxy:{proxy_id}:accounts"),
                InlineKeyboardButton(text="Remove Account", callback_data=f"nav:proxy:{proxy_id}:remove"),
            ],
            [InlineKeyboardButton(text="Audit History", callback_data=f"nav:proxy:{proxy_id}:audit")],
            *page_controls(back_to=f"proxy:{proxy_id}"),
        ]
    )


def proxy_rotation_preview_menu(proxy_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Confirm Rotate", callback_data=f"nav:proxy:{proxy_id}:rotate")],
            [InlineKeyboardButton(text="Cancel", callback_data=f"nav:proxy:{proxy_id}:manage")],
            *page_controls(back_to=f"proxy:{proxy_id}"),
        ]
    )


def proxy_result_menu(proxy_id: int, *, include_rollback: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text="Test Proxy", callback_data=f"nav:proxy:{proxy_id}:check:simulated")],
    ]
    if include_rollback:
        rows.append([InlineKeyboardButton(text="Rollback", callback_data=f"nav:proxy:{proxy_id}:rollback")])
    rows.extend(page_controls(back_to=f"proxy:{proxy_id}"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def proxy_import_success_menu(proxy_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Assign Account", callback_data=f"nav:proxy:{proxy_id}:assign")],
            [InlineKeyboardButton(text="Test Proxy", callback_data=f"nav:proxy:{proxy_id}:check:simulated")],
            [InlineKeyboardButton(text="Set Target Location", callback_data=f"nav:proxy:{proxy_id}:location")],
            [InlineKeyboardButton(text="Proxy Vault", callback_data=callback_for("proxies"))],
        ]
    )


def proxy_archive_confirm_menu(proxy_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Confirm Archive", callback_data=f"nav:proxy:{proxy_id}:archive")],
            [InlineKeyboardButton(text="Cancel", callback_data=f"nav:proxy:{proxy_id}:manage")],
            *page_controls(back_to=f"proxy:{proxy_id}:manage"),
        ]
    )


def proxy_delete_confirm_menu(proxy_id: int, *, can_delete: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if can_delete:
        rows.append([InlineKeyboardButton(text="Confirm Delete", callback_data=f"nav:proxy:{proxy_id}:delete")])
    rows.append([InlineKeyboardButton(text="Archive Instead", callback_data=f"nav:proxy:{proxy_id}:archive_confirm")])
    rows.append([InlineKeyboardButton(text="Cancel", callback_data=f"nav:proxy:{proxy_id}:manage")])
    rows.extend(page_controls(back_to=f"proxy:{proxy_id}:manage"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def proxy_account_choice_menu(proxy_id: int, account_buttons: list[tuple[str, str]], action: str) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in account_buttons]
    rows.extend(page_controls(back_to=f"proxy:{proxy_id}"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def account_proxy_choice_menu(account_id: int, proxy_buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in proxy_buttons]
    rows.extend(page_controls(back_to=f"account:{account_id}"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def models_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="View Models", callback_data=callback_for("models:list"))],
            [InlineKeyboardButton(text="Create Model", callback_data=callback_for("models:create"))],
            [InlineKeyboardButton(text="Create First Model", callback_data=callback_for("setup:wizard:model"))],
            [InlineKeyboardButton(text="Search Model", callback_data=callback_for("models:search"))],
            [InlineKeyboardButton(text="Model Dashboard", callback_data=callback_for("models:dashboard"))],
            *page_controls(back_to="menu"),
        ]
    )


def model_list_menu(model_buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in model_buttons]
    rows.extend(page_controls(back_to="models"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def model_detail_menu(model_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Edit Model", callback_data=f"nav:model:{model_id}:edit"),
                InlineKeyboardButton(text="Manage Team", callback_data=f"nav:model:{model_id}:team"),
            ],
            [
                InlineKeyboardButton(text="Manage Accounts", callback_data=f"nav:model:{model_id}:accounts"),
                InlineKeyboardButton(text="Manage Creators", callback_data=f"nav:model:{model_id}:creators"),
            ],
            [
                InlineKeyboardButton(text="Manage Opportunities", callback_data=f"nav:model:{model_id}:opportunities"),
                InlineKeyboardButton(text="View Tasks", callback_data=f"nav:model:{model_id}:tasks"),
            ],
            [
                InlineKeyboardButton(text="View Incidents", callback_data=f"nav:model:{model_id}:incidents"),
                InlineKeyboardButton(text="Audit History", callback_data=f"nav:model:{model_id}:audit"),
            ],
            [InlineKeyboardButton(text="Ask Help Copilot", callback_data=callback_for("help_copilot:edit_model"))],
            *page_controls(back_to="models:list"),
        ]
    )


def model_edit_menu(model_id: int, status: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="Edit Name", callback_data=f"nav:model:{model_id}:edit:display_name"),
            InlineKeyboardButton(text="Edit Stage Name", callback_data=f"nav:model:{model_id}:edit:stage_name"),
        ],
        [
            InlineKeyboardButton(text="Edit Country", callback_data=f"nav:model:{model_id}:edit:country"),
            InlineKeyboardButton(text="Edit Timezone", callback_data=f"nav:model:{model_id}:edit:timezone"),
        ],
        [InlineKeyboardButton(text="Edit Primary Platform", callback_data=f"nav:model:{model_id}:edit:primary_platform")],
        [
            InlineKeyboardButton(text="Edit Notes", callback_data=f"nav:model:{model_id}:edit:notes"),
            InlineKeyboardButton(text="Internal Notes", callback_data=f"nav:model:{model_id}:edit:internal_notes"),
        ],
        [
            InlineKeyboardButton(text="Set Active", callback_data=f"nav:model:{model_id}:status:active"),
            InlineKeyboardButton(text="Set Warning", callback_data=f"nav:model:{model_id}:status:warning"),
        ],
        [
            InlineKeyboardButton(text="Disable", callback_data=f"nav:model:{model_id}:status:disabled"),
            InlineKeyboardButton(text="Archive", callback_data=f"nav:model:{model_id}:archive"),
        ],
        [
            InlineKeyboardButton(text="Manage Team", callback_data=f"nav:model:{model_id}:team"),
            InlineKeyboardButton(text="Manage Accounts", callback_data=f"nav:model:{model_id}:accounts"),
        ],
    ]
    if status == "archived":
        rows.insert(0, [InlineKeyboardButton(text="Reactivate", callback_data=f"nav:model:{model_id}:status:active")])
    rows.extend(page_controls(back_to=f"model:{model_id}"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def model_team_menu(model_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Assign Manager", callback_data=f"nav:model:{model_id}:team:assign:manager")],
            [
                InlineKeyboardButton(
                    text="Assign Chatter Manager",
                    callback_data=f"nav:model:{model_id}:team:assign:chatter_manager",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Assign Senior Chatter",
                    callback_data=f"nav:model:{model_id}:team:assign:senior_chatter",
                )
            ],
            [InlineKeyboardButton(text="Assign Chatter", callback_data=f"nav:model:{model_id}:team:assign:chatter")],
            [InlineKeyboardButton(text="Assign VA", callback_data=f"nav:model:{model_id}:team:assign:va")],
            [InlineKeyboardButton(text="Remove Assignment", callback_data=f"nav:model:{model_id}:team:remove")],
            *page_controls(back_to=f"model:{model_id}"),
        ]
    )


def model_member_choice_menu(
    model_id: int,
    relationship_type: str,
    user_buttons: list[tuple[str, str]],
) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in user_buttons]
    rows.extend(page_controls(back_to=f"model:{model_id}:team"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def user_detail_menu(user_id: int, status: str, is_owner: bool = False) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if status == "pending":
        rows.append(
            [
                InlineKeyboardButton(text="Approve", callback_data=f"nav:user:{user_id}:approve"),
                InlineKeyboardButton(text="Deny", callback_data=f"nav:user:{user_id}:deny"),
            ]
        )
    if status == "active":
        rows.append([InlineKeyboardButton(text="Disable", callback_data=f"nav:user:{user_id}:disable")])
        if is_owner:
            rows.append([InlineKeyboardButton(text="Demote Owner", callback_data=f"nav:user:{user_id}:demote_owner")])
        else:
            rows.append([InlineKeyboardButton(text="Promote Owner", callback_data=f"nav:user:{user_id}:promote_owner")])
    if status in {"disabled", "denied"}:
        rows.append(
            [InlineKeyboardButton(text="Reactivate", callback_data=f"nav:user:{user_id}:reactivate")]
        )
    rows.append(
        [
            InlineKeyboardButton(text="Assign Role", callback_data=f"nav:user:{user_id}:assign_role"),
            InlineKeyboardButton(text="Remove Role", callback_data=f"nav:user:{user_id}:remove_role"),
        ]
    )
    rows.extend(page_controls(back_to="users"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def role_choice_menu(user_id: int, action: str, role_names: list[str]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=role_name, callback_data=f"nav:user:{user_id}:{action}:{role_name}")]
        for role_name in role_names
    ]
    rows.extend(page_controls(back_to=f"user:{user_id}"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def roles_menu(role_buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in role_buttons]
    rows.extend(page_controls(back_to="menu"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def role_detail_menu(role_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="View Permissions", callback_data=f"nav:role:{role_id}:permissions")],
            [
                InlineKeyboardButton(text="Add Permission", callback_data=f"nav:role:{role_id}:add_permission"),
                InlineKeyboardButton(
                    text="Remove Permission", callback_data=f"nav:role:{role_id}:remove_permission"
                ),
            ],
            [InlineKeyboardButton(text="Default Permission List", callback_data="nav:permissions")],
            *page_controls(back_to="roles"),
        ]
    )


def permission_choice_menu(role_id: int, action: str, permission_keys: list[str]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=key, callback_data=f"nav:role:{role_id}:{action}:{key}")]
        for key in permission_keys[:20]
    ]
    rows.extend(page_controls(back_to=f"role:{role_id}"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Setup Wizard", callback_data=callback_for("setup:wizard"))],
            [InlineKeyboardButton(text="Bot Status", callback_data=callback_for("bot_status"))],
            [InlineKeyboardButton(text="Production Status", callback_data=callback_for("production_status"))],
            [InlineKeyboardButton(text="Production Observability", callback_data=callback_for("production_observability"))],
            [InlineKeyboardButton(text="UI Self-Test", callback_data=callback_for("ui_self_test"))],
            [InlineKeyboardButton(text="Chat Cleanup", callback_data=callback_for("settings:chat_cleanup"))],
            [InlineKeyboardButton(text="Report a Problem", callback_data=callback_for("settings:report_problem"))],
            [InlineKeyboardButton(text="Button Health Report", callback_data=callback_for("button_health"))],
            [InlineKeyboardButton(text="Callback Failure Review", callback_data=callback_for("callback_failure_review"))],
            [InlineKeyboardButton(text="My Availability", callback_data=callback_for("availability"))],
            [InlineKeyboardButton(text="Team Availability", callback_data=callback_for("availability:team"))],
            [InlineKeyboardButton(text="Notification Digest Mode", callback_data=callback_for("notification_digest"))],
            [InlineKeyboardButton(text="View Audit Logs", callback_data=callback_for("audit_logs"))],
            [InlineKeyboardButton(text="Notification Group Setup", callback_data=callback_for("notification_group_setup"))],
            [InlineKeyboardButton(text="Notification Group Pilot", callback_data=callback_for("notification_group_pilot"))],
            [InlineKeyboardButton(text="Notification Routing", callback_data=callback_for("notification_routing"))],
            [InlineKeyboardButton(text="Notification Targets", callback_data=callback_for("notification_targets"))],
            *page_controls(back_to="owner_advanced"),
        ]
    )


def notification_targets_menu(target_buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in target_buttons]
    rows.append([InlineKeyboardButton(text="Add Target", callback_data=callback_for("notification_targets:add"))])
    rows.append(
        [
            InlineKeyboardButton(
                text="Register Current Chat as Fortuna Target",
                callback_data=callback_for("notification_targets:add_current"),
            )
        ]
    )
    rows.extend(page_controls(back_to="settings"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def notification_group_setup_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Register Current Chat as Fortuna Target",
                    callback_data=callback_for("notification_targets:add_current"),
                )
            ],
            [InlineKeyboardButton(text="Run Routing Test", callback_data=callback_for("notification_targets:routing_test"))],
            [InlineKeyboardButton(text="Notification Routing", callback_data=callback_for("notification_routing"))],
            [
                InlineKeyboardButton(text="Notification Targets", callback_data=callback_for("notification_targets")),
                InlineKeyboardButton(text="How to Register Groups", callback_data=callback_for("help:notification_groups")),
            ],
            [InlineKeyboardButton(text="Notification Group Pilot", callback_data=callback_for("notification_group_pilot"))],
            *page_controls(back_to="settings"),
        ]
    )


def notification_group_pilot_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Register This Chat",
                    callback_data=callback_for("notification_targets:add_current"),
                )
            ],
            [InlineKeyboardButton(text="Preview Routing", callback_data=callback_for("notification_targets:routing_test"))],
            [InlineKeyboardButton(text="Simulate Routing", callback_data=callback_for("notification_targets:routing_test"))],
            [
                InlineKeyboardButton(text="Run Creator Alert Pilot", callback_data=callback_for("notification_pilot:creator_alert")),
            ],
            [
                InlineKeyboardButton(text="Run Own Post Pilot", callback_data=callback_for("notification_pilot:own_post_alert")),
            ],
            [InlineKeyboardButton(text="Activation Checklist", callback_data=callback_for("notification_group_pilot"))],
            [InlineKeyboardButton(text="Ask Fortuna", callback_data=callback_for("help_copilot:notification_groups"))],
            *page_controls(back_to="settings"),
        ]
    )


def notification_routing_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Register Current Chat", callback_data=callback_for("notification_targets:add_current"))],
            [
                InlineKeyboardButton(text="Use 2 Groups", callback_data=callback_for("notification_routing:mode:2_group")),
                InlineKeyboardButton(text="Use 3 Groups", callback_data=callback_for("notification_routing:mode:3_group")),
            ],
            [
                InlineKeyboardButton(text="Test HQ", callback_data=callback_for("notification_targets:test:hq")),
                InlineKeyboardButton(text="Test Ops", callback_data=callback_for("notification_targets:test:ops")),
                InlineKeyboardButton(text="Test Alerts", callback_data=callback_for("notification_targets:test:alerts")),
            ],
            [InlineKeyboardButton(text="Simulate Alert Routing", callback_data=callback_for("notification_targets:routing_test"))],
            [InlineKeyboardButton(text="Delivery History", callback_data=callback_for("reports:digest:history"))],
            *page_controls(back_to="settings"),
        ]
    )


def notification_target_detail_menu(target_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Set Purpose", callback_data=f"nav:notification_target:{target_id}:purpose")],
            [
                InlineKeyboardButton(text="Disable Target", callback_data=f"nav:notification_target:{target_id}:disable"),
                InlineKeyboardButton(text="Test Send", callback_data=f"nav:notification_target:{target_id}:test"),
            ],
            [InlineKeyboardButton(text="Send Test Notification", callback_data=f"nav:notification_target:{target_id}:send_test")],
            *page_controls(back_to="notification_targets"),
        ]
    )


def notification_target_purpose_menu(target_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Fortuna HQ", callback_data=f"nav:notification_target:{target_id}:purpose:hq")],
            [InlineKeyboardButton(text="Fortuna Ops", callback_data=f"nav:notification_target:{target_id}:purpose:ops")],
            [InlineKeyboardButton(text="Fortuna Alerts", callback_data=f"nav:notification_target:{target_id}:purpose:alerts")],
            *page_controls(back_to=f"notification_target:{target_id}"),
        ]
    )


def bot_status_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Refresh", callback_data=callback_for("bot_status"))],
            [InlineKeyboardButton(text="Production Observability", callback_data=callback_for("production_observability"))],
            *page_controls(back_to="settings"),
        ]
    )


def production_observability_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Refresh", callback_data=callback_for("production_observability"))],
            [InlineKeyboardButton(text="Run Integrity Check", callback_data=callback_for("integrity"))],
            [InlineKeyboardButton(text="Bot Instance Diagnostics", callback_data=callback_for("bot_instance_status"))],
            [
                InlineKeyboardButton(text="Bot Status", callback_data=callback_for("bot_status")),
                InlineKeyboardButton(text="Notification Group Setup", callback_data=callback_for("notification_group_setup")),
            ],
            [
                InlineKeyboardButton(text="Notification Pilot", callback_data=callback_for("notification_group_pilot")),
                InlineKeyboardButton(text="UI Self-Test", callback_data=callback_for("ui_self_test")),
            ],
            [
                InlineKeyboardButton(text="How to Register Groups", callback_data=callback_for("help:notification_groups")),
                InlineKeyboardButton(text="Add Current Chat as Target", callback_data=callback_for("notification_targets:add_current")),
            ],
            [InlineKeyboardButton(text="Preview Routing", callback_data=callback_for("notification_targets:routing_test"))],
            *page_controls(back_to="owner_advanced"),
        ]
    )


def ui_self_test_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Run UI Self-Test", callback_data=callback_for("ui_self_test:run"))],
            [InlineKeyboardButton(text="Button Health Report", callback_data=callback_for("button_health"))],
            [InlineKeyboardButton(text="Callback Failure Review", callback_data=callback_for("callback_failure_review"))],
            [InlineKeyboardButton(text="Production Observability", callback_data=callback_for("production_observability"))],
            *page_controls(back_to="settings"),
        ]
    )


def proxy_real_check_pilot_menu(proxy_buttons: list[tuple[str, str]] | None = None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in (proxy_buttons or [])]
    rows.extend(
        [
            [InlineKeyboardButton(text="Olympix Wizard", callback_data=callback_for("proxies:olympix"))],
            [InlineKeyboardButton(text="Proxy Setup Check", callback_data=callback_for("proxies:entry_check"))],
            [InlineKeyboardButton(text="Ask Fortuna", callback_data=callback_for("help_copilot:proxy_setup"))],
            *page_controls(back_to="proxies"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def availability_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="On Shift", callback_data=callback_for("availability:set:on_shift")),
                InlineKeyboardButton(text="Off Shift", callback_data=callback_for("availability:set:off_shift")),
            ],
            [
                InlineKeyboardButton(text="Away", callback_data=callback_for("availability:set:away")),
                InlineKeyboardButton(text="Vacation", callback_data=callback_for("availability:set:vacation")),
            ],
            [InlineKeyboardButton(text="Unavailable", callback_data=callback_for("availability:set:unavailable"))],
            *page_controls(back_to="settings"),
        ]
    )


def onboarding_language_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="English", callback_data=callback_for("onboarding:language:English"))],
            [InlineKeyboardButton(text="Spanish", callback_data=callback_for("onboarding:language:Spanish"))],
            [InlineKeyboardButton(text="Portuguese", callback_data=callback_for("onboarding:language:Portuguese"))],
            [InlineKeyboardButton(text="Tagalog / Filipino", callback_data=callback_for("onboarding:language:Tagalog / Filipino"))],
            [InlineKeyboardButton(text="Serbian", callback_data=callback_for("onboarding:language:Serbian"))],
        ]
    )


def onboarding_country_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="United States", callback_data=callback_for("onboarding:country:United States"))],
            [InlineKeyboardButton(text="Philippines", callback_data=callback_for("onboarding:country:Philippines"))],
            [InlineKeyboardButton(text="Serbia", callback_data=callback_for("onboarding:country:Serbia"))],
            [InlineKeyboardButton(text="Colombia", callback_data=callback_for("onboarding:country:Colombia"))],
            [InlineKeyboardButton(text="Brazil", callback_data=callback_for("onboarding:country:Brazil"))],
            [InlineKeyboardButton(text="United Kingdom", callback_data=callback_for("onboarding:country:United Kingdom"))],
        ]
    )


def onboarding_timezone_menu(timezones: tuple[str, ...]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=value, callback_data=callback_for(f"onboarding:timezone:{value}"))] for value in timezones]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def onboarding_time_format_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="12h", callback_data=callback_for("onboarding:time_format:12h"))],
            [InlineKeyboardButton(text="24h", callback_data=callback_for("onboarding:time_format:24h"))],
        ]
    )


def onboarding_pending_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Language", callback_data=callback_for("onboarding:reset:language")),
                InlineKeyboardButton(text="Country", callback_data=callback_for("onboarding:reset:country")),
            ],
            [
                InlineKeyboardButton(text="Timezone", callback_data=callback_for("onboarding:reset:timezone")),
                InlineKeyboardButton(text="Time Format", callback_data=callback_for("onboarding:reset:time_format")),
            ],
        ]
    )
