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
    ("Automations", "automations"),
    ("Settings", "settings"),
)


def callback_for(page: str) -> str:
    return f"nav:{page}"


def main_menu() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for index in range(0, len(MENU_ITEMS), 2):
        rows.append(
            [
                InlineKeyboardButton(text=label, callback_data=callback_for(page))
                for label, page in MENU_ITEMS[index : index + 2]
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


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


def page_menu(back_to: str = "menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=page_controls(back_to=back_to))


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
                InlineKeyboardButton(text="Assigned Tasks", callback_data=callback_for("tasks:assigned")),
            ],
            [
                InlineKeyboardButton(text="Overdue Tasks", callback_data=callback_for("tasks:overdue")),
                InlineKeyboardButton(text="Blocked Tasks", callback_data=callback_for("tasks:blocked")),
            ],
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
            [InlineKeyboardButton(text="Reassign Task", callback_data=f"nav:task:{task_id}:assign")],
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
            [InlineKeyboardButton(text="View Incidents", callback_data=callback_for("incidents:list"))],
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
                InlineKeyboardButton(text="Escalate Incident", callback_data=f"nav:incident:{incident_id}:escalate"),
                InlineKeyboardButton(text="Resolve Incident", callback_data=f"nav:incident:{incident_id}:resolve"),
            ],
            [InlineKeyboardButton(text="Archive Incident", callback_data=f"nav:incident:{incident_id}:archive")],
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
            [InlineKeyboardButton(text="Team Accountability", callback_data=callback_for("reports:accountability"))],
            [InlineKeyboardButton(text="Executive Dashboard", callback_data=callback_for("reports:executive"))],
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
                InlineKeyboardButton(text="Generate Daily Briefing", callback_data=callback_for("reports:daily")),
                InlineKeyboardButton(text="Refresh", callback_data=callback_for("reports:daily")),
            ],
            [
                InlineKeyboardButton(text="Send to Owner", callback_data=callback_for("reports:daily:send_owner")),
                InlineKeyboardButton(text="Send to Operations Group", callback_data=callback_for("reports:daily:send_ops")),
            ],
            *page_controls(back_to="reports"),
        ]
    )


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
            [InlineKeyboardButton(text="View Audit Logs", callback_data=callback_for("audit_logs"))],
            [
                InlineKeyboardButton(text="Back", callback_data=callback_for("menu")),
                InlineKeyboardButton(text="Main Menu", callback_data=callback_for("menu")),
            ],
        ]
    )
