# Notification Routing

Sprint 9 introduces safe notification routing without spamming real groups or exposing Telegram chat IDs. Sprint 10 adds durable delivery-attempt records for actual send attempts. Sprint 11 adds availability-aware routing and Daily Digest delivery attempts.

## Goals

- Route important Agency OS events to the right Telegram destinations.
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
- Add Current Chat As Target.
- Set Purpose.
- Disable Target.
- Test Send metadata update.
- Send Test Notification to active testing targets only.
- Recent delivery attempts on target detail.
- Daily Digest delivery history.

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

## Future Work

- Add owner-approved routing activation per purpose.
- Add group/channel setup verification once Agency OS Telegram groups are created.
