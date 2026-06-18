# Database Schema

This document describes the current schema as of Sprint 18 and the planned direction. PostgreSQL is the production database, SQLAlchemy owns the models, and Alembic owns migrations.

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
- `language`: user language preference for onboarding and future localization.
- `country`: optional country preference.
- `timezone`: IANA timezone used for display and routing.
- `time_format`: `12h` or `24h`.
- `last_seen`: latest Telegram interaction timestamp.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- Unique constraint on `telegram_id`.
- `ix_users_telegram_id`.
- `ix_users_status`.
- `ix_users_language`.
- `ix_users_country`.
- `ix_users_timezone`.
- `ck_users_status` check constraint.
- `ck_users_time_format`.

Notes:

- `status` is the source of truth for access behavior.
- Pending users can update localization fields before approval, but cannot access operational screens.
- The legacy `role_id` column from the initial migration is not mapped by the current model and is not used. Removing it is deferred until an approved cleanup migration.

### user_availability

Stores shift and quiet-hours state for smart notification routing.

Columns:

- `id`: primary key.
- `user_id`: unique foreign key to `users.id`, cascade delete.
- `status`: one of `on_shift`, `off_shift`, `away`, `vacation`, or `unavailable`.
- `timezone`: IANA timezone used for local shift/quiet-hour interpretation.
- `shift_start_local`, `shift_end_local`: optional local shift window.
- `quiet_hours_start_local`, `quiet_hours_end_local`: optional local quiet-hours window.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- Unique constraint on `user_id`.
- `ck_user_availability_status`.
- `ix_user_availability_user_id`.
- `ix_user_availability_status`.
- `ix_user_availability_timezone`.

### team_onboarding_checklists

Tracks human rollout readiness for each user.

Columns:

- `id`: primary key.
- `user_id`: unique foreign key to `users.id`, cascade delete.
- `onboarded`: whether the admin has marked the user ready.
- `role_assigned`: role assignment confirmed.
- `timezone_confirmed`: timezone confirmed.
- `availability_configured`: availability setup confirmed.
- `help_center_viewed`: Help Center viewed.
- `readiness_score`: 0-100 readiness summary.
- `updated_by_user_id`: nullable foreign key to the admin who last changed the checklist.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- Unique index on `user_id`.
- `ck_team_onboarding_checklists_readiness_score`.
- `ix_team_onboarding_checklists_readiness_score`.
- `ix_team_onboarding_checklists_onboarded`.

### agency_activation_states

Stores the latest owner/admin activation readiness scan.

Columns:

- `id`: primary key.
- `models_ready`: 0-100 model setup readiness.
- `accounts_ready`: 0-100 account readiness, including model, proxy, auth, and health checks.
- `teams_ready`: 0-100 manager/chatter assignment readiness.
- `creators_ready`: 0-100 creator watchlist readiness.
- `opportunities_ready`: 0-100 opportunity readiness.
- `notifications_ready`: 0-100 notification target readiness.
- `readiness_score`: overall 0-100 agency readiness score.
- `blockers_json`: safe list of detected setup blockers.
- `recommendations_json`: safe list of suggested next actions.
- `updated_at`: scan timestamp.

Indexes and constraints:

- `ck_agency_activation_states_models_ready`.
- `ck_agency_activation_states_accounts_ready`.
- `ck_agency_activation_states_teams_ready`.
- `ck_agency_activation_states_creators_ready`.
- `ck_agency_activation_states_opportunities_ready`.
- `ck_agency_activation_states_notifications_ready`.
- `ck_agency_activation_states_readiness_score`.
- `ix_agency_activation_states_updated_at`.
- `ix_agency_activation_states_readiness_score`.

Notes:

- Activation scans are safe summaries. They must not include secrets, raw chat IDs, proxy passwords, platform passwords, or 2FA codes.
- The scan can generate recommendations and deduped setup tasks so the owner does not need to manually discover missing setup work.

### activation_blocker_decisions

Stores owner/admin decisions to hide or close specific readiness blockers.

Columns:

- `id`: primary key.
- `blocker_code`: stable blocker code, such as `model.missing_country`.
- `entity_type`: optional related entity type.
- `entity_id`: optional related entity id as text.
- `status`: `skipped` or `not_needed`.
- `reason`: optional safe operator note.
- `decided_by_user_id`: nullable foreign key to `users.id`.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- `uq_activation_blocker_decisions_key`.
- `ck_activation_blocker_decisions_status`.
- `ix_activation_blocker_decisions_status`.
- `ix_activation_blocker_decisions_blocker_code`.
- `ix_activation_blocker_decisions_decided_by`.

Notes:

- `skipped` suppresses the blocker from immediate owner focus.
- `not_needed` suppresses the blocker and can improve the readiness view when that setup item is intentionally out of scope.
- Decisions never store secrets or raw Telegram data.

### daily_autopilot_settings

Stores the owner-facing Daily Autopilot schedule and last-run status.

Columns:

- `id`: primary key.
- `owner_user_id`: nullable unique foreign key to `users.id`.
- `is_enabled`: whether the daily cycle is enabled.
- `timezone`: owner timezone for scheduling.
- `run_time_local`: local run time, stored as `HH:MM`.
- `included_actions_json`: safe list of daily cycle action names.
- `next_run_at`: next scheduled UTC run time.
- `last_run_at`: latest UTC run time.
- `last_result`: safe last result summary.
- `created_at`, `updated_at`: timestamps.

Indexes:

- `ix_daily_autopilot_settings_owner_user_id`.
- `ix_daily_autopilot_settings_is_enabled`.
- `ix_daily_autopilot_settings_next_run_at`.

Notes:

- Daily Autopilot uses safe internal scans and setup guidance. High-risk automations still require explicit owner approval.

### priority_items

Stores Fortuna COO-ranked operational priorities.

Columns:

- `id`: primary key.
- `source_type`: source entity family, such as `model`, `account`, `task`, `incident`, `opportunity`, `notification_target`, `automation_run`, or `readiness`.
- `source_id`: source identifier as text.
- `category`: priority category, such as `missing_proxy`, `critical_incident`, `overdue_task`, `unassigned_opportunity`, or a setup blocker code.
- `severity`: `info`, `warning`, or `critical`.
- `urgency`: `low`, `normal`, `high`, or `urgent`.
- `confidence`: 0-100 deterministic confidence score.
- `business_impact`: 0-100 impact score.
- `score`: final 0-100 priority score.
- `explanation`: human-readable reason and next-step context.
- `recommended_owner`: routing target label such as Owner, Admin, or Manager.
- `status`: `open`, `routed`, `acknowledged`, `resolved`, or `dismissed`.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- `uq_priority_items_source_category`.
- `ck_priority_items_severity`.
- `ck_priority_items_urgency`.
- `ck_priority_items_confidence`.
- `ck_priority_items_business_impact`.
- `ck_priority_items_score`.
- `ck_priority_items_status`.
- `ix_priority_items_source`.
- `ix_priority_items_category`.
- `ix_priority_items_status`.
- `ix_priority_items_score`.
- `ix_priority_items_recommended_owner`.
- `ix_priority_items_updated_at`.

Notes:

- Priority items are safe summaries. They must not include secrets, raw chat IDs, proxy passwords, tokens, platform passwords, or 2FA codes.
- The COO layer recommends routing and reassignment, but does not automatically move work or execute risky changes.

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

### event_logs

Lightweight durable event feed for reports, notifications, automations, self-healing, and future AI operations.

Columns:

- `id`: primary key.
- `event_type`: stable dotted event type.
- `actor_user_id`: nullable foreign key to `users.id`.
- `entity_type`: optional affected resource family.
- `entity_id`: optional affected resource ID.
- `metadata_json`: safe non-secret event metadata.
- `created_at`: timestamp.

Indexes and constraints:

- `ix_event_logs_event_type`.
- `ix_event_logs_actor_user_id`.
- `ix_event_logs_entity` on `entity_type`, `entity_id`.
- `ix_event_logs_created_at`.

### notification_digests

Bundles low-priority notification updates to reduce chat noise.

Columns:

- `id`: primary key.
- `user_id`: nullable user who owns or generated the digest.
- `purpose`: routing purpose such as `operations`.
- `status`: one of `open`, `sent`, or `archived`.
- `priority`: one of `low`, `normal`, or `critical`.
- `title`: digest title.
- `summary`: human-readable summary.
- `items_json`: safe list of update references.
- `item_count`: item count.
- `sent_at`: optional sent timestamp.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- `ck_notification_digests_status`.
- `ck_notification_digests_priority`.
- `ix_notification_digests_user_id`.
- `ix_notification_digests_purpose`.
- `ix_notification_digests_status`.
- `ix_notification_digests_priority`.
- `ix_notification_digests_created_at`.

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

### proxies

Encrypted proxy inventory and health state. The table retains legacy `name` and `metadata_json` columns from the placeholder resource migration for compatibility.

Columns:

- `id`: primary key.
- `name`: nullable legacy display name.
- `metadata_json`: safe non-secret metadata.
- `provider`: proxy provider label.
- `host`: proxy host.
- `port`: proxy port.
- `base_username`: provider username base.
- `session_suffix`: current session identity suffix.
- `previous_session_suffix`: rollback session suffix.
- `encrypted_password`: encrypted proxy password; never shown in Telegram or audits.
- `generated_username`: base username plus current session suffix.
- `status`: one of `healthy`, `warning`, `critical`, or `disabled`.
- `health_score`: 0-100 health score.
- `target_country`, `target_state`, `target_city`: desired location.
- `detected_country`, `detected_state`, `detected_city`: latest detected location.
- `last_health_check`: latest proxy check timestamp.
- `last_rotation`: latest rotation attempt timestamp.
- `last_successful_rotation`: latest successful rotation timestamp.
- `rotation_count`: total rotation attempts.
- `success_count`, `failure_count`: connection-test counters.
- `connection_test_count`: total connection tests.
- `location_mismatch_count`: target/detected mismatch counter.
- `rotation_success_count`, `rotation_failure_count`: rotation outcome counters.
- `latency_ms`: latest test latency.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- `ck_proxies_status`.
- `ck_proxies_health_score`.
- `ck_proxies_port`.
- `ix_proxies_provider`.
- `ix_proxies_status`.
- `ix_proxies_health_score`.
- `ix_proxies_target_location`.

### proxy_rotation_history

Append-style proxy rotation records used for rotation history and rollback context.

Columns:

- `id`: primary key.
- `proxy_id`: foreign key to `proxies.id`, cascade delete.
- `previous_session_suffix`: previous session suffix.
- `new_session_suffix`: generated session suffix.
- `status`: one of `started`, `succeeded`, `failed`, or `rolled_back`.
- `detected_country`, `detected_state`, `detected_city`: location detected during rotation.
- `latency_ms`: observed latency.
- `failure_reason`: safe failure reason.
- `created_by_user_id`: nullable foreign key to `users.id`.
- `created_at`: timestamp.

Indexes and constraints:

- `ck_proxy_rotation_history_status`.
- `ix_proxy_rotation_history_proxy_id`.
- `ix_proxy_rotation_history_status`.
- `ix_proxy_rotation_history_created_at`.

### proxy_health_check_results

Append-style proxy health check history. Sprint 27 adds this table so simulated checks, real SOCKS5 connectivity checks, and optional location checks are persisted instead of only updating counters on `proxies`.

Columns:

- `id`: primary key.
- `proxy_id`: foreign key to `proxies.id`, cascade delete.
- `check_type`: one of `simulated`, `connectivity`, `location`, or `full`.
- `status`: one of `passed`, `failed`, `warning`, or `skipped`.
- `latency_ms`: observed latency when available.
- `detected_ip_masked`: masked outgoing IP, never the full raw IP.
- `detected_country`, `detected_state`, `detected_city`: coarse location when available.
- `target_match`: nullable boolean showing whether detected location matched configured target.
- `error_message`: safe redacted error message.
- `created_at`: timestamp.

Indexes and constraints:

- `ck_proxy_health_check_results_check_type`.
- `ck_proxy_health_check_results_status`.
- `ix_proxy_health_check_results_proxy_id`.
- `ix_proxy_health_check_results_check_type`.
- `ix_proxy_health_check_results_status`.
- `ix_proxy_health_check_results_created_at`.

### tasks

Operational task queue. The production table retains legacy `name` and `metadata_json` columns from the Sprint 1 placeholder resource migration for compatibility, but the current model uses the domain columns below.

Columns:

- `id`: primary key.
- `title`: required task title.
- `description`: optional task details.
- `status`: one of `open`, `in_progress`, `blocked`, `complete`, or `archived`.
- `priority`: one of `low`, `normal`, `high`, or `urgent`.
- `model_brand_id`: nullable foreign key to `model_brands.id`, set null on model deletion.
- `account_id`: nullable foreign key to `accounts.id`, set null on account deletion.
- `proxy_id`: nullable foreign key to `proxies.id`, set null on proxy deletion.
- `owner_user_id`: nullable foreign key to `users.id`, set null on user deletion.
- `assigned_to_user_id`: nullable foreign key to `users.id`, set null on user deletion.
- `created_by_user_id`: nullable foreign key to `users.id`, set null on user deletion.
- `due_at`: optional due timestamp.
- `started_at`: nullable start timestamp.
- `completed_at`: nullable completion timestamp.
- `blocked_reason`: optional safe blocker note.
- `escalation_level`: numeric escalation step.
- `last_escalated_at`: nullable latest escalation timestamp.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- `ck_tasks_status`.
- `ck_tasks_priority`.
- `ix_tasks_status`.
- `ix_tasks_priority`.
- `ix_tasks_model_brand_id`.
- `ix_tasks_account_id`.
- `ix_tasks_proxy_id`.
- `ix_tasks_owner_user_id`.
- `ix_tasks_assigned_to_user_id`.
- `ix_tasks_created_by_user_id`.
- `ix_tasks_due_at`.
- `ix_tasks_escalation_level`.

### incidents

Incident records for manual, account, proxy, automation, and system issues. The table retains legacy `name`, `source_id`, `assigned_user_id`, and `metadata_json` columns for compatibility with Sprint 6 proxy repair rows.

Columns:

- `id`: primary key.
- `name`: nullable legacy display name.
- `title`: required incident title.
- `description`: optional incident details.
- `status`: one of `open`, `investigating`, `resolved`, or `archived`.
- `severity`: one of `info`, `warning`, or `critical`.
- `source_type`: optional source family: `manual`, `account`, `proxy`, `automation`, or `system`.
- `source_id`: legacy optional source resource ID.
- `assigned_user_id`: legacy nullable foreign key to `users.id`.
- `model_brand_id`: nullable foreign key to `model_brands.id`, set null on model deletion.
- `account_id`: nullable foreign key to `accounts.id`, set null on account deletion.
- `proxy_id`: nullable foreign key to `proxies.id`, set null on proxy deletion.
- `owner_user_id`: nullable foreign key to `users.id`, set null on user deletion.
- `assigned_to_user_id`: nullable foreign key to `users.id`, set null on user deletion.
- `created_by_user_id`: nullable foreign key to `users.id`, set null on user deletion.
- `resolved_by_user_id`: nullable foreign key to `users.id`, set null on user deletion.
- `resolution_notes`: optional safe resolution note.
- `escalation_level`: numeric escalation step.
- `escalation_history`: JSON list of safe escalation history entries.
- `last_escalated_at`: nullable latest escalation timestamp.
- `resolved_at`: nullable resolution timestamp.
- `metadata_json`: safe non-secret metadata.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- `ck_incidents_status`.
- `ck_incidents_severity`.
- `ck_incidents_source_type`.
- `ix_incidents_status`.
- `ix_incidents_severity`.
- `ix_incidents_source`.
- `ix_incidents_assigned_user_id`.
- `ix_incidents_model_brand_id`.
- `ix_incidents_account_id`.
- `ix_incidents_proxy_id`.
- `ix_incidents_owner_user_id`.
- `ix_incidents_assigned_to_user_id`.
- `ix_incidents_created_by_user_id`.
- `ix_incidents_escalation_level`.

### incident_timeline

Durable per-incident timeline entries for operational status movement and escalation context.

Columns:

- `id`: primary key.
- `incident_id`: foreign key to `incidents.id`, cascade delete.
- `actor_user_id`: nullable foreign key to `users.id`, set null on user deletion.
- `event_type`: stable dotted event type such as `incident.investigating`.
- `message`: safe human-readable timeline message.
- `metadata_json`: safe non-secret metadata.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- `ix_incident_timeline_incident_id`.
- `ix_incident_timeline_actor_user_id`.
- `ix_incident_timeline_event_type`.
- `ix_incident_timeline_created_at`.

### reports, automations

Current placeholder resource tables retained from the foundation.

Shared columns:

- `id`: primary key.
- `name`: required display name.
- `status`: module-local status, default `draft`.
- `metadata_json`: JSON object for safe non-secret metadata.
- `created_at`, `updated_at`: timestamps.

These tables are intentionally minimal until their modules need richer records. Sprint 9 adds dedicated automation rule and simulation-run tables below.

### automation_rules

No-code automation definitions. Rules move through draft, simulation, approval, activation, execution, verification, reporting, and rollback planning.

Columns:

- `id`: primary key.
- `name`: operator-facing automation name.
- `description`: optional operator-facing description.
- `category`: one of `infrastructure`, `operations`, `notifications`, `reports`, `intelligence`, `opportunities`, or `system`.
- `automation_type`: stable automation family/slug.
- `status`: one of `draft`, `simulated`, `pending_approval`, `approved`, `active`, `paused`, `retired`, `failed`, plus legacy `disabled` or `archived`.
- `trigger_type`: stable trigger family such as `manual`, `scheduled`, `event`, or `condition`.
- `trigger_config_json`: safe trigger config.
- `conditions_json`: safe deterministic checks to evaluate before execution.
- `actions_json`: safe action list. No social posting/commenting/liking/following actions are supported.
- `rollback_plan_json`: safe rollback plan and limitations.
- `risk_level`: `low`, `medium`, `high`, or `critical`.
- `requires_owner_approval`: true when Owner approval is mandatory.
- `created_by_user_id`: nullable foreign key to `users.id`.
- `approved_by_user_id`: nullable foreign key to `users.id`.
- `approved_at`: nullable approval timestamp.
- `last_simulated_at`: nullable latest simulation timestamp.
- `last_run_at`: nullable latest execution timestamp.
- `metadata_json`: safe non-secret metadata.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- `ck_automation_rules_category`.
- `ck_automation_rules_status`.
- `ck_automation_rules_risk_level`.
- `ix_automation_rules_name`.
- `ix_automation_rules_category`.
- `ix_automation_rules_automation_type`.
- `ix_automation_rules_status`.
- `ix_automation_rules_trigger_type`.
- `ix_automation_rules_risk_level`.
- `ix_automation_rules_created_by_user_id`.
- `ix_automation_rules_approved_by_user_id`.

### automation_simulation_runs

Durable dry-run records. These records preview what would happen without mutating production data.

Columns:

- `id`: primary key.
- `automation_rule_id`: nullable foreign key to `automation_rules.id`.
- `automation_name`: display name of the simulated automation.
- `automation_type`: automation family, such as `proxy_repair` or `daily_briefing`.
- `status`: one of `pending`, `running`, `succeeded`, `failed`, or `expired`, plus legacy `draft`, `simulated`, `approved`, or `rejected`.
- `simulated_by_user_id`: foreign key to `users.id`.
- `target_scope`: scope label for the preview.
- `would_trigger_count`: number of items that would be touched.
- `would_succeed_count`: estimated successful outcomes.
- `would_fail_count`: estimated failed outcomes.
- `affected_entities_json`: safe list of entities that could be affected.
- `impact_summary_json`: safe impact preview.
- `risk_level`: one of `low`, `medium`, `high`, or `critical`.
- `warnings_json`: safe warnings for operator review.
- `created_at`: timestamp.
- `finished_at`: nullable simulation finish timestamp.
- `expires_at`: simulation expiry timestamp.

Indexes and constraints:

- `ck_automation_simulation_runs_status`.
- `ck_automation_simulation_runs_risk_level`.
- `ix_automation_simulation_runs_rule_id`.
- `ix_automation_simulation_runs_automation_type`.
- `ix_automation_simulation_runs_status`.
- `ix_automation_simulation_runs_risk`.
- `ix_automation_simulation_runs_simulated_by`.
- `ix_automation_simulation_runs_created_at`.
- `ix_automation_simulation_runs_finished_at`.
- `ix_automation_simulation_runs_expires_at`.

### automation_approvals

Approval workflow records for automation activation.

Columns:

- `id`: primary key.
- `automation_rule_id`: foreign key to `automation_rules.id`.
- `requested_by_user_id`: foreign key to `users.id`.
- `approved_by_user_id`: nullable foreign key to `users.id`.
- `status`: `pending`, `approved`, `rejected`, or `expired`.
- `approval_reason`: optional safe approval note.
- `rejection_reason`: optional safe rejection note.
- `created_at`: request timestamp.
- `decided_at`: nullable decision timestamp.
- `expires_at`: nullable approval expiry timestamp.

### automation_runs

Live execution records. A run is created only after simulation and approval gates pass.

Columns:

- `id`: primary key.
- `automation_rule_id`: foreign key to `automation_rules.id`.
- `status`: `pending`, `running`, `succeeded`, `failed`, `skipped`, or `rolled_back`.
- `started_by_user_id`: nullable foreign key to `users.id`.
- `started_at`, `finished_at`: execution timing.
- `trigger_event_id`: nullable foreign key to `event_logs.id`.
- `affected_entities_json`: safe list of affected entities and step outputs.
- `result_summary_json`: safe result summary.
- `error_message`: nullable safe/redacted error.
- `rollback_available`: true when a rollback plan exists for at least one action.
- `rollback_status`: `not_needed`, `available`, `completed`, or `failed`.
- `created_at`, `updated_at`: timestamps.

### automation_run_steps

Step-by-step execution records for each automation action.

Columns:

- `id`: primary key.
- `automation_run_id`: foreign key to `automation_runs.id`, cascade delete.
- `step_order`: action order.
- `action_type`: registry action key.
- `status`: `pending`, `running`, `succeeded`, `failed`, `skipped`, or `rolled_back`.
- `entity_type`, `entity_id`: optional affected entity reference.
- `input_json`: safe action input.
- `output_json`: safe action output.
- `error_message`: nullable safe/redacted error.
- `started_at`, `finished_at`: step timing.
- `created_at`: timestamp.

### automation_schedules

Schedule configuration records for manual, recurring, or event-driven automation triggers.

Columns:

- `id`: primary key.
- `automation_rule_id`: foreign key to `automation_rules.id`.
- `schedule_type`: `manual`, `hourly`, `daily`, `weekly`, or `event_based`.
- `timezone`: IANA timezone label.
- `time_of_day_local`: optional local time.
- `day_of_week`: optional local day label.
- `is_active`: whether the schedule is enabled.
- `last_run_at`, `next_run_at`: nullable scheduling timestamps.
- `created_at`, `updated_at`: timestamps.

### daily_briefings

Persistent daily company briefing records generated from current database state.

Columns:

- `id`: primary key.
- `briefing_date`: date the briefing describes.
- `generated_by_user_id`: nullable foreign key to `users.id`.
- `agency_health_score`: 0-100 generated health score.
- `summary_text`: human-readable summary.
- `metrics_json`: aggregate metrics, safe only.
- `recommendations_json`: recommended actions, safe only.
- `created_at`: timestamp.

Indexes and constraints:

- `ix_daily_briefings_briefing_date`.
- `ix_daily_briefings_generated_by_user_id`.
- `ix_daily_briefings_created_at`.

### accountability_snapshots

Per-user accountability report snapshots. These are visibility snapshots, not punitive scoring records.

Columns:

- `id`: primary key.
- `snapshot_date`: date the snapshot describes.
- `user_id`: foreign key to `users.id`.
- `roles_json`: role names at generation time.
- `assigned_open_tasks`: active assigned task count.
- `completed_tasks_today`: completed task count for the snapshot date.
- `overdue_tasks`: overdue assigned task count.
- `assigned_open_incidents`: active assigned incident count.
- `resolved_incidents_today`: incidents resolved by the user that day.
- `last_seen_at`: nullable latest Telegram interaction timestamp.
- `score`: nullable lightweight visibility score.
- `created_at`: timestamp.

Indexes and constraints:

- `ix_accountability_snapshots_snapshot_date`.
- `ix_accountability_snapshots_user_id`.
- `ix_accountability_snapshots_date_user` on `snapshot_date`, `user_id`.
- `ix_accountability_snapshots_created_at`.

### notification_targets

Future routing targets for owner, operations, incidents, automation logs, and testing. Telegram chat IDs are encrypted or omitted and never shown raw in Telegram.

Columns:

- `id`: primary key.
- `name`: operator-facing label.
- `target_type`: one of `telegram_user`, `telegram_group`, or `telegram_channel`.
- `telegram_chat_id`: encrypted or null Telegram chat reference.
- `purpose`: one of `owner`, `operations`, `incidents`, `automation_logs`, or `testing`.
- `is_active`: active/disabled flag.
- `last_tested_at`: nullable timestamp for the latest safe test notification attempt.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- `ck_notification_targets_target_type`.
- `ck_notification_targets_purpose`.
- `ix_notification_targets_name`.
- `ix_notification_targets_target_type`.
- `ix_notification_targets_purpose`.
- `ix_notification_targets_is_active`.

### notification_delivery_attempts

Append-style delivery records for notification sends. These records track whether a send was attempted, sent, failed, or skipped without exposing raw chat IDs or secrets.

Columns:

- `id`: primary key.
- `notification_target_id`: foreign key to `notification_targets.id`, cascade delete.
- `event_type`: event or notification family being delivered.
- `status`: one of `pending`, `sent`, `failed`, or `skipped`.
- `error_message`: nullable safe/redacted error label.
- `attempted_at`: timestamp when delivery was attempted.
- `created_at`: creation timestamp.
- `metadata_json`: safe non-secret metadata.

Indexes and constraints:

- `ck_notification_delivery_attempts_status`.
- `ix_notification_delivery_attempts_target_id`.
- `ix_notification_delivery_attempts_event_type`.
- `ix_notification_delivery_attempts_status`.
- `ix_notification_delivery_attempts_attempted_at`.
- `ix_notification_delivery_attempts_created_at`.

### recommendations

Deterministic operational recommendations generated from current database state.

Columns:

- `id`: primary key.
- `recommendation_type`: stable recommendation family.
- `title`: short operator-facing title.
- `description`: safe detail text.
- `severity`: one of `info`, `warning`, or `critical`.
- `entity_type`: nullable related entity family.
- `entity_id`: nullable related entity ID.
- `status`: one of `open`, `acknowledged`, `dismissed`, or `resolved`.
- `generated_from_event_id`: nullable foreign key to `event_logs.id`.
- `metadata_json`: safe non-secret recommendation metadata.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- `ck_recommendations_severity`.
- `ck_recommendations_status`.
- `ix_recommendations_type`.
- `ix_recommendations_severity`.
- `ix_recommendations_status`.
- `ix_recommendations_entity`.
- `ix_recommendations_event`.
- `ix_recommendations_created_at`.

### system_heartbeats

Latest known status for core production services.

Columns:

- `id`: primary key.
- `service_name`: unique service identifier, such as `api`, `bot`, `db`, `redis`, or `railway_deployment`.
- `status`: safe status string.
- `last_seen_at`: latest heartbeat timestamp.
- `metadata_json`: safe non-secret metadata, such as deployment status labels.

Indexes and constraints:

- Unique constraint/index on `service_name`.
- `ix_system_heartbeats_status`.
- `ix_system_heartbeats_last_seen_at`.

### intelligence_signals

Operational observations generated by deterministic intelligence services.

Columns:

- `id`: primary key.
- `signal_type`: stable signal family.
- `severity`: `info`, `warning`, or `critical`.
- `entity_type`, `entity_id`: optional related entity reference.
- `title`, `description`: operator-facing summary.
- `confidence_score`: 0-100 confidence score.
- `metadata_json`: safe non-secret metadata only.
- `first_seen_at`, `last_seen_at`: detection timestamps.
- `occurrence_count`: number of related occurrences seen by the detector.
- `status`: `open`, `acknowledged`, `resolved`, or `dismissed`.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- `ck_intelligence_signals_severity`.
- `ck_intelligence_signals_confidence`.
- `ck_intelligence_signals_occurrence_count`.
- `ck_intelligence_signals_status`.
- `ix_intelligence_signals_type`.
- `ix_intelligence_signals_severity`.
- `ix_intelligence_signals_entity`.
- `ix_intelligence_signals_status`.
- `ix_intelligence_signals_last_seen_at`.

### issue_patterns

Recurring issue records derived from events, audits, incidents, tasks, accounts, proxies, notification delivery attempts, and heartbeats.

Columns:

- `id`: primary key.
- `pattern_type`: stable pattern family.
- `title`, `description`: operator-facing pattern summary.
- `entity_type`, `entity_id`: optional related entity reference.
- `severity`: `info`, `warning`, or `critical`.
- `confidence_score`: 0-100 confidence score.
- `occurrence_count`: related occurrence count.
- `related_event_ids_json`: safe list of related event/audit IDs where available.
- `suggested_action`: human-approved next action.
- `status`: `active`, `acknowledged`, `resolved`, or `dismissed`.
- `first_seen_at`, `last_seen_at`: detection timestamps.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- `ck_issue_patterns_severity`.
- `ck_issue_patterns_confidence`.
- `ck_issue_patterns_occurrence_count`.
- `ck_issue_patterns_status`.
- `ix_issue_patterns_type`.
- `ix_issue_patterns_severity`.
- `ix_issue_patterns_entity`.
- `ix_issue_patterns_status`.
- `ix_issue_patterns_last_seen_at`.

### trend_snapshots

Metric snapshots for deterministic trend analysis.

Columns:

- `id`: primary key.
- `snapshot_date`: date the metric describes.
- `metric_name`: stable metric name.
- `entity_type`, `entity_id`: optional entity-specific metric reference.
- `value_numeric`: integer metric value.
- `comparison_window`: `daily`, `weekly`, or `monthly`.
- `trend_direction`: `up`, `down`, `flat`, or `volatile`.
- `percent_change`: nullable integer percent change against the previous snapshot.
- `metadata_json`: safe metadata.
- `created_at`: timestamp.

Indexes and constraints:

- `ck_trend_snapshots_window`.
- `ck_trend_snapshots_direction`.
- `ix_trend_snapshots_snapshot_date`.
- `ix_trend_snapshots_metric`.
- `ix_trend_snapshots_entity`.
- `ix_trend_snapshots_window`.
- `ix_trend_snapshots_direction`.
- `ix_trend_snapshots_created_at`.

### workload_snapshots

Per-user workload intelligence snapshots.

Columns:

- `id`: primary key.
- `snapshot_date`: date the snapshot describes.
- `user_id`: foreign key to `users.id`, cascade delete.
- `open_tasks`, `overdue_tasks`: assigned task counts.
- `open_incidents`, `critical_incidents`: assigned incident counts.
- `completed_tasks_24h`, `resolved_incidents_24h`: recent throughput counts.
- `availability_status`: copied availability state.
- `workload_score`: deterministic workload score.
- `overload_status`: `normal`, `elevated`, `overloaded`, or `critical`.
- `metadata_json`: safe metadata.
- `created_at`: timestamp.

Indexes and constraints:

- `ck_workload_snapshots_overload_status`.
- `ck_workload_snapshots_score`.
- `ix_workload_snapshots_snapshot_date`.
- `ix_workload_snapshots_user_id`.
- `ix_workload_snapshots_overload_status`.
- `ix_workload_snapshots_created_at`.

### executive_insights

Executive-level insights generated from the intelligence layer.

Columns:

- `id`: primary key.
- `insight_type`: stable insight family.
- `title`, `body`: concise operator-facing insight.
- `severity`: `info`, `warning`, or `critical`.
- `confidence_score`: 0-100 confidence score.
- `recommended_action`: human-approved next action.
- `source_signal_ids_json`: safe list of source signal IDs.
- `status`: `open`, `acknowledged`, `resolved`, or `dismissed`.
- `created_at`, `updated_at`: timestamps.

### intelligence_runs

No-code intelligence scan history.

Columns:

- `id`: primary key.
- `run_type`: `pattern_detection`, `trend_analysis`, `workload_analysis`, `recommendation_generation`, `executive_briefing`, or `opportunity_scoring`.
- `status`: `pending`, `running`, `succeeded`, or `failed`.
- `started_by_user_id`: nullable foreign key to `users.id`.
- `started_at`, `finished_at`: run timing.
- `summary_json`: safe run summary.
- `error_message`: nullable safe failure label.

### opportunity_sources

Manual source records for future opportunity intelligence.

Columns:

- `id`: primary key.
- `platform`: `x`, `instagram`, `reddit`, or `other`.
- `name`, `url`, `niche`: source metadata.
- `is_active`: active/disabled flag.
- `created_at`, `updated_at`: timestamps.

### opportunities

Manual, human-approved opportunity records. No scraping or automatic posting is implemented.

Columns:

- `id`: primary key.
- `source_id`: nullable foreign key to `opportunity_sources.id`.
- `platform`: `x`, `instagram`, `reddit`, or `other`.
- `source_type`: nullable `manual`, `creator_watch`, or `own_post`.
- `source_reference_id`: nullable source record ID for creator/post/manual context.
- `title`, `url`, `niche`: opportunity metadata.
- `model_brand_id`: nullable foreign key to `model_brands.id`.
- `score`: 0-100 deterministic score.
- `priority`: `low`, `normal`, `high`, or `critical`.
- `status`: `discovered`, `reviewing`, `approved`, `assigned`, `completed`, `rejected`, or `archived`.
- `reason`: safe reason text.
- `suggested_angle`: safe human-approved angle.
- `assigned_to_user_id`: nullable foreign key to `users.id`.
- `due_at`: nullable due timestamp.
- `assigned_at`: nullable assignment timestamp.
- `completed_at`: nullable completion timestamp.
- `created_at`, `updated_at`: timestamps.

### opportunity_results

Manual result records for opportunity follow-up.

Columns:

- `id`: primary key.
- `opportunity_id`: foreign key to `opportunities.id`, cascade delete.
- `posted_by_user_id`: nullable foreign key to `users.id`.
- `status`: `not_posted`, `posted`, `skipped`, `failed`, or `rejected`.
- `clicks`, `conversions`: nullable manual result counts.
- `reason`: safe reason/result note.
- `notes`: safe operator notes.
- `created_at`, `updated_at`: timestamps.

### creator_watches

Manual creator watch records for human review.

Columns:

- `id`: primary key.
- `platform`: `x`, `instagram`, or `other`.
- `creator_name`: display name.
- `display_name`: optional operator-facing display name.
- `creator_username`: platform username or handle label.
- `profile_url`: optional profile URL.
- `niche`: optional niche label.
- `priority`: `low`, `normal`, `high`, or `critical`.
- `assigned_model_id`: nullable foreign key to `model_brands.id`.
- `assigned_team_id`: nullable placeholder for future team records.
- `assigned_chatter_id`: nullable foreign key to `users.id`.
- `notes`: safe operator notes.
- `status`: `active`, `disabled`, or `archived`.
- `is_active`: active/disabled flag.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- `ck_creator_watches_platform`.
- `ck_creator_watches_priority`.
- `ck_creator_watches_status`.
- `ix_creator_watches_platform`.
- `ix_creator_watches_creator_username`.
- `ix_creator_watches_niche`.
- `ix_creator_watches_priority`.
- `ix_creator_watches_status`.
- `ix_creator_watches_assigned_model_id`.
- `ix_creator_watches_assigned_team_id`.
- `ix_creator_watches_assigned_chatter_id`.
- `ix_creator_watches_is_active`.

### post_watches

Manual tracking records for important owned posts.

Columns:

- `id`: primary key.
- `model_brand_id`: foreign key to `model_brands.id`, cascade delete.
- `platform`: `x`, `instagram`, or `other`.
- `account_id`: nullable foreign key to `accounts.id`.
- `post_reference`: safe manual reference such as URL, slug, or internal label.
- `post_type`: `image`, `video`, `text`, `thread`, `story`, `reel`, or `other`.
- `status`: `recent`, `attention_needed`, `assigned`, or `archived`.
- `attention_level`: `monitor`, `engage`, or `urgent`.
- `assigned_chatter_id`: nullable foreign key to `users.id`.
- `assigned_team_id`: nullable placeholder for future team records.
- `notes`: safe operator notes.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- `ck_post_watches_platform`.
- `ck_post_watches_status`.
- `ck_post_watches_post_type`.
- `ck_post_watches_attention_level`.
- `ix_post_watches_model_brand_id`.
- `ix_post_watches_account_id`.
- `ix_post_watches_platform`.
- `ix_post_watches_status`.
- `ix_post_watches_attention_level`.
- `ix_post_watches_assigned_chatter_id`.
- `ix_post_watches_assigned_team_id`.
- `ix_post_watches_created_at`.

### comment_strategies

Deterministic human-review strategy prompts for opportunities. These are not automated comments.

Columns:

- `id`: primary key.
- `opportunity_id`: nullable foreign key to `opportunities.id`, cascade delete.
- `angle`: `curiosity`, `question`, `agreement`, `relatable`, `story`, `authority`, `contrarian`, `soft_cta`, `humor`, `educational`, or `supportive`.
- `tone`: short human-readable tone label.
- `sample_comment`: human-editable draft comment. Never posted automatically.
- `curiosity_score`: 0-100.
- `engagement_score`: 0-100.
- `risk_score`: 0-100.
- `reasoning`: safe explanation for the suggestion.
- `why_it_might_work`: safe explanation of expected value.
- `suggested_use_case`: safe operator guidance.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- `ck_comment_strategies_angle`.
- score range checks for curiosity, engagement, and risk.
- `ix_comment_strategies_opportunity_id`.
- `ix_comment_strategies_angle`.
- `ix_comment_strategies_risk_score`.

## Relationships

- A user can have many roles through `user_roles`.
- A user can have one availability record through `user_availability.user_id`.
- A role can have many users through `user_roles`.
- A role can have many permissions through `role_permissions`.
- A permission can belong to many roles through `role_permissions`.
- A model/brand can have many assigned users through `model_brand_members`.
- A user can be assigned to many model/brands through `model_brand_members`.
- A model/brand can have many accounts through `accounts.model_brand_id`.
- A proxy can have many accounts through `accounts.assigned_proxy_id`.
- A proxy can have many rotation history rows through `proxy_rotation_history.proxy_id`.
- A proxy can have many health check rows through `proxy_health_check_results.proxy_id`.
- A task can attach to a model/brand, account, proxy, owner user, assigned user, and creator.
- An incident can attach to a model/brand, account, proxy, owner user, assigned user, creator, and resolver.
- An incident can have many timeline entries through `incident_timeline.incident_id`.
- An account can have many auth sessions through `account_auth_sessions.account_id`.
- An auth session can have many hashed verification-code submissions through `account_verification_codes.auth_session_id`.
- An incident can point to a source resource through `source_type` and `source_id`.
- An audit log may reference an actor user through `actor_user_id`.
- An event log may reference an actor user through `actor_user_id`.
- A daily briefing may reference the user who generated it.
- An accountability snapshot references the user it describes.
- An automation simulation run references the user who simulated it.
- An automation rule can have many simulation runs, approvals, execution runs, and schedules.
- An automation run belongs to one automation rule and can have many ordered run steps.
- An automation approval belongs to one automation rule and references the requesting and deciding users.
- A recommendation may reference the event that generated it and may point to an entity by `entity_type`/`entity_id`.
- System heartbeats are keyed by service name and do not reference secrets or deployment credentials.
- A notification target can have many delivery attempts through `notification_delivery_attempts.notification_target_id`.
- Intelligence signals and issue patterns may point to any domain entity through `entity_type`/`entity_id`.
- Workload snapshots reference the user they describe through `workload_snapshots.user_id`.
- Executive insights store source signal IDs as safe JSON so insight generation can explain its inputs.
- Opportunity sources can have many opportunities through `opportunities.source_id`.
- Opportunities can attach to a model/brand and assigned user.
- Opportunity results belong to an opportunity and may reference the user who manually posted or recorded the result.
- Creator watch records can attach to a model/brand and assigned chatter.
- Post watch records attach to a model/brand and may attach to an account.
- Comment strategies can attach to an opportunity and are deleted with that opportunity.

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

Proxy status:

- `healthy`: proxy is operating normally.
- `warning`: proxy needs attention but remains usable.
- `critical`: proxy is failing, mismatched, or otherwise high risk.
- `disabled`: proxy is intentionally blocked.

Incident status:

- `open`: active incident requiring attention.
- `investigating`: incident is being worked or has been escalated.
- `resolved`: incident has been repaired with notes/history retained.
- `archived`: incident is administratively archived.

Task status:

- `open`: task is queued and not started.
- `in_progress`: task is actively being worked.
- `blocked`: task cannot move until another issue is resolved.
- `complete`: task is completed and has `completed_at`.
- `archived`: task is hidden from default active lists while preserving history.

Task priority:

- `low`: low urgency.
- `normal`: default urgency.
- `high`: elevated priority.
- `urgent`: immediate attention required.

Notification target state:

- `is_active = true`: eligible for future routing.
- `is_active = false`: disabled without deleting historical configuration or events.

Automation simulation status:

- `pending`: simulation record is queued.
- `running`: simulation is evaluating triggers, conditions, and impact.
- `succeeded`: simulation completed and did not mutate production records.
- `failed`: simulation failed safely.
- `expired`: preview is too old to approve.
- `draft`, `simulated`, `approved`, and `rejected`: legacy Sprint 9 review statuses retained for existing rows.

Automation rule status:

- `draft`: saved but not simulated yet.
- `simulated`: a current simulation exists for review.
- `pending_approval`: approval has been requested.
- `approved`: approved but not active.
- `active`: eligible for safe execution.
- `paused`: temporarily inactive.
- `retired`: no longer used.
- `failed`: latest execution failed and needs review.

Recommendation status:

- `open`: visible in the command center.
- `acknowledged`: operator has seen it.
- `dismissed`: operator decided it is not actionable.
- `resolved`: underlying issue has been addressed.

Intelligence signal status:

- `open`: visible in intelligence screens.
- `acknowledged`: operator has seen the signal.
- `resolved`: underlying issue has been addressed.
- `dismissed`: operator decided it is not actionable.

Issue pattern status:

- `active`: currently detected as recurring.
- `acknowledged`: operator has seen the pattern.
- `resolved`: root cause has been addressed.
- `dismissed`: operator decided it is not actionable.

Opportunity status:

- `discovered`: manually captured but not reviewed.
- `reviewing`: scored or under review.
- `approved`: human-approved for next action.
- `assigned`: assigned to a teammate.
- `completed`: manual result recorded as posted/completed.
- `rejected`: rejected by an operator.
- `archived`: hidden from default active views.

Learning and playbook status:

- Learning event outcomes are immutable once recorded and use `success`, `failure`, `partial`, `ignored`, or `unknown`.
- Playbooks use `draft`, `active`, `needs_review`, or `retired`.
- Playbook runs use append-style status history: `suggested`, `approved`, `running`, `succeeded`, `failed`, `skipped`, or `rolled_back`.
- Outcome memory rows update aggregate counters in place.
- Confidence records are append-only explanations.

## Learning and Memory Tables

### learning_events

Stores meaningful outcomes that Fortuna OS can learn from.

Columns:

- `id`: primary key.
- `event_type`: stable dotted learning event name.
- `source_type`: `task`, `incident`, `proxy`, `account`, `automation`, `recommendation`, `opportunity`, `notification`, or `system`.
- `source_id`: optional source record ID stored as text for cross-module flexibility.
- `entity_type`, `entity_id`: optional affected entity reference.
- `outcome`: `success`, `failure`, `partial`, `ignored`, or `unknown`.
- `severity`: `info`, `warning`, or `critical`.
- `summary`: concise safe operator summary.
- `details_json`: safe metadata only.
- `confidence_score`: optional 0-100 confidence score.
- `created_by_user_id`: nullable FK to `users.id`.
- `created_at`: timestamp.

Indexes and constraints:

- Check constraints on `source_type`, `outcome`, `severity`, and confidence bounds.
- Indexes on event type, source, entity, outcome, severity, creator, and creation time.

### playbooks

Reusable operating and recovery memory.

Columns:

- `id`: primary key.
- `name`: unique playbook name.
- `category`: `proxy`, `account`, `task`, `incident`, `automation`, `notification`, `opportunity`, or `system`.
- `trigger_summary`: human-readable trigger.
- `diagnosis_steps_json`, `resolution_steps_json`, `verification_steps_json`: ordered safe step lists.
- `rollback_steps_json`: nullable rollback/limitation steps.
- `risk_level`: `low`, `medium`, `high`, or `critical`.
- `confidence_score`: 0-100 current confidence.
- `success_count`, `failure_count`: aggregate run outcomes.
- `last_used_at`: nullable timestamp.
- `status`: `draft`, `active`, `needs_review`, or `retired`.
- `created_by_user_id`: nullable FK to `users.id`.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- Unique constraint on `name`.
- Check constraints on category, risk, status, confidence, and non-negative counts.
- Indexes on category, risk, status, confidence, and creator.

### playbook_runs

Tracks every time a playbook is suggested, approved, run, skipped, failed, succeeded, or rolled back.

Columns:

- `id`: primary key.
- `playbook_id`: FK to `playbooks.id`, cascade delete.
- `source_type`, `source_id`: optional source context.
- `status`: `suggested`, `approved`, `running`, `succeeded`, `failed`, `skipped`, or `rolled_back`.
- `started_by_user_id`, `approved_by_user_id`: nullable FKs to `users.id`.
- `confidence_before`, `confidence_after`: nullable 0-100 scores.
- `result_summary`: nullable safe summary.
- `safe_metadata_json`: safe metadata only.
- `created_at`, `finished_at`: timestamps.

Indexes and constraints:

- Check constraints on status and confidence bounds.
- Indexes on playbook, source, status, starter, approver, created time, and finished time.

### outcome_memory

Aggregates learning events into durable memory keys and success/failure rates.

Columns:

- `id`: primary key.
- `memory_key`: unique deterministic key such as `proxy_failure:proxy:12`.
- `memory_type`: `proxy_failure`, `account_issue`, `incident_pattern`, `automation_result`, `recommendation_result`, `opportunity_result`, `notification_failure`, `task_overdue`, or `system_health`.
- `entity_type`, `entity_id`: optional related entity.
- `occurrences`, `success_count`, `failure_count`, `partial_count`, `ignored_count`: aggregate counters.
- `success_rate`: integer 0-100.
- `last_outcome`: latest outcome.
- `last_seen_at`: latest learning event timestamp.
- `summary`: deterministic operator-readable summary.
- `metadata_json`: safe metadata only.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- Unique constraint on `memory_key`.
- Check constraints on memory type, last outcome, counters, and success-rate bounds.
- Indexes on memory type, entity, last outcome, success rate, and last seen time.

### confidence_records

Explains why confidence changed over time.

Columns:

- `id`: primary key.
- `subject_type`: `recommendation`, `playbook`, `automation`, `proxy`, `opportunity`, `intelligence_signal`, or `issue_pattern`.
- `subject_id`: subject record ID stored as text.
- `previous_score`: nullable 0-100 prior score.
- `new_score`: 0-100 updated score.
- `reason`: safe explanation.
- `evidence_json`: safe evidence metadata only.
- `created_at`: timestamp.

Indexes and constraints:

- Check constraints on subject type and confidence bounds.
- Indexes on subject and created time.

### Setup Wizard And UI Clarity Tables

Sprint 19 adds durable setup state and first-day checklist records so the owner can onboard the agency without relying on memory or placeholder screens.

`model_brands` now also stores:

- `country`: optional operating country for the model/brand.
- `timezone`: optional display timezone.
- `language_preference`: optional future localization preference.
- `primary_platform`: optional main platform label.
- `internal_notes`: owner/admin-only setup notes.
- `is_demo`: marks owner-created demo seed records.

Indexes were added for `country`, `timezone`, and `is_demo`.

`accounts`, `creator_watches`, `post_watches`, and `opportunities` now include `is_demo` so demo records can be created and cleared without touching production records.

### setup_wizard_states

Tracks an Owner/Admin setup session.

Columns:

- `id`: primary key.
- `owner_user_id`: FK to `users.id`.
- `model_brand_id`: nullable FK to the model created through the wizard.
- `status`: `started`, `in_progress`, `completed`, or `abandoned`.
- `current_step`: current setup step such as `model`, `accounts`, `team`, `creators`, `opportunities`, or `summary`.
- `summary_json`: safe summary metadata only.
- `missing_items_json`: safe list of missing setup items.
- `completed_at`: nullable completion timestamp.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- Check constraint on `status`.
- Indexes on owner, model, and status.

### first_day_checklists

Tracks the owner/manager first-day activation plan.

Columns:

- `id`: primary key.
- `user_id`: unique FK to `users.id`.
- Boolean checklist items for first model, accounts, manager, team, creators, opportunities, briefing, activation review, and production status.
- `completion_score`: 0-100.
- `metadata_json`: safe metadata only.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- Unique index on `user_id`.
- Check constraint on `completion_score`.
- Index on completion score.

## Sprint 22 Autonomous Operations

### operations_workflows

Tracks each autonomous diagnosis or preparation workflow Fortuna OS starts after something changes.

Columns:

- `id`: primary key.
- `workflow_type`: account, model, creator, opportunity, readiness, or daily-cycle workflow category.
- `source_type`: source entity family such as `account`, `model_brand`, `creator_watch`, `opportunity`, `agency_activation`, or `system`.
- `source_id`: source identifier stored as text for cross-entity flexibility.
- `status`: `pending`, `ready`, `running`, `completed`, `blocked`, `failed`, or `skipped`.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- Check constraint on `status`.
- Indexes on workflow type, source, status, and updated timestamp.

### operations_actions

Stores the next safe actions Fortuna OS prepared inside a workflow.

Columns:

- `id`: primary key.
- `workflow_id`: FK to `operations_workflows.id`.
- `action_type`: deterministic action key such as `assign_proxy`, `complete_auth_setup`, `recommend_assignee`, or `track_result`.
- `status`: `pending`, `ready`, `running`, `completed`, `blocked`, `failed`, or `skipped`.
- `priority`: `low`, `normal`, `high`, or `urgent`.
- `assigned_user_id`: nullable FK to `users.id` for routed ownership.
- `result_summary`: safe human-readable summary only.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- Check constraints on `status` and `priority`.
- Indexes on workflow, status, priority, assigned user, and creation timestamp.

### follow_ups

Tracks outstanding reminders Fortuna OS should revisit without relying on the owner to rediscover the issue.

Columns:

- `id`: primary key.
- `source_type`: source entity family.
- `source_id`: source identifier stored as text.
- `due_at`: UTC follow-up time.
- `assigned_user_id`: nullable FK to `users.id`.
- `status`: `pending`, `completed`, `blocked`, `failed`, or `skipped`.
- `reminder_count`: number of reminders already attempted.
- `created_at`, `updated_at`: timestamps.

Indexes and constraints:

- Check constraint on `status`.
- Indexes on source, status, due time, and assigned user.

## Soft Delete Strategy

- Users are not deleted during normal admin flows. Use `disabled` or `denied`.
- Roles and permissions should not be deleted casually because they affect audit interpretation and historical access context.
- Model/Brand records should use `disabled` or `archived` instead of hard deletion.
- Account records should use `disabled` or `archived` instead of hard deletion.
- Proxy records should use `disabled` instead of hard deletion.
- Tasks should use `complete` or `archived` instead of hard deletion.
- Incidents should use `resolved` or `archived` instead of hard deletion.
- Notification targets should be disabled instead of deleted.
- Notification delivery attempts are append-style history records and should not be deleted during normal operations.
- Automation simulation runs are history records and should not be deleted during normal operations.
- Recommendations should move through status instead of hard deletion.
- Intelligence signals, patterns, insights, runs, opportunities, and opportunity results should move through status instead of hard deletion.
- Creator watch records use `status` plus `is_active` for disabled/archived active-view filtering.
- Post watch records use `status` for recent, attention-needed, assigned, and archived states.
- Comment strategies are derived guidance and can be deleted with the parent opportunity.
- Setup wizard states are kept as operational history. Demo records are intentionally removable only through owner-only demo cleanup.
- Operations workflows, operations actions, and follow-ups are operational history and should move through status instead of being deleted.
- Learning events, playbook runs, outcome memory, and confidence records should not be hard deleted during normal operations.
- Playbooks should move to `needs_review` or `retired` instead of deletion.
- System heartbeat rows are updated in place by service name; state changes are still emitted to audit/event logs.
- Daily briefings, accountability snapshots, event logs, and audit logs are append-style history records.
- Future business resources should prefer status-based archival before hard deletes.

## Safe Metadata Strategy

Sprint 25 tightened metadata handling across audits, events, recommendations, heartbeats, incident timelines, and learning verification paths.

Safe JSON fields may store counts, entity IDs, statuses, timestamps, category names, and short human-readable summaries.

Unsafe values must be redacted before persistence:

- bot tokens
- API keys
- app/encryption keys
- passwords and proxy passwords
- credentials
- session strings
- verification codes and code hashes
- raw Telegram chat IDs
- owner Telegram IDs
- platform session payloads

The shared sanitizer is recursive, so nested dictionaries and lists are also redacted.

## Production Observability Reads

Sprint 26 does not add new tables. Production Observability reads existing tables:

- `system_heartbeats` for API, bot, DB, Redis, and Railway status labels.
- `alembic_version` for the current DB migration revision.
- local Alembic migration files for expected head revision.
- `audit_logs` for the latest audit event.
- `event_logs` for the latest system event.
- `automation_runs` for the latest automation run.
- `intelligence_runs` for the latest intelligence run.
- `notification_targets` for notification group readiness.

No secrets or raw environment variables are stored for observability.

## Sprint 28 Help And Pilot Tables

`help_knowledge_base`

- seeded help articles
- unique `topic`
- `role_scope`
- `related_route`
- timestamps

`help_question_logs`

- user asking the question
- original question
- detected intent
- safe answer summary
- optional feedback: `helpful`, `not_helpful`, `still_confused`
- timestamp

`ui_self_test_runs`

- owner who requested the run
- status: `passed`, `warning`, `failed`
- screens checked
- safe failures JSON
- safe warnings JSON
- timestamp

These tables do not store secrets, raw environment variables, proxy passwords, 2FA codes, platform credentials, or raw Telegram chat IDs.

## Future Planned Tables

- `account_credentials`: secret references only, not raw secrets.
- `proxy_credentials`: secret references only, not raw secrets.
- `proxy_health_checks`: proxy check results and failure reasons.
- `task_assignments`: richer task ownership and handoff history if one-assignee tasks become insufficient.
- `incident_events`: richer incident timeline events if escalation history JSON becomes insufficient.
- `report_runs`: richer report generation records if daily briefings/accountability snapshots are not enough.
- `repair_attempts`: self-healing attempts and outcomes.
- `ai_recommendations`: AI operations suggestions, confidence, and operator disposition.
- `opportunity_campaigns`: grouped opportunity batches once manual results need campaign-level attribution.
- `teams`: first-class team records to replace the placeholder `creator_watches.assigned_team_id`.
- `creator_watch_history`: optional creator-watch change history if the audit/event feed becomes too broad for manager views.
