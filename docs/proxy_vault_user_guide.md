# Proxy Vault User Guide

Proxy Vault stores operational proxy records for account routing and infrastructure health.

## What The Owner Sees

Telegram surfaces must show:

- provider
- host
- port
- masked generated username
- current session suffix
- target location
- detected location
- health score
- assigned accounts
- recent rotations

Telegram surfaces must not show:

- proxy password
- encrypted password blob
- raw provider credentials
- raw JSON
- Python dicts
- stack traces

## Olympix Mobile SOCKS5 Wizard

Use Proxies -> Olympix Mobile SOCKS5 Wizard.

Expected values:

- Host: `host.olympix.io`
- Port: `1080`
- Base username
- Password
- Target country
- Target state
- Target city optional

The password is accepted only through the bot flow, encrypted before storage, and never shown back in Telegram.

## Assignment Flow

Accounts can be assigned to a proxy from:

- Proxy detail -> Assign Account
- Account detail -> Assign Proxy
- Account setup checklist when an account is missing a proxy

When an account is missing a proxy, Fortuna OS should create a readiness blocker and recommend a setup action.

## Health, Simulation, And Real Checks

Proxy health is deterministic and based on stored counters:

- connection failures
- latency
- location mismatches
- rotation success/failure counts

Simulation remains the default behavior. Simulation views must clearly say they are simulations when no real provider test is running.

Sprint 26 requires every proxy health/location surface to label the verification reality:

- whether a real provider check is enabled
- whether the current check is simulated
- the last verified timestamp when available

Sprint 27 adds the first real provider adapter framework for Olympix Mobile SOCKS5. Real checks are disabled by default and must be owner-enabled per proxy. The adapter can:

- build the SOCKS5 connection from encrypted stored fields
- test outbound connectivity
- measure latency
- detect a masked outgoing IP
- optionally request coarse country/state/city location from the configured provider
- compare detected location to the target location

If the location provider is unavailable or low confidence, Fortuna OS labels the result as location unknown instead of pretending certainty.

## Proxy Health Check Results

`proxy_health_check_results` stores each check:

- check type: `simulated`, `connectivity`, `location`, or `full`
- status: `passed`, `failed`, `warning`, or `skipped`
- latency
- masked detected IP
- detected country/state/city
- target match
- safe error message
- created timestamp

Proxy Detail shows recent check history. Passwords, raw usernames, encrypted blobs, and full IP data are not shown.

## Owner-Controlled Flags

Environment defaults:

- `PROXY_REAL_HEALTH_CHECKS_ENABLED=false`
- `PROXY_REAL_LOCATION_CHECKS_ENABLED=false`
- `PROXY_HEALTH_TIMEOUT_SECONDS=10`
- `PROXY_LOCATION_PROVIDER=ipwhois`

The owner can enable/disable real checks for a proxy from Proxy Detail. Non-owner users cannot enable real checks. Running a real check while disabled stores a safe skipped result and does not touch the network.

## Safety

- Never log proxy passwords.
- Never show encrypted password blobs.
- Never include password/session secrets in audit metadata or EventLog metadata.
- Do not hardcode provider credentials.
- Do not use proxy logic for platform security evasion.
- Do not present simulated or low-confidence location data as certain.
