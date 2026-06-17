# Production Operations

Sprint 9 prepares Agency OS for production activation while stopping before billing-impacting or destructive actions.

## Current Production State

- Railway workspace inspection found 0 projects.
- API service is not created.
- Bot worker service is not created.
- PostgreSQL is not provisioned.
- Redis is not provisioned.
- Production variables are not present because services do not exist yet.

Owner approval is required before creating the Railway project and provisioning services.

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

`railway_deployment` heartbeat is a production status placeholder until Railway deployment exists.

## Production Safety

- Do not delete databases.
- Do not reset production data.
- Do not change billing without approval.
- Do not print or screenshot secret values.
- Run Alembic migrations after the production database is attached.
- Verify `/health` before starting the bot worker.

## Telegram Groups

Recommended Agency OS destinations:

- Agency OS - HQ
- Agency OS - Operations
- Agency OS - Incidents
- Agency OS - Automation Logs
- Agency OS - Testing Sandbox

Create and configure these only inside the Agency OS scope. Add `@FortunaSolstice_Bot` after confirming group/channel ownership and admin permissions.
