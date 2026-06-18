# Telegram Screen Architecture

Sprint 26 split the former monolithic Telegram screen renderer into a package:

`app/bot/screens/`

Domain modules:

- `home.py`
- `models.py`
- `accounts.py`
- `proxies.py`
- `tasks.py`
- `incidents.py`
- `reports.py`
- `intelligence.py`
- `learning.py`
- `automations.py`
- `opportunities.py`
- `activation.py`
- `coo.py`
- `settings.py`
- `team.py`
- `help.py`
- `router.py`
- `formatting.py`

Compatibility remains:

```python
from app.bot.screens import render_main_menu, render_page
```

`formatting.py` contains shared screen data structures, common helpers, menu imports, service imports, and formatting utilities. Domain modules import from it and expose render functions for their area.

`router.py` owns `render_page()` and preserves callback behavior.

Rules:

- Keep user-facing behavior stable when moving renderers.
- Put shared formatting helpers in `formatting.py`.
- Keep domain-specific rendering in the matching module.
- Avoid importing `router.py` from domain modules.
- Add callback rendering tests whenever a new Telegram button is introduced.
