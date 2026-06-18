from .formatting import *
from .accounts import render_account_list_page

PROXY_REALITY_NOTE = "Verification Mode: simulated by default. Real provider checks must be owner-enabled per proxy."


def _yes_no(value: bool) -> str:
    return "enabled" if value else "disabled"


def _result_location(result) -> str:
    return ", ".join(
        item for item in [result.detected_city, result.detected_state, result.detected_country] if item
    ) or "Unknown"

def render_proxies_home() -> Screen:
    return Screen(
        text="\n".join(
            [
                "Proxy Vault",
                "",
                "Manage encrypted proxy records, account assignments, and health checks.",
                "Use the Olympix wizard for Mobile SOCKS5 proxies. Passwords are encrypted and never shown back in Telegram.",
                PROXY_REALITY_NOTE,
            ]
        ),
        reply_markup=proxies_menu(),
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
        "This creates an encrypted proxy record. The password is never shown back in Telegram.",
        "",
        "Fixed provider details:",
        "Host: host.olympix.io",
        "Port: 1080",
        "",
        "Send the setup values in this format:",
        "base username | password | target country | target state | target city",
        "",
        "Example:",
        "customer-user | password | United States | Florida | Miami",
        "",
        "Target city is optional. Do not paste this into any unrelated chat.",
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
    affected_models = affected_models_for_proxy(session, proxy)
    target_location = ", ".join(
        item for item in [proxy.target_city, proxy.target_state, proxy.target_country] if item
    ) or "Not set"
    detected_location = ", ".join(
        item for item in [proxy.detected_city, proxy.detected_state, proxy.detected_country] if item
    ) or "Not checked yet"
    lines = [
        "Proxy Detail",
        "",
        f"Provider: {proxy.provider}",
        f"Host: {proxy.host}:{proxy.port}",
        f"Status: {proxy.status}",
        f"Health: {health.label} {health.score}/100",
        f"Real Checks: {_yes_no(mode.real_health_enabled)}",
        f"Real Location Checks: {_yes_no(mode.real_location_enabled)}",
        "Default Mode: simulated unless real checks are owner-enabled",
        f"Provider Adapter: Olympix Mobile SOCKS5",
        f"Check Timeout: {mode.timeout_seconds}s",
        f"Current Session: {_mask_proxy_value(proxy.session_suffix)}",
        f"Previous Session: {_mask_proxy_value(proxy.previous_session_suffix)}",
        f"Rotation Count: {proxy.rotation_count}",
        f"Generated Username: {_mask_proxy_value(proxy.generated_username)}",
        "Password: encrypted and hidden",
        f"Target Location: {target_location}",
        f"Detected Location: {detected_location}",
        f"Last Health Check: {proxy.last_health_check.isoformat() if proxy.last_health_check else 'Not checked yet'}",
        f"Last Verified: {proxy.last_health_check.isoformat() if proxy.last_health_check else 'Not verified yet'}",
        f"Last Rotation: {proxy.last_rotation.isoformat() if proxy.last_rotation else 'Never'}",
        f"Last Successful Rotation: {proxy.last_successful_rotation.isoformat() if proxy.last_successful_rotation else 'Never'}",
        f"Accounts Using Proxy: {len(assigned_accounts)}",
        f"Accounts Missing Proxy: {len(accounts_missing_proxy(session))}",
        f"Models Affected: {len(affected_models)}",
    ]
    if last_result is None:
        lines.extend(
            [
                "",
                "Latest Check:",
                "- No health check results stored yet.",
            ]
        )
    else:
        lines.extend(
            [
                "",
                "Latest Check:",
                f"- Type: {last_result.check_type}",
                f"- Status: {last_result.status}",
                f"- Latency: {last_result.latency_ms if last_result.latency_ms is not None else 'Unknown'} ms",
                f"- Detected IP: {last_result.detected_ip_masked or 'Unknown'}",
                f"- Detected Location: {_result_location(last_result)}",
                f"- Target Match: {last_result.target_match if last_result.target_match is not None else 'Unknown'}",
                f"- Checked: {last_result.created_at.isoformat() if last_result.created_at else 'Unknown'}",
            ]
        )
        if last_result.error_message:
            lines.append(f"- Note: {last_result.error_message}")
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
        timestamp = log.created_at.isoformat() if log.created_at else "pending timestamp"
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
        when = result.created_at.isoformat() if result.created_at else "Unknown"
        lines.append(f"{when}")
        lines.append(f"   {result.check_type}: {result.status}")
        lines.append(f"   Latency: {result.latency_ms if result.latency_ms is not None else 'Unknown'} ms")
        lines.append(f"   Location: {_result_location(result)} | Target Match: {result.target_match if result.target_match is not None else 'Unknown'}")
        if result.error_message:
            lines.append(f"   Note: {result.error_message}")
        lines.append("")
    return Screen(text="\n".join(lines).strip(), reply_markup=page_menu(back_to=f"proxy:{proxy.id}"))

