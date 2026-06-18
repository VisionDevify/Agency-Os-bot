# Notification Routing

Sprint 9 introduces safe notification routing without spamming real groups or exposing Telegram chat IDs. Sprint 10 adds durable delivery-attempt records for actual send attempts. Sprint 11 adds availability-aware routing and Daily Digest delivery attempts. Sprint 12 adds critical intelligence signal routing through the same safe delivery-attempt path. Sprint 16 adds Notification Digest Mode for bundling low-priority updates. Sprint 17 adds opportunity and creator-watch routing keys. Sprint 18 adds digestable creator, own-post, assignment, high-priority opportunity, and result-recorded events. Sprint 27 adds Notification Group Setup and a safe routing smoke test.

## Goals

- Route important Fortuna OS events to the right Telegram destinations.
- Keep raw chat IDs encrypted and hidden from normal UI.
- Allow safe testing before real production delivery.
- Audit and event-log every routing configuration change.

## Target Purposes

- `owner`: owner and executive alerts.
- `operations`: daily operations, accountability, and task/report summaries.
- `incidents`: critical incidents, account/proxy failures, and escalations.
- `automation_logs`: simulation results, repair attempts, and system automation events.
- `testing`: safe sandbox for test sends and deployment checks.

## Routing Rules

- Daily Briefing -> owner + operations.
- Accountability Report -> operations.
- Critical Incident -> owner + incidents.
- Proxy Repair Failed -> incidents + automation logs.
- Proxy Repair Succeeded -> automation logs.
- Deployment Event -> testing + owner.
- Automation Simulation -> automation logs.
- Daily Digest -> owner/HQ + operations, depending on the requested purpose.
- Task Assigned -> assigned user when available; otherwise operations.
- Overdue Task -> operations.
- Escalated Task -> operations + owner.
- Escalated Incident -> owner + incidents.
- Critical Intelligence Signal -> owner + incidents + operations.
- Creator Watch Created -> operations.
- Creator Assigned -> operations.
- Own Post Added -> operations.
- Opportunity Created -> operations.
- Opportunity Assigned -> operations.
- High Priority Opportunity -> owner + operations.
- Opportunity Result Recorded -> operations.
- Opportunity Digest -> operations.
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

- Required target readiness for HQ, Operations, Incidents, Automation Logs, and Testing Sandbox.
- Register Current Chat as Fortuna Target from the Telegram group/channel being registered.
- Run Routing Test.
- Last delivery status per purpose.
- Direct link to the manual group-registration help.

## Manual Group Registration

Fortuna OS notification groups/channels are not auto-created by the app. Create and register them manually:

1. Create `Fortuna OS - HQ`.
2. Create `Fortuna OS - Operations`.
3. Create `Fortuna OS - Incidents`.
4. Create `Fortuna OS - Automation Logs`.
5. Create `Fortuna OS - Testing Sandbox`.
6. Add `@FortunaSolstice_Bot`.
7. Open each group/channel.
8. Use Settings -> Notification Targets -> Register Current Chat as Fortuna Target.
9. Set purpose:
   - HQ -> `owner`.
   - Operations -> `operations`.
   - Incidents -> `incidents`.
   - Automation Logs -> `automation_logs`.
   - Testing Sandbox -> `testing`.
10. Send test notifications only to the Testing Sandbox target until the owner approves broader delivery.

## Production Readiness Card

Sprint 26 adds a notification readiness card to Settings -> Production Observability.

It checks whether active targets exist for:

- HQ
- Operations
- Incidents
- Automation Logs
- Testing Sandbox

The card never shows raw Telegram chat IDs. Use Settings -> Notification Targets for target details and masked identifiers.

Do not register unrelated Telegram chats. Do not expose raw chat IDs in screenshots, audits, events, or support messages.

## Routing Smoke Test

Settings -> Notification Group Setup -> Run Routing Test creates durable delivery-attempt records:

- Testing Sandbox: one real safe test message if configured.
- HQ, Operations, Incidents, Automation Logs: simulated/skipped delivery attempts only.
- Missing targets: shown as skipped/missing.

Every attempt is audited and event-logged. Raw chat IDs remain encrypted at rest and masked in Telegram.

## Safety Rules

- Only Owner/Admin can manage targets.
- Raw chat IDs are encrypted at rest.
- Telegram UI shows masked chat IDs only.
- Test sends are limited to active `testing` targets.
- Do not send to real operations/incidents channels until the owner approves routing activation.
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
