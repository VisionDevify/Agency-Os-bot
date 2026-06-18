# Production Smoke Test

Run this checklist only after the Railway project, services, and environment variables exist. Do not print secret values while testing.

## Preconditions

- Railway project: `Fortuna OS Bot`.
- Services: API, Bot Worker, PostgreSQL, Redis.
- Required variables are present in Railway variable UI.
- `alembic upgrade head` has completed successfully.
- `@FortunaSolstice_Bot` is attached to approved Fortuna OS Telegram destinations only.

## Checklist

1. Open the API `/health` endpoint.
   - Expected: safe JSON with API, DB, and Redis status labels.
2. Open Telegram and send `/start` to `@FortunaSolstice_Bot`.
   - Expected: owner setup remains intact and the main menu opens.
3. Open Executive Command Center.
   - Expected: agency health, production status, heartbeat, and latest event data render.
4. Open Reports -> Daily Briefing -> Generate Today's Briefing.
   - Expected: briefing is created, audited, and event-logged.
5. Open Settings -> Notification Targets.
   - Expected: targets render with masked chat IDs only.
6. Send one test notification to the Testing Sandbox target only.
   - Expected: `notification_delivery_attempts` records pending then sent or failed.
7. Open Settings -> Bot Status.
   - Expected: environment, API, bot, DB, Redis, last heartbeat, last delivery attempt, and failed notification count render.
8. Open Settings -> Audit Logs.
   - Expected: report, delivery, and status events appear without secrets.
9. Confirm EventLog records exist for generated reports and notification delivery outcomes.
10. Restart services or redeploy if safe.
   - Expected: database-backed records persist.

## Failure Handling

- Do not reset or delete production databases.
- If `/health` reports DB or Redis unhealthy, inspect Railway service attachments and variables without printing values.
- If the bot reports token errors, verify `TELEGRAM_BOT_TOKEN` is present in the Bot Worker service only through Railway's masked variable UI.
- If notification send fails, inspect Notification Target status and purpose. Raw chat IDs should remain masked in Telegram and encrypted at rest.
