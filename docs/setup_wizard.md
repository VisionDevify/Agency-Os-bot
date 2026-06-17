# Setup Wizard

The Setup Wizard is the first production path for an owner or admin.

Telegram entry points:

- Owner Home -> Setup Agency.
- Settings -> Setup Wizard.
- Models empty state -> Create First Model.

## Flow

1. Create Model/Brand.
2. Add accounts.
3. Assign team.
4. Add creator watch starters.
5. Create starter opportunities.
6. Review setup summary.

## Create Model/Brand

The first model captures:

- display name
- stage name
- country
- timezone
- optional notes

Model detail can later edit:

- display name
- stage name
- country
- timezone
- status
- notes
- internal notes
- team
- accounts
- creator watchlist
- opportunities

## Add Accounts

Accounts attach to a model/brand.

Supported record types:

- Instagram
- X
- OnlyFans
- Email
- Other

The setup flow stores account records and auth state only. It does not collect platform passwords and does not automate platform actions.

## Assign Team

Supported model relationships:

- manager
- chatter manager
- senior chatter
- chatter
- VA
- viewer

Only Owner/Admin users with setup permissions can assign team members.

## Starter Creators And Opportunities

Creator Watch starters help the team know who matters first.

Starter opportunities are manual work items. Strategy suggestions are drafts for human review only. Agency OS does not post, comment, like, follow, scrape, or bypass platform security.

## Demo Seed Mode

Demo Seed Mode is owner-only.

It can create:

- demo model
- demo account
- demo creator
- demo opportunity

Demo records are marked with `is_demo` and can be cleared without touching real production records.
