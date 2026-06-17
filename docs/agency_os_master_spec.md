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

## Roadmap

- Sprint 5: Accounts Foundation attached to Models/Brands.
- Sprint 6: Proxy Vault and health-check model.
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
- Accounts: placeholder resource model for future account inventory.
- Proxies: placeholder resource model and session-string rotation placeholder.
- Tasks: placeholder resource model for future work queues.
- Incidents: placeholder resource model for future incident handling and repair tracking.
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
- Accounts: account inventory, status, credentials references, and assignment workflows.
- Proxy Vault: proxy records, health checks, rotation events, and credential-safe storage.
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

Accounts, Revenue, Proxy Assignments, Automation Rules, Daily Briefings, and AI Operations Brain integration are intentionally TODO hooks until those modules have real records.

## Foundation Hardening Review

GREEN:

- Owner bootstrap is centralized and idempotent.
- Permission checks are concentrated in service/navigation layers instead of scattered through handlers.
- Telegram navigation edits existing messages and avoids chat spam.
- `.env` is ignored, and `.env.example` is placeholder-only.
- Core auth tables use unique constraints and join-table uniqueness to prevent duplicate memberships.
- Audit logging exists for admin actions and denied access attempts.

YELLOW:

- Audit event names were normalized to event-style names for permission and access events.
- Audit metadata now masks Telegram IDs instead of storing raw IDs for routine admin/user events.
- Pending-user creation is now audited.
- Owner-protection failures are now audited.
- Pending Users navigation was made explicit.
- Role removal choices now show only assigned roles.
- User status now has a database check constraint.

RED:

- The original `users.role_id` column exists in the earliest migration but is not used by the current model. It should be removed in a future cleanup migration only after explicit approval because it is a schema deletion.
- The audit log is still the only event sink. A dedicated event table or queue should wait until real automation/reporting consumers exist.
- The resource placeholder tables are intentionally thin. Their domain-specific constraints should be added when each module is built.
