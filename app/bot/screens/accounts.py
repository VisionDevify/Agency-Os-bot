from .formatting import *

def render_accounts_home() -> Screen:
    return Screen(
        text="Accounts\n\nCreate a model first, then attach Instagram, X, OnlyFans, Email, or Other accounts.",
        reply_markup=accounts_menu(),
    )

def render_account_list_page(
    session: Session,
    *,
    accounts: list[Account] | None = None,
    title: str = "Accounts",
    back_to: str = "accounts",
) -> Screen:
    current_accounts = accounts if accounts is not None else list_accounts(session)
    lines = [title, ""]
    buttons: list[tuple[str, str]] = []
    if not current_accounts:
        if back_to.startswith("model:") or title.startswith("Accounts for "):
            lines.append("No accounts yet. Add an account to this model from Setup Fortuna or Accounts -> Add Account.")
        else:
            lines.append("No accounts yet. Create a model first, then attach IG/X/OF/Email accounts.")
    for account in current_accounts[:15]:
        health = account_health(account)
        model_name = account.model_brand.display_name if account.model_brand else "Unassigned"
        lines.append(f"{account.id}. {platform_label(account.platform)} @{account.username}")
        lines.append(f"   Model: {model_name} | Status: {account.status}")
        lines.append(f"   Auth: {account.auth_status} | Health: {health.label} {health.score}/100")
        buttons.append(_account_button(account))
    return Screen(text="\n".join(lines), reply_markup=account_list_menu(buttons, back_to=back_to))

def render_account_model_choice_page(session: Session) -> Screen:
    models = list_model_brands(session)
    lines = ["Choose Model/Brand", ""]
    buttons: list[tuple[str, str]] = []
    if not models:
        lines.append("No models yet. Start by creating your first model/brand.")
        buttons.append(("Create First Model", "nav:setup:wizard:model"))
    for model_brand in models:
        buttons.append((model_brand.display_name, f"nav:accounts:add:model:{model_brand.id}"))
    return Screen(text="\n".join(lines), reply_markup=account_model_choice_menu(buttons))

def render_account_platform_choice_page(session: Session, model_id: int) -> Screen:
    model_brand = session.get(ModelBrand, model_id)
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="accounts:add"))
    return Screen(
        text=f"Choose Platform\n\nModel: {model_brand.display_name}",
        reply_markup=account_platform_menu(model_brand.id),
    )

def render_account_input_page(session: Session, model_id: int, platform: str) -> Screen:
    model_brand = session.get(ModelBrand, model_id)
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="accounts:add"))
    return Screen(
        text="\n".join(
            [
                "Add Account",
                "",
                f"Model: {model_brand.display_name}",
                f"Platform: {platform_label(platform)}",
                "",
                "Send username or username | display name.",
            ]
        ),
        reply_markup=page_menu(back_to=f"accounts:add:model:{model_id}"),
    )

def render_accounts_by_model_page(session: Session) -> Screen:
    models = list_model_brands(session)
    lines = ["Accounts by Model", ""]
    buttons: list[tuple[str, str]] = []
    if not models:
        lines.append("No models yet. Start by creating your first model/brand.")
        buttons.append(("Create First Model", "nav:setup:wizard:model"))
    for model_brand in models:
        count = len(accounts_for_model(session, model_brand.id))
        lines.append(f"{model_brand.display_name}: {count}")
        buttons.append((f"{model_brand.display_name} ({count})", f"nav:accounts:model:{model_brand.id}"))
    return Screen(text="\n".join(lines), reply_markup=account_list_menu(buttons, back_to="accounts"))

def render_accounts_by_platform_page() -> Screen:
    return Screen(text="Accounts by Platform", reply_markup=platform_filter_menu())

def render_account_detail_page(session: Session, account_id: int) -> Screen:
    account = session.scalar(
        select(Account)
        .where(Account.id == account_id)
        .options(
            selectinload(Account.model_brand),
            selectinload(Account.auth_sessions),
            selectinload(Account.assigned_proxy),
        )
    )
    if account is None:
        return Screen(text="Account not found.", reply_markup=page_menu(back_to="accounts:list"))
    model_name = account.model_brand.display_name if account.model_brand else "Unassigned"
    health = account_health(account)
    last_checked = format_user_datetime(None, account.last_checked_at) if account.last_checked_at else "Not checked yet"
    proxy_assignment = "Not assigned"
    if account.assigned_proxy:
        if is_archived_proxy(account.assigned_proxy) or is_placeholder_proxy(account.assigned_proxy):
            proxy_assignment = "Hidden archived proxy"
        else:
            proxy_assignment = f"{account.assigned_proxy.provider} ({mask_session_suffix(account.assigned_proxy.session_suffix)})"
    lines = [
        "Account Detail",
        "",
        f"Platform: {platform_label(account.platform)}",
        f"Username: @{account.username}",
        f"Display Name: {account.display_name}",
        f"Model/Brand: {model_name}",
        f"Status: {account.status}",
        f"Auth Status: {account.auth_status}",
        f"Health: {health.label} {health.score}/100",
        f"Proxy Assignment: {proxy_assignment}",
        f"Last Checked: {last_checked}",
        f"Notes: {account.notes or 'None'}",
    ]
    if account.assigned_proxy is None:
        proxy_count = len(list_proxies(session, include_disabled=False))
        lines.extend(
            [
                "",
                "This account needs a proxy.",
                "Best next action: Assign a healthy proxy.",
            ]
        )
        if proxy_count:
            lines.append("Fortuna can help you choose one from the saved proxies.")
        else:
            lines.append("Add your first proxy, then come back here to assign it.")
    return Screen(text="\n".join(lines), reply_markup=account_detail_menu(account.id))

def render_account_proxy_assignment_page(session: Session, account_id: int) -> Screen:
    account = session.get(Account, account_id)
    if account is None:
        return Screen(text="Account not found.", reply_markup=page_menu(back_to="accounts:list"))
    proxies = list_proxies(session, include_disabled=False)
    buttons = [
        (
            f"{proxy.provider} {mask_session_suffix(proxy.session_suffix)}",
            f"nav:account:{account.id}:proxy:assign:{proxy.id}",
        )
        for proxy in proxies
    ]
    lines = [
        "Assign Proxy",
        "",
        f"Account: @{account.username}",
        "",
        "This account needs a proxy.",
        "Choose a healthy saved proxy, or add one first if the list is empty.",
        "",
    ]
    if not buttons:
        lines.extend(["No active proxies available.", "Add your first proxy from Proxy Vault -> Add Olympix Proxy."])
    return Screen(text="\n".join(lines), reply_markup=account_proxy_choice_menu(account.id, buttons))

def render_account_auth_prompt_page(session: Session, account_id: int) -> Screen:
    account = session.get(Account, account_id)
    if account is None:
        return Screen(text="Account not found.", reply_markup=page_menu(back_to="accounts:list"))
    auth_session = latest_waiting_auth_session(session, account.id)
    if auth_session is None:
        return Screen(
            text="Enter 2FA Code\n\nNo waiting auth session. Start Login/Auth Session first.",
            reply_markup=page_menu(back_to=f"account:{account.id}"),
        )
    return Screen(
        text="\n".join(
            [
                "Enter 2FA Code",
                "",
                f"Account: {platform_label(account.platform)} @{account.username}",
                "Send the verification code in the next message.",
                "The bot will store only a hash and will try to delete your code message.",
            ]
        ),
        reply_markup=page_menu(back_to=f"account:{account.id}"),
    )

def render_account_audit_page(session: Session, account_id: int) -> Screen:
    account = session.get(Account, account_id)
    if account is None:
        return Screen(text="Account not found.", reply_markup=page_menu(back_to="accounts:list"))
    logs = account_audit_logs(session, account)
    lines = ["Account Audit History", "", f"Account: {platform_label(account.platform)} @{account.username}", ""]
    if not logs:
        lines.append("No account audit events yet.")
    for log in logs:
        timestamp = format_user_datetime(None, log.created_at) if log.created_at else "pending timestamp"
        lines.append(f"{timestamp}")
        lines.append(f"Action: {log.action} | Status: {log.status}")
        lines.append("")
    return Screen(text="\n".join(lines).strip(), reply_markup=page_menu(back_to=f"account:{account.id}"))

