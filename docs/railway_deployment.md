# Railway Deployment

Sprint 8 inspected Railway and found the logged-in workspace has no project yet. This repo is now prepared for Railway, but project creation, service creation, database provisioning, and any billing-impacting action require owner approval.

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
{"status":"ok"}
```

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

## Current Blockers

- No Railway project exists in the inspected workspace.
- API, bot worker, PostgreSQL, and Redis services must be created.
- Required variables must be added in Railway without exposing values.
- A production migration command must be run after the database is attached.
