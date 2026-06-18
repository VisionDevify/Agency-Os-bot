# Production Verification

Sprint 25 production checks focus on safe, non-destructive verification.

## Verified Production Shape

- API service exposes public `/health`.
- `/health` returns safe labels for API, database backend, database durability, and Redis.
- `/health` writes heartbeat records without returning secrets.
- Bot worker owns Telegram polling.
- Local Docker bot worker should remain stopped when production polling is active.
- PostgreSQL and Redis are required for production-ready persistence. Emergency SQLite must be treated as degraded.
- Railway start commands remain service-specific:
  - API: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
  - Bot Worker: `python -m app.bot.runner`
- Owner-only Production Observability is available from Settings -> Production Observability.

## Safe Checks

Use:

```bash
curl https://agency-os-bot-production.up.railway.app/health
```

Expected safe response:

```json
{"status":"ok","api":"healthy","db":"healthy","db_backend":"postgresql","redis":"healthy"}
```

If the response shows `db_backend=sqlite_fallback`, production is running in emergency storage mode and data may not survive redeploys or restarts.

Telegram verification should use only the Fortuna OS bot and approved Fortuna OS spaces.

## No-Secret Rules

- Do not print Railway env var values.
- Do not screenshot secret values.
- Do not print bot tokens, owner Telegram IDs, database URLs, Redis URLs, encryption keys, or proxy passwords.
- Do not dump production logs into public channels.

## Current Observability Limits

- Public `/health` remains intentionally safe and non-secret. Use the owner-only Production Observability screen for backend durability, Alembic revision, bot heartbeat, latest audit/event, latest automation run, latest intelligence run, and notification target readiness.
- Owner-only `/integrity` verifies DB backend, revision, owner/role records, audit/event writes, key tables, Redis, and polling guard status.
- Railway deployment logs are still inspected through Railway UI unless a future safe status integration is added.
- Notification group delivery remains pending until Fortuna OS groups/channels are created and registered.

## Sprint 26 Observability Checklist

Open Settings -> Production Observability and confirm:

- app display name renders
- environment renders
- missing build metadata renders as `Unknown`
- Alembic current and expected revision render
- API, bot, Postgres, Redis, and Railway status render
- storage backend, durability, risk, owner count, audit count, event count, Redis ping, and polling guard render
- bot startup, polling-loop, and last-update heartbeat fields render
- latest audit/event/automation/intelligence rows render or say `None`
- notification target readiness renders without raw chat IDs
- Railway logs note says logs must be viewed in Railway
