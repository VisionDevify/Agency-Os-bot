# Recommendations Engine

Sprint 9 adds deterministic recommendations. This is not AI yet; it is a rules-based engine driven by current database state.

## Current Recommendation Sources

- Accounts Missing Proxy.
- Critical Incidents Open.
- Overdue Tasks.
- Proxies Warning/Critical.
- Accounts Needing Login, 2FA, expired auth, or locked auth.
- Models Without Assigned Manager.
- Models Without Chatter Team.
- Proxy Location Mismatch.
- Failed Repair Attempts.

## Statuses

- `open`: visible in Executive Command Center.
- `acknowledged`: operator has seen it.
- `dismissed`: operator decided it is not actionable.
- `resolved`: underlying issue has been addressed.

## Telegram UI

Executive Dashboard -> Recommendations supports:

- View Recommendations.
- Acknowledge.
- Dismiss.
- Mark Resolved.
- Jump to Related Entity when an entity link exists.

## Safety Rules

- Metadata is safe only.
- Do not include credentials, tokens, raw chat IDs, proxy passwords, verification codes, code hashes, or platform session data.
- Recommendation generation is deterministic and idempotent for open recommendation families where practical.
- AI-generated recommendations should be introduced later with confidence, provenance, and owner approval boundaries.

## Future Work

- Add recommendation deduplication windows.
- Add event-driven generation from EventLog.
- Add notification routing for critical recommendations.
- Add AI Operations Brain summaries on top of deterministic recommendations.
