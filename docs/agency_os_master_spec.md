# Agency OS Master Spec

## Project Vision

Agency OS Bot is the secure Telegram command center for agency operations. Its first job is to make ownership, access control, auditability, and navigation reliable before adding business automations. The bot should behave like an operations console: fast to scan, hard to misuse, and careful with secrets.

The long-term system should coordinate users, roles, models and brands, social or platform accounts, proxy health, tasks, incidents, reports, automations, simulation mode, self-healing, and an AI operations brain that can explain status and recommend safe actions.

## Completed Sprints

- Sprint 1: secure Python foundation with FastAPI, aiogram, PostgreSQL, SQLAlchemy, Alembic, Docker Compose, pytest, `.gitignore`, and placeholder-only `.env.example`.
- Sprint 1.5: Telegram inline UI framework with dashboard, main menu, back/main controls, and in-place message edits to avoid chat spam.
- Sprint 2: persistent PostgreSQL-backed users, roles, permissions, owner setup, pending users, audit logs, and real permission checks.
- Sprint 2.5/3: foundation hardening, living architecture docs, stricter audit naming, masked audit metadata, pending-user queue, user admin workflows, role assignment/removal, role permission editing, owner protection checks, and expanded tests.
- Sprint 4: Models/Brands command center, team assignments, model health scoring, model-specific audit history, dashboard model metrics, and lightweight model event emission.
- Sprint 5: Accounts foundation attached to Models/Brands, account status/auth tracking, secure auth-session records, hashed 2FA submission flow, account health, dashboard account metrics, and account audit history.
- Sprint 6: Infrastructure intelligence layer with Proxy Vault, encrypted proxy passwords, session rotation/rollback, proxy health scoring, account proxy assignment, location verification, proxy incidents, simulation mode, and self-healing V1.
- Sprint 7: Operations command layer with real tasks, real incidents, escalation paths, department dashboards, daily company briefing, team accountability reporting, and operations event emission.
- Sprint 8: Executive intelligence and Railway production readiness with database-backed daily briefings, accountability snapshots, EventLog, Notification Targets, Executive Dashboard V2, operations reporting, and Railway deployment documentation/config.
- Sprint 9: Production activation preparation, notification routing V1, automation simulation run records, deterministic recommendations, system heartbeats, Bot Status, and Executive Command Center upgrades.
- Sprint 10: Production launch approval boundaries, Railway trial-credit blocker documentation, notification delivery attempt persistence, production status upgrades, and production smoke-test documentation.

## Roadmap

- Sprint 11: Telegram group/channel activation after owner approval, Railway production project creation, and production smoke-test execution.
- Sprint 12: Self-healing playbooks, repair approval gates, and richer repair event tracking.
- Sprint 12: AI Operations Brain for summaries, anomaly explanations, and recommended next actions.

## Core Modules

- Dashboard: operational summary for users, accounts, proxies, tasks, and incidents.
- Models: central command object for model/brand identity, team assignments, health, future accounts, work, incidents, reports, revenue, and audit history.
- Users: Telegram principals, statuses, role assignment, and recent audit context.
- Roles: default and custom role records with permission memberships.
- Permissions: named capability flags checked by services and Telegram navigation.
- Audit Logs: append-only safety trail for important actions and denied attempts.
- Accounts: Model/Brand-attached account inventory for Instagram, X, OnlyFans, Email, and Other, including auth-state tracking, credential references, short-lived auth sessions, and hashed verification-code submissions.
- Proxies: encrypted Proxy Vault with account assignment, session suffix rotation, rollback, health scoring, location verification, simulation, and repair workflows.
- Tasks: real work queue with status, priority, assignment, due dates, completion, model/account attachment, and audit/event history.
- Incidents: real escalation and resolution records with severity, source, assignment, proxy/account/model attachment, escalation history, and audit/event history.
- Reports: database-backed daily briefing, accountability snapshots, executive command center, operations dashboard, chatter dashboard placeholder, VA dashboard placeholder, and event-backed report view/generation tracking.
- Notifications: encrypted Telegram notification targets, purpose-based routing rules, masked chat IDs, testing-only safe sends, and durable delivery-attempt records.
- Automations: placeholder resource model plus durable simulation runs for preview/approve workflows.
- Recommendations: deterministic operational recommendations generated from database state.
- System Status: service heartbeats for API, bot, db, redis, and Railway deployment state.
- Settings: administrative utilities including audit log access, Bot Status, and Notification Targets.

## Roles

- Owner: bootstrap authority and emergency bypass. Owners bypass permission checks and are protected from lockout.
- Admin: broad administrative operator. Can manage users, roles, modules, automations, and audit visibility.
- Manager: operational manager. Can manage accounts, tasks, incidents, reports, and automations.
- VA: support operator for dashboard, tasks, and upload-oriented workflows.
- Chatter Manager: team lead for chatter dashboards, team management, and content approval.
- Senior Chatter: elevated chatter role for approval and upload workflows.
- Chatter: chatter dashboard and upload workflows.
- Viewer: read-focused dashboard access.
- Model/Client: limited dashboard and content approval role.

## Permissions

Default permissions:

- `view_dashboard`
- `manage_users`
- `manage_roles`
- `manage_accounts`
- `manage_proxies`
- `manage_tasks`
- `manage_incidents`
- `manage_reports`
- `manage_automations`
- `view_audit_logs`
- `approve_content`
- `upload_content`
- `view_credentials`
- `rotate_proxy`
- `resolve_incidents`
- `view_chatter_dashboard`
- `manage_chatter_team`

Owner bypass is implemented at the service layer and should remain the final authority. Permission checks should be called from workflows before management actions and from Telegram navigation before restricted screens render.

Model/Brand assignment changes require `manage_users` or `manage_accounts`. Model creation, status updates, and archival require `manage_accounts`.

## Security Rules

- Never commit `.env`, bot tokens, owner IDs, encryption keys, database passwords, or live session strings.
- `.env.example` contains placeholders only.
- Do not log raw secrets, raw bot tokens, or raw session strings.
- Audit details must avoid secrets and should mask sensitive identifiers such as Telegram IDs.
- Unknown Telegram users are created as pending and inactive unless they match `OWNER_TELEGRAM_ID`.
- Pending, denied, and disabled users cannot access operational screens.
- Non-owner users cannot assign Owner role.
- Users cannot edit their own roles unless they are Owner.
- The final Owner cannot be disabled and cannot lose the Owner role.
- Owner role deletion is blocked.
- Owner role permissions are treated as lockout-sensitive and cannot be removed through normal editing.
- Account credential values are never stored directly; account records may only keep credential references.
- Plaintext passwords and plaintext 2FA codes must never be stored, logged, audited, or shown in Telegram.
- Verification codes are hashed immediately, expire quickly, and the bot should try to delete Telegram messages that contain submitted codes.
- Proxy passwords are encrypted at rest and never shown in Telegram, events, audits, or logs.
- Proxy session suffixes may be shown because they are operational identity controls, but raw provider passwords and credentials must remain hidden.
- Future real platform connections should prefer official APIs or OAuth where available.
- Destructive repo or database cleanup requires explicit confirmation.

## Audit Philosophy

The audit log is the safety record, not a debug dump. It should answer who attempted what, against which resource, whether it succeeded, and when. It should not store secrets or unnecessarily expose raw identifiers.

Important actions should use stable event-style names, such as:

- `user.pending_created`
- `user.approved`
- `user.denied`
- `user.disabled`
- `user.reactivated`
- `role.assigned`
- `role.removed`
- `permission.added_to_role`
- `permission.removed_from_role`
- `model.created`
- `model.updated`
- `model.disabled`
- `model.archived`
- `member.assigned`
- `member.removed`
- `model.health.changed`
- `account.created`
- `account.updated`
- `account.disabled`
- `account.archived`
- `account.auth_session.started`
- `account.auth_session.waiting_for_code`
- `account.auth_code.submitted`
- `account.auth_session.success`
- `account.auth_session.failed`
- `account.auth_session.expired`
- `account.auth_status.changed`
- `proxy.created`
- `proxy.assigned`
- `proxy.unassigned`
- `proxy.health.changed`
- `proxy.rotation.started`
- `proxy.rotation.succeeded`
- `proxy.rotation.failed`
- `proxy.location.mismatch`
- `proxy.incident.created`
- `proxy.repair.succeeded`
- `proxy.repair.failed`
- `task.created`
- `task.assigned`
- `task.started`
- `task.blocked`
- `task.completed`
- `task.archived`
- `task.overdue`
- `incident.created`
- `incident.assigned`
- `incident.escalated`
- `incident.resolved`
- `incident.archived`
- `briefing.generated`
- `briefing.viewed`
- `briefing.send_requested`
- `accountability.generated`
- `accountability.viewed`
- `dashboard.viewed`
- `report.viewed`
- `notification_target.created`
- `notification_target.updated`
- `notification_target.disabled`
- `notification_target.tested`
- `notification.routed`
- `notification.delivery_attempted`
- `notification.delivery_succeeded`
- `notification.delivery_failed`
- `automation.simulated`
- `automation.simulation.approved`
- `automation.simulation.rejected`
- `recommendation.generated`
- `recommendation.acknowledged`
- `recommendation.dismissed`
- `recommendation.resolved`
- `recommendation.status_changed`
- `heartbeat.status_changed`
- `access.denied`
- `owner.protection_triggered`

## Telegram UX Philosophy

Telegram is the operator console, so navigation should be calm and predictable:

- Use inline keyboards for all primary navigation.
- Every screen should expose Back and Main Menu controls.
- Navigation should edit the current bot message whenever possible.
- Dashboard refreshes should happen in place.
- Avoid sending new messages for menu movement.
- Denied, pending, and disabled states should show short human-readable messages.

## Future Modules

- Models/Brands: model and brand profiles, ownership, account grouping, and operating rules.
- Accounts: account inventory, Model/Brand attachment, status, auth status, credential references, secure auth-session handling, and hashed verification-code workflows.
- Proxy Vault: proxy records, encrypted passwords, health checks, rotation events, account assignment, and repair workflows.
- Tasks: assigned work, status movement, overdue queues, model/account attachment, and SLA signals.
- Incidents: incident creation, triage, severity, ownership, escalation, and resolution.
- Reports: operational summaries, daily briefings, team accountability reports, audit summaries, health metrics, and exportable views.
- Automations: repeatable workflows with simulation mode before live execution.
- Simulation Mode: dry-run execution that records intended changes without performing risky actions.
- Self-Healing: playbooks that detect failures, attempt safe repairs, and emit repair events.
- AI Operations Brain: contextual summaries, anomaly explanations, and recommended actions based on events and current state.

## Model/Brand Command Center

Model/Brand is now the central object. Future operational data should attach to it directly or through account/task/incident/report relationships.

Intended relationship map:

- Instagram Accounts
- X Accounts
- OnlyFans Accounts
- Assigned Chatters
- Assigned Managers
- Assigned VAs
- Tasks
- Incidents
- Reports
- Revenue
- Health
- Audit History

Current team relationship types:

- `manager`
- `chatter_manager`
- `senior_chatter`
- `chatter`
- `va`
- `viewer`

Current health score inputs:

- open incidents
- disabled accounts
- warning accounts
- unassigned manager
- unassigned chatter team

Accounts now attach directly to Model/Brand records. Revenue, Proxy Assignments, Automation Rules, Daily Briefings, and AI Operations Brain integration are intentionally TODO hooks until those modules have real records.

## Accounts Foundation

Accounts are operational records, not automation clients. Sprint 5 deliberately avoids scraping, bypassing security, or risky platform automation.

Supported platforms:

- `instagram`
- `x`
- `onlyfans`
- `email`
- `other`

Current account state:

- Status: `healthy`, `warning`, `critical`, `disabled`, or `archived`.
- Auth status: `not_connected`, `connected`, `needs_login`, `needs_2fa`, `expired`, or `locked`.
- Credential references: `credential_ref`, `connected_email_ref`, and masked phone metadata only.
- Auth sessions: short-lived records for login or 2FA handling.
- Verification codes: hashed only, never stored as plaintext.

The Telegram account workflow supports viewing accounts, adding an account to a Model/Brand, filtering by model or platform, viewing accounts needing attention, starting an auth session, submitting a verification code, marking connected or needs-login, disabling, archiving, and viewing account-specific audit history.

Account health currently considers disabled or archived state, auth state, critical/warning flags, and missing Model/Brand attachment. Proxy health is intentionally a future hook.

## Infrastructure Intelligence Layer

Sprint 6 introduces the first active maintenance subsystem.

Proxy Vault records store:

- provider, host, port, base username, generated username, and current session suffix
- encrypted password only, never plaintext
- target and detected location
- health score, status, latency, test counters, mismatch counters, and rotation counters
- last health check, last rotation, and last successful rotation timestamps

Session identity is driven by `session_suffix`. Changing any character creates a new provider session identity. Rotation stores current and previous sessions and appends `proxy_rotation_history` records. Rollback swaps back to the previous session when available.

Location verification compares detected country, state, and optional city against the target. If location does not match, the service can rotate again until a match or max attempts is reached. Mismatches emit safe events and can create proxy incidents.

Proxy health score is currently deterministic and based on:

- success/failure rate
- latency
- location mismatches
- rotation success/failure rate
- disabled state

Self-Healing V1 follows the Agency OS safety pattern:

- Preview
- Simulate
- Approve
- Execute

The current repair workflow can rotate and retest a failing proxy, close open proxy incidents when repaired, or create a critical incident when repair fails. Automatic repair activation remains gated by owner approval; simulation mode shows what would rotate, repair, and fail without applying changes.

## Operations Command Layer

Sprint 7 turns daily operations into first-class records.

Tasks now support:

- `open`, `in_progress`, `blocked`, `complete`, and `archived` status.
- `low`, `normal`, `high`, and `urgent` priority.
- assignment to a user.
- optional Model/Brand and Account attachment.
- optional due date and completion timestamp.
- Telegram flows for viewing, creating, reassignment, blocking, completion, archiving, overdue work, and assigned work.

Incidents now support:

- `info`, `warning`, and `critical` severity.
- `open`, `investigating`, `resolved`, and `archived` status.
- `manual`, `account`, `proxy`, `automation`, and `system` source types.
- optional Model/Brand, Account, and Proxy attachment.
- assignment, escalation, resolution notes, and escalation history.

Escalation paths:

- Chatter issues: Chatter -> Senior Chatter -> Chatter Manager -> Manager -> Owner.
- VA issues: VA -> Manager -> Owner.
- Proxy/System issues: Admin/Manager -> Owner.

Department dashboards:

- Executive Dashboard: models, accounts, proxy health, open/overdue work, incidents, and completed tasks today.
- Operations Dashboard: pending/blocked work, incidents by severity, account warnings, and proxy warnings.
- Chatter Dashboard: assigned models, open tasks, escalations, and notes placeholder.
- VA Dashboard: assigned models/accounts, upload/task placeholder, and overdue items.

Daily Company Briefing aggregates agency health, model/account/proxy health, incidents, completed work, overdue work, top users by completed tasks, recent audit highlights, and recommended actions. Team Accountability summarizes each user by open tasks, completed work today, overdue work, assigned incidents, last seen, and roles.

## Foundation Hardening Review

GREEN:

- Owner bootstrap is centralized and idempotent.
- Permission checks are concentrated in service/navigation layers instead of scattered through handlers.
- Telegram navigation edits existing messages and avoids chat spam.
- `.env` is ignored, and `.env.example` is placeholder-only.
- Core auth tables use unique constraints and join-table uniqueness to prevent duplicate memberships.
- Audit logging exists for admin actions and denied access attempts.
- Account auth flow stores verification-code hashes only and uses safe audit metadata.
- Proxy Vault encrypts proxy passwords and keeps Telegram/audit views credential-safe.
- Infrastructure dashboard now summarizes proxy health, assignment, rotations, failures, incidents, and average health score.
- Tasks and incidents now have domain models, service-level permission checks, Telegram workflows, and audit-backed events.
- Reports now include daily briefing, accountability, and department dashboards without external analytics.
- Sprint 8 adds dedicated EventLog persistence while preserving audit logs as the operator-facing safety trail.
- Railway readiness files and docs exist, with project creation blocked until explicit owner approval.

YELLOW:

- Audit event names were normalized to event-style names for permission and access events.
- Audit metadata now masks Telegram IDs instead of storing raw IDs for routine admin/user events.
- Pending-user creation is now audited.
- Owner-protection failures are now audited.
- Pending Users navigation was made explicit.
- Role removal choices now show only assigned roles.
- User status now has a database check constraint.
- Accounts graduated from placeholder resources to Model/Brand-attached records with platform, account status, auth status, and health constraints.
- Proxies and incidents graduated from placeholder resources to domain tables while preserving legacy placeholder columns for migration safety.
- Tasks graduated from placeholder resources to a real domain table while preserving legacy placeholder columns in PostgreSQL for migration safety.
- Sprint 6 mojibake in health labels was cleaned to explicit Unicode escapes.

RED:

- The original `users.role_id` column exists in the earliest migration but is not used by the current model. It should be removed in a future cleanup migration only after explicit approval because it is a schema deletion.
- EventLog is now a lightweight event sink. A queue/stream should wait until real automation/reporting consumers need asynchronous delivery.
- Reports and automations are still placeholder tables. Current generated report screens are computed from live records and audit events.
- Proxy health tests are simulated service results until a real provider/network adapter is introduced.
- Railway has no project/services in the inspected workspace yet. Sprint 10 observed a trial/credit boundary, so production deploy still requires explicit owner approval before creating API, bot worker, PostgreSQL, and Redis services and setting variables in Railway.

## Executive Intelligence Layer

Sprint 8 makes reporting durable and executive-facing.

Executive Dashboard V2 shows:

- agency health score
- model health counts
- account health/auth attention counts
- proxy health and accounts missing proxy
- open and overdue work
- open and critical incidents
- today's completed tasks
- recent high-risk events

Daily Company Briefings are persisted in `daily_briefings` with a date, generator, health score, summary text, metrics JSON, recommendations JSON, and timestamp. The Telegram reports screen supports generating today's briefing, viewing the latest briefing, refreshing, and safe send placeholders for owner and operations destinations.

Team Accountability now writes `accountability_snapshots` per user. Scores are intentionally lightweight visibility signals, not punitive metrics. Current inputs include open assigned tasks, completed tasks today, overdue tasks, open assigned incidents, resolved incidents today, last seen time, and roles.

Notification Targets are placeholders for future routing. They can represent Telegram users, groups, or channels for owner, operations, incidents, automation logs, or testing purposes. Chat IDs are encrypted or omitted and are never shown raw in Telegram.

EventLog is the durable lightweight event feed for reporting and future automations. It stores event type, actor, entity type/id, safe metadata, and timestamp. AuditLog remains the human safety trail.

## Production Activation And Command Center

Sprint 9 turns the executive view into a live company command center without adding risky platform automation.

Executive Command Center now includes:

- Agency Health Score.
- Operational status banner.
- critical alerts.
- top deterministic recommendations.
- shortcuts for daily briefing, accountability, infrastructure, incidents, and Bot Status.
- production status, last deployment status, last bot heartbeat, and last event logged.

Notification Routing V1 uses `notification_targets` with encrypted chat IDs and purpose-based routing:

- Daily Briefing -> owner + operations.
- Accountability Report -> operations.
- Critical Incident -> owner + incidents.
- Proxy Repair Failed -> incidents + automation logs.
- Proxy Repair Succeeded -> automation logs.
- Deployment Event -> testing + owner.
- Automation Simulation -> automation logs.

Only Owner/Admin can manage notification targets. Normal Telegram views mask chat IDs. Test sends are intentionally limited to active `testing` targets until real groups/channels are approved and configured.

Automation Simulation Runs are durable safety previews. They record what an automation would trigger, would likely succeed, would likely fail, risk level, impact summary, creator, creation time, and expiry. Simulations must not mutate production proxies, accounts, tasks, or incidents.

Recommendations are deterministic for now. They are generated from current database state for issues such as missing proxies, critical incidents, overdue tasks, warning/critical proxies, accounts needing login, models without managers, models without chatter teams, location mismatches, and failed repair attempts.

System Heartbeats track service health for `api`, `bot`, `db`, `redis`, and `railway_deployment`. Heartbeats audit state changes only, not every check.

Sprint 10 adds Notification Delivery Attempts. A real send creates a `pending` attempt and then records `sent`, `failed`, or `skipped`. Failed attempts store only safe/redacted messages, audit delivery failures, emit EventLog rows, and create warning recommendations after repeated failures.

Bot Status now shows environment, API, bot, DB, Redis, Railway deployment status, last heartbeat, last deployment data if available, latest delivery attempt, failed notification count, and latest event type.

## Railway Production Readiness

The repo has a Railway API service config, `/health` endpoint with safe heartbeat checks, Docker `PORT` support, and deployment docs. Railway inspection found the logged-in workspace has zero projects, so no production services or variables currently exist to verify.

Expected production services:

- API service
- Bot worker service
- PostgreSQL
- Redis

Required variables:

- `TELEGRAM_BOT_TOKEN`
- `DATABASE_URL`
- `REDIS_URL`
- `APP_SECRET_KEY`
- `ENCRYPTION_KEY`
- `OWNER_TELEGRAM_ID`

Production blockers are documented in `docs/railway_deployment.md`.
