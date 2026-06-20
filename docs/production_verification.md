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

Use the canonical public production health URL:

```bash
curl https://agency-os-bot-production.up.railway.app/health
```

Expected safe response:

```json
{"status":"ok","api":"healthy","db":"healthy","db_backend":"postgresql","redis":"healthy"}
```

If the response shows `db_backend=sqlite_fallback`, production is running in emergency storage mode and data may not survive redeploys or restarts.

Telegram verification should use only the Fortuna OS bot and approved Fortuna OS spaces.

## Railway CLI Verification

Use the official Railway CLI when authentication is available. The local helper is CI-safe and non-mutating:

```bash
python scripts/verify_railway.py --health-url https://agency-os-bot-production.up.railway.app/health --json
```

If the CLI is installed outside `PATH`, pass it explicitly:

```powershell
$env:RAILWAY_CLI_COMMAND="$env:USERPROFILE\.railway\bin\railway.exe"
python scripts\verify_railway.py --health-url https://agency-os-bot-production.up.railway.app/health --json
```

The script never prints Railway variables, tokens, database URLs, or Redis URLs. It reports each check as `pass`, `fail`, or `unavailable` for:

- Railway CLI installed
- Railway authentication
- linked project
- API service
- worker service
- PostgreSQL service
- Redis service
- public `/health`

If authentication or project access is missing, direct service checks are `unavailable` with a blocking reason. Public `/health` can still verify the safe runtime state exposed by the API.

## Build Metadata

`/health` and Production Observability expose only safe build proof:

- `GIT_COMMIT`, or Railway's `RAILWAY_GIT_COMMIT_SHA` fallback when available
- `APP_VERSION`
- `DEPLOYED_AT`

Missing values show `unknown`. Never place secrets, URLs, tokens, or dumped environment text in these fields.

## Recovery Activation Checks

Recovery cannot become healthy without external backup evidence. Before running the first real backup, configure these Railway variables:

- `BACKUP_S3_ENDPOINT`
- `BACKUP_S3_BUCKET`
- `BACKUP_S3_REGION`
- `BACKUP_S3_ACCESS_KEY`
- `BACKUP_S3_SECRET_KEY`

Backblaze B2 should use its S3-compatible endpoint through the S3-compatible setup flow. Credential values must stay in Railway or a future secure owner-only secret flow, not normal Telegram chat.

Recovery verification statuses:

- `critical`: no configured storage or no trusted backup evidence
- `needs_attention`: storage configured but backups are missing, stale, or verification failed
- `needs_review`: backup verified, but restore validation is missing or partial
- `healthy`: storage configured, backup verified, restore verified, provider available, and no active recovery concerns

Severity handling:

- Critical findings halt Recovery activation and require owner review.
- Blocking findings stop the affected verification track and require a missing prerequisite, such as Railway auth or storage credentials.
- Warnings are documented follow-ups, such as missing optional build metadata or Telegram automation limits.

## No-Secret Rules

- Do not print Railway env var values.
- Do not screenshot secret values.
- Do not print bot tokens, owner Telegram IDs, database URLs, Redis URLs, encryption keys, or proxy passwords.
- Do not dump production logs into public channels.

## Current Observability Limits

- Public `/health` remains intentionally safe and non-secret. It now includes safe build proof fields (`git_commit`, `build_version`, `deployed_at`) plus `alembic_revision`, backend durability, and Redis status. Use the owner-only Production Observability screen for deeper bot heartbeat, latest audit/event, latest automation run, latest intelligence run, and notification target readiness.
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
