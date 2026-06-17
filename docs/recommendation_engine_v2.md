# Recommendation Engine V2

Sprint 12 upgrades deterministic recommendations with intelligence-backed explanation metadata.

## Recommendation Metadata

New intelligence-backed recommendations can include:

- `reason`
- `confidence_score`
- `source_signal_ids`
- `source_pattern_id`
- `suggested_action`
- related entity type and ID

Telegram exposes this through:

- Executive Dashboard -> Recommendations.
- Recommendation Detail -> Why am I seeing this?

## New Categories

- Reassign Work.
- Review Model Health.
- Review Account Health.
- Replace/Rotate Proxy.
- Investigate Recurring Incident.
- Fix Notification Target.
- Escalate Critical Issue.
- Review Team Availability.
- Clean Up Stale Tasks.

## Status Actions

Recommendations still move through:

- `open`
- `acknowledged`
- `dismissed`
- `resolved`

Status changes audit and emit safe events.

## Learning Feedback

Sprint 15 adds recommendation feedback:

- Useful.
- Not Useful.
- Wrong.
- Needs Review.

Feedback creates a learning event, updates outcome memory, creates a confidence record, and audits a safe summary. One click only nudges confidence lightly; repeated evidence should matter more than a single reaction.

## Safety

Recommendation metadata must not include tokens, credentials, verification codes, proxy passwords, raw chat IDs, or platform session data. Recommendations should explain and guide. They should not execute risky actions directly.
