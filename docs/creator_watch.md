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
- demo flag for owner-created training records.

## Telegram Flow

Opportunities -> Creator Watchlist supports:

- View Watchlist.
- Guided Add Creator flow:
  - choose platform;
  - enter username;
  - enter display name;
  - enter niche;
  - choose priority;
  - optionally assign model/brand;
  - optionally assign chatter/team member;
  - add optional notes;
  - create the watch record.
- Creator detail with platform, username, display name, niche, priority, model, chatter/team, status, timestamps, and notes.
- Edit Priority.
- Edit Niche.
- Assign Model.
- Assign Chatter.
- Disable.
- Archive.
- Create Opportunity From Creator.
- Explain This Screen through Help Copilot.

Team assignment is now active enough for managers to move creators into the daily chatter workflow.

## Safety

- Only users with opportunity management permissions can create or modify watch records.
- Chatters can view opportunity workspace pages through their role-specific home.
- Every create, update, assignment, disable, archive, and opportunity-conversion action is audited and emits a safe event.
- No external platform data is collected automatically.
- Demo creator records are marked and can be cleared through owner-only Demo Seed Mode.
