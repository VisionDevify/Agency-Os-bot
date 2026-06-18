# Production Observability

Sprint 26 adds an owner-only Production Observability screen:

Settings -> Production Observability

The screen shows safe operational metadata only:

- app display name
- environment
- optional app version
- optional git commit
- optional deployed timestamp
- optional Railway deployment id
- Alembic current revision
- expected Alembic head
- API, bot, Postgres, Redis, and Railway heartbeat status
- bot started timestamp
- last polling loop heartbeat
- last Telegram update timestamp
- duplicate polling guard status
- last audit event
- last event log
- last automation run
- last intelligence run
- notification group readiness

It does not show:

- bot token
- database URL
- Redis URL
- app secret key
- encryption key
- owner Telegram id
- raw environment variables

If build metadata is missing, the screen renders `Unknown` instead of failing.

Railway logs are not pulled into the app. View deployment and runtime logs in the Railway dashboard.

## Build Metadata

Optional environment variables:

- `APP_VERSION`
- `GIT_COMMIT`
- `DEPLOYED_AT`
- `RAILWAY_DEPLOYMENT_ID`

These values are safe labels for operators. They must not contain secrets.

## Bot Heartbeat

The bot heartbeat stores safe metadata:

- startup time
- last polling-loop heartbeat
- last Telegram update processed
- polling guard type
- Redis lock status

The heartbeat merges safe metadata over time so startup and live polling fields can coexist.

## Notification Readiness

Production Observability checks whether active targets exist for:

- HQ
- Operations
- Incidents
- Automation Logs
- Testing Sandbox

Registration still happens from Telegram:

1. Open the target group or channel.
2. Add `@FortunaSolstice_Bot`.
3. Use Settings -> Notification Targets -> Register Current Chat as Fortuna Target.
4. Select the correct purpose.
5. Send test notifications only to Testing Sandbox until owner approval.
