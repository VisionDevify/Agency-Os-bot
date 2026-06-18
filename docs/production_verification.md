# Production Verification

Sprint 25 production checks focus on safe, non-destructive verification.

## Verified Production Shape

- API service exposes public `/health`.
- `/health` returns safe labels for API, database, and Redis.
- `/health` writes heartbeat records without returning secrets.
- Bot worker owns Telegram polling.
- Local Docker bot worker should remain stopped when production polling is active.
- PostgreSQL and Redis are attached to production.
- Railway start commands remain service-specific:
  - API: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
  - Bot Worker: `python -m app.bot.runner`

## Safe Checks

Use:

```bash
curl https://agency-os-bot-production.up.railway.app/health
```

Expected safe response:

```json
{"status":"ok","api":"healthy","db":"healthy","redis":"healthy"}
```

Telegram verification should use only the Fortuna OS bot and approved Fortuna OS spaces.

## No-Secret Rules

- Do not print Railway env var values.
- Do not screenshot secret values.
- Do not print bot tokens, owner Telegram IDs, database URLs, Redis URLs, encryption keys, or proxy passwords.
- Do not dump production logs into public channels.

## Current Observability Limits

- Production Alembic head is normally enforced by startup migrations, but the public health endpoint does not expose revision details.
- Railway deployment status is still inspected through Railway UI unless a future safe status integration is added.
- Notification group delivery remains pending until Fortuna OS groups/channels are created and registered.
