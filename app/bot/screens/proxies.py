from .formatting import *
from .accounts import render_account_list_page

PROXY_REALITY_NOTE = "Verification Mode: simulated by default. Real provider checks must be owner-enabled per proxy."


def _yes_no(value: bool) -> str:
    return "enabled" if value else "disabled"


def _result_location(result) -> str:
    return ", ".join(
        item for item in [result.detected_city, result.detected_state, result.detected_country] if item
    ) or "Unknown"

def render_proxies_home(session: Session | None = None) -> Screen:
    if session is not None:
        proxies = list_proxies(session)
        healthy = 0
        needs_attention = 0
        real_enabled = 0
        for proxy in proxies:
            health = calculate_proxy_health(proxy)
            if proxy.status == "healthy" and health.score >= 80:
                healthy += 1
            else:
                needs_attention += 1
            if proxy_check_mode(proxy).real_health_enabled:
                real_enabled += 1
        missing_proxy = len(accounts_missing_proxy(session))
        total = len(proxies)
    else:
        total = healthy = needs_attention = missing_proxy = real_enabled = 0
    return Screen(
        text="\n".join(
            [
                "\U0001f6e1 Proxy Vault",
                "",
                f"Total Proxies: {total}",
                f"Healthy: {healthy}",
                f"Needs Attention: {needs_attention}",
                f"Missing Accounts: {missing_proxy}",
                f"Real Checks: {'Enabled' if real_enabled else 'Disabled'}",
                "",
                "Fortuna noticed proxy setup matters before accounts go live.",
                "Add a proxy, assign accounts, then test safely.",
                "",
                "Fortuna will never show proxy passwords back in Telegram.",
            ]
        ),
        reply_markup=proxies_menu(),
    )


def render_proxy_advanced_page() -> Screen:
    return Screen(
        text="\n".join(
            [
                "Proxy Vault Advanced",
                "",
                "Diagnostics and infrastructure views live here.",
                "Real provider checks stay off until an owner enables them.",
            ]
        ),
        reply_markup=proxies_advanced_menu(),
    )

def render_proxy_list_page(session: Session) -> Screen:
    proxies = list_proxies(session)
    lines = ["Proxy Vault", ""]
    buttons: list[tuple[str, str]] = []
    if not proxies:
        lines.append("No proxies yet. Add an encrypted proxy with the Olympix wizard or create a placeholder for testing.")
    for proxy in proxies[:15]:
        health = calculate_proxy_health(proxy)
        lines.append(f"{proxy.id}. {proxy.provider} {proxy.host}:{proxy.port}")
        lines.append(f"   Status: {proxy.status} | Health: {health.label} {health.score}/100")
        lines.append(f"   Target: {proxy.target_state or proxy.target_country or 'Not set'}")
        mode = proxy_check_mode(proxy)
        lines.append(f"   Real Checks: {_yes_no(mode.real_health_enabled)} | Location: {_yes_no(mode.real_location_enabled)}")
        lines.append("   Default Mode: simulated unless real checks are owner-enabled")
        buttons.append(_proxy_button(proxy))
    return Screen(text="\n".join(lines), reply_markup=proxy_list_menu(buttons))

def render_olympix_proxy_wizard_page() -> Screen:
    lines = [
        "Olympix Mobile SOCKS5 Wizard",
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
    return Screen("\n".join(lines), page_menu(back_to="proxies"))

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
    if proxy is None:
        return Screen(text="Proxy not found.", reply_markup=page_menu(back_to="proxies:list"))
    health = calculate_proxy_health(proxy)
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
    last_check_label = "Not tested"
    target_match = "Unknown"
    if last_result is not None:
        last_check_label = f"{last_result.status.title()} ({last_result.check_type})"
        target_match = "Yes" if last_result.target_match else "No" if last_result.target_match is False else "Unknown"
    lines = [
        "Proxy Detail",
        "",
        f"Provider: {proxy.provider}",
        "Type: SOCKS5 Mobile",
        f"Status: {_status_marker(proxy.status)} {proxy.status.replace('_', ' ').title()}",
        f"Health: {health.label} {health.score}/100",
        f"Target: {target_location}",
        f"Detected: {detected_location}",
        f"Accounts: {len(assigned_accounts)}",
        f"Real Checks: {_yes_no(mode.real_health_enabled)}",
        f"Real Check: {'On' if mode.real_health_enabled else 'Off'}",
        "Mode: simulated unless real checks are owner-enabled",
        "",
        "Latest Check:",
        f"- Status: {last_check_label}",
        f"- Latency: {last_result.latency_ms if last_result and last_result.latency_ms is not None else 'Not checked'}",
        f"- Detected IP: {last_result.detected_ip_masked if last_result and last_result.detected_ip_masked else 'Not checked'}",
        f"- Target Match: {target_match}",
        f"- Verified: {format_user_datetime(None, last_result.created_at) if last_result and last_result.created_at else 'Not checked yet'}",
        "",
        "Password: encrypted and hidden.",
    ]
    if last_result is None:
        lines.extend(["", "Nothing has been tested yet. Start with Test."])
    elif last_result.error_message:
        lines.extend(["", f"Note: {last_result.error_message}"])
    if health.reasons:
        lines.extend(["", "Health Reasons:"])
        lines.extend(f"- {reason}" for reason in health.reasons)
    return Screen(text="\n".join(lines), reply_markup=proxy_detail_menu(proxy.id))

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
    if proxy is None:
        return Screen(text="Proxy not found.", reply_markup=page_menu(back_to="proxies:list"))
    buttons = [
        (
            f"{account.id}. @{account.username}",
            f"nav:proxy:{proxy.id}:assign:{account.id}",
        )
        for account in accounts_missing_proxy(session)
    ]
    lines = ["Assign Account to Proxy", "", f"Proxy: {proxy.provider} {proxy.host}:{proxy.port}", ""]
    if not buttons:
        lines.append("No accounts are missing proxies.")
    return Screen(text="\n".join(lines), reply_markup=proxy_account_choice_menu(proxy.id, buttons, "assign"))

def render_proxy_remove_account_page(session: Session, proxy_id: int) -> Screen:
    proxy = session.get(Proxy, proxy_id)
    if proxy is None:
        return Screen(text="Proxy not found.", reply_markup=page_menu(back_to="proxies:list"))
    buttons = [
        (
            f"{account.id}. @{account.username}",
            f"nav:proxy:{proxy.id}:remove:{account.id}",
        )
        for account in accounts_for_proxy(session, proxy)
    ]
    lines = ["Remove Account from Proxy", "", f"Proxy: {proxy.provider} {proxy.host}:{proxy.port}", ""]
    if not buttons:
        lines.append("No accounts are assigned to this proxy.")
    return Screen(text="\n".join(lines), reply_markup=proxy_account_choice_menu(proxy.id, buttons, "remove"))

def render_accounts_missing_proxy_page(session: Session) -> Screen:
    return render_account_list_page(
        session,
        accounts=accounts_missing_proxy(session),
        title="Accounts Missing Proxy",
        back_to="proxies",
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
    lines = [
        "Infrastructure Dashboard",
        "",
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

