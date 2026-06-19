# Production Reconciliation Report

Sprint 41 added a trust repair pass so Fortuna does not show old infrastructure warnings as current truth.

## Green: Current Truth Source

- `SystemTruth` now centralizes production health for PostgreSQL durability, Redis health, bot instance safety, Alembic revision state, visible placeholder proxies, notification targets, setup readiness, owner count, callback errors, and production readiness.
- Production Observability reads current issues from `SystemTruth` instead of rebuilding its own health rules.
- Home, Production Observability, Integrity, and the Daily Cycle trigger stale-warning reconciliation.

## Yellow: Stale Records Reconciled

The reconciliation service resolves or completes only records that live truth proves are no longer active:

- storage durability warnings when PostgreSQL is durable and Redis is healthy.
- SQLite fallback warnings when the active backend is PostgreSQL.
- production instability warnings when current production truth is ready.
- duplicate polling warnings when one primary bot instance is active and no duplicate is detected.
- placeholder proxy warnings when normal Proxy Vault has zero visible placeholder proxies.

Affected record types:

- `Recommendation`: moved to `resolved`.
- `PriorityItem`: moved to `resolved`.
- `IntelligenceSignal`: moved to `resolved`.
- `IssuePattern`: moved to `resolved`.
- `FollowUp`: moved to `completed` when it is clearly tied to a resolved infrastructure warning.

Friction items are preserved as historical UX records because the current schema does not have a resolved/archive status.

## Red: Preserved Records

Fortuna does not auto-resolve real setup blockers:

- missing models/accounts/team/creators/opportunities.
- missing notification targets.
- account setup gaps.
- active callback failures that are not proven stale by live truth.
- real proxy failures or production warnings that still match current state.

## Why This Matters

Current status screens must answer what is true now. Intelligence and audit history may remember past issues, but those records should not make healthy production look degraded.

## Verification

Regression coverage checks:

- `SystemTruth` reports PostgreSQL/Redis healthy.
- Production Observability does not show “Storage is not production-ready” when PostgreSQL and Redis are healthy.
- stale storage, SQLite, duplicate polling, production instability, and placeholder proxy warnings resolve automatically.
- historical production instability does not appear as an active current health issue.
- simple health screens avoid raw internal warning types.
