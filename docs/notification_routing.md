# Notification Routing

Sprint 9 introduces safe notification routing without spamming real groups or exposing Telegram chat IDs. Sprint 10 adds durable delivery-attempt records for actual send attempts. Sprint 11 adds availability-aware routing and Daily Digest delivery attempts. Sprint 12 adds critical intelligence signal routing through the same safe delivery-attempt path. Sprint 16 adds Notification Digest Mode for bundling low-priority updates. Sprint 17 adds opportunity and creator-watch routing keys. Sprint 18 adds digestable creator, own-post, assignment, high-priority opportunity, and result-recorded events. Sprint 27 adds Notification Group Setup and a safe routing smoke test. Sprint 38 simplifies owner-facing routing to three groups and adds manual creator/own-post alert routing. Sprint 39 adds persistent 2-group/3-group routing mode and safe creator/own-post alert pilots.

## Goals

- Route important Fortuna OS events to the right Telegram destinations.
- Keep raw chat IDs encrypted and hidden from normal UI.
- Allow safe testing before real production delivery.
- Audit and event-log every routing configuration change.

## Target Purposes

- `hq`: Fortuna HQ, for owner alerts, production status, approvals, critical issues, and daily executive summaries.
- `ops`: Fortuna Ops, for tasks, assignments, setup reminders, opportunities assigned to team, and daily operations summaries.
- `alerts`: Fortuna Alerts, for big creator post alerts, own-post alerts, high-priority opportunity alerts, and urgent timing alerts.

Legacy purposes remain valid internally:

- `owner`, `incidents`, and `testing` map to `hq`.
- `operations` and `automation_logs` map to `ops`.

## Routing Mode

Fortuna supports two owner-facing modes:

- `3_group`: separate Fortuna HQ, Fortuna Ops, and Fortuna Alerts targets.
- `2_group`: Fortuna HQ stays private, while Ops-style and Alerts-style traffic are routed to the combined Alerts/team-action target.

The routing mode is stored in `notification_routing_configs`. It can be changed from Settings -> Notification Routing. Changing modes does not require new code or new migrations.

## Routing Rules

- Daily Briefing -> hq + ops.
- Accountability Report -> ops.
- Critical Incident -> hq + ops.
- Proxy Repair Failed -> hq + ops.
- Proxy Repair Succeeded -> ops.
- Deployment Event -> hq.
- Automation Simulation -> ops.
- Daily Digest -> owner/HQ + operations, depending on the requested purpose.
- Task Assigned -> assigned user when available; otherwise operations.
- Overdue Task -> operations.
- Escalated Task -> operations + owner.
- Escalated Incident -> owner + incidents.
- Critical Intelligence Signal -> hq + ops.
- Creator Watch Created -> ops.
- Creator Assigned -> ops.
- New Creator Post Alert -> alerts.
- New Own Post Alert -> alerts by default, or ops if configured for that post.
- Own Post Added -> ops.
- Opportunity Created -> ops.
- Opportunity Assigned -> ops.
- High Priority Opportunity -> alerts + hq.
- Opportunity Result Recorded -> ops.
- Opportunity Digest -> ops.
- Low-priority updates -> notification digest bundle when immediate delivery is not required.

## Smart Routing Inputs

Sprint 11 routing considers:

- target purpose
- event severity
- assigned user
- user availability status
- quiet hours
- escalation level

If a user is `off_shift`, `away`, `vacation`, `unavailable`, or inside quiet hours, direct user delivery is suppressed for normal work and routed to Operations instead. Critical and escalated events add Owner/HQ and Incidents routes.

## Telegram UI

Settings -> Notification Targets supports:

- View Targets.
- Add Target placeholder.
- Register Current Chat as Fortuna Target (formerly Add Current Chat As Target).
- Set Purpose.
- Disable Target.
- Test Send metadata update.
- Send Test Notification to active testing targets only.
- Recent delivery attempts on target detail.
- Daily Digest delivery history.
- Notification Digest Mode for bundled low-priority updates.

Settings -> Notification Group Setup supports:

- Required target readiness for Fortuna HQ, Fortuna Ops, and Fortuna Alerts.
- Register Current Chat as Fortuna Target from the Telegram group/channel being registered.
- Run Routing Test.
- Last delivery status per purpose.
- Direct link to the manual group-registration help.

Settings -> Notification Routing supports:

- Current routing mode.
- HQ/Ops/Alerts configured status.
- Combined Ops/Alerts indicator for 2-group mode.
- Register Current Chat.
- Set Routing Mode.
- Test HQ, Ops, and Alerts safely.
- Simulate Alert Routing.
- Delivery History.

## Manual Group Registration

Fortuna OS notification groups/channels are not auto-created by the app. Create and register them manually:

1. Create `Fortuna HQ`.
2. Create `Fortuna Ops` if using 3-group mode.
3. Create `Fortuna Alerts`, or use it as the combined Ops/Alerts group in 2-group mode.
4. Add `@FortunaSolstice_Bot`.
5. Open each group/channel.
6. Use Settings -> Notification Targets -> Register Current Chat as Fortuna Target.
7. Set purpose:
   - Fortuna HQ -> `hq`.
   - Fortuna Ops -> `ops`.
   - Fortuna Alerts -> `alerts`.
8. Use routing preview before sending real group alerts.

## Production Readiness Card

Sprint 26 adds a notification readiness card to Settings -> Production Observability.

It checks whether active targets exist for:

- Fortuna HQ
- Fortuna Ops
- Fortuna Alerts

The card never shows raw Telegram chat IDs. Use Settings -> Notification Targets for target details and masked identifiers.

Do not register unrelated Telegram chats. Do not expose raw chat IDs in screenshots, audits, events, or support messages.

## Routing Smoke Test

Settings -> Notification Group Setup -> Run Routing Test creates durable delivery-attempt records:

- HQ, Ops, and Alerts: previewed as delivery attempts by default.
- Legacy Testing Sandbox targets can still receive a safe test if one exists.
- Missing targets: shown as skipped/missing.

Every attempt is audited and event-logged. Raw chat IDs remain encrypted at rest and masked in Telegram.

## Sprint 28 Notification Group Pilot

Settings -> Notification Group Pilot gives the owner a single readiness view for the three required Fortuna spaces:

- Fortuna HQ
- Fortuna Ops
- Fortuna Alerts

It shows configured/missing status, last delivery state, and the manual activation checklist. The Register This Chat button must be used from inside the Telegram group or channel being registered.

The pilot keeps real delivery conservative:

- Routing tests are simulated unless the owner explicitly sends a real test to an approved target.
- Raw chat IDs remain hidden.

## Sprint 39 Alert Pilots

Settings -> Notification Group Pilot can run safe internal pilots:

- Creator Alert Pilot: creates a demo creator, demo creator-post alert, opportunity, strategies, learning event, and notification routing result.
- Own Post Alert Pilot: creates a demo own-post alert, opportunity, follow-up task, learning event, and notification routing result.

If no Telegram target is configured, the pilot does not crash or spam. It creates a recommendation such as "Register Fortuna Alerts Target" and records a safe routing event. If a target is configured, delivery attempts are created as pending/skipped/sent according to the explicit test path.

## Safety Rules

- Only Owner/Admin can manage targets.
- Raw chat IDs are encrypted at rest.
- Telegram UI shows masked chat IDs only.
- Real sends require an explicit owner-approved target action.
- Do not send to real operations or alerts channels until the owner approves routing activation.
- Respect availability and quiet hours for non-critical user-targeted notifications.
- Audit/event metadata must never contain tokens, raw chat IDs, credentials, proxy passwords, or verification codes.

## Delivery Attempt Records

`notification_delivery_attempts` stores one row per send attempt:

- target
- event type
- status: `pending`, `sent`, `failed`, or `skipped`
- safe error message
- attempted timestamp
- safe metadata

The service creates an audit record for every attempted send. Successful and failed outcomes also emit EventLog rows. Repeated failed deliveries generate a warning recommendation so operators can repair the target.

The Telegram UI still masks chat IDs. Failure text is deliberately coarse and redacted if it looks like it might contain tokens, keys, passwords, credentials, or chat IDs.

## Intelligence Signal Routing

Critical intelligence signals summarize recurring or high-confidence risks, such as repeated proxy failures, production instability, recurring incidents, or overloaded users. When a critical signal is created, routing may create notification delivery attempts for active owner, incidents, and operations targets.

Signal routing must stay digest-friendly:

- summarize the signal title, severity, entity, and confidence.
- avoid raw logs and raw Telegram chat IDs.
- avoid credentials, proxy passwords, verification codes, tokens, session strings, or platform session data.
- route repeated signals as records/operators can inspect, not chat spam.

## Future Work

- Add owner-approved routing activation per purpose.
- Add group/channel setup verification once Fortuna OS Telegram groups are created.

## Automation Routing

Automation notifications should stay summary-first.

Suggested routing:

- High-risk approval needed -> owner/HQ.
- Simulation completed -> automation logs.
- Automation run succeeded -> automation logs.
- Automation run failed -> automation logs and incidents when severity is high/critical.
- Task or incident automation result -> operations.
- Proxy repair failure -> incidents and automation logs.
- Daily digest automation -> owner/HQ and operations after target approval.

Low-risk run details should be grouped into run history instead of sent as separate chat messages. Telegram notifications should link operators back to the relevant automation rule, simulation, run, or incident screen when possible.

Delivery attempts must still be recorded for every real send. Metadata should include only safe IDs, event type, purpose, status, and coarse error messages.

## Notification Digest Mode

Notification Digest Mode stores bundled updates in `notification_digests`.

Use it for:

- skipped low-priority delivery attempts.
- pending non-critical updates.
- grouped operational noise.

Do not use it for:

- critical incidents.
- owner approval gates.
- production outage alerts.
- security-sensitive events.

Digest items store safe references only. They must not include message bodies, secrets, raw chat IDs, platform credentials, 2FA codes, or proxy passwords.
