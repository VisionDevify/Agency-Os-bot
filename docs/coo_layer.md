# Fortuna COO Layer

Sprint 24 introduces the first COO behavior layer for Fortuna OS.

The goal is not more CRUD. The goal is operational coordination:

- Inspect current state.
- Rank what matters.
- Decide who should own it.
- Show the next action clearly.
- Reduce owner noise by routing non-owner work to managers/admins.

## Priority Engine

`priority_items` stores ranked work signals from:

- readiness blockers
- missing proxies
- missing managers/team
- critical incidents
- overdue tasks
- unassigned opportunities
- repeated notification delivery failures
- failed automation runs

Each item has:

- severity
- urgency
- confidence
- business impact
- score
- explanation
- recommended owner
- status

The score is deterministic and bounded 0-100.

## Today Top 5

Today Top 5 is the operator-facing action list. It turns ranked priorities into five concrete next actions with:

- title
- owner
- score
- explanation
- fix path when available

## Routing

Fortuna routes attention by category:

- Critical incident -> Owner
- Failed automation -> Owner
- Missing proxy -> Admin
- Missing manager/team -> Manager
- Unassigned opportunity -> Manager
- Overdue task -> Manager

Routing is advisory in Sprint 24. Fortuna does not automatically reassign work.

## Work Queues

Manager Queue shows:

- Needs Assignment
- Needs Approval
- Needs Attention
- Needs Escalation
- Due Today
- Overdue

My Work shows:

- Due Today
- Priority
- Due Soon
- Waiting On Me
- Opportunities
- Tasks

## Readiness Score V2

Readiness V2 explains:

- why readiness is low
- biggest blockers
- fastest score gains
- estimated score improvement per action

Examples:

- Add timezone: +5
- Assign manager: +10
- Assign proxy: +12

## COO Briefing

The COO Briefing answers:

- What changed?
- What needs attention?
- What is blocked?
- What should happen next?
- Who is overloaded?
- Who is idle?
- What should be delegated?

## Safety Boundaries

The COO layer does not:

- post, comment, like, follow, or scrape
- bypass platform security
- store social passwords
- expose secrets
- auto-approve high-risk actions
- auto-reassign humans without approval

All metadata must remain safe and sanitized.
