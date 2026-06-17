# Agency Intelligence Brain V1

Sprint 12 turns Agency OS from a command center into the first version of an operations brain.

This layer is deterministic. It does not call an LLM, scrape external platforms, automate posting, bypass security, or request platform credentials. It reads Agency OS records and writes safe intelligence records that operators can review.

## Core Records

- `intelligence_signals`: observations such as recurring failures, overloaded users, degraded production services, or negative metric movement.
- `issue_patterns`: recurring issue clusters with occurrence counts and suggested action.
- `trend_snapshots`: metric snapshots with trend direction and percent change.
- `workload_snapshots`: per-user workload and overload classification.
- `executive_insights`: concise executive summaries generated from the intelligence layer.
- `intelligence_runs`: no-code run history for pattern detection, trend analysis, workload analysis, recommendations, executive briefing, and opportunity scoring.

## Telegram Surfaces

- Intelligence -> command center status.
- Intelligence -> Run Analysis.
- Intelligence -> Signals.
- Intelligence -> Patterns.
- Intelligence -> Trends.
- Reports -> Workload Intelligence.
- Reports -> Executive Intelligence Briefing.
- Executive Dashboard -> Recommendations -> Why am I seeing this?

## Safety Limits

- No scraping.
- No automatic posting or commenting.
- No real IG/X/OnlyFans integrations.
- No plaintext credentials, codes, tokens, proxy passwords, raw chat IDs, or session data in metadata.
- Critical signal notifications use delivery attempts and safe summaries only.

## Future AI Hooks

The deterministic layer creates clean data for a future AI Operations Brain:

- source signals and confidence scores.
- issue patterns and related event IDs.
- trend snapshots and negative movement.
- workload overload context.
- recommendation reason and suggested next action.

Future AI should explain and prioritize. It should not execute risky actions without explicit operator approval.

## Automation Suggestions

Sprint 14 lets deterministic intelligence suggest internal Agency OS automations.

Examples:

- recurring proxy failures -> suggest Proxy Repair Assistant.
- overdue tasks rising -> suggest Overdue Task Escalation.
- repeated notification delivery failures -> suggest Notification Failure Watch.
- critical incident recurrence -> suggest Critical Incident Escalation.

The suggestion creates a draft automation from the recommendation context. It does not activate, approve, or run the rule. Operators must still simulate, review impact, approve when required, and explicitly activate/run.

Automation suggestions must not create social posting, scraping, credential-handling, or security-evasion actions.
