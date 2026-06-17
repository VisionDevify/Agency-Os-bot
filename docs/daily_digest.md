# Daily Digest

Daily Digest is the operator-facing delivery flow built on top of Daily Company Briefing.

## Purpose

The digest gives managers and the owner a compact daily view of:

- Agency Health Score.
- Critical incidents.
- Overdue tasks.
- Accounts needing attention.
- Proxies needing attention.
- Top recommendations.
- Team accountability highlights.
- Production status.

## Telegram Flow

Reports -> Daily Digest supports:

- Generate Digest.
- Preview Digest.
- Send to HQ.
- Send to Operations.
- Schedule Digest placeholder.
- Delivery History.

## Delivery Semantics

`digest.sent` means Agency OS created durable delivery-attempt records for active targets matching the requested purpose. It does not mean Telegram accepted the message. Actual Telegram delivery is represented by:

- `notification.delivery_succeeded`
- `notification.delivery_failed`
- `notification.delivery_skipped`

## Safety

- Digest delivery requires `manage_reports`.
- Raw chat IDs stay encrypted and masked.
- Delivery metadata must not contain tokens, credentials, platform passwords, proxy passwords, verification codes, or raw chat IDs.
- Sending to real groups should happen only after targets are registered and reviewed.

## Events And Audits

Digest flow records:

- `digest.generated`
- `digest.previewed`
- `digest.send_requested`
- `digest.sent`
- `digest.failed`

Every delivery attempt records:

- `notification.delivery_attempted`
- final success/failure event when known

Repeated delivery failures generate a warning recommendation for the affected notification target.
