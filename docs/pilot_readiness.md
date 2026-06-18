# Pilot Readiness

Sprint 28 prepares two production pilots without forcing unsafe activation.

## Notification Group Pilot

Path:

`Settings -> Notification Group Pilot`

Required spaces:

- Fortuna OS - HQ
- Fortuna OS - Operations
- Fortuna OS - Incidents
- Fortuna OS - Automation Logs
- Fortuna OS - Testing Sandbox

The pilot screen shows which purposes are configured, the last delivery status, and the manual checklist.

Safe behavior:

- Testing Sandbox can receive one safe routing test.
- HQ, Operations, Incidents, and Automation Logs are simulated/skipped unless the owner explicitly expands delivery.
- Raw chat IDs remain encrypted at rest and masked in Telegram.

## Proxy Real Check Pilot

Path:

`Proxy Vault -> Real Check Pilot`

The pilot screen shows:

- saved proxies
- per-proxy real health/location flag state
- latest check status
- target location
- clear reminder that passwords are encrypted and hidden

Default behavior:

- global real checks remain disabled
- per-proxy real checks remain disabled until owner-enabled
- tests use mocked external network calls

## UI Self-Test

Path:

`Settings -> UI Self-Test`

Command:

`/selftest`

The self-test renders important screens internally and checks for:

- empty output
- missing buttons
- raw JSON or dict-like output
- stack traces
- secret-like strings

This gives the owner a reliable verification path when Telegram Web callbacks are flaky.

## Production Bot Startup

The API service owns Alembic migrations. The bot worker should start polling after acquiring the Redis polling guard and recording heartbeat. It must not block on migrations before polling.
