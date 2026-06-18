# Automation Simulation

Fortuna OS follows the safety posture:

- Preview
- Simulate
- Approve
- Execute

Sprint 9 added durable simulation records without enabling live automation execution. Sprint 14 upgrades this into a full automation builder with rule definitions, simulation impact previews, approvals, run records, step records, and rollback planning.

## Tables

`automation_rules` stores durable automation definitions, including trigger type/config, conditions, actions, rollback plan, risk level, status, creator, approver, and run timestamps.

`automation_simulation_runs` stores dry-run results:

- automation name and type.
- status.
- simulated by user.
- target scope.
- would-trigger count.
- would-succeed count.
- would-fail count.
- safe impact summary.
- risk level.
- creation and expiry timestamps.

## Current Simulation Types And Rules

- Proxy Repair Simulation.
- Daily Briefing Simulation.

Proxy repair simulation reads current proxy health and estimates which proxies would rotate, repair, or fail. It does not rotate sessions or alter proxy/account/incident records.

Daily briefing simulation previews aggregate reporting impact. It does not create a `daily_briefings` row or send notifications.

## Approval Rules

- Simulations do not execute live changes.
- High/critical risk approval requires Owner.
- Approval now gates activation and execution for mutating or high-risk rules.
- Every simulation creates audit and EventLog records.

## Future Work

- Add scheduled execution.
- Add richer no-code rule creation forms.
- Add owner-approved routing activation per notification purpose.
