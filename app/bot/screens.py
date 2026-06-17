from dataclasses import dataclass

from aiogram.types import InlineKeyboardMarkup
from sqlalchemy import desc, select
from sqlalchemy.orm import Session, selectinload

from app.bot.menu import (
    dashboard_menu,
    main_menu,
    model_detail_menu,
    model_edit_menu,
    model_list_menu,
    model_member_choice_menu,
    model_team_menu,
    models_menu,
    page_menu,
    permission_choice_menu,
    role_choice_menu,
    role_detail_menu,
    roles_menu,
    settings_menu,
    user_detail_menu,
    users_menu,
)
from app.models.audit import AuditLog
from app.models.model_brand import MODEL_BRAND_RELATIONSHIP_TYPES, ModelBrand, ModelBrandMember
from app.models.permissions import Permission, Role
from app.models.user import User
from app.services.auth import DEFAULT_PERMISSION_DESCRIPTIONS
from app.services.dashboard import DashboardStats, dashboard_stats, placeholder_dashboard_stats
from app.services.model_brands import (
    RELATIONSHIP_LABELS,
    active_users_for_assignment,
    list_model_brands,
    model_audit_logs,
    summarize_members,
)
from app.services.model_health import calculate_model_health


@dataclass(frozen=True)
class Screen:
    text: str
    reply_markup: InlineKeyboardMarkup


PAGE_TITLES: dict[str, str] = {
    "users": "Users",
    "models": "Models",
    "roles": "Roles",
    "accounts": "Accounts",
    "proxies": "Proxies",
    "tasks": "Tasks",
    "incidents": "Incidents",
    "reports": "Reports",
    "automations": "Automations",
    "settings": "Settings",
}


def render_main_menu() -> Screen:
    return Screen(text="Agency OS\nSelect an area.", reply_markup=main_menu())


def render_dashboard(stats: DashboardStats | None = None, session: Session | None = None) -> Screen:
    current = stats or (dashboard_stats(session) if session is not None else placeholder_dashboard_stats())
    lines = [
        "Dashboard",
        "",
        f"Total Users: {current.total_users}",
        f"Active Users: {current.active_users}",
        f"Accounts: {current.accounts}",
        f"Healthy Proxies: {current.healthy_proxies}",
        f"Open Tasks: {current.open_tasks}",
        f"Open Incidents: {current.open_incidents}",
        f"Models: {current.models}",
        f"Healthy Models: {current.healthy_models}",
        f"Warning Models: {current.warning_models}",
        f"Critical Models: {current.critical_models}",
        "",
        "Top Models by Activity:",
    ]
    lines.extend(f"- {item}" for item in current.top_model_activity[:5])
    if not current.top_model_activity:
        lines.append("- No model activity yet")
    lines.extend(["", "Recent Model Events:"])
    lines.extend(f"- {item}" for item in current.recent_model_events[:5])
    if not current.recent_model_events:
        lines.append("- No model events yet")
    text = "\n".join(lines)
    return Screen(text=text, reply_markup=dashboard_menu())


def render_models_home() -> Screen:
    return Screen(text="Models\nCommand center.", reply_markup=models_menu())


def _model_identity(model_brand: ModelBrand) -> str:
    if model_brand.stage_name:
        return f"{model_brand.display_name} ({model_brand.stage_name})"
    return model_brand.display_name


def render_model_list_page(session: Session) -> Screen:
    models = list_model_brands(session)
    lines = ["Models", ""]
    buttons: list[tuple[str, str]] = []
    if not models:
        lines.append("No models yet.")
    for model_brand in models[:10]:
        health = calculate_model_health(model_brand)
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
        health = calculate_model_health(model_brand)
        lines.append(f"{model_brand.display_name}: {health.label} {health.score}/100")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="models"))


def _member_names(members: list[User]) -> str:
    if not members:
        return "None"
    return ", ".join(user.display_name or user.username or f"User {user.id}" for user in members)


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
    health = calculate_model_health(model_brand)
    lines = [
        "Model Detail",
        "",
        f"Name: {model_brand.display_name}",
        f"Stage Name: {model_brand.stage_name or 'Not set'}",
        f"Status: {model_brand.status}",
        f"Health: {health.label} {health.score}/100",
        f"Managers Assigned: {_member_names(managers)}",
        f"Chatters Assigned: {_member_names(chatters)}",
        f"VAs Assigned: {_member_names(vas)}",
        "Accounts Count: 0",
        "Open Tasks: 0",
        "Open Incidents: 0",
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
                f"Status: {model_brand.status}",
            ]
        ),
        reply_markup=model_edit_menu(model_brand.id, model_brand.status),
    )


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


def render_users_page(session: Session, status_filter: str | None = None) -> Screen:
    users = session.scalars(
        select(User).options(selectinload(User.roles)).order_by(User.id).limit(10)
    ).all()
    all_pending_count = sum(1 for user in users if user.status == "pending")
    if status_filter is not None:
        users = [user for user in users if user.status == status_filter]
    title = "Pending Users" if status_filter == "pending" else "Users"
    lines = [title, "", f"Pending: {all_pending_count}", ""]
    if not users:
        lines.append("No users yet.")
    buttons: list[tuple[str, str]] = []
    for user in users:
        role_names = ", ".join(role.name for role in user.roles) or "No roles"
        if user.display_name and user.username:
            identity = f"{user.display_name} (@{user.username})"
        elif user.username:
            identity = f"@{user.username}"
        else:
            identity = user.display_name or f"User {user.id}"
        lines.append(f"{user.id}. {identity}")
        lines.append(f"   Status: {user.status} | Roles: {role_names}")
        buttons.append((f"{user.id}. {identity} ({user.status})", f"nav:user:{user.id}"))
    return Screen(text="\n".join(lines), reply_markup=users_menu(buttons))


def _masked_telegram_id(value: int) -> str:
    raw = str(value)
    if len(raw) <= 4:
        return "hidden"
    return f"{raw[:2]}...{raw[-2:]}"


def render_user_detail_page(session: Session, user_id: int) -> Screen:
    user = session.scalar(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles), selectinload(User.roles).selectinload(Role.permissions))
    )
    if user is None:
        return Screen(text="User not found.", reply_markup=page_menu(back_to="users"))

    role_names = ", ".join(role.name for role in user.roles) or "No roles"
    logs = session.scalars(
        select(AuditLog)
        .where(AuditLog.resource_type == "user", AuditLog.resource_id == str(user.id))
        .order_by(desc(AuditLog.created_at), desc(AuditLog.id))
        .limit(5)
    ).all()
    recent = [f"- {log.action} ({log.status})" for log in logs] or ["- No recent user actions"]
    username = f"@{user.username}" if user.username else "Not set"
    created_at = user.created_at.isoformat() if user.created_at else "pending timestamp"
    last_seen = user.last_seen.isoformat() if user.last_seen else "Not seen yet"
    lines = [
        "User Detail",
        "",
        f"Display Name: {user.display_name or 'Unknown'}",
        f"Username: {username}",
        f"Telegram ID: {_masked_telegram_id(user.telegram_id)}",
        f"Status: {user.status}",
        f"Roles: {role_names}",
        f"Created: {created_at}",
        f"Last Seen: {last_seen}",
        "",
        "Recent Audit Actions:",
        *recent,
    ]
    return Screen(text="\n".join(lines), reply_markup=user_detail_menu(user.id, user.status))


def render_role_assignment_page(session: Session, user_id: int, action: str) -> Screen:
    user = session.scalar(select(User).where(User.id == user_id).options(selectinload(User.roles)))
    if user is None:
        return Screen(text="User not found.", reply_markup=page_menu(back_to="users"))
    title = "Assign Role" if action == "assign_role" else "Remove Role"
    if action == "remove_role":
        role_names = sorted(role.name for role in user.roles)
    else:
        assigned = {role.name for role in user.roles}
        role_names = [
            role_name
            for role_name in session.scalars(select(Role.name).order_by(Role.name)).all()
            if role_name not in assigned
        ]
    if not role_names:
        return Screen(
            text=f"{title}\n\nNo roles available.",
            reply_markup=page_menu(back_to=f"user:{user_id}"),
        )
    return Screen(
        text=f"{title}\n\nUser: {user.display_name or user.username or user.id}",
        reply_markup=role_choice_menu(user_id, action, list(role_names)),
    )


def render_roles_page(session: Session) -> Screen:
    roles = session.scalars(
        select(Role).options(selectinload(Role.permissions)).order_by(Role.name)
    ).all()
    lines = ["Roles", ""]
    buttons: list[tuple[str, str]] = []
    for role in roles:
        lines.append(f"{role.id}. {role.name} ({len(role.permissions)} permissions)")
        buttons.append((role.name, f"nav:role:{role.id}"))
    return Screen(text="\n".join(lines), reply_markup=roles_menu(buttons))


def render_role_detail_page(session: Session, role_id: int) -> Screen:
    role = session.scalar(
        select(Role).where(Role.id == role_id).options(selectinload(Role.permissions))
    )
    if role is None:
        return Screen(text="Role not found.", reply_markup=page_menu(back_to="roles"))
    permissions = "\n".join(f"- {permission.key}" for permission in sorted(role.permissions, key=lambda p: p.key))
    if not permissions:
        permissions = "- No permissions"
    return Screen(
        text=f"Role\n\nName: {role.name}\nPermissions:\n{permissions}",
        reply_markup=role_detail_menu(role.id),
    )


def render_permission_list_page(session: Session, role_id: int, action: str) -> Screen:
    role = session.scalar(
        select(Role).where(Role.id == role_id).options(selectinload(Role.permissions))
    )
    if role is None:
        return Screen(text="Role not found.", reply_markup=page_menu(back_to="roles"))
    role_keys = {permission.key for permission in role.permissions}
    if action == "add_permission":
        permission_keys = [key for key in DEFAULT_PERMISSION_DESCRIPTIONS if key not in role_keys]
        title = "Add Permission"
    else:
        permission_keys = sorted(role_keys)
        title = "Remove Permission"
    if not permission_keys:
        return Screen(text=f"{title}\n\nNo permissions available.", reply_markup=page_menu(back_to=f"role:{role.id}"))
    return Screen(
        text=f"{title}\n\nRole: {role.name}",
        reply_markup=permission_choice_menu(role.id, action, permission_keys),
    )


def render_default_permissions_page() -> Screen:
    lines = ["Default Permissions", ""]
    lines.extend(f"- {key}" for key in DEFAULT_PERMISSION_DESCRIPTIONS)
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="roles"))


def render_audit_logs_page(session: Session) -> Screen:
    logs = session.scalars(
        select(AuditLog).order_by(desc(AuditLog.created_at), desc(AuditLog.id)).limit(10)
    ).all()
    lines = ["Audit Logs", ""]
    if not logs:
        lines.append("No audit logs yet.")
    for log in logs:
        actor = log.actor_user_id if log.actor_user_id is not None else "system"
        target = f"{log.resource_type}:{log.resource_id}" if log.resource_id else log.resource_type
        timestamp = log.created_at.isoformat() if log.created_at else "pending timestamp"
        lines.append(f"{timestamp}")
        lines.append(f"Actor: {actor} | Action: {log.action}")
        lines.append(f"Target: {target} | Status: {log.status}")
        lines.append("")
    return Screen(text="\n".join(lines).strip(), reply_markup=page_menu(back_to="settings"))


def render_access_pending() -> Screen:
    return Screen(
        text="Access pending approval.",
        reply_markup=main_menu(),
    )


def render_disabled() -> Screen:
    return Screen(text="Account disabled.", reply_markup=main_menu())


def render_denied() -> Screen:
    return Screen(text="Access denied.", reply_markup=main_menu())


def render_page(page: str, session: Session | None = None) -> Screen:
    if page == "models":
        return render_models_home()
    if page in {"models:list", "models:search"} and session is not None:
        return render_model_list_page(session)
    if page == "models:dashboard" and session is not None:
        return render_model_dashboard_page(session)
    if page.startswith("model:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            model_id = int(parts[1])
            if len(parts) == 2:
                return render_model_detail_page(session, model_id)
            if parts[2] == "edit":
                return render_model_edit_page(session, model_id)
            if parts[2] == "team":
                if len(parts) >= 5 and parts[3] == "assign":
                    return render_model_assignment_page(session, model_id, parts[4])
                if len(parts) >= 4 and parts[3] == "remove":
                    return render_model_remove_assignment_page(session, model_id)
                return render_model_team_page(session, model_id)
            if parts[2] == "audit":
                return render_model_audit_page(session, model_id)
            if parts[2] in {"accounts", "tasks", "incidents"}:
                return render_model_placeholder_page(session, model_id, parts[2].title())
    if page == "users" and session is not None:
        return render_users_page(session)
    if page == "users:pending" and session is not None:
        return render_users_page(session, status_filter="pending")
    if page.startswith("user:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            if len(parts) >= 3 and parts[2] in {"assign_role", "remove_role"}:
                return render_role_assignment_page(session, int(parts[1]), parts[2])
            return render_user_detail_page(session, int(parts[1]))
    if page == "roles" and session is not None:
        return render_roles_page(session)
    if page.startswith("role:") and session is not None:
        parts = page.split(":")
        if len(parts) >= 2 and parts[1].isdigit():
            if len(parts) >= 3 and parts[2] in {"add_permission", "remove_permission"}:
                return render_permission_list_page(session, int(parts[1]), parts[2])
            return render_role_detail_page(session, int(parts[1]))
    if page == "permissions":
        return render_default_permissions_page()
    if page == "audit_logs" and session is not None:
        return render_audit_logs_page(session)
    if page == "settings":
        return Screen(text="Settings\n\nAdministrative tools.", reply_markup=settings_menu())
    title = PAGE_TITLES.get(page, "Unknown")
    return Screen(text=f"{title}\n\nManagement tools will appear here.", reply_markup=page_menu())
