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
- External storage is considered configured only after Fortuna tests provider connectivity, authentication, upload, download, verification, and safe cleanup.
- Backup success requires an encrypted artifact, a remote upload, and checksum verification. Missing storage, unsupported runtime backup, or upload failure must be reported as `not_configured`, `manual_required`, or `failed`.

## External Backup Storage

Recovery Center supports S3-compatible storage now. Add these values as secure hosting variables, then use **Recovery Center -> Backup Storage -> S3-Compatible -> Activate / Test From Railway Env**:

- `BACKUP_S3_ENDPOINT`
- `BACKUP_S3_BUCKET`
- `BACKUP_S3_REGION`
- `BACKUP_S3_ACCESS_KEY`
- `BACKUP_S3_SECRET_KEY`

Backblaze B2 should be connected through its S3-compatible endpoint using the S3-compatible setup path. Direct B2, Google Drive, Cloudflare R2, and Azure Blob are prepared as future extension points and must not be shown as protected until implemented and tested.

Credential values must stay in the hosting provider or another secure owner-only secret flow. Do not paste storage credentials into normal Telegram chat.

## Safety Limits

- Do not paste database URLs, Telegram tokens, proxy passwords, or encryption keys into Telegram.
- Do not restore over a real database without a fresh backup and owner approval.
- Do not call local runtime backup storage production-safe external redundancy.

## Current Known Gaps

External backup storage and full test database restore may still be `Not set up yet` until the owner configures a real external target and restore-test database.
