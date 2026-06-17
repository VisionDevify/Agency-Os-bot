# Database Schema

This document describes the current schema as of Sprint 5 and the planned direction. PostgreSQL is the production database, SQLAlchemy owns the models, and Alembic owns migrations.

## Current Tables

### users

Stores Telegram-linked human principals.

Columns:

- `id`: primary key.
- `telegram_id`: unique Telegram numeric ID.
- `display_name`: optional Telegram display name.
- `username`: optional Telegram username.
- `is_owner`: owner bootstrap flag.
- `is_active`: active/blocking flag.
- `status`: one of `pending`, `active`, `disabled`, or `denied`.
- `last_seen`: latest Telegram interaction timestamp.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- Unique constraint on `telegram_id`.
- `ix_users_telegram_id`.
- `ix_users_status`.
- `ck_users_status` check constraint.

Notes:

- `status` is the source of truth for access behavior.
- The legacy `role_id` column from the initial migration is not mapped by the current model and is not used. Removing it is deferred until an approved cleanup migration.

### roles

Stores role definitions.

Columns:

- `id`: primary key.
- `name`: unique role name.
- `description`: optional description.
- `created_at`: timestamp from the initial migration.

Indexes and constraints:

- Unique constraint on `name`.
- `ix_roles_name`.

### permissions

Stores permission keys.

Columns:

- `id`: primary key.
- `key`: unique permission key.
- `description`: optional description.

Indexes and constraints:

- Unique constraint on `key`.
- `ix_permissions_key`.

### user_roles

Join table between users and roles.

Columns:

- `user_id`: foreign key to `users.id`, cascade delete.
- `role_id`: foreign key to `roles.id`, cascade delete.

Indexes and constraints:

- Composite primary key on `user_id`, `role_id`.
- `uq_user_roles_user_role`.
- `ix_user_roles_user_id`.
- `ix_user_roles_role_id`.

### role_permissions

Join table between roles and permissions.

Columns:

- `role_id`: foreign key to `roles.id`, cascade delete.
- `permission_id`: foreign key to `permissions.id`, cascade delete.

Indexes and constraints:

- Composite primary key on `role_id`, `permission_id`.
- `uq_role_permissions_role_permission`.
- `ix_role_permissions_role_id`.
- `ix_role_permissions_permission_id`.

### audit_logs

Append-style record of important actions, denied attempts, and owner-protection events.

Columns:

- `id`: primary key.
- `actor_user_id`: nullable foreign key to `users.id`.
- `action`: stable event-style action name.
- `resource_type`: affected resource family.
- `resource_id`: optional affected resource ID or route key.
- `status`: `success`, `denied`, or another workflow-safe status.
- `details`: JSON metadata that must not contain secrets.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- `ix_audit_logs_actor_user_id`.
- `ix_audit_logs_action`.
- `ix_audit_logs_resource` on `resource_type`, `resource_id`.
- `ix_audit_logs_created_at`.

### model_brands

Central model/brand command object.

Columns:

- `id`: primary key.
- `display_name`: required public/admin display name.
- `stage_name`: optional stage or brand-facing name.
- `status`: one of `active`, `warning`, `disabled`, or `archived`.
- `notes`: optional operator notes.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- `ck_model_brands_status`.
- `ix_model_brands_display_name`.
- `ix_model_brands_stage_name`.
- `ix_model_brands_status`.

### model_brand_members

Relationship table between Model/Brand records and assigned users.

Columns:

- `model_brand_id`: foreign key to `model_brands.id`, cascade delete.
- `user_id`: foreign key to `users.id`, cascade delete.
- `relationship_type`: one of `manager`, `chatter_manager`, `senior_chatter`, `chatter`, `va`, or `viewer`.

Indexes and constraints:

- Composite primary key on `model_brand_id`, `user_id`, `relationship_type`.
- `uq_model_brand_members_model_user_type`.
- `ck_model_brand_members_relationship_type`.
- `ix_model_brand_members_model_brand_id`.
- `ix_model_brand_members_user_id`.
- `ix_model_brand_members_relationship_type`.

### accounts

Model/Brand-attached account inventory. Accounts track operational state and auth state but never store raw passwords, raw 2FA codes, or credential payloads.

Columns:

- `id`: primary key.
- `name`: legacy nullable display field retained from Sprint 1 placeholder resources.
- `metadata_json`: legacy safe metadata JSON retained for compatibility.
- `model_brand_id`: nullable foreign key to `model_brands.id`, set null on model deletion.
- `platform`: one of `instagram`, `x`, `onlyfans`, `email`, or `other`.
- `username`: required platform username or identifier.
- `display_name`: required operator-facing display name.
- `account_url`: optional URL.
- `status`: one of `healthy`, `warning`, `critical`, `disabled`, or `archived`.
- `auth_status`: one of `not_connected`, `connected`, `needs_login`, `needs_2fa`, `expired`, or `locked`.
- `credential_ref`: optional external secret reference only.
- `connected_email_ref`: optional external email credential reference only.
- `connected_phone_mask`: optional masked phone label.
- `assigned_proxy_id`: nullable foreign key to `proxies.id`, set null on proxy deletion.
- `notes`: optional operator notes.
- `last_checked_at`: optional latest health/auth check timestamp.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- `ck_accounts_platform`.
- `ck_accounts_status`.
- `ck_accounts_auth_status`.
- `ix_accounts_model_brand_id`.
- `ix_accounts_platform`.
- `ix_accounts_status`.
- `ix_accounts_auth_status`.
- `ix_accounts_username`.

### account_auth_sessions

Short-lived login/auth workflow records. These are coordination records only; they do not store credentials or codes.

Columns:

- `id`: primary key.
- `account_id`: foreign key to `accounts.id`, cascade delete.
- `status`: one of `pending`, `waiting_for_code`, `submitted`, `success`, `failed`, `expired`, or `cancelled`.
- `requested_by_user_id`: foreign key to `users.id`, set null if the user is removed.
- `handled_by_user_id`: nullable foreign key to `users.id`, set null if the user is removed.
- `expires_at`: auth-session expiry timestamp, currently ten minutes from creation.
- `failure_reason`: optional safe failure reason.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- `ck_account_auth_sessions_status`.
- `ix_account_auth_sessions_account_id`.
- `ix_account_auth_sessions_status`.
- `ix_account_auth_sessions_expires_at`.
- `ix_account_auth_sessions_requested_by_user_id`.

### account_verification_codes

Stores hashed verification-code submissions for short-lived auth sessions. The plaintext code is never persisted.

Columns:

- `id`: primary key.
- `auth_session_id`: foreign key to `account_auth_sessions.id`, cascade delete.
- `code_hash`: HMAC-SHA256 hash of the submitted code scoped to the auth session.
- `code_type`: one of `email`, `sms`, `authenticator`, or `backup_code`.
- `submitted_by_user_id`: foreign key to `users.id`, set null if the user is removed.
- `expires_at`: code expiry timestamp, currently five minutes from submission.
- `used_at`: nullable timestamp set by future real integrations after consuming the code.
- `created_at`: timestamp.

Indexes and constraints:

- `ck_account_verification_codes_code_type`.
- `ix_account_verification_codes_auth_session_id`.
- `ix_account_verification_codes_expires_at`.

### proxies, tasks, incidents, reports, automations

Current placeholder resource tables.

Shared columns:

- `id`: primary key.
- `name`: required display name.
- `status`: module-local status, default `draft`.
- `metadata_json`: JSON object for safe non-secret metadata.
- `created_at`, `updated_at`: timestamps.

These tables are intentionally minimal until their modules are implemented.

## Relationships

- A user can have many roles through `user_roles`.
- A role can have many users through `user_roles`.
- A role can have many permissions through `role_permissions`.
- A permission can belong to many roles through `role_permissions`.
- A model/brand can have many assigned users through `model_brand_members`.
- A user can be assigned to many model/brands through `model_brand_members`.
- A model/brand can have many accounts through `accounts.model_brand_id`.
- An account can have many auth sessions through `account_auth_sessions.account_id`.
- An auth session can have many hashed verification-code submissions through `account_verification_codes.auth_session_id`.
- An audit log may reference an actor user through `actor_user_id`.

## Status Strategy

User status:

- `pending`: created from Telegram but awaiting approval. Blocked from operational screens.
- `active`: approved and allowed to access screens permitted by roles.
- `disabled`: blocked by an admin action. Can be reactivated.
- `denied`: rejected by an admin action. Can be reactivated if policy allows.

Model/Brand status:

- `active`: operating normally.
- `warning`: requires attention but remains operational.
- `disabled`: operationally blocked without deleting history.
- `archived`: hidden from default active lists while preserving history.

Account status:

- `healthy`: account record is operating normally.
- `warning`: account needs operator attention but is not considered critical.
- `critical`: account needs urgent attention.
- `disabled`: account is intentionally disabled but kept for history.
- `archived`: hidden from default active lists while preserving history.

Account auth status:

- `not_connected`: no confirmed active connection exists.
- `connected`: account has been marked connected.
- `needs_login`: operator login action is needed.
- `needs_2fa`: verification code flow is needed.
- `expired`: auth/session state expired.
- `locked`: platform-side lockout or equivalent operator intervention required.

Soft-delete strategy:

- Users are not deleted during normal admin flows. Use `disabled` or `denied`.
- Roles and permissions should not be deleted casually because they affect audit interpretation and historical access context.
- Model/Brand records should use `disabled` or `archived` instead of hard deletion.
- Account records should use `disabled` or `archived` instead of hard deletion.
- Future business resources should prefer status-based archival before hard deletes.

## Future Planned Tables

- `account_credentials`: secret references only, not raw secrets.
- `proxy_credentials`: secret references only, not raw secrets.
- `proxy_health_checks`: proxy check results and failure reasons.
- `task_assignments`: task ownership and handoff history.
- `incident_events`: incident timeline events.
- `report_runs`: report generation records.
- `automation_runs`: simulation and live automation run records.
- `events`: durable operational event stream once multiple consumers need it.
- `repair_attempts`: self-healing attempts and outcomes.
- `ai_recommendations`: AI operations suggestions, confidence, and operator disposition.
