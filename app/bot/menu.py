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
