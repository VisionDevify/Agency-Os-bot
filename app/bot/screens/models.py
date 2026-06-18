from .formatting import *

def render_models_home() -> Screen:
    return Screen(
        text="Models / Brands\n\nEverything in Fortuna OS starts with a model or brand.",
        reply_markup=models_menu(),
    )

def render_model_list_page(session: Session) -> Screen:
    models = list_model_brands(session)
    lines = ["Models", ""]
    buttons: list[tuple[str, str]] = []
    if not models:
        lines.append("No models yet. Start by creating your first model/brand to unlock accounts, creators, and opportunities.")
    for model_brand in models[:10]:
        accounts = accounts_for_model(session, model_brand.id)
        health = calculate_model_health(
            model_brand,
            disabled_accounts=sum(1 for account in accounts if account.status == "disabled"),
            warning_accounts=sum(
                1
                for account in accounts
                if account.status == "warning" or account.auth_status in {"needs_login", "needs_2fa"}
            ),
        )
        identity = _model_identity(model_brand)
        lines.append(f"{model_brand.id}. {identity}")
        lines.append(f"   Status: {model_brand.status} | Health: {health.label} {health.score}/100")
        buttons.append((f"{model_brand.id}. {model_brand.display_name}", f"nav:model:{model_brand.id}"))
    return Screen(text="\n".join(lines), reply_markup=model_list_menu(buttons))

def render_model_dashboard_page(session: Session) -> Screen:
    models = list_model_brands(session)
    lines = ["Model Dashboard", ""]
    if not models:
        lines.append("No models yet.")
    for model_brand in models[:10]:
        accounts = accounts_for_model(session, model_brand.id)
        health = calculate_model_health(
            model_brand,
            disabled_accounts=sum(1 for account in accounts if account.status == "disabled"),
            warning_accounts=sum(
                1
                for account in accounts
                if account.status == "warning" or account.auth_status in {"needs_login", "needs_2fa"}
            ),
        )
        lines.append(f"{model_brand.display_name}: {health.label} {health.score}/100")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="models"))

def render_model_detail_page(session: Session, model_id: int) -> Screen:
    model_brand = session.scalar(
        select(ModelBrand)
        .where(ModelBrand.id == model_id)
        .options(selectinload(ModelBrand.members).selectinload(ModelBrandMember.user))
    )
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="models:list"))
    members = summarize_members(model_brand)
    managers = members["manager"]
    chatters = members["chatter_manager"] + members["senior_chatter"] + members["chatter"]
    vas = members["va"]
    accounts = accounts_for_model(session, model_brand.id)
    health = calculate_model_health(
        model_brand,
        disabled_accounts=sum(1 for account in accounts if account.status == "disabled"),
        warning_accounts=sum(
            1
            for account in accounts
            if account.status == "warning" or account.auth_status in {"needs_login", "needs_2fa"}
        ),
    )
    platform_counts = {platform: sum(1 for account in accounts if account.platform == platform) for platform in ACCOUNT_PLATFORMS}
    attention_count = sum(
        1
        for account in accounts
        if account.status in {"warning", "critical", "disabled"}
        or account.auth_status in {"needs_login", "needs_2fa", "expired", "locked"}
    )
    model_tasks = tasks_for_model(session, model_brand.id)
    model_incidents = incidents_for_model(session, model_brand.id)
    open_task_count = sum(1 for task in model_tasks if task.status in {"open", "in_progress", "blocked"})
    open_incident_count = sum(1 for incident in model_incidents if incident.status in {"open", "investigating"})
    lines = [
        "Model Detail",
        "",
        f"Name: {model_brand.display_name}",
        f"Stage Name: {model_brand.stage_name or 'Not set'}",
        f"Country: {model_brand.country or 'Not set'}",
        f"Timezone: {model_brand.timezone or 'Not set'}",
        f"Primary Platform: {model_brand.primary_platform or 'Not set'}",
        f"Status: {model_brand.status}",
        f"Health: {health.label} {health.score}/100",
        f"Managers Assigned: {_member_names(managers)}",
        f"Chatters Assigned: {_member_names(chatters)}",
        f"VAs Assigned: {_member_names(vas)}",
        f"Accounts Count: {len(accounts)}",
        f"Instagram Count: {platform_counts['instagram']}",
        f"X Count: {platform_counts['x']}",
        f"OnlyFans Count: {platform_counts['onlyfans']}",
        f"Email Count: {platform_counts['email']}",
        f"Accounts Needing Attention: {attention_count}",
        f"Open Tasks: {open_task_count}",
        f"Open Incidents: {open_incident_count}",
        f"Notes: {model_brand.notes or 'None'}",
    ]
    return Screen(text="\n".join(lines), reply_markup=model_detail_menu(model_brand.id))

def render_model_edit_page(session: Session, model_id: int) -> Screen:
    model_brand = session.get(ModelBrand, model_id)
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="models:list"))
    return Screen(
        text="\n".join(
            [
                "Edit Model",
                "",
                f"Name: {model_brand.display_name}",
                f"Stage Name: {model_brand.stage_name or 'Not set'}",
                f"Country: {model_brand.country or 'Not set'}",
                f"Timezone: {model_brand.timezone or 'Not set'}",
                f"Primary Platform: {model_brand.primary_platform or 'Not set'}",
                f"Status: {model_brand.status}",
                f"Notes: {model_brand.notes or 'None'}",
                "",
                "Choose a field to edit. Changes are saved, audited, and reflected across dashboards.",
            ]
        ),
        reply_markup=model_edit_menu(model_brand.id, model_brand.status),
    )

def render_model_field_edit_page(session: Session, model_id: int, field: str) -> Screen:
    model_brand = session.get(ModelBrand, model_id)
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="models:list"))
    labels = {
        "display_name": "Name",
        "stage_name": "Stage Name",
        "country": "Country",
        "timezone": "Timezone",
        "primary_platform": "Primary Platform",
        "notes": "Notes",
        "internal_notes": "Internal Notes",
    }
    current = getattr(model_brand, field, None)
    label = labels.get(field, field.replace("_", " ").title())
    lines = [
        f"Edit {label}",
        "",
        f"Model: {model_brand.display_name}",
        f"Current: {current or 'Not set'}",
        "",
        "Send the new value in chat.",
        "Type skip to leave it unchanged.",
    ]
    return Screen("\n".join(lines), page_menu(back_to=f"model:{model_id}:edit"))

def render_model_team_page(session: Session, model_id: int) -> Screen:
    model_brand = session.scalar(
        select(ModelBrand)
        .where(ModelBrand.id == model_id)
        .options(selectinload(ModelBrand.members).selectinload(ModelBrandMember.user))
    )
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="models:list"))
    members = summarize_members(model_brand)
    lines = ["Manage Team", "", f"Model: {model_brand.display_name}", ""]
    for relationship_type in MODEL_BRAND_RELATIONSHIP_TYPES:
        lines.append(f"{RELATIONSHIP_LABELS[relationship_type]}: {_member_names(members[relationship_type])}")
    return Screen(text="\n".join(lines), reply_markup=model_team_menu(model_brand.id))

def render_model_assignment_page(
    session: Session,
    model_id: int,
    relationship_type: str,
) -> Screen:
    model_brand = session.scalar(
        select(ModelBrand)
        .where(ModelBrand.id == model_id)
        .options(selectinload(ModelBrand.members).selectinload(ModelBrandMember.user))
    )
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="models:list"))
    assigned_ids = {
        member.user_id
        for member in model_brand.members
        if member.relationship_type == relationship_type
    }
    user_buttons: list[tuple[str, str]] = []
    for user in active_users_for_assignment(session):
        if user.id in assigned_ids:
            continue
        identity = user.display_name or user.username or f"User {user.id}"
        user_buttons.append(
            (
                identity,
                f"nav:model:{model_brand.id}:team:assign:{relationship_type}:{user.id}",
            )
        )
    lines = [
        f"Assign {RELATIONSHIP_LABELS.get(relationship_type, relationship_type)}",
        "",
        f"Model: {model_brand.display_name}",
    ]
    if not user_buttons:
        lines.extend(["", "No active users available."])
    return Screen(
        text="\n".join(lines),
        reply_markup=model_member_choice_menu(model_brand.id, relationship_type, user_buttons),
    )

def render_model_remove_assignment_page(session: Session, model_id: int) -> Screen:
    model_brand = session.scalar(
        select(ModelBrand)
        .where(ModelBrand.id == model_id)
        .options(selectinload(ModelBrand.members).selectinload(ModelBrandMember.user))
    )
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="models:list"))
    user_buttons: list[tuple[str, str]] = []
    for member in model_brand.members:
        identity = member.user.display_name or member.user.username or f"User {member.user_id}"
        relationship = RELATIONSHIP_LABELS.get(member.relationship_type, member.relationship_type)
        user_buttons.append(
            (
                f"{relationship}: {identity}",
                f"nav:model:{model_brand.id}:team:remove:{member.relationship_type}:{member.user_id}",
            )
        )
    lines = ["Remove Assignment", "", f"Model: {model_brand.display_name}"]
    if not user_buttons:
        lines.extend(["", "No assignments yet."])
    return Screen(
        text="\n".join(lines),
        reply_markup=model_member_choice_menu(model_brand.id, "member", user_buttons),
    )

def render_model_audit_page(session: Session, model_id: int) -> Screen:
    model_brand = session.get(ModelBrand, model_id)
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="models:list"))
    logs = model_audit_logs(session, model_brand)
    lines = ["Model Audit History", "", f"Model: {model_brand.display_name}", ""]
    if not logs:
        lines.append("No model audit events yet.")
    for log in logs:
        timestamp = log.created_at.isoformat() if log.created_at else "pending timestamp"
        lines.append(f"{timestamp}")
        lines.append(f"Action: {log.action} | Status: {log.status}")
        lines.append("")
    return Screen(text="\n".join(lines).strip(), reply_markup=page_menu(back_to=f"model:{model_id}"))

def render_model_placeholder_page(session: Session, model_id: int, title: str) -> Screen:
    model_brand = session.get(ModelBrand, model_id)
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="models:list"))
    return Screen(
        text=f"{title}\n\nModel: {model_brand.display_name}\nCount: 0",
        reply_markup=page_menu(back_to=f"model:{model_id}"),
    )

def render_model_creators_page(session: Session, model_id: int) -> Screen:
    model_brand = session.get(ModelBrand, model_id)
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="models:list"))
    creators = [creator for creator in list_creator_watches(session, active_only=False, limit=100) if creator.assigned_model_id == model_id]
    lines = ["Model Creators", "", f"Model: {model_brand.display_name}", ""]
    buttons: list[tuple[str, str]] = []
    if not creators:
        lines.append("No creators assigned yet. Add a creator from the setup wizard or Creator Watchlist.")
        buttons.append(("Add Creator Starter", "nav:setup:wizard:creators"))
    for creator in creators[:15]:
        lines.append(f"{creator.id}. {creator.display_name or creator.creator_name} (@{creator.creator_username})")
        lines.append(f"   Platform: {creator.platform} | Niche: {creator.niche or 'Not set'} | Priority: {creator.priority}")
        buttons.append((f"{creator.id}. {creator.display_name or creator.creator_name}", f"nav:creator:{creator.id}"))
    return Screen("\n".join(lines), account_list_menu(buttons, back_to=f"model:{model_id}"))

def render_model_opportunities_page(session: Session, model_id: int) -> Screen:
    model_brand = session.get(ModelBrand, model_id)
    if model_brand is None:
        return Screen(text="Model not found.", reply_markup=page_menu(back_to="models:list"))
    opportunities = [
        opportunity
        for opportunity in list_opportunities(session, include_archived=True, limit=100)
        if opportunity.model_brand_id == model_id
    ]
    lines = ["Model Opportunities", "", f"Model: {model_brand.display_name}", ""]
    buttons: list[tuple[str, str]] = []
    if not opportunities:
        lines.append("No opportunities yet. Create a starter opportunity from setup or add one manually.")
        buttons.append(("Create Starter Opportunity", "nav:setup:wizard:opportunities"))
    for opportunity in opportunities[:15]:
        lines.append(f"{opportunity.id}. {opportunity.title}")
        lines.append(f"   Status: {opportunity.status} | Priority: {opportunity.priority} | Score: {opportunity.score}")
        buttons.append((f"{opportunity.id}. {opportunity.title[:34]}", f"nav:opportunity:{opportunity.id}"))
    return Screen("\n".join(lines), account_list_menu(buttons, back_to=f"model:{model_id}"))

