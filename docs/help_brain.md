# Fortuna Help Brain

Fortuna Help Brain upgrades the earlier Help Copilot into a context-aware support layer for team members.

It answers from:

- user role and permissions
- current screen context when provided
- live readiness blockers
- assigned tasks, opportunities, and incidents
- notification/proxy setup state
- seeded help knowledge base articles

## User Paths

- Help Center -> Ask Fortuna
- key screens -> Ask Fortuna or Explain This Screen
- feedback buttons: Helpful, Not Helpful, Still Confused

## Safety

Help Brain must not expose:

- tokens
- raw environment variables
- proxy passwords
- encrypted credential blobs
- 2FA codes
- restricted admin details to non-admin users

When a user lacks permission, the answer should explain what they can do instead and who should help them.

## Persistence

`help_knowledge_base` stores seeded help articles.

`help_question_logs` stores the question, detected intent, answer summary, feedback, and timestamp.

Feedback creates a safe `LearningEvent` so Fortuna can learn which explanations reduce confusion.

## Seeded Topics

- Owner start guide
- Manager start guide
- Chatter start guide
- VA start guide
- Model setup
- Account setup
- Proxy setup
- Notification group setup
- Opportunity workflow
- Tasks
- Incidents
- Readiness score
- Daily Autopilot
- Fortuna HQ
- What Fortuna Did

## Current Limits

The Help Brain is deterministic. It does not call an external AI provider yet, and it does not execute actions directly from a help answer.
