from .formatting import *
from .accounts import render_account_list_page

def render_my_models_page(session: Session, user: User) -> Screen:
    model_ids = select(ModelBrandMember.model_brand_id).where(ModelBrandMember.user_id == user.id)
    models = list(session.scalars(select(ModelBrand).where(ModelBrand.id.in_(model_ids)).order_by(ModelBrand.display_name)).all())
    lines = ["My Models", ""]
    buttons: list[tuple[str, str]] = []
    if not models:
        lines.append("No models are assigned yet.")
    for model_brand in models[:15]:
        lines.append(f"{model_brand.id}. {_model_identity(model_brand)}")
        lines.append(f"   Status: {model_brand.status}")
        buttons.append((model_brand.display_name[:40], f"nav:model:{model_brand.id}"))
    return Screen(text="\n".join(lines), reply_markup=model_list_menu(buttons))

def render_my_accounts_page(session: Session, user: User) -> Screen:
    model_ids = select(ModelBrandMember.model_brand_id).where(ModelBrandMember.user_id == user.id)
    accounts = list(
        session.scalars(
            select(Account)
            .where(Account.model_brand_id.in_(model_ids))
            .options(selectinload(Account.model_brand))
            .order_by(Account.platform, Account.username)
        ).all()
    )
    return render_account_list_page(session, accounts=accounts, title="My Accounts", back_to="menu")

def render_my_opportunities_page(session: Session, user: User) -> Screen:
    opportunities = list(
        session.scalars(
            select(Opportunity)
            .where(Opportunity.assigned_to_user_id == user.id)
            .order_by(desc(Opportunity.updated_at), desc(Opportunity.id))
            .limit(20)
        ).all()
    )
    lines = ["My Opportunities", ""]
    tab_counts = {
        "New": sum(1 for opportunity in opportunities if opportunity.status == "assigned"),
        "In Progress": sum(1 for opportunity in opportunities if opportunity.status == "reviewing"),
        "Posted": sum(1 for opportunity in opportunities if opportunity.status == "completed"),
        "Needs Result": sum(1 for opportunity in opportunities if opportunity.status in {"assigned", "reviewing"}),
        "Completed": sum(1 for opportunity in opportunities if opportunity.status == "completed"),
    }
    lines.extend(f"{label}: {count}" for label, count in tab_counts.items())
    lines.append("")
    buttons: list[tuple[str, str]] = []
    if not opportunities:
        lines.append("No opportunities assigned yet.")
    for opportunity in opportunities:
        lines.append(f"{opportunity.id}. {opportunity.title}")
        lines.append(f"   Priority: {opportunity.priority} | Score: {opportunity.score}/100 | Status: {opportunity.status}")
        buttons.append((f"{opportunity.id}. {opportunity.title[:36]}", f"nav:opportunity:{opportunity.id}"))
    return Screen(text="\n".join(lines), reply_markup=opportunities_menu(buttons))

def render_client_dashboard_page(session: Session, user: User) -> Screen:
    details = personalized_dashboard(session, user)
    lines = [
        "My Dashboard",
        "",
        f"Assigned Models: {details['assigned_models']}",
        f"Tasks Due Today: {details['tasks_due_today']}",
        f"Open Incidents: {details['open_incidents']}",
        "",
        "Reports and team visibility are kept simple here.",
    ]
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="menu"))

def render_my_reports_page(session: Session, user: User) -> Screen:
    details = personalized_dashboard(session, user)
    lines = [
        "My Reports",
        "",
        f"Role: {details['role']}",
        f"Assigned Models: {details['assigned_models']}",
        f"Performance Score: {details['performance']['accountability_score']}",
        "",
        "Full agency reports stay with managers and owners.",
    ]
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="menu"))

def render_my_team_page(session: Session, user: User) -> Screen:
    members = list(
        session.scalars(
            select(User)
            .join(ModelBrandMember, ModelBrandMember.user_id == User.id)
            .where(
                ModelBrandMember.model_brand_id.in_(
                    select(ModelBrandMember.model_brand_id).where(ModelBrandMember.user_id == user.id)
                )
            )
            .options(selectinload(User.roles))
            .distinct()
            .order_by(User.display_name)
        ).all()
    )
    lines = ["My Team", ""]
    if not members:
        lines.append("No team members are visible yet.")
    for member in members[:15]:
        roles = ", ".join(role.name for role in member.roles) or "No role"
        lines.append(f"- {_identity(member)} | {roles}")
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="menu"))

def render_uploads_placeholder_page() -> Screen:
    lines = [
        "Uploads",
        "",
        "Upload workflows are prepared as a placeholder.",
        "For now, use Tasks and Availability to coordinate upload work.",
    ]
    return Screen(text="\n".join(lines), reply_markup=page_menu(back_to="menu"))

def render_team_qa_page(session: Session) -> Screen:
    checklists = list_onboarding_checklists(session)
    lines = ["Team QA", "", "Rollout readiness checklist.", ""]
    buttons: list[tuple[str, str]] = []
    if not checklists:
        lines.append("No users yet.")
    for checklist in checklists[:20]:
        user = checklist.user
        lines.append(f"{user.id}. {_identity(user)}")
        lines.append(f"   Readiness: {checklist.readiness_score}% | Onboarded: {checklist.onboarded}")
        buttons.append((f"{user.id}. {_identity(user)[:32]}", f"nav:team_qa:{user.id}"))
    return Screen(text="\n".join(lines), reply_markup=team_qa_menu(buttons))

def render_team_qa_detail_page(session: Session, user_id: int) -> Screen:
    target = session.scalar(
        select(User).where(User.id == user_id).options(selectinload(User.roles), selectinload(User.availability))
    )
    if target is None:
        return Screen(text="User not found.", reply_markup=page_menu(back_to="team_qa"))
    checklist = list_onboarding_checklists(session)
    current = next(item for item in checklist if item.user_id == target.id)
    lines = [
        "Team QA Detail",
        "",
        f"User: {_identity(target)}",
        f"Roles: {', '.join(role.name for role in target.roles) or 'No roles'}",
        f"Readiness Score: {current.readiness_score}%",
        "",
        f"Role Assigned: {current.role_assigned}",
        f"Timezone Confirmed: {current.timezone_confirmed}",
        f"Availability Configured: {current.availability_configured}",
        f"Help Center Viewed: {current.help_center_viewed}",
        f"Onboarded: {current.onboarded}",
    ]
    return Screen(text="\n".join(lines), reply_markup=team_qa_detail_menu(target.id))

def render_notification_digest_mode_page(session: Session, user: User | None = None, *, generate: bool = False) -> Screen:
    if generate:
        create_notification_digest(session, actor=user, user=user, purpose="operations")
    digests = list_notification_digests(session)
    lines = [
        "Notification Digest Mode",
        "",
        "Low-priority updates are bundled here so the team is not flooded with alerts.",
        "Critical alerts still route immediately.",
        "",
    ]
    if not digests:
        lines.append("No digests yet.")
    for digest in digests[:10]:
        lines.append(f"{digest.id}. {digest.title} | {digest.status} | {digest.item_count} update(s)")
        lines.append(f"   {digest.summary}")
    return Screen(text="\n".join(lines), reply_markup=notification_digest_mode_menu())

def render_scheduled_automations_page(session: Session, user: User | None = None, *, run_due: bool = False) -> Screen:
    results = run_due_scheduled_automations(session, actor=user) if run_due else []
    summary = scheduled_automation_summary(session)
    lines = [
        "Scheduled Automations",
        "",
        "Only low-risk automations auto-run initially.",
        "High-risk work still requires review and approval.",
        "",
        f"Schedules: {summary['total']}",
        f"Active Schedules: {summary['active']}",
        f"Successful Runs: {summary['successful']}",
        f"Failed Runs: {summary['failed']}",
        f"Skipped Runs: {summary['skipped']}",
    ]
    if run_due:
        lines.extend(["", "Run Results:"])
        if not results:
            lines.append("- No due safe automations.")
        for result in results:
            lines.append(f"- {result.rule_name}: {result.status} ({result.reason})")
    return Screen(text="\n".join(lines), reply_markup=scheduled_automations_menu())

def render_daily_autopilot_page(session: Session, user: User | None = None) -> Screen:
    summary = daily_autopilot_summary(session, user)
    next_run = summary["next_run"].isoformat() if summary["next_run"] else "Disabled"
    last_run = summary["last_run"].isoformat() if summary["last_run"] else "Not run yet"
    lines = [
        "Daily Autopilot",
        "",
        f"Status: {'Enabled' if summary['enabled'] else 'Disabled'}",
        f"Owner Timezone: {summary['timezone']}",
        f"Run Time: {summary['run_time_local']}",
        f"Next Run: {next_run}",
        f"Last Run: {last_run}",
        f"Last Result: {summary['last_result']}",
        "",
        "Included Actions:",
    ]
    lines.extend(f"- {action}" for action in summary["included_actions"])
    lines.extend(
        [
            "",
            "Only safe daily checks are enabled here. High-risk automations still require explicit owner approval.",
        ]
    )
    return Screen("\n".join(lines), daily_autopilot_menu(summary["enabled"]))

