# Fortuna OS Disaster Recovery Runbook

Fortuna should never pretend recovery is complete without evidence. Use Recovery Center as the source of truth for the latest backup, checksum, encryption, storage target, restore test, and recovery risk score.

## What You Need

- Code repo access.
- Railway project access or a replacement host.
- Postgres and Redis services.
- Required environment secrets stored outside Telegram.
- Latest encrypted backup with checksum.

## Recovery Steps

1. Create a new Railway project or equivalent host.
2. Provision PostgreSQL and Redis.
3. Deploy the Fortuna repo.
4. Set required environment variables.
5. Restore the latest encrypted backup into PostgreSQL.
6. Run `alembic upgrade head`.
7. Verify `/health`.
8. Verify `/integrity`.
9. Verify `/botstatus`.
10. Verify Telegram `/start` responds once.

## Evidence Rules

- If no successful backup exists, status is `Not set up yet`.
- If no restore test exists, status is `Not tested yet`.
- A checksum/decryption verification is useful, but it is not a full restore test unless a test database restore was completed.
- Recovery risk is calculated from backup age, recent failures, storage redundancy, encryption, checksum records, and restore-test evidence.

## Safety Limits

- Do not paste database URLs, Telegram tokens, proxy passwords, or encryption keys into Telegram.
- Do not restore over a real database without a fresh backup and owner approval.
- Do not call local runtime backup storage production-safe external redundancy.

## Current Known Gaps

External backup storage and full test database restore may still be `Not set up yet` until the owner configures a real external target and restore-test database.
