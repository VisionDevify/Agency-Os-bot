# Codex Context Pack

Future sprint prompts must begin with: "Before changing code, read docs/codex_context.md."

## Project Overview

Fortuna OS is a Telegram-first operations assistant for an agency workflow. It guides owners, managers, chatters, and VAs through setup, opportunities, alerts, proxy management, recovery, and operational health.

Fortuna should feel calm, guided, and trustworthy. Primary screens answer:

1. What is happening?
2. Is anything wrong?
3. What should I do next?

Technical details stay behind Details, Technical Details, or Advanced views.

## Architecture

The app is a Python backend with SQLAlchemy models, Alembic migrations, Telegram screen renderers, service-layer workflows, and Railway production deployment. Telegram UI screens are rendered as text plus inline buttons. Button callbacks are routed through central navigation and callback protection services.

Important layers:

- Models: persistent database entities.
- Services: business rules, status truth, safety gates, scoring, backup, callback, and observability logic.
- Screens: user-facing Telegram text and buttons.
- Docs/tests: safety, verification, and regression coverage.

## Production Truth

Production truth must come from live evidence, not stale recommendations.

Current production safety principles:

- PostgreSQL is required for durable production storage.
- Redis is required for durable polling and callback safety.
- SQLite fallback is not production-safe unless explicitly emergency-enabled.
- `/health`, `/integrity`, `/botstatus`, and Production Observability must not contradict each other.
- Missing setup is not the same as a failed system.

## Recovery Status

Recovery status is evidence-backed only.

Evidence inputs:

- External storage configured and tested.
- Verified backup artifact.
- Verified checksum and encryption/decryptability.
- Restore validation result.
- Backup age and recent failure history.
- Provider availability.

Allowed recovery states:

- `healthy`
- `needs_review`
- `needs_attention`
- `critical`

Never show Protected, Passed, Successful, or Healthy unless supporting records exist.

## Callback Storm Protections

Button presses must never crash the bot worker.

Protections include:

- Per-user callback locking.
- Per-message edit locking.
- Short navigation debounce.
- Separate long-lived idempotency for state-changing actions.
- Safe edit-or-send wrapper.
- Global callback exception boundary.
- Stale navigation session/version handling.

Navigation idempotency must be narrow and short-lived. Back, Home, Help, Refresh, and Main Menu should not become stuck behind broad "Already handled" blocking.

## /start Cleanup Behavior

`/start` should make Fortuna feel like an app reset:

- Delete tracked temporary menu/navigation/help/status/error messages where Telegram permits.
- Preserve alerts, reports, exports, approvals, incidents, and delivery notifications.
- Create one fresh Home screen.
- Mark that message as the only active navigation session.
- Reject old buttons through active navigation session and navigation version checks.

Canonical message labels:

- `temporary_navigation`
- `temporary_help`
- `temporary_status`
- `temporary_error`
- `persistent_alert`
- `persistent_report`
- `persistent_export`
- `persistent_approval`
- `persistent_incident`
- `persistent_delivery`
- `unknown_preserve`

Only `temporary_*` labels are eligible for automatic cleanup.

## Social Intelligence Architecture

Fortuna may analyze compliant, human-provided, official, exported, or approved public social data. Fortuna must not scrape private data, bypass platform limits, or automate platform actions.

Module ownership:

- Comment Intelligence owns comment intake and observations.
- Profile Intelligence owns profile records and repeated-profile detection.
- Discovery owns approved source intake and discovery leads.
- Compliance owns validation gates and logs.
- Opportunity owns conversion, assignment, and outcome tracking.

Shared engines:

- Evaluation scores and ranks only after compliance passes.
- Learning updates memory and confidence from approved events.
- Alert routing sends or simulates approved alerts only.
- Evidence explains why Fortuna made a suggestion.

## Platform Connection Philosophy

Platform Connections use layered truth:

1. Website Reachability
2. Login / Session / API Connection
3. Stats Access
4. Notification Routing
5. Activation Readiness

Truth rules:

- Not connected yet does not mean broken.
- Reachable does not mean logged in.
- Logged in does not mean stats are available.
- Stats available does not mean fresh.
- Healthy is never assumed.

Fortuna may prepare Instagram, X, OnlyFans, Telegram, Email, Backup Storage, and System Alerts connections, but it must never mark a platform connected without successful verification evidence.

## UX Language Rules

Use calm, human wording:

- "Fortuna checked this for you."
- "Nothing urgent here."
- "Next best move..."
- "Ready when you are."
- "This needs your attention."

Avoid developer leakage on simple screens:

- snake_case
- raw IDs
- raw callback names
- raw enum names
- database table names
- metrics walls
- stack traces

Buttons should be emoji-first where practical.

## Status Truth Rules

Use shared status vocabulary where possible:

- `healthy`
- `needs_review`
- `needs_attention`
- `critical`

Overall status is the most severe active validated condition. Historical problems must not appear as current issues after live truth proves they are resolved.

## Compliance Rules

Fortuna may observe, summarize, recommend, and route human-reviewed work.

Fortuna must not:

- auto-post
- auto-comment
- auto-like
- auto-follow
- scrape private data
- evade platform security
- bypass rate limits
- expose secrets
- fabricate connection, stats, backup, restore, notification, or readiness states

Humans execute.

## Protected Behaviors

Always preserve:

- Secrets and credentials.
- Telegram alerts, reports, approvals, exports, incident messages, and delivery notifications.
- Production data unless the owner explicitly approves destructive cleanup.
- Compliance gates around social workflows.
- Honest degraded states when evidence is missing.

## Roadmap

Near-term priorities:

- Finish platform connection activation with secure credential flows.
- Add official/approved connector integrations only when owner-approved.
- Continue mobile Telegram QA.
- Keep reducing developer leakage.
- Expand role-specific workflows once owner setup is stable.
- Strengthen live verification paths for Railway and Telegram.
