from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

MENU_ITEMS: tuple[tuple[str, str], ...] = (
    ("Dashboard", "dashboard"),
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
            [InlineKeyboardButton(text="Main Menu", callback_data=callback_for("menu"))],
        ]
    )


def page_menu(back_to: str = "menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=page_controls(back_to=back_to))
