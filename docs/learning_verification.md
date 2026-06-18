# Learning Verification

Sprint 25 verified the learning engine against real service paths rather than only screen rendering.

## Verified Capture Paths

- Task completed -> `LearningEvent` + `OutcomeMemory`
- Task blocked/overdue -> `LearningEvent` + `OutcomeMemory`
- Incident resolved/escalated -> `LearningEvent` + `OutcomeMemory`
- Proxy repair/rotation/location outcomes -> `LearningEvent` + `OutcomeMemory`
- Automation run success/failure/skipped -> `LearningEvent` + `OutcomeMemory`
- Recommendation feedback/status -> `LearningEvent`, `OutcomeMemory`, and `ConfidenceRecord`
- Opportunity result -> `LearningEvent`, `OutcomeMemory`, score/confidence adjustment
- Notification delivery success/failure -> `LearningEvent` + `OutcomeMemory`

## Verified End-To-End Chain

Sprint 25 tests verify this safe chain:

User action -> DB record -> AuditLog -> EventLog -> LearningEvent -> OutcomeMemory -> ConfidenceRecord when feedback changes confidence.

## Playbook Memory

Seeded playbooks remain deterministic and human-approved:

- Proxy Recovery
- Account Attention
- Critical Incident
- Overdue Task Recovery
- Notification Failure
- Automation Failure
- Opportunity Learning

High-risk playbooks are not auto-run. They can be suggested, reviewed, and tracked through `playbook_runs`.

## Safety

Learning metadata is recursively sanitized. Learning records must not store tokens, passwords, platform credentials, proxy passwords, raw chat IDs, verification codes, session strings, or code hashes.

## Known Limits

- Confidence scoring is intentionally conservative and deterministic.
- Learning does not modify code or automatically approve risky automations.
- Outcome quality improves only when operators record outcomes consistently.
