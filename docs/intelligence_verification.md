# Intelligence Verification

Sprint 25 verified that the intelligence layer is not just static Telegram copy.

## Verified Data Sources

The deterministic intelligence service reads persisted Fortuna OS records:

- EventLog
- AuditLog
- Incidents and IncidentTimeline
- Tasks
- Proxies
- Accounts
- Models/Brands
- Recommendations
- NotificationDeliveryAttempts
- SystemHeartbeats

## Verified Outputs

`run_full_intelligence_scan()` creates durable `intelligence_runs` rows and runs:

- pattern detection
- trend analysis
- workload analysis
- recommendation generation
- executive briefing
- opportunity scoring

The Sprint 25 verification test creates live proxy failure events, runs the full scan, and confirms persisted:

- `IntelligenceSignal`
- `IssuePattern`
- `TrendSnapshot`
- `WorkloadSnapshot`
- `Recommendation`
- `EventLog`

## Deduplication

Signals and patterns upsert by type/entity/status, so repeated scans update open records instead of spraying duplicates.

## Safety

Metadata flows through recursive sanitization. Tokens, passwords, credentials, keys, proxy passwords, raw chat IDs, owner Telegram IDs, verification codes, and code hashes are redacted before they reach audits, event logs, recommendations, heartbeats, and timeline metadata.

## Known Limits

- No scraping.
- No social posting/commenting/liking/following.
- No platform login automation.
- No LLM reasoning yet.
- Trend analysis depends on previously stored snapshots, so trend quality improves with repeated scans over time.
