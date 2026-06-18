# PostgreSQL Recovery Plan

Fortuna OS should run production data on PostgreSQL and Redis. SQLite is only a local development or explicit emergency fallback.

## Option A: Railway PostgreSQL and Redis

Use this when the Railway workspace has available credits/resources.

1. In Railway, open the Fortuna OS project.
2. Add a PostgreSQL service.
3. Add a Redis service.
4. Attach `DATABASE_URL` from PostgreSQL to the app service.
5. Attach `REDIS_URL` from Redis to the app service.
6. Set `ALLOW_SQLITE_FALLBACK=false`.
7. Run `alembic upgrade head`.
8. Verify `/health` returns `db_backend=postgresql` and `redis=healthy`.

Approval boundary: do not upgrade billing, add credits, or provision paid services without owner approval.

## Option B: External Managed PostgreSQL and Redis

Use this when Railway cannot provision more resources on the current plan.

1. Create a managed PostgreSQL database with a reputable provider.
2. Create a managed Redis instance.
3. Copy the provider URLs directly into Railway variables.
4. Do not paste secrets into chat.
5. Set `ALLOW_SQLITE_FALLBACK=false`.
6. Run `alembic upgrade head`.
7. Verify `/integrity`.

## Option C: Move Hosting

Use this if Railway limits continue blocking durable persistence.

1. Choose a host that includes or supports managed PostgreSQL and Redis.
2. Set the same app environment variables.
3. Run migrations.
4. Verify `/health`, `/integrity`, and Telegram `/start`.

## Emergency SQLite Data

If emergency SQLite contains data:

1. Do not delete it.
2. Export a backup with `python scripts/export_sqlite_backup.py`.
3. Review the backup before migrating to PostgreSQL.
4. Do not blindly overwrite PostgreSQL with emergency data.
