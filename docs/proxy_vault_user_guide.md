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

## Health And Simulation

Current proxy health is deterministic and based on stored counters:

- connection failures
- latency
- location mismatches
- rotation success/failure counts

Provider-level network checks and location verification are still adapter placeholders unless explicitly integrated later. Simulation views must clearly say they are simulations when no real provider test is running.

Sprint 26 requires every proxy health/location surface to label the verification reality:

- whether a real provider check is enabled
- whether the current check is simulated
- the last verified timestamp when available

Current production behavior is simulated provider check. This avoids fake certainty until a real Olympix/provider adapter exists.

## Safety

- Never log proxy passwords.
- Never show encrypted password blobs.
- Never include password/session secrets in audit metadata or EventLog metadata.
- Do not hardcode provider credentials.
- Do not use proxy logic for platform security evasion.
