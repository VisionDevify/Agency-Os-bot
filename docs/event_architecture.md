# Event Architecture

Agency OS should become event-driven over time. The current audit log is the first durable record of important events. A dedicated event table, queue, or stream should be added only when reports, notifications, automations, self-healing, or AI operations need a shared event feed.

## Principle

Every important action emits an event.

Events should be stable, small, and safe. They should say what happened, who triggered it, what resource it targeted, whether it succeeded, when it happened, and provide only safe metadata.

## Event Consumers

Future events can feed:

- Audit logs: compliance and operator accountability.
- Reports: operational summaries and trend analysis.
- Notifications: Telegram alerts, admin queues, and incident routing.
- Automations: triggers for safe follow-up actions.
- Self-healing: detection and repair workflows.
- AI Operations Brain: context for summaries, anomaly explanations, and recommendations.

## Current Lightweight Pattern

Sprint 4 keeps event work lightweight:

- Admin and access events are written through audit helpers.
- Model/Brand domain events are emitted through `app.services.events.emit_event`.
- Event names use a consistent dotted format.
- Sensitive metadata is masked or omitted.
- No separate event bus exists yet.

This avoids over-engineering while preserving a clean upgrade path.

## Example Events

- `user.pending_created`: unknown Telegram user started the bot and was placed in pending review.
- `user.approved`: admin approved a pending, denied, or disabled user.
- `user.denied`: admin denied a user.
- `user.disabled`: admin disabled a user.
- `user.reactivated`: admin reactivated a denied or disabled user.
- `role.assigned`: role added to a user.
- `role.removed`: role removed from a user.
- `permission.added_to_role`: permission added to a role.
- `permission.removed_from_role`: permission removed from a role.
- `model.created`: model/brand record created.
- `model.updated`: model/brand metadata or status updated.
- `model.disabled`: model/brand disabled.
- `model.archived`: model/brand archived.
- `member.assigned`: user assigned to a model/brand team.
- `member.removed`: user removed from a model/brand team.
- `model.health.changed`: model/brand health snapshot emitted after a meaningful model/team change.
- `access.denied`: user attempted a restricted or blocked action.
- `owner.protection_triggered`: lockout protection blocked a risky action.
- `account.added`: future account inventory item created.
- `proxy.failed`: future proxy health check failed.
- `incident.created`: future incident opened.
- `task.completed`: future task completed.
- `automation.simulated`: future automation dry-run completed.
- `repair.succeeded`: future self-healing repair succeeded.

## Future Event Shape

A future `events` table or stream should likely include:

- `id`
- `event_name`
- `actor_user_id`
- `resource_type`
- `resource_id`
- `status`
- `payload`
- `correlation_id`
- `created_at`

The audit log can remain a consumer of events. Not every event must be shown to operators, but every security-relevant event should be auditable.

## Safety Rules

- Do not put tokens, passwords, session strings, encryption keys, or raw credential payloads in events.
- Prefer secret references or masked identifiers.
- Use stable event names so reports and automations do not break.
- Emit denied and failed attempts, not just successful actions.
- Treat simulation events as first-class records so operators can review intended changes before live execution.
