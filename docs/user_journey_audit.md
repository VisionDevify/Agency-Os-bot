# Fortuna User Journey Audit

Sprint 42 productization review.

## Design Model

Every primary screen should use three layers:

1. What matters right now.
2. What the user should do next.
3. Technical details, only behind More Details, Technical Details, or Advanced.

The product should never lead with database state, IDs, scores, raw event names, callback names, or internal enum values.

## Owner

What they care about:

- Is Fortuna running?
- What is blocking setup?
- What should be fixed first?
- Are proxies, accounts, alerts, and opportunities ready enough for real operations?

What they should see first:

- Calm Home status.
- Today's focus.
- One next best move.
- Proxy Vault, Opportunities, Help, and More.

What should be hidden:

- Raw readiness scoring internals.
- Audit/event counts.
- Callback diagnostics.
- Detailed automation and intelligence metrics.

Actions that matter most:

- Continue setup.
- Review today's priorities.
- Add or assign a proxy.
- Create opportunities.
- Ask Fortuna for the next action.

## Manager

What they care about:

- Who needs work?
- What needs assignment?
- What alerts need attention?
- Who is blocked or overloaded?

What they should see first:

- Team.
- Assignments.
- Alerts.
- Help.

What should be hidden:

- Proxy Vault internals.
- Automation internals.
- Intelligence/debug screens.
- Owner-only production diagnostics.

Actions that matter most:

- Open Assignments.
- Assign work.
- Review alerts.
- Ask for help when access or routing is unclear.

## Chatter

What they care about:

- What work is waiting on me?
- What opportunities are assigned?
- What alerts need manual review?
- Where do I record results?

What they should see first:

- My Work.
- Opportunities.
- Alerts.
- Help.

What should be hidden:

- Proxies.
- Automations.
- Readiness scoring.
- Production observability.
- Owner/admin setup internals.

Actions that matter most:

- Review opportunities.
- Complete assigned tasks.
- Record opportunity results.
- Keep availability accurate.

## VA

What they care about:

- What tasks are assigned?
- What account/setup work is waiting?
- Where do I ask for help?

What they should see first:

- Tasks.
- Assignments.
- Help.

What should be hidden:

- Intelligence internals.
- Automation internals.
- Production diagnostics.
- Proxy secrets or provider details.

Actions that matter most:

- Open tasks.
- Review assignments.
- Ask Fortuna or a manager when blocked.

## Productization Decisions

- Owner Home remains simple by default, with advanced systems behind More.
- Team homes are intentionally short and role-specific.
- Setup follows one visible path: Model, Account, Proxy, Team, Creators, Opportunities, Alerts, Daily Cycle.
- Help Brain answers with one next step instead of a menu of possibilities.
- Friction items are grouped by severity so UX repair can be prioritized.

## Remaining Watch Areas

- Continue checking major screens for button creep after each sprint.
- Keep Proxy Vault beginner-facing by default.
- Keep diagnostics useful but behind technical details.
- Use owner mobile QA as the final source of truth for Telegram usability.
