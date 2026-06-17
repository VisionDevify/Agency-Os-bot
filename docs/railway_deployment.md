# Railway Deployment

Sprint 8 inspected Railway and found the logged-in workspace has no project yet. Sprint 9 re-confirmed the workspace currently has 0 projects. Sprint 10 re-inspected the workspace and found a trial/credit banner, so project creation, service creation, database provisioning, and any billing-impacting action require owner approval.

## Current Railway Status

- Project count: 0 in the inspected workspace.
- Production API service: not created.
- Production bot worker service: not created.
- Production PostgreSQL: not created.
- Production Redis: not created.
- Production environment variables: not present because services do not exist yet.
- Action needed: owner approval to create the Railway project and provision services.
- Approval blocker: creating the project/services may consume trial credit or require billing confirmation.

## Expected Services

- API service: runs FastAPI with `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`.
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
- `PORT` if Railway does not inject it automatically.

## API Service

The root `railway.json` is suitable for the API service:

- Dockerfile builder.
- `/health` health check.
- restart on failure.
- start command using Railway `PORT`.

After deployment, verify:

```bash
curl https://<api-service-domain>/health
```

Expected response:

```json
{"status":"ok","api":"healthy","db":"healthy","redis":"healthy"}
```

If PostgreSQL or Redis are not attached yet, `/health` may return `unknown` or `unhealthy` for those dependencies while still avoiding secret output.

## Bot Worker Service

Create a separate Railway service from the same repo and override the start command:

```bash
python -m app.bot.runner
```

Do not expose an HTTP domain for the worker unless a future webhook mode is added. Current bot mode uses polling.

## Migration Strategy

Run migrations after database variables are present and before starting the bot worker:

```bash
alembic upgrade head
```

Recommended safe flow:

1. Provision PostgreSQL and Redis.
2. Attach variables to API and bot services.
3. Deploy API.
4. Run `alembic upgrade head` as a one-off Railway command.
5. Verify `/health`.
6. Start or redeploy the bot worker.
7. Verify `/start` in Telegram.

Do not reset, delete, or recreate production databases without explicit approval.

## Smoke Test

After deploy, run the checklist in `docs/production_smoke_test.md`.

## Current Blockers

- No Railway project exists in the inspected workspace.
- API, bot worker, PostgreSQL, and Redis services must be created.
- Required variables must be added in Railway without exposing values.
- A production migration command must be run after the database is attached.
- Creating services and databases may consume Railway trial credit or require billing decisions, so it is intentionally blocked until owner approval.
