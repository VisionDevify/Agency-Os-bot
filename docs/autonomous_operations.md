# Fortuna OS Autonomous Operations

Sprint 22 shifts Fortuna OS from passive menus toward operational behavior.

When important internal records change, Fortuna OS asks: what should happen next?

## What It Can Do

- Inspect account, model, creator, opportunity, and readiness state.
- Create durable operations workflows.
- Create safe next actions with priority and optional assignee.
- Create follow-ups for unresolved setup or operational issues.
- Create duplicate-safe setup tasks through the activation engine.
- Create recommendations for operator review.
- Route owner attention only for critical or owner-only work.

## What It Cannot Do

- It does not post, comment, like, follow, scrape, or automate external platforms.
- It does not store platform passwords.
- It does not expose bot tokens, proxy passwords, 2FA codes, or raw chat IDs.
- It does not execute high-risk automations without the existing simulation and approval path.

## Autopilots

### Account Autopilot

Runs after account creation.

Checks:

- model assignment
- proxy assignment
- auth status
- manager assignment
- VA assignment
- account readiness

Outputs:

- operations workflow
- setup actions
- recommendations
- follow-up if the account is not ready

### Model Autopilot

Runs after model creation or update.

Checks:

- country
- timezone
- primary platform
- manager
- chatter team

It also refreshes the activation scan so readiness and setup tasks do not wait for a manual owner scan.

### Opportunity Autopilot

Runs after opportunity creation.

Checks:

- score
- strategy generation
- assignee recommendation
- result tracking follow-up

All strategy output remains human-approved guidance only.

### Creator Autopilot

Runs after creator watch creation.

Checks:

- watch profile completeness
- niche validation
- assignee suggestion
- model/opportunity bucket
- strategy category

## Daily Cycle

The daily cycle currently runs safely when triggered by Owner/Admin:

- readiness scan
- recommendation refresh

The readiness scan is the duplicate-safe place where setup tasks are created from detected gaps, so normal create/update flows do not flood dashboards with tasks.

Future scheduling can call the same service once production timing and notification targets are approved.

## Owner Attention

Owner attention is reserved for:

- critical incidents
- high-risk proxy actions
- owner approvals
- final-owner protection events

Routine setup gaps route toward Admin/Manager-style ownership where possible.

## Follow-Ups

Follow-ups are durable reminders tied to a source record. They are used when setup is incomplete, an opportunity needs a result, or a record should be revisited later.

They are operational history and should move through status instead of being deleted.
