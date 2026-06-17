# Notification Routing

Sprint 9 introduces safe notification routing without spamming real groups or exposing Telegram chat IDs.

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

## Telegram UI

Settings -> Notification Targets supports:

- View Targets.
- Add Target placeholder.
- Add Current Chat As Target.
- Set Purpose.
- Disable Target.
- Test Send metadata update.
- Send Test Notification to active testing targets only.

## Safety Rules

- Only Owner/Admin can manage targets.
- Raw chat IDs are encrypted at rest.
- Telegram UI shows masked chat IDs only.
- Test sends are limited to active `testing` targets.
- Do not send to real operations/incidents channels until the owner approves routing activation.
- Audit/event metadata must never contain tokens, raw chat IDs, credentials, proxy passwords, or verification codes.

## Future Work

- Add `event_deliveries` for per-target delivery attempts.
- Add owner-approved routing activation per purpose.
- Add group/channel setup verification once Agency OS Telegram groups are created.
