# Pattern Recognition

Pattern recognition in Sprint 12 is rule-based and auditable.

## Current Inputs

- `event_logs`
- `audit_logs`
- `incidents`
- `incident_timeline`
- `tasks`
- `proxies`
- `accounts`
- `model_brands`
- `recommendations`
- `notification_delivery_attempts`
- `system_heartbeats`

## Current Patterns

- Recurring proxy failures: same proxy failure events 3 or more times in 24 hours.
- Repeated proxy location mismatch: same proxy mismatch events repeatedly.
- Account health degradation: account status is warning or critical.
- Model health decline: model/brand status is warning or disabled.
- Repeated overdue tasks: same user or model has repeated overdue tasks.
- Incident recurrence: same model/account/proxy has repeated active incidents.
- Notification delivery failure cluster: same target has repeated failed attempts.
- Production instability: service heartbeat is not healthy/running/ok.

## Outputs

Each actionable pattern can create or update:

- `intelligence_signals`
- `issue_patterns`
- deterministic `recommendations`
- `event_logs`
- safe audit records

## Safe Metadata

Pattern metadata can include counts, event IDs, entity type, entity ID, severity, and confidence. It must not include credentials, tokens, platform session data, proxy passwords, raw chat IDs, verification codes, or code hashes.

## Future Rules

Future pattern families should stay deterministic first:

- model health drop over multiple snapshots.
- account auth degradation over multiple snapshots.
- repeated task blockers by department.
- repeated incident escalation by source.
- repair playbook failure recurrence.
