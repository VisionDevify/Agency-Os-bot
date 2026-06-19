# Production Persistence Report

Sprint 32 exists because the public health endpoint can look green while the app is using emergency SQLite storage instead of durable PostgreSQL.

## Current Confirmed State

Current canonical public production health URL:

```bash
https://agency-os-bot-production.up.railway.app/health
```

As of the durable cutover, `/health` is expected to report `db_backend=postgresql`, `db_durable=true`, and `redis=healthy`.

## Historical Sprint 32 Finding

- Current production API health was reachable at `https://agency-os-bot-production-60d3.up.railway.app/health`.
- Railway PostgreSQL and Redis could not be provisioned because the workspace hit the free-plan resource provision limit.
- The emergency production `DATABASE_URL` was set to a SQLite URL using the `sqlite+pysqlite` driver.
- Redis was not configured at the time of this audit, so duplicate polling protection is not durable.
- Sprint 33 adds a bot kill-switch: production polling is blocked when Redis is missing unless `ALLOW_POLLING_WITHOUT_REDIS=true` is explicitly set.

## Backend

- Current backend must be verified with `/health`, `/integrity`, and Production Observability.
- Production-ready backend: PostgreSQL.
- Production-ready Redis status: healthy.
- Historical Sprint 32 backend: SQLite emergency fallback until PostgreSQL was provisioned.
- Historical Sprint 32 safe driver/scheme: `sqlite+pysqlite`.
- Historical Sprint 32 SQLite location: Railway/container temporary filesystem, intended as `/tmp/fortuna_os.db`.

## Risk Level

Current risk depends on live `/health` and `/integrity`.

Historical Sprint 32 risk: High / degraded.

SQLite in Railway is not production-grade durable storage. Data may survive for a running container, but it can be lost on redeploy, restart, container replacement, or filesystem cleanup. Redis missing also means the polling guard cannot safely coordinate multiple bot workers across processes.

## Immediate Fix

1. Provision Railway PostgreSQL and Redis after billing/credit approval, or use external managed PostgreSQL and Redis.
2. Set production `DATABASE_URL` to PostgreSQL.
3. Set production `REDIS_URL` to Redis.
4. Set `ALLOW_SQLITE_FALLBACK=false`.
5. Set `BOT_PRIMARY_INSTANCE=true` only on the one bot worker.
6. Keep `ALLOW_POLLING_WITHOUT_REDIS=false`.
7. Run `alembic upgrade head` against PostgreSQL.
8. Verify `/health` shows `db_backend=postgresql` and `redis=healthy`.
9. Verify `/botstatus` shows one active primary instance and no duplicate pollers.

## Long-Term Fix

- Keep SQLite fallback disabled in production by default.
- Use `/integrity` after every deployment.
- Use `/botstatus` after every bot deployment.
- Keep Production Observability visible to Owner only.
- Export any emergency SQLite data before moving to PostgreSQL.

## Data Integrity Questions

1. Is Fortuna using PostgreSQL or SQLite right now?
   - The backend is now exposed by `/health` as `db_backend`.
2. What is the exact DATABASE_URL driver/scheme?
   - `/health` exposes only the safe driver/scheme as `db_driver`, never credentials.
3. Is Redis connected?
   - `/health` reports `redis=healthy`, `unhealthy`, or `unknown`.
4. Is Redis required for safe bot polling?
   - Yes. Without Redis, the duplicate polling guard is not durable across workers.
5. Are writes durable across Railway restarts?
   - PostgreSQL: yes. SQLite emergency fallback: no/unknown.
6. Where is SQLite stored if fallback is active?
   - Railway/container temporary filesystem, currently intended as `/tmp/fortuna_os.db`.
7. Would data be lost on redeploy/restart?
   - With SQLite emergency fallback, yes, that is a real risk.
8. Are migrations running against Postgres or SQLite?
   - `/integrity` and Production Observability show the backend and Alembic revision.
9. Does production have expected Alembic revision?
   - `/integrity` checks current versus expected head.
10. Does production contain expected records?
   - `/integrity` checks owner, roles, audit/event write paths, learning, automation, and proxy tables.
