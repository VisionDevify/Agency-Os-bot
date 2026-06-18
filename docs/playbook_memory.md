# Playbook Memory

Playbooks are reusable operating memories for recurring Fortuna OS situations.

They describe:

- what triggers the playbook.
- how to diagnose the issue.
- how to resolve it.
- how to verify recovery.
- how to roll back when rollback is possible.
- what risk level applies.
- how much confidence Fortuna OS currently has in the playbook.

## Seeded Playbooks

- Proxy Recovery Playbook.
- Account Attention Playbook.
- Critical Incident Playbook.
- Overdue Task Recovery Playbook.
- Notification Failure Playbook.
- Automation Failure Playbook.
- Opportunity Learning Playbook.

## Recommendation Matching

The playbook engine ranks matches by:

- source category, such as proxy, incident, task, or automation.
- event type and entity type.
- severity.
- current confidence score.
- historical success/failure counts.

## Run History

`playbook_runs` records each suggestion or use:

- suggested.
- approved.
- running.
- succeeded.
- failed.
- skipped.
- rolled back.

Successful runs raise confidence slightly. Failed or rolled-back runs lower confidence and should move playbooks toward review when patterns repeat.

## Approval Boundary

Playbooks are memory and guidance. They do not bypass automation approval gates, owner approval, permission checks, or simulation requirements. High-risk playbooks should remain operator-approved.
