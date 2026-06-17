# Opportunity Intelligence Foundation

Sprint 12 created the database and Telegram foundation for future funnel intelligence. Sprint 17 turned it into an everyday Opportunity Command Center for chatters and managers. Sprint 18 adds guided intake and assignment workflows.

It does not scrape X, Instagram, Reddit, OnlyFans, or any other platform. It does not automate posting, commenting, messaging, liking, following, or bypassing platform controls. Everything is manual and human-approved.

## Records

### OpportunitySource

- platform: `x`, `instagram`, `reddit`, or `other`
- name
- optional URL
- optional niche
- active flag

### Opportunity

- optional source
- platform
- source type and source reference ID
- title
- optional URL
- optional niche
- optional Model/Brand
- deterministic score
- priority
- status: `discovered`, `reviewing`, `approved`, `assigned`, `completed`, `rejected`, `archived`
- reason
- suggested angle
- optional assigned user
- optional due, assigned, and completed timestamps

### OpportunityResult

- opportunity
- optional user who manually posted or recorded the outcome
- status: `not_posted`, `posted`, `skipped`, `failed`, `rejected`
- optional clicks and conversions
- safe reason
- safe notes

### CreatorWatch

- platform: `x`, `instagram`, or `other`
- creator name, display name, and username
- optional profile URL
- niche
- priority
- optional assigned model, team placeholder, and chatter
- status and active flag

### PostWatch

- model/brand
- platform
- optional account
- post reference
- post type
- status: `recent`, `attention_needed`, `assigned`, or `archived`
- attention level
- optional assigned chatter/team placeholder
- safe notes

### CommentStrategy

- optional opportunity
- angle
- tone
- sample comment draft
- curiosity score
- engagement score
- risk score
- safe reasoning
- why it might work
- suggested use case

## Telegram Flows

- Opportunities -> Command Center.
- Opportunities -> Creator Watchlist.
- Opportunities -> Own Post Watch.
- Opportunities -> View Opportunities.
- Opportunities -> Add Opportunity guided flow.
- Creator Watchlist -> Add Creator guided flow.
- Own Post Watch -> Add Own Post guided flow.
- Opportunity Detail -> Assign Chatter.
- Opportunity Detail -> Change Status.
- Opportunity Detail -> Suggested Strategies.
- Opportunity Detail -> Regenerate Strategies.
- Opportunity Detail -> Record Result.
- Opportunity Detail -> Create Task.
- Opportunities -> Opportunity Results.
- Chatter Home -> Chatter Workspace.
- Manager Home -> Manager Opportunity View.

## Scoring

Scoring is deterministic and simple:

- Model/Brand attached increases score.
- Niche present increases score.
- URL present increases score.
- Reason present increases score.
- Suggested angle present increases score.
- Historical outcome memory can nudge score up or down when enough similar safe internal results exist.

## Opportunity Learning

Sprint 15 records manual opportunity results into outcome memory.

The system can learn by:

- platform.
- niche.
- source.
- suggested angle.
- Model/Brand.
- assigned user.

Opportunity learning can identify stronger niches, stronger angles, weak sources, and poor-result patterns. It still does not scrape, post, comment, message, like, follow, or automate public platform behavior.

Sprint 17 also tracks:

- best angles.
- best niches.
- best sources.
- weak sources.
- most successful teams or chatters.
- creator watch and post watch operating context.

## Future Direction

Future AI target discovery, comment strategy suggestions, and conversion attribution can attach to these records. Any real integration should prefer official APIs/OAuth where available and keep human approval before public actions.
