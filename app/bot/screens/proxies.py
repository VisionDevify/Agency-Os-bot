from app.models.proxy import ProxyRotationHistory

from .formatting import *
from .accounts import render_account_list_page
from app.services.live_safety import live_data_safety_status

PROXY_REALITY_NOTE = "Verification Mode: simulated by default. Real provider checks must be owner-enabled per proxy."


def _yes_no(value: bool) -> str:
    return "enabled" if value else "disabled"


def _result_location(result) -> str:
    return ", ".join(
        item for item in [result.detected_city, result.detected_state, result.detected_country] if item
    ) or "Unknown"


def _is_hidden_proxy(proxy: Proxy) -> bool:
    return is_archived_proxy(proxy) or is_placeholder_proxy(proxy)


def _proxy_summary_name(proxy: Proxy) -> str:
    proxy_type = (proxy.metadata_json or {}).get("proxy_type") or "Mobile"
    if "olympix" in (proxy.provider or "").casefold():
        return "Olympix Mobile"
    return f"{proxy.provider} {proxy_type}".strip()


def render_proxies_home(session: Session | None = None) -> Screen:
    if session is not None:
        proxies = list_proxies(session)
        real_enabled = 0
        for proxy in proxies:
            if proxy_check_mode(proxy).real_health_enabled:
                real_enabled += 1
        missing_proxy = len(accounts_missing_proxy(session))
        total = len(proxies)
    else:
        proxies = []
        total = missing_proxy = real_enabled = 0
    return Screen(
        text="\n".join(
            (
                [
                    "\U0001f6e1 Proxy Vault",
                    "",
                    "No real proxies saved yet.",
                    "",
                    "Next:",
                    "Paste your Olympix proxy string.",
                    "",
                    "What to paste:",
                    "host:port:username:password",
                    "",
                    "Fortuna encrypts the password and never shows it back.",
                ]
                if total == 0
                else [
                    "\U0001f6e1 Proxy Vault",
                    "",
                    f"{total} real {'proxy' if total == 1 else 'proxies'} saved.",
                    "",
                    "Next:",
                    "Assign it to an account." if total == 1 else "Choose one to manage or add another.",
                    "",
                    "Proxy:",
                    f"{_proxy_summary_name(proxies[0])}",
                    f"Status: {'Not tested' if proxies[0].last_health_check is None else proxies[0].status.replace('_', ' ').title()}",
                    f"Session: {mask_session_suffix(proxies[0].session_suffix)}",
                    f"Accounts: {len(accounts_for_proxy(session, proxies[0])) if session is not None else 0}",
                    "",
                    f"Real Checks: {'On' if real_enabled else 'Off'}",
                    (
                        f"{missing_proxy} account{'s' if missing_proxy != 1 else ''} still need a proxy."
                        if missing_proxy
                        else "Nothing urgent here."
                    ),
                ]
            )
        ),
        reply_markup=proxies_menu(),
    )


def render_proxy_rotation_help_page() -> Screen:
    return Screen(
        text="\n".join(
            [
                "How Rotation Works",
                "",
                "Olympix gives a fresh session when Fortuna changes the session suffix.",
                "",
                "Current idea:",
                "session_abcd1234 -> session_new5678",
                "",
                "Fortuna saves the old session first, so rollback is available after a rotation.",
            ]
        ),
        reply_markup=page_menu(back_to="proxies"),
    )


def render_proxy_advanced_page() -> Screen:
    return Screen(
        text="\n".join(
            [
                "Proxy Vault Advanced",
                "",
                "Diagnostics and infrastructure views live here.",
                "Real provider checks stay off until an owner enables them.",
                "",
                "Placeholder cleanup is safe: assigned proxies are archived, unassigned empty placeholders are removed.",
            ]
        ),
        reply_markup=proxies_advanced_menu(),
    )


def render_proxy_add_page() -> Screen:
    return Screen(
        text="\n".join(
            [
                "Add Proxy",
                "",
                "Fortuna can save your Olympix SOCKS5 proxy in one paste.",
                "",
                "Best path:",
                "Paste the full proxy string once.",
                "",
                "Format:",
                "host:port:username:password",
                "",
                "Password is encrypted and never shown again.",
            ]
        ),
        reply_markup=proxy_add_menu(),
    )


def render_olympix_proxy_paste_page(session: Session | None = None) -> Screen:
    safety = live_data_safety_status(session) if session is not None else None
    safety_lines: list[str] = []
    if safety is not None:
        safety_lines = [
            "Before you paste real proxy credentials, Fortuna checked:",
            *[f"{'[ok]' if check.passed else '[fix]'} {check.label}" for check in safety.checks],
            "",
        ]
        if not safety.safe:
            return Screen(
                text="\n".join(
                    [
                        "Paste Olympix Proxy",
                        "",
                        *safety_lines,
                        "Real credential entry is blocked until these checks pass.",
                        "",
                        "Next best move:",
                        "Open Production Observability, then /integrity and /botstatus.",
                    ]
                ),
                reply_markup=page_menu(back_to="proxies:add"),
            )
    return Screen(
        text="\n".join(
            [
                "Paste Olympix Proxy",
                "",
                *safety_lines,
                "Send one message in this format:",
                "host:port:username:password",
                "",
                "Example structure:",
                "host.olympix.io:1080:user_xxxxxx,type_mobile,session_yyyyyyyy:password",
                "",
                "Fortuna will extract:",
                "- Host",
                "- Port",
                "- Base username",
                "- Session suffix",
                "- Password",
                "",
                "The password is encrypted immediately and never shown again.",
            ]
        ),
        reply_markup=page_menu(back_to="proxies:add"),
    )


def render_proxy_list_page(session: Session) -> Screen:
    proxies = list_proxies(session)
    lines = ["\U0001f6e1 Proxy Vault", ""]
    buttons: list[tuple[str, str]] = []
    if not proxies:
        lines.extend(
            [
                "No real proxies saved yet.",
                "",
                "Next:",
                "Paste your Olympix proxy string.",
                "",
                "What to paste:",
                "host:port:username:password",
            ]
        )
        return Screen(text="\n".join(lines), reply_markup=proxies_menu())
    lines.append(f"{len(proxies)} real {'proxy' if len(proxies) == 1 else 'proxies'} saved.")
    lines.extend(["", "Next:", "Assign a proxy to an account.", ""])
    for index, proxy in enumerate(proxies[:10], start=1):
        assigned_count = len(accounts_for_proxy(session, proxy))
        last_status = "Not tested" if proxy.last_health_check is None else proxy.status.replace("_", " ").title()
        lines.extend(
            [
                f"{index}. {_proxy_summary_name(proxy)}",
                f"Status: {last_status}",
                f"Session: {mask_session_suffix(proxy.session_suffix)}",
                f"Accounts: {assigned_count}",
                "",
            ]
        )
        buttons.append(_proxy_button(proxy))
    if len(proxies) == 1:
        proxy = proxies[0]
        return Screen(
            text="\n".join(lines).strip(),
            reply_markup=choice_menu(
                [
                    ("Assign Proxy", f"nav:proxy:{proxy.id}:assign"),
                    ("Rotate Proxy", f"nav:proxy:{proxy.id}:rotate_preview"),
                    ("View Details", f"nav:proxy:{proxy.id}"),
                    ("Add Another", "nav:proxies:olympix:paste"),
                    ("Manage", f"nav:proxy:{proxy.id}:manage"),
                ],
                back_to="proxies",
            ),
        )
    return Screen(text="\n".join(lines), reply_markup=proxy_list_menu(buttons))

def render_olympix_proxy_wizard_page() -> Screen:
    lines = [
        "Olympix Mobile SOCKS5 Wizard",
        "",
        "Recommended:",
        "Use Paste Full Proxy String if you already have host:port:username:password.",
        "",
        "Step 1: Host",
        "Default: host.olympix.io",
        "",
        "Step 2: Port",
        "Default: 1080",
        "",
        "Step 3: Base username",
        "Paste the part before ,session_",
        "",
        "Step 4: Session suffix",
        "Example: bf534e5c",
        "",
        "Step 5: Password",
        "Password is encrypted and never shown again.",
        "The password is never shown after save.",
        "",
        "Step 6: Target location",
        "Country / State / City",
        "",
        "Step 7: Review masked summary",
        "Fortuna will show only safe proxy details before save.",
        "",
        "Step 8: Save",
        "",
        "Send the setup values like this:",
        "base username | password | target country | target state | target city",
        "",
        "Target city is optional. Only enter credentials here in the bot.",
    ]
    return Screen("\n".join(lines), proxy_add_menu())

def render_proxy_entry_check_page(session: Session) -> Screen:
    status = proxy_entry_status(session)
    lines = [
        "Proxy Setup Check",
        "",
        f"Saved Proxies: {status.total_proxies}",
        f"Encrypted Ready Proxies: {status.real_proxies}",
        f"Accounts Missing Proxy: {status.accounts_missing_proxy}",
        "",
        status.guidance,
        "",
        "Secrets stay hidden. Passwords are stored encrypted and are never displayed back in Telegram.",
    ]
    return Screen("\n".join(lines), proxy_entry_check_menu(status.needs_setup))


def render_proxy_real_check_pilot_page(session: Session) -> Screen:
    proxies = list_proxies(session)
    lines = [
        "Real Check Pilot",
        "",
        "Pilot goal: test one saved proxy safely before any broader monitoring rollout.",
        "Global real checks stay disabled by default. Owner must enable real checks per proxy.",
        "",
        f"Saved Proxies: {len(proxies)}",
    ]
    buttons: list[tuple[str, str]] = []
    if not proxies:
        lines.extend(
            [
                "",
                "No proxy is saved yet.",
                "Use the Olympix wizard and enter credentials only through the secure bot UI.",
            ]
        )
    for proxy in proxies[:10]:
        mode = proxy_check_mode(proxy)
        result = latest_proxy_health_check_results(session, proxy, limit=1)
        latest = result[0] if result else None
        latest_line = "no check yet"
        if latest is not None:
            latest_time = format_user_datetime(None, latest.created_at) if latest.created_at else "unknown time"
            latest_line = f"{latest.check_type} {latest.status} at {latest_time}"
        lines.extend(
            [
                "",
                f"Proxy {proxy.id}: {proxy.provider}",
                f"   Real Health Checks: {_yes_no(mode.real_health_enabled)}",
                f"   Real Location Checks: {_yes_no(mode.real_location_enabled)}",
                f"   Last Check: {latest_line}",
                f"   Target: {proxy.target_state or proxy.target_country or 'not set'}",
                "   Password: encrypted and hidden",
            ]
        )
        buttons.append((f"Open Proxy {proxy.id}", f"nav:proxy:{proxy.id}"))
    lines.extend(
        [
            "",
            "Pilot Steps:",
            "1. Choose a test proxy.",
            "2. Confirm credentials are already saved.",
            "3. Enable real checks for that proxy only.",
            "4. Run a real connectivity check.",
            "5. Review the saved result and learning/recommendations.",
        ]
    )
    return Screen(text="\n".join(lines), reply_markup=proxy_real_check_pilot_menu(buttons))


def render_proxy_detail_page(session: Session, proxy_id: int) -> Screen:
    proxy = session.scalar(
        select(Proxy)
        .where(Proxy.id == proxy_id)
        .options(selectinload(Proxy.accounts).selectinload(Account.model_brand))
    )
    if proxy is None or _is_hidden_proxy(proxy):
        return Screen(text="Proxy not found.", reply_markup=page_menu(back_to="proxies:list"))
    mode = proxy_check_mode(proxy)
    recent_results = latest_proxy_health_check_results(session, proxy, limit=5)
    last_result = recent_results[0] if recent_results else None
    assigned_accounts = accounts_for_proxy(session, proxy)
    target_location = ", ".join(
        item for item in [proxy.target_city, proxy.target_state, proxy.target_country] if item
    ) or "Not set"
    detected_location = ", ".join(
        item for item in [proxy.detected_city, proxy.detected_state, proxy.detected_country] if item
    ) or "Not checked yet"
    status_label = "\U0001f7e1 Not Tested" if last_result is None else f"{_status_marker(proxy.status)} {proxy.status.replace('_', ' ').title()}"
    last_check_label = "Never"
    target_match = "Unknown"
    if last_result is not None:
        last_check_label = f"{last_result.status.title()} ({last_result.check_type})"
        target_match = "Yes" if last_result.target_match else "No" if last_result.target_match is False else "Unknown"
    lines = [
        "Proxy Details",
        "",
        f"Provider: {_proxy_summary_name(proxy)}",
        f"Status: {status_label}",
        f"Real Check: {'On' if mode.real_health_enabled else 'Off'}",
        f"Assigned Accounts: {len(assigned_accounts)}",
        "",
        "Connection:",
        f"Host: {proxy.host}",
        f"Port: {proxy.port}",
        f"User: {mask_proxy_username(proxy.base_username)}",
        f"Session: {mask_session_suffix(proxy.session_suffix)}",
        "Password: Encrypted",
        "",
        "Location:",
        f"Target: {target_location}",
        f"Detected: {detected_location}",
        "",
        "Last Check:",
        last_check_label,
        f"Target Match: {target_match}",
        "",
        "Next best move:",
        "Assign this proxy to an account or run a test.",
    ]
    if last_result is not None and last_result.error_message:
        lines.extend(["", f"Note: {last_result.error_message}"])
    return Screen(text="\n".join(lines), reply_markup=proxy_detail_menu(proxy.id))


def render_proxy_manage_page(session: Session, proxy_id: int) -> Screen:
    proxy = session.get(Proxy, proxy_id)
    if proxy is None or _is_hidden_proxy(proxy):
        return Screen(text="Proxy not found.", reply_markup=page_menu(back_to="proxies:list"))
    assigned_count = len(accounts_for_proxy(session, proxy))
    return Screen(
        text="\n".join(
            [
                "Manage Proxy",
                "",
                "Choose what you want to do.",
                "",
                f"Proxy: {_proxy_summary_name(proxy)}",
                f"Session: {mask_session_suffix(proxy.session_suffix)}",
                f"Accounts: {assigned_count}",
                "",
                "Fortuna will explain risky actions before confirming.",
            ]
        ),
        reply_markup=proxy_manage_menu(proxy.id),
    )


def render_proxy_import_success_page(session: Session, proxy_id: int) -> Screen:
    proxy = session.get(Proxy, proxy_id)
    if proxy is None:
        return Screen(text="Proxy not found.", reply_markup=page_menu(back_to="proxies"))
    lines = [
        "Proxy saved \u2705",
        "",
        f"Provider: {proxy.provider}",
        f"Type: {(proxy.metadata_json or {}).get('proxy_type', 'SOCKS5 Mobile')}",
        f"Host: {proxy.host}",
        f"Port: {proxy.port}",
        f"User: {mask_proxy_username(proxy.base_username)}",
        f"Session: {mask_session_suffix(proxy.session_suffix)}",
        "Password: Encrypted",
        "",
        "Next:",
        "Assign this proxy to an account.",
    ]
    return Screen("\n".join(lines), proxy_import_success_menu(proxy.id))


def render_proxy_rotation_preview_page(session: Session, proxy_id: int) -> Screen:
    proxy = session.get(Proxy, proxy_id)
    if proxy is None or _is_hidden_proxy(proxy):
        return Screen(text="Proxy not found.", reply_markup=page_menu(back_to="proxies:list"))
    return Screen(
        text="\n".join(
            [
                "\U0001f504 Rotate Proxy",
                "",
                "This changes the session suffix so Olympix gives a fresh session/IP.",
                "",
                "Current session:",
                mask_session_suffix(proxy.session_suffix),
                "",
                "Fortuna will not show or log the proxy password.",
            ]
        ),
        reply_markup=proxy_rotation_preview_menu(proxy.id),
    )


def render_proxy_rotation_result_page(session: Session, proxy_id: int, history_id: int | None = None) -> Screen:
    proxy = session.get(Proxy, proxy_id)
    history = session.get(ProxyRotationHistory, history_id) if history_id else None
    if proxy is None:
        return Screen(text="Proxy not found.", reply_markup=page_menu(back_to="proxies:list"))
    old_session = history.previous_session_suffix if history else proxy.previous_session_suffix
    new_session = history.new_session_suffix if history else proxy.session_suffix
    lines = [
        "Session rotated \u2705",
        "",
        f"Old session: {mask_session_suffix(old_session)}",
        f"New session: {mask_session_suffix(new_session)}",
        "",
        "Next best move:",
        "Run a test, then assign or keep using this proxy.",
    ]
    return Screen("\n".join(lines), proxy_result_menu(proxy.id, include_rollback=True))


def render_proxy_rollback_result_page(session: Session, proxy_id: int, history_id: int | None = None) -> Screen:
    proxy = session.get(Proxy, proxy_id)
    history = session.get(ProxyRotationHistory, history_id) if history_id else None
    if proxy is None:
        return Screen(text="Proxy not found.", reply_markup=page_menu(back_to="proxies:list"))
    lines = [
        "Rollback complete \u2705",
        "",
        f"Restored session: {mask_session_suffix(history.new_session_suffix if history else proxy.session_suffix)}",
        "",
        "Fortuna restored the previous session suffix.",
    ]
    return Screen("\n".join(lines), proxy_result_menu(proxy.id))


def render_proxy_no_rollback_page(session: Session, proxy_id: int) -> Screen:
    return Screen(
        "No previous session saved yet.\n\nRotate this proxy once before rollback is available.",
        page_menu(back_to=f"proxy:{proxy_id}:manage"),
    )


def render_proxy_check_result_page(session: Session, proxy_id: int) -> Screen:
    proxy = session.get(Proxy, proxy_id)
    if proxy is None:
        return Screen(text="Proxy not found.", reply_markup=page_menu(back_to="proxies:list"))
    results = latest_proxy_health_check_results(session, proxy, limit=1)
    result = results[0] if results else None
    lines = [
        "Proxy Test Result",
        "",
        "Password: Encrypted",
    ]
    if result is None:
        lines.append("No result was recorded.")
    else:
        lines.extend(
            [
                f"Mode: {result.check_type.title()}",
                f"Status: {result.status.title()}",
                f"Latency: {result.latency_ms if result.latency_ms is not None else 'Unknown'} ms",
                f"Detected: {_result_location(result)}",
                f"Target Match: {'Yes' if result.target_match else 'No' if result.target_match is False else 'Unknown'}",
            ]
        )
        if result.error_message:
            lines.append(f"Note: {result.error_message}")
    return Screen("\n".join(lines), proxy_result_menu(proxy.id))


def render_proxy_location_page(session: Session, proxy_id: int) -> Screen:
    proxy = session.get(Proxy, proxy_id)
    if proxy is None:
        return Screen(text="Proxy not found.", reply_markup=page_menu(back_to="proxies:list"))
    current = ", ".join(item for item in [proxy.target_city, proxy.target_state, proxy.target_country] if item) or "Not set"
    return Screen(
        "\n".join(
            [
                "Set Target Location",
                "",
                f"Current target: {current}",
                "",
                "Send location like this:",
                "Country | State | City",
                "",
                "City is optional.",
            ]
        ),
        page_menu(back_to=f"proxy:{proxy.id}"),
    )


def render_proxy_detail_advanced_page(session: Session, proxy_id: int) -> Screen:
    proxy = session.get(Proxy, proxy_id)
    if proxy is None or _is_hidden_proxy(proxy):
        return Screen(text="Proxy not found.", reply_markup=page_menu(back_to="proxies:list"))
    mode = proxy_check_mode(proxy)
    lines = [
        "Proxy Advanced Tools",
        "",
        f"Real Checks: {'On' if mode.real_health_enabled else 'Off'}",
        f"Location Checks: {'On' if mode.real_location_enabled else 'Off'}",
        f"Previous Session: {mask_session_suffix(proxy.previous_session_suffix)}",
        "",
        "High-risk actions stay owner-controlled.",
    ]
    return Screen("\n".join(lines), proxy_detail_advanced_menu(proxy.id, real_enabled=mode.real_health_enabled))

def render_proxy_assigned_accounts_page(session: Session, proxy_id: int) -> Screen:
    proxy = session.get(Proxy, proxy_id)
    if proxy is None:
        return Screen(text="Proxy not found.", reply_markup=page_menu(back_to="proxies:list"))
    accounts = accounts_for_proxy(session, proxy)
    return render_account_list_page(
        session,
        accounts=accounts,
        title=f"Accounts Using Proxy {proxy.id}",
        back_to=f"proxy:{proxy.id}",
    )

def render_proxy_assign_account_page(session: Session, proxy_id: int) -> Screen:
    proxy = session.get(Proxy, proxy_id)
    if proxy is None or _is_hidden_proxy(proxy):
        return Screen(text="Proxy not found.", reply_markup=page_menu(back_to="proxies:list"))
    buttons = [
        (
            f"{account.id}. @{account.username}",
            f"nav:proxy:{proxy.id}:assign:{account.id}",
        )
        for account in accounts_missing_proxy(session)
    ]
    lines = [
        "Assign Account to Proxy",
        "",
        f"Proxy: {_proxy_summary_name(proxy)}",
        f"Session: {mask_session_suffix(proxy.session_suffix)}",
        "",
        "This will attach the proxy to the selected account and run a safe simulated check.",
        "",
    ]
    if not buttons:
        if list_accounts(session):
            lines.append("No accounts are missing proxies. Nothing to assign right now.")
        else:
            lines.append("No accounts exist yet. Add an account first, then return here to assign this proxy.")
    return Screen(text="\n".join(lines), reply_markup=proxy_account_choice_menu(proxy.id, buttons, "assign"))

def render_proxy_remove_account_page(session: Session, proxy_id: int) -> Screen:
    proxy = session.get(Proxy, proxy_id)
    if proxy is None or _is_hidden_proxy(proxy):
        return Screen(text="Proxy not found.", reply_markup=page_menu(back_to="proxies:list"))
    buttons = [
        (
            f"{account.id}. @{account.username}",
            f"nav:proxy:{proxy.id}:remove:{account.id}",
        )
        for account in accounts_for_proxy(session, proxy)
    ]
    lines = [
        "Remove Account from Proxy",
        "",
        f"Proxy: {_proxy_summary_name(proxy)}",
        "Password: Encrypted",
        "",
        "This will detach the selected account. The proxy itself will stay saved.",
        "",
    ]
    if not buttons:
        lines.append("No accounts are assigned to this proxy.")
    return Screen(text="\n".join(lines), reply_markup=proxy_account_choice_menu(proxy.id, buttons, "remove"))


def render_proxy_archive_confirm_page(session: Session, proxy_id: int) -> Screen:
    proxy = session.get(Proxy, proxy_id)
    if proxy is None or _is_hidden_proxy(proxy):
        return Screen(text="Proxy not found.", reply_markup=page_menu(back_to="proxies:list"))
    return Screen(
        "\n".join(
            [
                "Archive Proxy",
                "",
                f"Proxy: {_proxy_summary_name(proxy)}",
                f"Session: {mask_session_suffix(proxy.session_suffix)}",
                "",
                "Archive hides this proxy from Proxy Vault and prevents future assignment, rotation, and checks.",
                "History stays available for audit.",
            ]
        ),
        proxy_archive_confirm_menu(proxy.id),
    )


def render_proxy_delete_confirm_page(session: Session, proxy_id: int) -> Screen:
    proxy = session.get(Proxy, proxy_id)
    if proxy is None or _is_hidden_proxy(proxy):
        return Screen(text="Proxy not found.", reply_markup=page_menu(back_to="proxies:list"))
    assigned = accounts_for_proxy(session, proxy)
    can_delete = not assigned
    lines = [
        "Delete Proxy",
        "",
        f"Proxy: {_proxy_summary_name(proxy)}",
        f"Session: {mask_session_suffix(proxy.session_suffix)}",
        "",
    ]
    if can_delete:
        lines.extend(
            [
                "Delete is permanent.",
                "Only use this for a proxy you no longer need.",
            ]
        )
    else:
        lines.extend(
            [
                f"This proxy is assigned to {len(assigned)} active account(s).",
                "Remove it from accounts first, or archive it instead.",
            ]
        )
    return Screen("\n".join(lines), proxy_delete_confirm_menu(proxy.id, can_delete=can_delete))


def render_proxy_archive_result_page() -> Screen:
    return Screen("Proxy archived.\n\nIt is hidden from the normal Proxy Vault now.", page_menu(back_to="proxies"))


def render_proxy_delete_result_page() -> Screen:
    return Screen("Proxy deleted.\n\nIt will no longer appear in Proxy Vault.", page_menu(back_to="proxies"))


def render_proxy_cleanup_result_page(session: Session) -> Screen:
    remaining = len(list_placeholder_proxies(session, include_archived=False))
    return Screen(
        "\n".join(
            [
                "Placeholder Cleanup",
                "",
                f"Placeholder proxies still visible to cleanup: {remaining}",
                "",
                "Normal Proxy Vault only shows real, non-archived proxies.",
            ]
        ),
        page_menu(back_to="proxies"),
    )

def render_accounts_missing_proxy_page(session: Session) -> Screen:
    missing = accounts_missing_proxy(session)
    if missing:
        return render_account_list_page(
            session,
            accounts=missing,
            title="Accounts Missing Proxy",
            back_to="proxies",
        )
    if list_accounts(session):
        return Screen(
            "Accounts Missing Proxy\n\nNothing urgent here. Every active account already has a proxy assigned.",
            page_menu(back_to="proxies"),
        )
    return Screen(
        "Accounts Missing Proxy\n\nNo accounts exist yet. Create a model and account first, then assign a proxy.",
        choice_menu([("Add Account", "nav:accounts:add"), ("Create First Model", "nav:setup:wizard:model")], back_to="proxies"),
    )

def render_proxy_simulation_page(session: Session) -> Screen:
    summary = simulation_mode_summary(session)
    lines = [
        "Simulation Mode",
        "",
        "Yesterday:",
        f"Would Rotate: {summary.would_rotate} Proxies",
        f"Would Repair: {summary.would_repair} Proxies",
        f"Would Fail: {summary.would_fail} Proxies",
        "",
        "No changes applied.",
        PROXY_REALITY_NOTE,
        "Owner approval is required before automatic repair activation.",
    ]
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="proxies"))

def render_infrastructure_dashboard_page(session: Session) -> Screen:
    stats = infrastructure_stats(session)
    issues = stats.warning_proxies + stats.critical_proxies + stats.accounts_missing_proxy
    if stats.critical_proxies:
        status = "Needs Attention"
        next_action = "Review critical proxies first."
    elif stats.accounts_missing_proxy:
        status = "Needs Setup"
        next_action = "Assign proxies to accounts missing one."
    elif stats.warning_proxies:
        status = "Watch"
        next_action = "Review warning proxies when convenient."
    else:
        status = "Healthy"
        next_action = "No action needed."
    lines = [
        "Infrastructure Dashboard",
        "",
        f"Status: {status}",
        f"Issues Found: {issues}",
        "",
        "Recommended Action:",
        next_action,
        "",
        "Technical Details:",
        f"Total Proxies: {stats.total_proxies}",
        f"Healthy: {stats.healthy_proxies}",
        f"Warning: {stats.warning_proxies}",
        f"Critical: {stats.critical_proxies}",
        f"Disabled: {stats.disabled_proxies}",
        f"Accounts Assigned: {stats.accounts_assigned_proxy}",
        f"Accounts Missing Proxy: {stats.accounts_missing_proxy}",
        f"Average Health Score: {stats.average_health_score}",
        PROXY_REALITY_NOTE,
        "",
        "Recent Rotations:",
    ]
    lines.extend(f"- {item}" for item in stats.recent_rotations[:5])
    if not stats.recent_rotations:
        lines.append("- No rotations yet")
    lines.extend(["", "Recent Failures:"])
    lines.extend(f"- {item}" for item in stats.recent_failures[:5])
    if not stats.recent_failures:
        lines.append("- No failures yet")
    lines.extend(["", "Recent Incidents:"])
    lines.extend(f"- {item}" for item in stats.recent_incidents[:5])
    if not stats.recent_incidents:
        lines.append("- No proxy incidents yet")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="proxies"))

def render_proxy_audit_page(session: Session, proxy_id: int) -> Screen:
    proxy = session.get(Proxy, proxy_id)
    if proxy is None:
        return Screen(text="Proxy not found.", reply_markup=page_menu(back_to="proxies:list"))
    logs = recent_proxy_audit_logs(session, proxy)
    lines = ["Proxy Audit History", "", f"Proxy: {proxy.provider} {proxy.host}:{proxy.port}", ""]
    if not logs:
        lines.append("No proxy audit events yet.")
    for log in logs:
        timestamp = format_user_datetime(None, log.created_at) if log.created_at else "pending timestamp"
        lines.append(f"{timestamp}")
        lines.append(f"Action: {log.action} | Status: {log.status}")
        lines.append("")
    return Screen(text="\n".join(lines).strip(), reply_markup=page_menu(back_to=f"proxy:{proxy.id}"))


def render_proxy_check_history_page(session: Session, proxy_id: int) -> Screen:
    proxy = session.get(Proxy, proxy_id)
    if proxy is None:
        return Screen(text="Proxy not found.", reply_markup=page_menu(back_to="proxies:list"))
    results = latest_proxy_health_check_results(session, proxy, limit=10)
    lines = [
        "Proxy Check History",
        "",
        f"Proxy: {proxy.provider} {proxy.host}:{proxy.port}",
        "Password: encrypted and hidden",
        "",
    ]
    if not results:
        lines.append("No check history yet. Run a simulated check first, or enable real checks and run a real check.")
    for result in results:
        when = format_user_datetime(None, result.created_at) if result.created_at else "Unknown"
        lines.append(f"{when}")
        lines.append(f"   {result.check_type}: {result.status}")
        lines.append(f"   Latency: {result.latency_ms if result.latency_ms is not None else 'Unknown'} ms")
        lines.append(f"   Location: {_result_location(result)} | Target Match: {result.target_match if result.target_match is not None else 'Unknown'}")
        if result.error_message:
            lines.append(f"   Note: {result.error_message}")
        lines.append("")
    return Screen(text="\n".join(lines).strip(), reply_markup=page_menu(back_to=f"proxy:{proxy.id}"))

