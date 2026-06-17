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

## Roadmap

- Sprint 7: Task and Incident operations workflows.
- Sprint 8: Reports, metrics, and notification routing.
- Sprint 9: Automations with simulation mode as the default safety posture.
- Sprint 10: Self-healing playbooks and repair event tracking.
- Sprint 11: AI Operations Brain for summaries, anomaly explanations, and recommended next actions.

## Core Modules

- Dashboard: operational summary for users, accounts, proxies, tasks, and incidents.
- Models: central command object for model/brand identity, team assignments, health, future accounts, work, incidents, reports, revenue, and audit history.
- Users: Telegram principals, statuses, role assignment, and recent audit context.
- Roles: default and custom role records with permission memberships.
- Permissions: named capability flags checked by services and Telegram navigation.
- Audit Logs: append-only safety trail for important actions and denied attempts.
- Accounts: Model/Brand-attached account inventory for Instagram, X, OnlyFans, Email, and Other, including auth-state tracking, credential references, short-lived auth sessions, and hashed verification-code submissions.
- Proxies: encrypted Proxy Vault with account assignment, session suffix rotation, rollback, health scoring, location verification, simulation, and repair workflows.
- Tasks: placeholder resource model for future work queues.
- Incidents: source-linked incident records used first by proxy repair/location workflows.
- Reports: placeholder resource model for future operational reports.
- Automations: placeholder resource model with simulation-mode placeholder.
- Settings: administrative utilities including audit log access.

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
- Tasks: assigned work, status movement, approvals, and SLA signals.
- Incidents: incident creation, triage, severity, ownership, and resolution.
- Reports: operational summaries, audit summaries, health metrics, and exportable views.
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

RED:

- The original `users.role_id` column exists in the earliest migration but is not used by the current model. It should be removed in a future cleanup migration only after explicit approval because it is a schema deletion.
- The audit log is still the only event sink. A dedicated event table or queue should wait until real automation/reporting consumers exist.
- Task, report, and automation placeholder tables are intentionally thin. Their domain-specific constraints should be added when each module is built.
- Proxy health tests are simulated service results until a real provider/network adapter is introduced.
