# Rollback Planning

Rollback V1 is a planning layer, not a promise that every action can be undone.

## Supported Rollback Concepts

The rollback planner can describe:

- proxy session rollback.
- task assignment or escalation restoration when previous state is recorded.
- incident assignment or escalation restoration when previous state is recorded.
- recommendation status restoration when previous state is recorded.

## Limitations

Some actions cannot be fully undone:

- Sent notifications cannot be unsent.
- Generated reports and digests remain as audit history.
- Event logs and audit logs are append-only.
- External platform actions are out of scope because Sprint 14 does not perform them.

## Operator View

Rule Detail exposes:

- rollback available yes/no.
- rollback steps.
- rollback limitations.

Automation Run Detail exposes:

- rollback available.
- rollback status.
- step output needed for future rollback execution.

Future sprints can add explicit rollback execution for actions where previous state is captured strongly enough.
