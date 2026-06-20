# Recovery Center

Recovery Center is evidence-based. It must never claim Fortuna is protected unless storage, backup, checksum, encryption, provider, and restore evidence support that claim.

## Owner Summary

Recovery is healthy only when:

- External backup storage has passed connection testing.
- A verified backup exists.
- The backup artifact is encrypted.
- The checksum is recorded and verified.
- The provider can read the uploaded artifact.
- Restore validation has passed.
- Recent failures do not require attention.

If any evidence is missing, Recovery Center should say `critical`, `needs_attention`, or `needs_review`, with one next best move.

## Status Model

- `critical`: no configured storage, no trusted backup, restore capability unavailable, or protection cannot be trusted.
- `needs_attention`: storage configured but backups are missing, outdated, failed, or verification failed.
- `needs_review`: backup verified but restore validation is missing, partial, or outdated.
- `healthy`: storage configured, backup verified, restore verified, provider available, and no active recovery concerns.

## Required Railway Variables

Set these in Railway variables. Confirm presence only; never print values.

- `BACKUP_S3_ENDPOINT`
- `BACKUP_S3_BUCKET`
- `BACKUP_S3_REGION`
- `BACKUP_S3_ACCESS_KEY`
- `BACKUP_S3_SECRET_KEY`

Backblaze B2 should use its S3-compatible endpoint through the S3-Compatible setup path for now.

## Activation Flow

1. Open Recovery Center.
2. Open Backup Storage.
3. Open S3-Compatible Storage.
4. Add the `BACKUP_S3_*` variables in Railway.
5. Tap Activate / Test From Railway Env.
6. Confirm connection testing passes.
7. Run Backup.
8. Confirm the backup result says uploaded, verified, encrypted, and checksummed.
9. Run Restore Test.
10. Treat `verified_only` as partial evidence, not a full restore pass.

## Connection Test Evidence

Storage becomes active only after:

- Endpoint is reachable.
- Authentication succeeds.
- Bucket exists.
- Test write succeeds.
- Test read succeeds.
- Test cleanup succeeds when safe.

Failures should create Recovery findings and plain-language owner guidance. Provider errors belong behind Details.

## Backup Evidence

Backup success requires:

- BackupRun record.
- Immutable run identifier.
- Backup artifact.
- Encryption applied.
- Checksum calculated.
- Upload succeeded.
- Remote uploaded object verified.

If any part fails, the outcome is `failed`, `manual_required`, or `not_configured`.

## Restore Evidence

Restore validation outcomes:

- `passed`: actual restore validation passed.
- `verified_only`: artifact is readable/checksummed/decryptable, but no full restore database validation happened.
- `failed`: checksum, download, decryptability, or restore validation failed.
- `not_available`: no backup is available.

`verified_only` improves evidence but does not make Recovery fully healthy by itself.

## Railway Verification

Use the CI-safe verifier:

```bash
python scripts/verify_railway.py --health-url https://agency-os-bot-production.up.railway.app/health --json
```

If Railway CLI is installed outside `PATH`:

```powershell
$env:RAILWAY_CLI_COMMAND="$env:USERPROFILE\.railway\bin\railway.exe"
python scripts\verify_railway.py --health-url https://agency-os-bot-production.up.railway.app/health --json
```

The verifier is read-only and emits `pass`, `fail`, or `unavailable` for CLI, auth, project, services, and public health.

## Build Metadata

Set these safe labels in Railway when possible:

- `GIT_COMMIT`, or use Railway's `RAILWAY_GIT_COMMIT_SHA` fallback.
- `APP_VERSION`
- `DEPLOYED_AT`

Missing metadata shows `unknown`. Never put secrets, URLs, tokens, or raw environment dumps in metadata fields.

## Sprint Halt Rules

- Critical: stop Recovery activation and escalate if backup success contradicts artifact evidence, checksum/decryptability fails, restore validation fails, or uploaded artifact verification fails.
- Blocking: pause the affected track if Railway auth, project access, storage credentials, or required restore infrastructure are missing.
- Warning: continue but document optional metadata gaps, Telegram automation limits, or `verified_only` restore evidence.
