# Fortuna Mobile Live QA

Use Telegram mobile as the source of truth for owner QA.

## Test Path

1. Send `/start`.
2. Tap `Setup`.
3. Open `First Workspace Guide`.
4. Tap `Complete Model`.
5. Try `Add Account`.
6. Open `Proxy Vault`.
7. Tap `Add Proxy`.
8. Open `Paste Full Proxy String`.
9. Cancel safely if you are not ready to paste real credentials.
10. Open `View Proxies`.
11. Try `Assign Proxy`.
12. Open `Opportunities`.
13. Open `Help`.
14. Send `/integrity`.
15. Send `/botstatus`.
16. Send `/callback_failures`.

## What To Report

For every issue, send:

- Screen name.
- Button pressed.
- What happened.
- What you expected.
- Screenshot or screen recording if possible.

## In-Bot Reporting

Use `Settings -> Report a Problem`.

Send one message in this format:

`Screen | what happened | severity | notes`

Severity can be `low`, `medium`, `high`, or `critical`.

## Live Data Safety

Before pasting a real proxy string, confirm the paste screen shows:

- PostgreSQL durable.
- Redis healthy.
- Encryption enabled.
- Single bot instance.
- Polling safety.
- No SQLite fallback.

If Fortuna blocks proxy credential entry, run `/integrity` and `/botstatus` first.

