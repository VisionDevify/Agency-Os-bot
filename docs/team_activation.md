# Team Activation

Team Activation measures whether a team member is ready to use Fortuna OS day to day.

It is a friendly rollout signal, not a punishment score.

## Activation Score

Sprint 18 calculates a simple score and QA flags from:

- onboarding complete.
- availability set.
- role assigned.
- first task completed.
- first opportunity reviewed.
- Help Center viewed.
- timezone confirmed.
- pending approval status.
- missing assigned work.
- chatter model/opportunity assignment gaps.

Managers can open Team Activation QA to see who needs onboarding help, role assignment, timezone setup, availability setup, assigned work, or chatter-specific assignment.

## Chatter Home And Workspace

Chatters primarily see:

- My Models.
- My Opportunities.
- My Tasks.
- Availability.
- Help.

Opportunity workspace details include:

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
- overdue opportunities.
- completed today.
- distribution by model.
- distribution by niche.

## Notification Improvements

Sprint 18 adds routing keys for:

- creator watch alerts.
- opportunity assignment alerts.
- high-priority opportunity alerts.
- own post alerts.
- result recorded alerts.
- opportunity digests.

Routing still uses existing notification targets, delivery attempts, availability rules, and digest mode. Low-priority notifications should be bundled where possible.
