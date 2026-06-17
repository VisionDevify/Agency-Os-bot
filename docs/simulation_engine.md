# Simulation Engine

The simulation engine previews what an automation would do before any live execution.

## Guarantees

- Simulations do not mutate production entities.
- Simulations write `automation_simulation_runs`.
- Simulations emit `automation.simulated`.
- Simulations audit safe summaries only.
- Simulations expire after the configured review window.

## Output

Each simulation stores:

- automation rule reference.
- automation name and type.
- status.
- simulator user.
- target scope.
- would-trigger count.
- would-succeed estimate.
- would-fail estimate.
- affected entities, safe only.
- impact summary, safe only.
- warnings.
- risk level.
- created, finished, and expiry timestamps.

## Impact Preview

Impact previews answer:

- What starts it?
- Checks before running.
- What it will do.
- What could be affected.
- How to undo it.
- What cannot be fully rolled back.

## Safety

High-risk and critical-risk simulations do not grant permission to run. They only provide review context. Owner approval is still required before activation.
