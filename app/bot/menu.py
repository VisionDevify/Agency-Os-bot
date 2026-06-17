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


def help_center_menu(topic_buttons: list[tuple[str, str]] | None = None) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in (topic_buttons or [])]
    rows.append([InlineKeyboardButton(text="Help Copilot", callback_data=callback_for("help_copilot"))])
    rows.extend(page_controls(back_to="menu"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


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


def scheduled_automations_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Run Due Safe Automations", callback_data=callback_for("automations:scheduled:run_due"))],
            [InlineKeyboardButton(text="Automation Health", callback_data=callback_for("automations:health"))],
            *page_controls(back_to="automations"),
        ]
    )


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
    rows.extend(page_controls(back_to="menu"))
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
                InlineKeyboardButton(text="Assign Proxy", callback_data=f"nav:account:{account_id}:proxy:assign"),
                InlineKeyboardButton(text="Remove Proxy", callback_data=f"nav:account:{account_id}:proxy:remove"),
            ],
            [InlineKeyboardButton(text="View Audit History", callback_data=f"nav:account:{account_id}:audit")],
            *page_controls(back_to="accounts:list"),
        ]
    )


def proxies_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="View Proxies", callback_data=callback_for("proxies:list"))],
            [InlineKeyboardButton(text="Create Proxy", callback_data=callback_for("proxies:create"))],
            [InlineKeyboardButton(text="Accounts Missing Proxy", callback_data=callback_for("proxies:missing"))],
            [InlineKeyboardButton(text="Simulation Mode", callback_data=callback_for("proxies:simulation"))],
            [InlineKeyboardButton(text="Infrastructure Dashboard", callback_data=callback_for("proxies:dashboard"))],
            *page_controls(back_to="menu"),
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
            *page_controls(back_to="menu"),
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
            *page_controls(back_to="menu"),
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
            [InlineKeyboardButton(text="Playbooks", callback_data=callback_for("intelligence:learning:playbooks"))],
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
            *page_controls(back_to="intelligence"),
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


def opportunities_menu(opportunity_buttons: list[tuple[str, str]] | None = None) -> InlineKeyboardMarkup:
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
            [InlineKeyboardButton(text="Score Opportunities", callback_data=callback_for("opportunities:score"))],
            [
                InlineKeyboardButton(text="Opportunity Results", callback_data=callback_for("opportunities:results")),
                InlineKeyboardButton(text="Manager View", callback_data=callback_for("opportunities:manager")),
            ],
        ]
    )
    rows.extend(page_controls(back_to="menu"))
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


def help_copilot_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="How do I add a creator?", callback_data=callback_for("help_copilot:add_creator"))],
            [InlineKeyboardButton(text="How do I assign an opportunity?", callback_data=callback_for("help_copilot:assign_opportunity"))],
            [InlineKeyboardButton(text="Where are my opportunities?", callback_data=callback_for("help_copilot:my_opportunities"))],
            [InlineKeyboardButton(text="Why can't I access this?", callback_data=callback_for("help_copilot:access"))],
            [InlineKeyboardButton(text="What should I do next?", callback_data=callback_for("help_copilot:next"))],
            [InlineKeyboardButton(text="How do I record results?", callback_data=callback_for("help_copilot:record_results"))],
            [InlineKeyboardButton(text="How do I complete an opportunity?", callback_data=callback_for("help_copilot:opportunity"))],
            [InlineKeyboardButton(text="How does Availability work?", callback_data=callback_for("help_copilot:availability"))],
            *page_controls(back_to="help"),
        ]
    )


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
            [InlineKeyboardButton(text="View Rules", callback_data=callback_for("automations:rules"))],
            [InlineKeyboardButton(text="Built-In Templates", callback_data=callback_for("automations:templates"))],
            [InlineKeyboardButton(text="Create Rule", callback_data=callback_for("automations:create"))],
            [
                InlineKeyboardButton(text="Simulations", callback_data=callback_for("automations:simulations")),
                InlineKeyboardButton(text="Pending Approvals", callback_data=callback_for("automations:approvals")),
            ],
            [
                InlineKeyboardButton(text="Run History", callback_data=callback_for("automations:runs")),
                InlineKeyboardButton(text="Automation Health", callback_data=callback_for("automations:health")),
            ],
            [InlineKeyboardButton(text="Scheduled Runs", callback_data=callback_for("automations:scheduled"))],
            *page_controls(back_to="menu"),
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
    rows.extend(page_controls(back_to=back_to))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def proxy_detail_menu(proxy_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Assign Account", callback_data=f"nav:proxy:{proxy_id}:assign"),
                InlineKeyboardButton(text="Remove Account", callback_data=f"nav:proxy:{proxy_id}:remove"),
            ],
            [InlineKeyboardButton(text="View Assigned Accounts", callback_data=f"nav:proxy:{proxy_id}:accounts")],
            [
                InlineKeyboardButton(text="Rotate Session", callback_data=f"nav:proxy:{proxy_id}:rotate"),
                InlineKeyboardButton(text="Rollback Session", callback_data=f"nav:proxy:{proxy_id}:rollback"),
            ],
            [
                InlineKeyboardButton(text="Verify Location", callback_data=f"nav:proxy:{proxy_id}:verify"),
                InlineKeyboardButton(text="Repair/Test", callback_data=f"nav:proxy:{proxy_id}:repair"),
            ],
            [InlineKeyboardButton(text="Audit History", callback_data=f"nav:proxy:{proxy_id}:audit")],
            *page_controls(back_to="proxies:list"),
        ]
    )


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
                InlineKeyboardButton(text="View Accounts", callback_data=f"nav:model:{model_id}:accounts"),
                InlineKeyboardButton(text="View Tasks", callback_data=f"nav:model:{model_id}:tasks"),
            ],
            [
                InlineKeyboardButton(text="View Incidents", callback_data=f"nav:model:{model_id}:incidents"),
                InlineKeyboardButton(text="Audit History", callback_data=f"nav:model:{model_id}:audit"),
            ],
            *page_controls(back_to="models:list"),
        ]
    )


def model_edit_menu(model_id: int, status: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(text="Set Active", callback_data=f"nav:model:{model_id}:status:active"),
            InlineKeyboardButton(text="Set Warning", callback_data=f"nav:model:{model_id}:status:warning"),
        ],
        [
            InlineKeyboardButton(text="Disable", callback_data=f"nav:model:{model_id}:status:disabled"),
            InlineKeyboardButton(text="Archive", callback_data=f"nav:model:{model_id}:archive"),
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


def user_detail_menu(user_id: int, status: str) -> InlineKeyboardMarkup:
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
            [InlineKeyboardButton(text="Bot Status", callback_data=callback_for("bot_status"))],
            [InlineKeyboardButton(text="Production Status", callback_data=callback_for("production_status"))],
            [InlineKeyboardButton(text="My Availability", callback_data=callback_for("availability"))],
            [InlineKeyboardButton(text="Team Availability", callback_data=callback_for("availability:team"))],
            [InlineKeyboardButton(text="Notification Digest Mode", callback_data=callback_for("notification_digest"))],
            [InlineKeyboardButton(text="View Audit Logs", callback_data=callback_for("audit_logs"))],
            [InlineKeyboardButton(text="Notification Targets", callback_data=callback_for("notification_targets"))],
            [
                InlineKeyboardButton(text="Back", callback_data=callback_for("menu")),
                InlineKeyboardButton(text="Main Menu", callback_data=callback_for("menu")),
            ],
        ]
    )


def notification_targets_menu(target_buttons: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=label, callback_data=callback)] for label, callback in target_buttons]
    rows.append([InlineKeyboardButton(text="Add Target", callback_data=callback_for("notification_targets:add"))])
    rows.append([InlineKeyboardButton(text="Add Current Chat As Target", callback_data=callback_for("notification_targets:add_current"))])
    rows.extend(page_controls(back_to="settings"))
    return InlineKeyboardMarkup(inline_keyboard=rows)


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
            [InlineKeyboardButton(text="Owner", callback_data=f"nav:notification_target:{target_id}:purpose:owner")],
            [InlineKeyboardButton(text="Operations", callback_data=f"nav:notification_target:{target_id}:purpose:operations")],
            [InlineKeyboardButton(text="Incidents", callback_data=f"nav:notification_target:{target_id}:purpose:incidents")],
            [
                InlineKeyboardButton(
                    text="Automation Logs",
                    callback_data=f"nav:notification_target:{target_id}:purpose:automation_logs",
                )
            ],
            [InlineKeyboardButton(text="Testing", callback_data=f"nav:notification_target:{target_id}:purpose:testing")],
            *page_controls(back_to=f"notification_target:{target_id}"),
        ]
    )


def bot_status_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Refresh", callback_data=callback_for("bot_status"))],
            *page_controls(back_to="settings"),
        ]
    )


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
