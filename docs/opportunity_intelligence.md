# Opportunity Intelligence Foundation

Sprint 12 creates the database and Telegram foundation for future funnel intelligence.

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
- title
- optional URL
- optional niche
- optional Model/Brand
- deterministic score
- status: `discovered`, `reviewing`, `approved`, `assigned`, `completed`, `rejected`, `archived`
- reason
- suggested angle
- optional assigned user

### OpportunityResult

- opportunity
- optional user who manually posted or recorded the outcome
- status: `not_posted`, `posted`, `skipped`, `failed`
- optional clicks and conversions
- safe notes

## Telegram Flows

- Opportunities -> View Opportunities.
- Opportunities -> Add Opportunity Manually.
- Opportunity Detail -> Score Opportunity.
- Opportunity Detail -> Assign to Me.
- Opportunity Detail -> Mark Posted.
- Opportunities -> Opportunity Results.

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

## Future Direction

Future AI target discovery, comment strategy suggestions, and conversion attribution can attach to these records. Any real integration should prefer official APIs/OAuth where available and keep human approval before public actions.
