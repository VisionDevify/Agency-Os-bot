# Creator Watch

Creator Watch is a human-review queue for creators that may matter to a model/brand, team, or chatter.

It does not scrape profiles, post comments, follow accounts, bypass platform rules, or automate public platform actions.

## Data

`creator_watches` stores:

- platform: `x`, `instagram`, or `other`.
- creator name and username.
- optional profile URL.
- niche.
- priority: `low`, `normal`, `high`, or `critical`.
- optional assigned model/brand.
- optional assigned team ID placeholder.
- optional assigned chatter.
- notes.
- active flag.

## Telegram Flow

Opportunities -> Creator Watchlist supports:

- View Watchlist.
- Add Creator placeholder.
- Assign Chatter.
- Disable Creator.
- Archive Creator.

Edit and team assignment are intentionally lightweight in Sprint 17. Rich forms can be added later.

## Safety

- Only users with opportunity management permissions can create or modify watch records.
- Chatters can view opportunity workspace pages through their role-specific home.
- Every create, assignment, disable, and archive action is audited and emits a safe event.
- No external platform data is collected automatically.
