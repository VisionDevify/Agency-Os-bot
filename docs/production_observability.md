# Production Observability

Sprint 26 adds an owner-only Production Observability screen:

Settings -> Production Observability

The screen shows safe operational metadata only. It uses the same safe build metadata as `/health`:

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
- configured notification target count
- proxy real-check flags
- last real proxy health check
- recent proxy health warnings/failures

It does not show:

- bot token
- database URL
- Redis URL
- app secret key
- encryption key
- owner Telegram id
- raw environment variables

If build metadata is missing, the screen renders `unknown` instead of failing.

Railway logs are not pulled into the app. View deployment and runtime logs in the Railway dashboard.

## Build Metadata

Optional environment variables:

- `APP_VERSION`
- `GIT_COMMIT`
- `DEPLOYED_AT`
- `RAILWAY_DEPLOYMENT_ID`

Set `GIT_COMMIT`, `APP_VERSION`, and `DEPLOYED_AT` in Railway for deploy verification. These values are safe labels for operators. They must not contain secrets, URLs, tokens, or dumped environment values. Suspicious values are hidden as `unknown`.

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
3. Use Settings -> Notification Group Setup -> Register Current Chat as Fortuna Target.
4. Select the correct purpose.
5. Send test notifications only to Testing Sandbox until owner approval.

## Proxy Health Reality

Production Observability shows whether global real proxy health and location checks are enabled, the last real proxy check status/time, and whether recent proxy health failures exist. Real checks remain disabled by default. Per-proxy owner enablement and check history are shown in Proxy Detail.

## Sprint 28 Help And Pilot Signals

Production Observability also shows:

- Help questions in the last 24 hours.
- Confused help feedback count.
- Notification pilot configured count.
- Proxy pilot enabled proxy count.
- Last UI Self-Test result.

UI Self-Test is owner-only and can be opened from Settings or run with `/selftest`. It renders core Telegram screens internally, which gives the owner a verification path when Telegram Web callbacks are unreliable.

The API service owns startup migrations. The bot worker must not run Alembic before polling; it should acquire the Redis polling guard, record heartbeat, and start polling promptly.
