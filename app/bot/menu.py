from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

MENU_ITEMS = [
    "Dashboard",
    "Users",
    "Roles",
    "Accounts",
    "Proxies",
    "Tasks",
    "Incidents",
    "Reports",
    "Automations",
    "Settings",
]


def main_menu() -> ReplyKeyboardMarkup:
    rows = [[KeyboardButton(text=item)] for item in MENU_ITEMS]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)
