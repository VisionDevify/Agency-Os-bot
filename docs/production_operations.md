# Production Operations

Sprint 9 prepared Agency OS for production activation while stopping before billing-impacting or destructive actions. Sprint 10 added delivery-attempt tracking. Owner approval was later granted for Railway production activation.
Sprint 11 adds a Redis-backed bot polling guard and operator-facing production status controls.

## Current Production State

- Railway project exists for Agency OS.
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

## Health And Heartbeats

The `/health` endpoint returns safe labels for API, database, and Redis. It also updates `system_heartbeats` for:

- `api`
- `db`
- `redis`

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
- The bot runner uses a Redis lock to refuse duplicate polling when another Agency OS bot process appears active.

## Telegram Groups

Recommended Agency OS destinations:

- Agency OS - HQ
- Agency OS - Operations
- Agency OS - Incidents
- Agency OS - Automation Logs
- Agency OS - Testing Sandbox

Create and configure these only inside the Agency OS scope. Add `@FortunaSolstice_Bot` after confirming group/channel ownership and admin permissions.

If Telegram Web requires manual group creation, use these steps:

1. Create each group/channel with the exact Agency OS name.
2. Add `@FortunaSolstice_Bot`.
3. Open the bot UI in that chat.
4. Use Settings -> Notification Targets -> Add Current Chat As Target.
5. Set the matching purpose.
6. Send only one test notification to Testing Sandbox.

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

- Reports -> Manager Command View.
- Reports -> Daily Digest.
- Tasks -> My Tasks and Team Tasks.
- Incidents -> Open Incidents and Critical Incidents.
- Settings -> My Availability.
- Settings -> Production Status.
