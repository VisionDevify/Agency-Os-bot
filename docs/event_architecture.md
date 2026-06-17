# Event Architecture

Agency OS should become event-driven over time. Audit logs remain the operator-facing safety record. Sprint 8 added `event_logs` as the first lightweight durable event feed for reports, notifications, automations, self-healing, and future AI operations. Sprint 9 adds notification routing events, durable automation simulation events, recommendations, and heartbeat state changes. Sprint 11 adds operations activation events for task ownership, incident timelines, localization, availability, smart notification routing, daily digest delivery, and duplicate polling protection.

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

Sprint 8 keeps event work lightweight:

- Admin and access events are written through audit helpers.
- Model/Brand, Account, Proxy, Task, Incident, Briefing, Accountability, Dashboard, Report, Notification Target, Automation Simulation, Recommendation, and Heartbeat domain events are emitted through `app.services.events.emit_event`.
- `emit_event` writes an `audit_logs` row and an `event_logs` row with sanitized metadata.
- Event names use a consistent dotted format.
- Sensitive metadata is masked or omitted.
- No queue, stream, or asynchronous worker exists yet.

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
- `account.created`: account inventory record created and attached to a model/brand when available.
- `account.updated`: account metadata, status, or notes changed.
- `account.disabled`: account intentionally disabled.
- `account.archived`: account archived without deleting history.
- `account.auth_session.started`: login/auth coordination session opened.
- `account.auth_session.waiting_for_code`: auth session is waiting for a verification code.
- `account.auth_code.submitted`: verification code submitted and hashed; plaintext code is not stored.
- `account.auth_session.success`: auth session marked successful.
- `account.auth_session.failed`: auth session marked failed with a safe reason.
- `account.auth_session.expired`: auth session expired.
- `account.auth_status.changed`: account auth status changed.
- `proxy.created`: proxy vault record created with encrypted password storage.
- `proxy.assigned`: proxy assigned to an account.
- `proxy.unassigned`: proxy removed from an account.
- `proxy.health.changed`: proxy health score or status changed.
- `proxy.rotation.started`: session suffix rotation started.
- `proxy.rotation.succeeded`: session suffix rotation succeeded.
- `proxy.rotation.failed`: session suffix rotation failed.
- `proxy.location.mismatch`: detected proxy location did not match target.
- `proxy.incident.created`: proxy workflow created an incident.
- `proxy.repair.succeeded`: self-healing repair workflow succeeded.
- `proxy.repair.failed`: self-healing repair workflow failed and requires attention.
- `task.created`: task opened.
- `task.assigned`: task assigned or reassigned to a user.
- `task.reassigned`: task moved from one assignee to another.
- `task.started`: task moved to in-progress.
- `task.blocked`: task marked blocked.
- `task.completed`: task completed.
- `task.escalated`: task escalation level increased.
- `task.archived`: task archived without deletion.
- `task.overdue`: task crossed its due date while still active.
- `task.overdue_detected`: overdue detection pass found an active overdue task.
- `incident.created`: incident opened.
- `incident.assigned`: incident assigned or reassigned.
- `incident.investigating`: incident moved into investigation.
- `incident.escalated`: incident escalated to the next path step.
- `incident.resolved`: incident resolved with notes/history retained.
- `incident.archived`: incident archived without deletion.
- `digest.generated`: Daily Digest generated from current operational metrics.
- `digest.previewed`: Daily Digest preview opened.
- `digest.send_requested`: operator requested digest delivery attempts.
- `digest.sent`: digest delivery attempts were created for active targets.
- `digest.failed`: digest delivery was requested but no active target existed.
- `user.language_updated`: user language preference changed.
- `user.country_updated`: user country preference changed.
- `user.timezone_updated`: user timezone preference changed.
- `user.time_format_updated`: user 12h/24h preference changed.
- `availability.updated`: user shift/availability status changed.
- `briefing.generated`: daily company briefing generated.
- `briefing.viewed`: latest daily briefing viewed.
- `briefing.send_requested`: operator requested a send placeholder.
- `accountability.generated`: team accountability report generated.
- `accountability.viewed`: accountability report viewed.
- `dashboard.viewed`: dashboard page viewed.
- `report.viewed`: report page viewed.
- `notification_target.created`: notification target placeholder created.
- `notification_target.updated`: notification target purpose or safe metadata changed.
- `notification_target.disabled`: notification target disabled.
- `notification_target.tested`: operator requested a safe target test.
- `notification.routed`: routing service selected delivery targets for an event.
- `access.denied`: user attempted a restricted or blocked action.
- `owner.protection_triggered`: lockout protection blocked a risky action.
- `automation.simulated`: automation dry-run completed without mutating production records.
- `automation.simulation.approved`: simulation preview approved.
- `automation.simulation.rejected`: simulation preview rejected.
- `recommendation.generated`: deterministic recommendation created from current state.
- `recommendation.acknowledged`: operator acknowledged a recommendation.
- `recommendation.dismissed`: operator dismissed a recommendation.
- `recommendation.resolved`: operator marked a recommendation resolved.
- `recommendation.status_changed`: recommendation status changed.
- `heartbeat.status_changed`: service heartbeat status changed.
- `repair.succeeded`: future self-healing repair succeeded.

## Future Event Shape

Current `event_logs` table includes:

- `id`
- `event_type`
- `actor_user_id`
- `entity_type`
- `entity_id`
- `metadata_json`
- `created_at`

Future queue/stream expansion can add status, correlation IDs, delivery attempts, and replay controls when real consumers need them. Not every event must be shown to operators, but every security-relevant event should remain auditable.

## Safety Rules

- Do not put tokens, passwords, session strings, encryption keys, or raw credential payloads in events.
- Do not put plaintext verification codes or code hashes in events.
- Do not put proxy passwords or encrypted proxy password blobs in events.
- Prefer secret references or masked identifiers.
- Use stable event names so reports and automations do not break.
- Emit denied and failed attempts, not just successful actions.
- Treat simulation events as first-class records so operators can review intended changes before live execution.

## Account Event Notes

Accounts attach directly to Model/Brand records. Account events should include safe metadata such as account ID, model/brand ID, platform, username, status, auth status, and session ID when needed. Credential values, passwords, verification-code values, and raw platform session data must stay outside events and audits.

Future real integrations should prefer official APIs or OAuth where available. Platform automation, scraping, and security bypass behavior are intentionally out of scope.

## Proxy Event Notes

Proxy events are the first self-healing feed. They should power audit logs, infrastructure dashboards, future reports, notifications, automated repair review, and AI operations summaries.

Safe proxy event metadata can include proxy ID, provider, host, port, status, health score, target/detected location, account ID, model/brand ID, rotation history ID, and failure category. Raw passwords, provider credentials, and secret-bearing payloads must never be emitted.

Simulation mode should produce reviewable summaries before automatic repair is activated. The operator flow remains:

- Preview
- Simulate
- Approve
- Execute

## Operations Event Notes

Tasks and incidents now emit operational events through the audit-backed event helper. Safe task metadata can include task ID, status, priority, model/brand ID, account ID, proxy ID, owner user ID, assigned user ID, escalation level, blocked reason category, and due/completion state. Safe incident metadata can include incident ID, status, severity, source type, model/brand ID, account ID, proxy ID, owner user ID, assigned user ID, escalation level, and safe resolution state.

Incident timeline entries are stored in `incident_timeline` so operational history remains visible even when audit logs are filtered. Timeline metadata follows the same no-secret rule as EventLog.

Daily briefing and accountability events are report-generation events. They should include only aggregate counts, not secrets or sensitive message content. Future notification routing can consume these events to send summaries to the owner or operations group after explicit operator approval.

Daily Digest events build on Daily Briefing. `digest.sent` means durable delivery attempts were created; it does not guarantee Telegram delivery until the corresponding `notification.delivery_succeeded` event exists.

Localization and availability events are operational preferences. They can include language, country, timezone, time format, and availability status, but should not include private schedule notes beyond safe shift/quiet-hour fields.

## Executive Intelligence Event Notes

Executive dashboards emit `dashboard.viewed` events for report visibility. Daily briefings persist metrics in `daily_briefings` and emit `briefing.generated`; viewing or requesting placeholder sends is audited. Team accountability persists per-user `accountability_snapshots` and emits `accountability.generated`.

Notification Target events should include only type and purpose. Telegram chat IDs should be encrypted or omitted and never emitted as raw event metadata.

## Sprint 9 Event Notes

Notification routing stays purpose-based for now. Routing events can include event type, purpose, and target count, but not raw chat IDs. Delivery attempt history is persisted in `notification_delivery_attempts`.

Automation simulation events are first-class safety records. They should include automation type, target scope, would-trigger count, would-succeed count, would-fail count, and risk level. They should not imply any live action was executed.

Recommendation events are deterministic and safe. They should identify recommendation type, severity, entity type, and entity ID when present. Recommendation metadata must not include credentials, tokens, chat IDs, proxy passwords, verification codes, or raw session data.

Heartbeat events are emitted only when a service status changes. Routine heartbeat refreshes should update `system_heartbeats` without filling the audit log with noise.
