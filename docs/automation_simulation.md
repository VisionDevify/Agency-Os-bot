# Automation Simulation

Agency OS follows the safety posture:

- Preview
- Simulate
- Approve
- Execute

Sprint 9 adds durable simulation records without enabling live automation execution.

## Tables

`automation_rules` is a future-ready placeholder for automation definitions.

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

## Current Simulation Types

- Proxy Repair Simulation.
- Daily Briefing Simulation.

Proxy repair simulation reads current proxy health and estimates which proxies would rotate, repair, or fail. It does not rotate sessions or alter proxy/account/incident records.

Daily briefing simulation previews aggregate reporting impact. It does not create a `daily_briefings` row or send notifications.

## Approval Rules

- Simulations do not execute live changes.
- High/critical risk approval requires Owner.
- Approval is a placeholder state until a future sprint builds execution playbooks.
- Every simulation creates audit and EventLog records.

## Future Work

- Add automation builder UI.
- Add live execution records.
- Add owner-approved execution gates.
- Add event delivery and rollback tracking.
