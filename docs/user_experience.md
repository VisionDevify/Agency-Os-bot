# User Experience

Agency OS should feel like a calm company command center, not a technical admin panel.

## Human-Friendly Labels

- Intelligence Signals -> Things To Watch
- Issue Patterns -> Recurring Problems
- Outcome Memory -> What We've Learned
- Executive Insights -> Management Insights

The underlying database and code can keep precise technical names, but Telegram screens should use language that team members understand quickly.

## Personalized Dashboard

Every active user should see:

- welcome back
- role
- availability status
- tasks due today
- overdue items
- assigned models
- recommended action
- performance snapshot
- recent activity

Owner/Admin/Manager users can still open the full command center.

## Daily Experience

The Daily Experience screen gives one daily work view:

- morning/afternoon/evening greeting
- role
- today's priorities
- tasks due
- open incidents
- recommendations
- quick actions

This should become the default daily habit screen for non-admin users.

## Notification Digest Mode

Low-priority updates can be bundled into `notification_digests`.

Critical alerts still bypass digest mode and route through the incident/owner paths.

## Sprint 19 Clarity Pass

Every Telegram screen should answer three questions quickly:

- Where am I?
- What is this for?
- What should I do next?

Empty states should be instructional:

- No models yet -> create the first model/brand.
- No accounts yet -> create a model first, then attach accounts.
- No opportunities yet -> add a creator, watch an own post, or create one manually.

Button order should put the most common setup or daily action first. Advanced systems such as Proxy Vault, Intelligence internals, and Automation internals stay owner/admin-only unless a role explicitly has permission.

Simplified homes:

- Chatter: My Models, My Opportunities, My Tasks, Availability, Help.
- VA: My Models, My Accounts, My Tasks, Availability, Help.
- Manager: Team, Models, Tasks, Incidents, Opportunities, Reports.
- Owner/Admin: Executive Command Center, Intelligence, Models, Accounts, Proxies, Operations, Reports, Automation, Settings, Setup Agency, First Day Plan.
