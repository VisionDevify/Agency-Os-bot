# Railway Deployment

Sprint 8 inspected Railway and found the logged-in workspace had no project yet. Sprint 9 re-confirmed the workspace had 0 projects. Sprint 10 re-inspected the workspace and found a trial/credit banner, so project creation, service creation, database provisioning, and any billing-impacting action required owner approval. Owner approval was later granted for Fortuna OS production activation.

## Current Railway Status

- Project created for Fortuna OS production. The visible Railway project label may still be the generated project name unless it is renamed in the Railway UI.
- Production API service: created from `VisionDevify/Agency-Os-bot`.
- Production bot worker service: created from `VisionDevify/Agency-Os-bot`.
- Production PostgreSQL: created and attached.
- Production Redis: created and attached.
- Production environment variables: added in Railway without printing values.
- API public domain: `agency-os-bot-production.up.railway.app`.
- Remaining check: verify public `/health` after any networking/start-command changes finish deploying.

## Expected Services

- API service: runs FastAPI with `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- Bot worker service: runs `python -m app.bot.runner`.
- PostgreSQL service.
- Redis service.

## Required Variables

Set these in Railway variables. Confirm presence only; never print values.

- `TELEGRAM_BOT_TOKEN`
- `DATABASE_URL`
- `REDIS_URL`
- `APP_SECRET_KEY`
- `ENCRYPTION_KEY`
- `OWNER_TELEGRAM_ID`

Shared/app variables:

- `APP_SECRET_KEY`
- `ENCRYPTION_KEY`
- `OWNER_TELEGRAM_ID`

Bot worker variables:

- `TELEGRAM_BOT_TOKEN`
- `DATABASE_URL`
- `REDIS_URL`
- `APP_SECRET_KEY`
- `ENCRYPTION_KEY`
- `OWNER_TELEGRAM_ID`

API service variables:

- `DATABASE_URL`
- `REDIS_URL`
- `APP_SECRET_KEY`
- `ENCRYPTION_KEY`
- `OWNER_TELEGRAM_ID`
- `GIT_COMMIT`
- `APP_VERSION`
- `DEPLOYED_AT`

Safe build metadata variables:

- `GIT_COMMIT`: short or full git commit SHA deployed to Railway.
- `APP_VERSION`: human-readable release/build label.
- `DEPLOYED_AT`: deployment timestamp, preferably ISO 8601.

These values are returned by `/health` and Production Observability so operators can prove what code is running. They must never contain secrets, URLs, tokens, or dumped environment values.

## API Service

The root `railway.json` is suitable for shared repo deployments:

- Dockerfile builder.
- restart on failure.
- no shared start command, so it does not override the bot worker.

The API exposes `/health`. Verify it manually after deployment, or configure an API-only Railway
healthcheck in the API service settings. Do not put a shared healthcheck in `railway.json`, because
the bot worker service runs as a polling worker and should not be treated as an HTTP service.

The API uses the Dockerfile default command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

After deployment, verify:

```bash
curl https://<api-service-domain>/health
```

Expected response:

```json
{
  "app_name": "Fortuna OS",
  "environment": "production",
  "git_commit": "198e746",
  "build_version": "v50.1",
  "deployed_at": "2026-06-19T12:00:00Z",
  "alembic_revision": "0037_social_comment_profiles",
  "status": "ok",
  "api": "healthy",
  "db": "healthy",
  "db_backend": "postgresql",
  "db_durable": true,
  "redis": "healthy"
}
```

If `GIT_COMMIT`, `APP_VERSION`, or `DEPLOYED_AT` are missing, `/health` returns `unknown` for those safe metadata fields. If PostgreSQL or Redis are not attached yet, `/health` must say so. Emergency SQLite in Railway returns `status=degraded`, `db=degraded`, and `db_backend=sqlite_fallback`. Do not treat a production bot as durable until `db_backend=postgresql`, `db_durable=true`, and `redis=healthy`.

## Bot Worker Service

Create a separate Railway service from the same repo and override the start command:

```bash
python -m app.bot.runner
```

Verify the worker container command with `/proc/1/cmdline`; it should show `python -m app.bot.runner`,
not `uvicorn app.main:app`.

Do not expose an HTTP domain for the worker unless a future webhook mode is added. Current bot mode uses polling.

## Migration Strategy

Migrations run at API startup after database variables are present. The bot worker should not own migrations. A manual migration command is still safe when needed:

```bash
alembic upgrade head
```

Recommended safe flow:

1. Provision PostgreSQL and Redis.
2. Attach variables to API and bot services.
3. Deploy API.
4. Allow startup migrations to run, or run `alembic upgrade head` as a one-off Railway command if needed.
5. Verify `/health`.
6. Start or redeploy the bot worker.
7. Verify `/start` in Telegram.

Do not reset, delete, or recreate production databases without explicit approval.

## Smoke Test

After deploy, run the checklist in `docs/production_smoke_test.md`.

## Current Blockers

- Public API `/health` must return `db_backend=postgresql` and `redis=healthy` for production-ready persistence.
- If Railway resource limits block PostgreSQL/Redis, follow `docs/postgres_recovery_plan.md`.
- Telegram production `/start` should be smoke-tested after the Railway bot worker is confirmed active.
- Telegram groups/channels and notification target registration are still manual/future production setup items.
