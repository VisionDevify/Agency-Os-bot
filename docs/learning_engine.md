# Learning Engine

Sprint 15 adds the memory layer for Agency OS.

The learning engine records meaningful outcomes from internal Agency OS workflows and turns them into safe operational memory. It is deterministic and does not scrape, post, comment, like, follow, request platform credentials, bypass security, or modify code.

## Core Records

- `learning_events`: immutable outcome records from tasks, incidents, proxies, automations, recommendations, opportunities, notifications, and system health.
- `outcome_memory`: aggregated counters and success rates by deterministic memory key.
- `playbooks`: reusable fix/process memory.
- `playbook_runs`: history of playbook suggestions and use.
- `confidence_records`: append-only explanation of confidence changes.

## Captured Outcomes

- `task.completed`: success.
- `task.blocked`: partial.
- `task.overdue_detected`: warning/failure signal.
- `incident.resolved`: success.
- `incident.escalated`: partial/warning.
- `proxy.repair.succeeded`, `proxy.rotation.succeeded`: success.
- `proxy.repair.failed`, `proxy.rotation.failed`, `proxy.location.mismatch`: failure or warning.
- `automation.run.succeeded`, `automation.run.failed`, `automation.run.skipped`: automation outcome memory.
- `recommendation.resolved`, `recommendation.dismissed`, `recommendation.acknowledged`: recommendation outcome memory.
- `opportunity.result_recorded`: manual result memory.
- `notification.delivery_succeeded`, `notification.delivery_failed`: notification memory.

## Telegram Surfaces

- Intelligence -> Learning Center.
- Intelligence -> Learning Center -> Playbooks.
- Intelligence -> Learning Center -> Outcome Memory.
- Intelligence -> Learning Center -> Confidence Changes.
- Intelligence -> Learning Center -> Automation Learning.
- Intelligence -> Learning Center -> Opportunity Learning.
- Intelligence -> Learning Center -> Executive Memory Briefing.

## Safety Rules

- Metadata must be safe and redacted.
- No tokens, credentials, platform passwords, proxy passwords, 2FA codes, raw chat IDs, or session data.
- High-risk playbooks are not auto-run.
- Learning may recommend action, but operators still approve execution through existing permission and automation gates.
- The system does not self-modify code.
