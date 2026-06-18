# Outcome Memory

Outcome memory aggregates learning events into durable operational memory.

Instead of treating every incident, repair, automation run, recommendation, or opportunity as isolated, Fortuna OS keeps counters and success rates by deterministic memory key.

## Memory Types

- `proxy_failure`.
- `account_issue`.
- `incident_pattern`.
- `automation_result`.
- `recommendation_result`.
- `opportunity_result`.
- `notification_failure`.
- `task_overdue`.
- `system_health`.

## Memory Keys

Examples:

- `proxy_failure:proxy:12`.
- `automation_result:automation_rule:4`.
- `recommendation_result:recommendation:22`.
- `opportunity_result:opportunity:9`.
- `notification_failure:notification_target:3`.
- `task_overdue:user:17`.

## Aggregates

Each memory tracks:

- occurrences.
- success count.
- failure count.
- partial count.
- ignored count.
- success rate.
- last outcome.
- last seen time.
- deterministic summary.

## Use Cases

Outcome memory powers:

- executive memory briefing.
- playbook confidence.
- automation learning.
- opportunity scoring adjustments.
- repeated failure detection.
- future AI operations explanations.

## Safety

Outcome memory stores safe summaries and metadata only. It must never store credentials, tokens, 2FA codes, proxy passwords, raw platform sessions, or raw Telegram chat IDs.
