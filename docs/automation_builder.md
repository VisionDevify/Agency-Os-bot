# Automation Builder

Sprint 14 turns Automations from simulation-only placeholders into a no-code operations builder.

## Lifecycle

Every automation follows this path:

1. Draft
2. Simulate
3. Review Impact
4. Approve
5. Activate
6. Run
7. Verify
8. Report
9. Rollback if available

No automation should become active without a valid simulation. Any mutation action requires approval. High-risk, critical-risk, and proxy repair automations require Owner approval.

## Rule Shape

Automation rules are persisted in `automation_rules` and include:

- name and description.
- category.
- trigger type and safe trigger config.
- deterministic conditions.
- action list.
- rollback plan.
- risk level.
- owner approval requirement.
- creator and approver references.
- simulation and run timestamps.

Automation configs must never contain tokens, passwords, credentials, verification codes, raw Telegram chat IDs, proxy passwords, or platform session data.

## Trigger Registry V1

Supported trigger families:

- Manual Trigger: Owner/Admin taps Run Now.
- Scheduled Trigger: daily briefing, intelligence scan, recommendation refresh.
- Event Trigger: `proxy.health.changed`, `incident.created`, `task.overdue_detected`, `recommendation.generated`, `notification.delivery_failed`.
- Condition Trigger: proxy health below threshold, overdue task count above threshold, critical incidents open, accounts needing attention.

Social platform triggers are intentionally out of scope. The builder does not scrape, post, comment, like, follow, or bypass platform security.

## Condition Registry V1

Supported checks:

- entity status equals.
- severity equals.
- health score below threshold.
- overdue count above threshold.
- availability status equals.
- notification failures above threshold.
- time window allowed.
- user has role.
- model/account/proxy exists.
- recommendation severity equals.

All conditions are deterministic, logged safely, and testable.

## Action Registry V1

Allowed actions are internal Agency OS actions:

- Infrastructure: simulate proxy repair, rotate proxy session, test proxy health, create proxy incident, escalate proxy incident.
- Operations: create task, assign/escalate task, create incident, assign/escalate incident.
- Reports: generate daily digest, executive intelligence briefing, accountability snapshot hooks.
- Intelligence: run intelligence scan, generate recommendations, create intelligence signal hooks.
- Notifications: record/send safe notification attempts to purpose targets.
- System: create recommendation, write event log.

No action posts, comments, likes, follows, scrapes, requests platform credentials, or stores platform passwords.

## Built-In Templates

Sprint 14 seeds:

- Daily Intelligence Scan.
- Daily Executive Digest.
- Overdue Task Escalation.
- Critical Incident Escalation.
- Proxy Repair Assistant.
- Notification Failure Watch.

Templates are regular rules after seeding. Operators can simulate, review, approve, activate, pause, and retire them.

## Automation Learning

Sprint 15 connects automation run outcomes to the learning engine.

- Successful runs create success learning events and can raise confidence.
- Failed runs create failure learning events, outcome memory, and review recommendations.
- Skipped runs are tracked as partial outcomes.
- Repeated failure should suggest pausing or reviewing the rule.
- Successful repeated operation can support future recommendations to activate safe manual rules.

Automation learning does not bypass simulation, approval, owner gates, or rollback limitations.
