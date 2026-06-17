# Team Activation

Team Activation measures whether a team member is ready to use Agency OS day to day.

It is a friendly rollout signal, not a punishment score.

## Activation Score

Sprint 17 calculates a simple score from:

- onboarding complete.
- availability set.
- role assigned.
- first task completed.
- first opportunity reviewed.
- Help Center viewed.

Managers can open Team Activation to see who needs onboarding help.

## Chatter Workspace

Chatters see:

- today's opportunities.
- assigned opportunities.
- assigned models.
- assigned tasks.
- recent results.
- recommended next action.

This keeps the daily experience focused and avoids exposing internal systems like Proxy Vault or Automation internals unless permissions explicitly allow it.

## Manager View

Managers see:

- team opportunities.
- unassigned opportunities.
- high-priority opportunities.
- opportunity results.
- top performing angles.
- most active chatters.

## Notification Improvements

Sprint 17 adds routing keys for:

- creator watch alerts.
- opportunity assignment alerts.
- high-priority opportunity alerts.
- opportunity digests.

Routing still uses existing notification targets, delivery attempts, availability rules, and digest mode. Low-priority notifications should be bundled where possible.
