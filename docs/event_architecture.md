# Event Architecture

Agency OS should become event-driven over time. Audit logs remain the operator-facing safety record. Sprint 8 added `event_logs` as the first lightweight durable event feed for reports, notifications, automations, self-healing, and future AI operations. Sprint 9 adds notification routing events, durable automation simulation events, recommendations, and heartbeat state changes. Sprint 11 adds operations activation events for task ownership, incident timelines, localization, availability, smart notification routing, daily digest delivery, and duplicate polling protection. Sprint 12 adds deterministic intelligence events for signals, patterns, trends, workload, executive insights, intelligence runs, recommendations, and manual opportunities. Sprint 15 adds learning events, outcome memory, playbook runs, confidence changes, and feedback events. Sprint 16 adds team rollout, notification digest, and scheduled automation execution events. Sprint 17 adds creator watch, own post watch, comment strategy, Help Copilot, activation, and opportunity routing events. Sprint 18 adds guided intake, assignment, result-recording, and strategy-regeneration events.

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
- Learning Engine: remembers what worked, what failed, and which playbooks or recommendations should be trusted next time.

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
- `notification.digest_created`: low-priority notification updates were bundled into a digest.
- `team.onboarding_checklist_updated`: manager/admin updated a user's rollout readiness checklist.
- `automation.schedule_updated`: automation schedule timing or active state changed.
- `automation.scheduled_run.skipped`: scheduler skipped a due automation because a safety gate blocked it.
- `automation.scheduled_runs_processed`: scheduler processed due automation schedules.
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
- `intelligence.signal.created`: deterministic intelligence signal created.
- `intelligence.pattern.detected`: recurring issue pattern created.
- `intelligence.trend.recorded`: trend snapshot persisted.
- `workload.analysis.completed`: workload analysis pass completed.
- `executive_insight.created`: executive insight persisted.
- `executive_intelligence_briefing.generated`: executive intelligence briefing generated.
- `intelligence_run.started`: no-code intelligence run started.
- `intelligence_run.succeeded`: no-code intelligence run succeeded.
- `intelligence_run.failed`: no-code intelligence run failed.
- `opportunity.created`: manual opportunity created.
- `opportunity.scored`: deterministic opportunity score updated.
- `opportunity.assigned`: opportunity assigned to a user.
- `opportunity.high_priority`: high-priority opportunity alert routing key.
- `opportunity.digest`: opportunity digest routing key.
- `opportunity.result_recorded`: manual opportunity result recorded.
- `opportunity_scoring.completed`: deterministic opportunity scoring run completed.
- `creator_watch.created`: creator watch record created.
- `creator_watch.assigned`: creator watch record assigned to a chatter/model/team.
- `creator_watch.disabled`: creator watch record disabled.
- `creator_watch.archived`: creator watch record archived from active view.
- `post_watch.created`: own post watch record created.
- `comment_strategy.generated`: deterministic human-review strategy prompts generated for an opportunity.
- `help_copilot.answered`: Help Copilot returned a role-aware explanation.
- `learning.event.created`: safe learning event captured from an operational outcome.
- `playbook.suggested`: playbook was recommended or suggested to an operator.
- `playbook.run.created`: playbook run or use record was created.
- `playbook.succeeded`: playbook use succeeded and may raise confidence.
- `playbook.failed`: playbook use failed and should reduce confidence or require review.
- `recommendation.feedback.useful`: operator said a recommendation was useful.
- `recommendation.feedback.not_useful`: operator said a recommendation was not useful.
- `recommendation.feedback.wrong`: operator marked recommendation reasoning as wrong.
- `playbook.feedback.useful`: operator marked a playbook useful.
- `playbook.feedback.needs_review`: operator marked a playbook for review.
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

## Sprint 16 Event Notes

Role-specific homes do not need an event for every view beyond normal dashboard/report view events. Team QA updates are auditable because they affect rollout readiness.

Notification digest events should include item counts and purpose only. They must not include raw Telegram chat IDs, message bodies, tokens, credentials, or private content.

Scheduled automation execution is conservative. Low-risk rules can run automatically after simulation/approval gates are satisfied. High-risk or owner-gated rules should create skipped run records instead of silently doing nothing.

## Intelligence Event Notes

Sprint 12 intelligence is deterministic and internal-only. It reads existing Agency OS data and writes signals, patterns, trend snapshots, workload snapshots, executive insights, recommendations, and run records.

Safe intelligence metadata can include:

- signal type, severity, confidence score, entity type, and entity ID.
- pattern type, occurrence count, source event IDs, and suggested action.
- trend metric name, trend direction, percent change, and snapshot ID.
- workload score, overload status, and availability status.
- opportunity platform, score, status, niche, model/brand ID, and assigned user ID.

Unsafe metadata remains forbidden:

- bot tokens, passwords, encryption keys, proxy passwords, credentials, raw Telegram chat IDs, verification codes, code hashes, platform session data, or scraped content.

Critical intelligence signals may create notification delivery attempts through the existing purpose-based routing rules. The delivery attempt should summarize the signal and route to owner/HQ, incidents, or operations targets when active. It should not send raw diagnostic dumps.

Opportunity events are manual-only. They must not imply automatic scraping, posting, commenting, liking, following, or platform automation. Future AI opportunity discovery must remain human-approved and should prefer official APIs where available.

## Sprint 17 Opportunity Activation Notes

Creator Watch and Own Post Watch are internal tracking records. Safe metadata can include platform, priority, niche, model/brand ID, assigned chatter ID, status, and count summaries. It must not include scraped content, platform credentials, passwords, tokens, raw session data, or private messages.

## Sprint 18 Opportunity Workflow Events

Sprint 18 emits and audits:

- `creator.created`
- `creator.updated`
- `creator.assigned`
- `creator.priority_changed`
- `creator.disabled`
- `creator.archived`
- `opportunity.created`
- `opportunity.assigned`
- `opportunity.status_changed`
- `opportunity.strategy_generated`
- `opportunity.result_recorded`
- `opportunity.completed`
- `post_watch.created`
- `post_watch.assigned`
- `post_watch.status_changed`

These events describe internal workflow state only. They must never imply external posting, commenting, liking, following, scraping, credential use, platform evasion, or automatic social-platform actions.

Comment strategy events are guidance-only. They can include strategy counts, score ranges, and `posting: manual_only`, but must not imply that Agency OS posted, commented, liked, followed, or messaged anyone.

Help Copilot events can include the question category and next action. They should not include secrets, raw chat IDs, raw private messages, or diagnostic dumps.

## Automation Builder Event Notes

Sprint 14 automation events are internal Agency OS events. They describe rule management, simulations, approvals, execution, rollback planning, and metrics. They must not imply external social-platform automation.

Core automation event names:

- `automation.rule.created`
- `automation.rule.simulated`
- `automation.approval.requested`
- `automation.approved`
- `automation.rejected`
- `automation.activated`
- `automation.paused`
- `automation.resumed`
- `automation.retired`
- `automation.run.started`
- `automation.run.succeeded`
- `automation.run.failed`
- `automation.run.skipped`
- `automation.suggested`

Safe metadata can include automation rule ID, simulation run ID, automation run ID, rule category, trigger type, action types, risk level, status, affected entity IDs, counts, duration, and rollback availability.

Unsafe metadata remains forbidden:

- bot tokens, passwords, encryption keys, proxy passwords, credential references with secret-bearing context, raw Telegram chat IDs, verification codes, code hashes, platform session data, and raw provider payloads.

Simulation events mean "reviewed as a dry run." They do not mean a proxy was rotated, a task was reassigned, an incident was escalated, or a notification was sent. Live execution must create `automation_runs` and `automation_run_steps` before recording success/failure events.

## Sprint 19 Setup Events

Setup Wizard events are internal operational events. They help reports and audits explain how the agency was initialized.

Core setup event names:

- `setup.started`
- `setup.completed`
- `model.created`
- `model.updated`
- `account.created`
- `member.assigned`
- `creator.created`
- `opportunity.created`

Setup audits include:

- `setup.model_created`
- `setup.account_added`
- `setup.team_assigned`
- `setup.creator_added`
- `setup.opportunity_created`
- `setup.completed`
- `demo.created`
- `demo.cleared`

Safe metadata can include model ID, account ID, creator ID, opportunity ID, relationship type, platform, counts, missing setup items, and demo flags.

Unsafe metadata remains forbidden:

- bot tokens, passwords, encryption keys, proxy passwords, platform passwords, verification codes, raw Telegram chat IDs, and private platform content.
