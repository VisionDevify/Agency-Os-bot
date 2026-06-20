# Production Operations

Sprint 9 prepared Fortuna OS for production activation while stopping before billing-impacting or destructive actions. Sprint 10 added delivery-attempt tracking. Owner approval was later granted for Railway production activation.
Sprint 11 adds a Redis-backed bot polling guard and operator-facing production status controls.
Sprint 12 adds deterministic intelligence scans, executive intelligence briefings, workload intelligence, and manual opportunity intelligence.
Sprint 25 adds verification docs and focused regression tests for health, bot ownership, safe metadata, intelligence, learning, and core Telegram callbacks.

## Current Production State

- Railway project exists for Fortuna OS.
- API service is created from `VisionDevify/Agency-Os-bot`.
- Bot worker service is created from `VisionDevify/Agency-Os-bot`.
- PostgreSQL is provisioned.
- Redis is provisioned.
- Production variables are configured in Railway without exposing values.

## Expected Railway Services

- API service from `agency-os-bot`.
- Bot worker service from `agency-os-bot`.
- PostgreSQL.
- Redis.

## Required Variables

Confirm presence only; never print values:

- `TELEGRAM_BOT_TOKEN`
- `DATABASE_URL`
- `REDIS_URL`
- `APP_SECRET_KEY`
- `ENCRYPTION_KEY`
- `OWNER_TELEGRAM_ID`
- `GIT_COMMIT`
- `APP_VERSION`
- `DEPLOYED_AT`

Safe build metadata:

- `GIT_COMMIT`: commit SHA deployed to Railway.
- `RAILWAY_GIT_COMMIT_SHA`: Railway-provided safe fallback commit SHA when `GIT_COMMIT` is not set.
- `APP_VERSION`: release/build label.
- `DEPLOYED_AT`: deployment timestamp.

These labels are safe to show in `/health` and Production Observability. Do not put secrets, URLs, tokens, or dumped env values in these fields.

Recovery storage variables:

- `BACKUP_S3_ENDPOINT`
- `BACKUP_S3_BUCKET`
- `BACKUP_S3_REGION`
- `BACKUP_S3_ACCESS_KEY`
- `BACKUP_S3_SECRET_KEY`

Confirm only whether they are present. Do not print values. Missing storage credentials mean Recovery remains non-healthy and backup/restore activation is blocked until the owner configures them.

## Health And Heartbeats

The `/health` endpoint returns safe labels for API, database, Redis, build metadata, and Alembic revision. It also updates `system_heartbeats` for:

- `api`
- `db`
- `redis`

Public production health URL:

```bash
curl https://agency-os-bot-production.up.railway.app/health
```

Expected proof fields include `app_name`, `environment`, `git_commit`, `build_version`, `deployed_at`, `alembic_revision`, `db_backend`, `db_durable`, and `redis`. Missing build metadata renders as `unknown`; secrets and connection URLs are never returned.

Run the CI-safe Railway verifier after deploy:

```bash
python scripts/verify_railway.py --health-url https://agency-os-bot-production.up.railway.app/health --json
```

If the Railway CLI is installed outside `PATH`:

```powershell
$env:RAILWAY_CLI_COMMAND="$env:USERPROFILE\.railway\bin\railway.exe"
python scripts\verify_railway.py --health-url https://agency-os-bot-production.up.railway.app/health --json
```

The verifier is read-only. It reports Railway CLI, auth, linked project, API, worker, Postgres, Redis, and public health as `pass`, `fail`, or `unavailable`.

The bot worker records `bot` heartbeat rows on startup and Telegram activity.

`railway_deployment` heartbeat remains a production status placeholder until automated deployment
status ingestion is added.

## Production Status Dashboard

Settings -> Bot Status shows:

- environment: `local`, `railway`, or `unknown`
- API, bot, DB, Redis, and Railway deployment status
- last heartbeat timestamp
- last deployment status/time when available
- last notification delivery attempt
- failed notification count
- latest EventLog event type

These values are database-backed through `system_heartbeats`, `event_logs`, and `notification_delivery_attempts`.

## Production Safety

- Do not delete databases.
- Do not reset production data.
- Do not change billing without approval.
- Do not print or screenshot secret values.
- Run Alembic migrations after the production database is attached.
- Verify `/health` before starting the bot worker.
- Keep only one bot poller active. The production worker owns Telegram polling; local bot processes should stay stopped unless production polling is intentionally paused.
- The bot runner uses a token-scoped Redis owner lock (`telegram_polling_owner:*`) to refuse duplicate polling when another Fortuna OS bot process appears active.
- If Telegram reports `terminated by other getUpdates request`, Fortuna records a critical polling-conflict event, opens a recommendation to stop the duplicate poller, and surfaces the issue in `/botstatus`, `/selftest`, and Production Observability.
- `BOT_PRIMARY_INSTANCE=false` disables Telegram polling for a service even if a bot token exists.
- In Railway/production, Redis is required for polling unless `ALLOW_POLLING_WITHOUT_REDIS=true` is explicitly set for emergency mode.
- Owner-only `/botstatus` shows the masked bot instance ID, primary polling flag, Redis lock status, polling owner, service role/name, DB backend, latest conflict, and duplicate active instance warning.

## Telegram Groups

Recommended Fortuna OS destinations:

- Fortuna OS - HQ
- Fortuna OS - Operations
- Fortuna OS - Incidents
- Fortuna OS - Automation Logs
- Fortuna OS - Testing Sandbox

Create and configure these only inside the Fortuna OS scope. Add `@FortunaSolstice_Bot` after confirming group/channel ownership and admin permissions.

If Telegram Web requires manual group creation, use these steps:

1. Create `Fortuna OS - HQ`.
2. Create `Fortuna OS - Operations`.
3. Create `Fortuna OS - Incidents`.
4. Create `Fortuna OS - Automation Logs`.
5. Create `Fortuna OS - Testing Sandbox`.
6. Add `@FortunaSolstice_Bot` to each Fortuna OS group/channel.
7. Open each group/channel in Telegram.
8. Use Settings -> Notification Group Setup -> Register Current Chat as Fortuna Target from inside that group/channel.
9. Set the matching purpose:
   - HQ -> owner.
   - Operations -> operations.
   - Incidents -> incidents.
   - Automation Logs -> automation_logs.
   - Testing Sandbox -> testing.
10. Send a test notification only to Testing Sandbox until the owner approves real routing.

Use Settings -> Notification Group Setup -> Run Routing Test after at least the Testing Sandbox target is registered. The smoke test sends only to Testing Sandbox by default and records simulated/skipped attempts for the other purposes.

Do not use unrelated Telegram chats as notification targets. Do not send test notifications to HQ, Operations, Incidents, or Automation Logs until routing is intentionally activated.

## Delivery Attempts

Every real send attempt should create a `notification_delivery_attempts` row before delivery and then mark it `sent`, `failed`, or `skipped`.

Audit actions:

- `notification.delivery_attempted`
- `notification.delivery_succeeded`
- `notification.delivery_failed`

EventLog events:

- `notification.delivery_succeeded`
- `notification.delivery_failed`

Repeated failures create a warning recommendation for the affected Notification Target.

## Daily Operations

Daily agency usage should start from:

- Owner Home -> Owner Daily Checklist.
- Owner Home -> Fortuna Activation.
- Fortuna Automation -> Daily Autopilot.
- Fortuna Activation -> What Fortuna Did.
- Reports -> Manager Command View.
- Reports -> Executive Intelligence Briefing.
- Reports -> Workload Intelligence.
- Intelligence -> Run Analysis.
- Reports -> Daily Digest.
- Tasks -> My Tasks and Team Tasks.
- Incidents -> Open Incidents and Critical Incidents.
- Settings -> My Availability.
- Settings -> Production Status.

## Production Activation And Daily Autopilot

Sprint 23 turns activation into a guided daily operator loop:

- Fortuna Activation shows readiness blockers with `Fix Now`, `Explain`, `Skip for Later`, and `Mark Not Needed`.
- `Skip for Later` suppresses a blocker from immediate owner focus.
- `Mark Not Needed` suppresses a blocker when that setup item is intentionally out of scope.
- Owner Daily Checklist summarizes readiness score, owner approvals, critical incidents, accounts needing setup, unassigned opportunities, follow-ups due, and Daily Autopilot status.
- Daily Autopilot stores owner timezone, local run time, next run, last run, last result, and included safe actions in `daily_autopilot_settings`.
- Daily Autopilot Run Now executes the safe daily cycle, refreshes recommendations, runs intelligence checks, prepares a follow-up digest, and records automation health.
- What Fortuna Did summarizes autonomous actions, tasks, recommendations, follow-ups, automation runs, and errors for today, seven days, or all time.

High-risk automations, proxy repair mutations, and owner approvals remain gated. Daily Autopilot does not authorize social posting, scraping, credential handling, or platform security bypassing.

## Intelligence Operations

The Intelligence Command Center is safe to run in production because Sprint 12 scans are deterministic reads plus safe writes to Fortuna OS tables. They do not scrape external platforms, post content, rotate proxies, repair infrastructure, or mutate risky production resources without an explicit operator workflow.

Recommended daily flow:

1. Open Reports -> Executive Intelligence Briefing.
2. Run Intelligence -> Run Full Intelligence Scan if fresh analysis is needed.
3. Review Signals, Patterns, Trends, and Workload Intelligence.
4. Open Recommendations and use "Why am I seeing this?" before assigning work.
5. Use Opportunities only for manual, human-approved opportunity records.

Critical signals can create notification delivery attempts for configured owner/incidents/operations targets. Delivery attempts remain durable records and must not include secrets or raw chat IDs.

## Automation Operations

Sprint 14 adds a production-safe automation builder. Operators should manage automations from Automations -> Automation Dashboard.

Recommended flow:

1. Review Built-In Templates.
2. Open Rule Detail.
3. Run Simulation.
4. Review Impact Preview and rollback limitations.
5. Request or apply approval when required.
6. Activate only after a valid simulation exists.
7. Run Now only for approved/active rules.
8. Review Run History, Run Detail, and Step Detail after execution.

Production safeguards:

- No automation should become active without a simulation.
- High/critical risk automations require Owner approval.
- Proxy repair automation defaults to approval-required.
- Simulation runs do not mutate production entities.
- Execution writes `automation_runs` and `automation_run_steps` before reporting success/failure.
- Automation logs, audits, events, and Telegram screens must not show secrets.
- Social posting, commenting, liking, following, scraping, credential collection, and security bypass behavior remain out of scope.

Automation health metrics should be checked from Automations -> Automation Health and Executive Command Center. Failed high-risk automations should be reviewed before rerun.

## Production Observability

Sprint 26 adds an owner-only observability screen:

Settings -> Production Observability

This screen shows safe operational labels:

- app display name
- environment
- optional version, commit, deploy timestamp, and Railway deployment id
- Alembic current revision and expected head
- API, bot, Postgres, Redis, and Railway heartbeat status
- bot startup, polling-loop, and last Telegram update timestamps
- last audit, event, automation, and intelligence records
- notification group readiness

It does not display raw environment variables, tokens, database URLs, Redis URLs, or secret keys.

Railway logs must still be viewed in Railway. The app intentionally shows a placeholder explanation instead of scraping Railway logs.

If the Alembic revision status is `Mismatch`, inspect migration history and run only the normal forward migration command. Do not run destructive downgrade/reset commands.

## Sprint 28 Help And Pilot Operations

Help Brain:

- Use Help Center -> Ask Fortuna for role-aware workflow answers.
- Feedback buttons write safe learning events.
- Help answers must never include secrets, proxy passwords, raw chat IDs, or restricted admin data for non-admin users.

Notification pilot:

- Use Settings -> Notification Group Pilot to register and test groups.
- Testing Sandbox is the only default real-send target.
- Other purposes are simulated during routing tests until owner approval expands delivery.

Proxy pilot:

- Use Proxy Vault -> Real Check Pilot to test one saved proxy.
- Real checks remain owner-controlled and disabled by default.
- Proxy passwords are entered only through the secure bot UI and never displayed.

UI self-test:

- Use Settings -> UI Self-Test or `/selftest`.
- The self-test renders key screens internally and reports failures/warnings without depending on Telegram Web callback clicks.

Bot worker startup:

- API owns Alembic migrations.
- Bot worker should not run Alembic before polling.
- If API health is green but Telegram is silent, check bot worker logs for polling startup and heartbeat, not API health alone.

## Recovery Operations

Recovery Center is evidence-based. It must not show protected, healthy, passed, or successful unless real backup and restore evidence supports that state.

Owner activation flow:

1. Configure the `BACKUP_S3_*` variables in Railway.
2. Open Recovery Center -> Backup Storage.
3. Open S3-Compatible setup.
4. Activate / Test From Railway Env.
5. Confirm the connection test writes, reads, verifies, and cleans up a test object.
6. Run Backup.
7. Confirm the backup artifact was encrypted, uploaded, checksummed, and verified.
8. Run Restore Test.
9. Treat `verified_only` as a warning, not a full restore pass.

Backblaze B2 should be connected through its S3-compatible endpoint using the S3-Compatible setup path.

Sprint halt conditions for Recovery activation:

- Critical: checksum mismatch, decryptability failure, uploaded artifact cannot be verified, restore validation failed, or any fake-success contradiction.
- Blocking: missing Railway auth, missing project access, missing storage credentials, unavailable storage connection test, or missing restore-test prerequisite.
- Warning: optional build metadata missing, Telegram Web unavailable, or restore evidence is partial (`verified_only`).

Owner escalation must include the failed step, observed evidence, severity, and the exact owner action needed.
