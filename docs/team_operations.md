# Team Operations

Sprint 11 activates Fortuna OS for daily agency work.

## Operating Screens

- Tasks -> My Tasks: work assigned to the current user.
- Tasks -> Team Tasks: all assigned, non-archived work.
- Tasks -> Overdue Tasks: active work past due.
- Incidents -> Open Incidents: unresolved operational issues.
- Incidents -> Critical Incidents: high-priority incident queue.
- Reports -> Manager Command View: people on shift, open work, overdue work, critical incidents, recommendations, and delivery failures.
- Settings -> My Availability: current shift status.
- Settings -> Team Availability: manager/admin visibility into team availability.

## Task Ownership

Tasks now support:

- owner user
- assignee
- model/brand attachment
- account attachment
- proxy attachment
- due timestamp
- started and completed timestamps
- blocked reason
- escalation level and latest escalation timestamp

Important task events:

- `task.created`
- `task.assigned`
- `task.reassigned`
- `task.started`
- `task.blocked`
- `task.completed`
- `task.escalated`
- `task.overdue_detected`

## Incident Ownership

Incidents now support:

- owner user
- assignee
- severity and status
- source type
- model/brand, account, and proxy attachment
- escalation level
- resolution notes
- resolver and resolved timestamp
- durable timeline entries

Every status change writes an `incident_timeline` row. The timeline is for operator context and must follow the same no-secret rule as audit metadata.

Important incident events:

- `incident.created`
- `incident.assigned`
- `incident.investigating`
- `incident.escalated`
- `incident.resolved`
- `incident.archived`

## Escalation Direction

Current escalation direction:

- Chatter -> Senior Chatter -> Chatter Manager -> Manager -> Owner.
- VA -> Manager -> Owner.
- Proxy/System issue -> Admin/Manager -> Owner.

The current implementation records escalation level and history. Full configurable escalation paths are planned for a later sprint.

## Manager Daily Routine

Recommended morning flow:

1. Open Reports -> Manager Command View.
2. Check on-shift/off-shift counts.
3. Review overdue tasks.
4. Review critical incidents.
5. Generate Reports -> Daily Digest.
6. Send the digest to HQ or Operations after confirming notification targets.
7. Confirm Audit Logs show expected operations events.
