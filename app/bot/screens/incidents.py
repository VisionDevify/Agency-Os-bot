from .formatting import *

def render_incidents_home() -> Screen:
    return Screen(text="Incidents\nEscalation and resolution center.", reply_markup=incidents_menu())

def render_incident_list_page(
    session: Session,
    *,
    incidents: list[Incident] | None = None,
    title: str = "Incidents",
    back_to: str = "incidents",
) -> Screen:
    current_incidents = incidents if incidents is not None else list_incidents(session)
    lines = [title, ""]
    buttons: list[tuple[str, str]] = []
    if not current_incidents:
        lines.append("No incidents yet.")
    for incident in current_incidents[:15]:
        assignee = _identity(incident.assigned_to)
        source = incident.source_type or "manual"
        lines.append(f"{incident.id}. {_status_marker(incident.severity)} {incident.title}")
        lines.append(f"   Severity: {severity_label(incident.severity)} | Status: {incident.status}")
        lines.append(f"   Source: {source} | Assigned: {assignee}")
        buttons.append(_incident_button(incident))
    return Screen(text="\n".join(lines), reply_markup=incident_list_menu(buttons, back_to=back_to))

def render_incident_detail_page(session: Session, incident_id: int) -> Screen:
    incident = get_incident(session, incident_id)
    if incident is None:
        return Screen(text="Incident not found.", reply_markup=page_menu(back_to="incidents:list"))
    model = incident.model_brand.display_name if incident.model_brand else "No model"
    account = f"{incident.account.platform} @{incident.account.username}" if incident.account else "No account"
    proxy = f"{incident.proxy.provider} {incident.proxy.host}:{incident.proxy.port}" if incident.proxy else "No proxy"
    resolved = incident.resolved_at.isoformat() if incident.resolved_at else "Not resolved"
    logs = incident_audit_logs(session, incident, limit=3)
    recent = [f"- {log.action} ({log.status})" for log in logs] or ["- No recent incident events"]
    lines = [
        "Incident Detail",
        "",
        f"Title: {incident.title}",
        f"Description: {incident.description or 'None'}",
        f"Severity: {_status_marker(incident.severity)} {severity_label(incident.severity)}",
        f"Status: {incident.status}",
        f"Source: {incident.source_type or 'manual'}",
        f"Model/Brand: {model}",
        f"Account: {account}",
        f"Proxy: {proxy}",
        f"Assigned To: {_identity(incident.assigned_to)}",
        f"Escalation Target: {escalation_target_for(incident)}",
        f"Resolved: {resolved}",
        f"Resolution Notes: {incident.resolution_notes or 'None'}",
        "",
        "Recent Events:",
        *recent,
    ]
    return Screen(text="\n".join(lines), reply_markup=incident_detail_menu(incident.id))

def render_incident_assignment_page(session: Session, incident_id: int) -> Screen:
    incident = get_incident(session, incident_id)
    if incident is None:
        return Screen(text="Incident not found.", reply_markup=page_menu(back_to="incidents:list"))
    buttons = [
        (_identity(user), f"nav:incident:{incident.id}:assign:{user.id}")
        for user in active_users_for_assignment(session)
        if user.id != incident.assigned_to_user_id
    ]
    lines = ["Assign Incident", "", f"Incident: {incident.title}", ""]
    if not buttons:
        lines.append("No active users available.")
    return Screen(text="\n".join(lines), reply_markup=incident_user_choice_menu(incident.id, buttons))

def render_incident_timeline_page(session: Session, incident_id: int) -> Screen:
    incident = get_incident(session, incident_id)
    if incident is None:
        return Screen(text="Incident not found.", reply_markup=page_menu(back_to="incidents:list"))
    entries = incident_timeline(session, incident)
    lines = ["Incident Timeline", "", f"Incident: {incident.title}", ""]
    if not entries:
        lines.append("No timeline entries yet.")
    for entry in entries[:15]:
        actor = _identity(entry.actor)
        when = entry.created_at.isoformat() if entry.created_at else "pending timestamp"
        lines.append(f"{when}")
        lines.append(f"{entry.event_type} by {actor}")
        lines.append(entry.message)
        lines.append("")
    return Screen(text="\n".join(lines).strip(), reply_markup=page_menu(back_to=f"incident:{incident.id}"))

