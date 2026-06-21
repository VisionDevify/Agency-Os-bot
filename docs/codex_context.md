# Codex Context Pack

Future sprint prompts must begin with: "Before changing code, read docs/codex_context.md."

## Project Overview

Fortuna OS is a Telegram-first operations assistant for an agency workflow. It guides owners, managers, chatters, and VAs through setup, opportunities, alerts, proxy management, recovery, and operational health.

Fortuna should feel calm, guided, and trustworthy. Primary screens answer:

1. What is happening?
2. Is anything wrong?
3. What should I do next?

Technical details stay behind Details, Technical Details, or Advanced views.

## Architecture

The app is a Python backend with SQLAlchemy models, Alembic migrations, Telegram screen renderers, service-layer workflows, and Railway production deployment. Telegram UI screens are rendered as text plus inline buttons. Button callbacks are routed through central navigation and callback protection services.

Important layers:

- Models: persistent database entities.
- Services: business rules, status truth, safety gates, scoring, backup, callback, and observability logic.
- Screens: user-facing Telegram text and buttons.
- Docs/tests: safety, verification, and regression coverage.

## Production Truth

Production truth must come from live evidence, not stale recommendations.

Current production safety principles:

- PostgreSQL is required for durable production storage.
- Redis is required for durable polling and callback safety.
- SQLite fallback is not production-safe unless explicitly emergency-enabled.
- `/health`, `/integrity`, `/botstatus`, and Production Observability must not contradict each other.
- Missing setup is not the same as a failed system.

## Recovery Status

Recovery status is evidence-backed only.

Evidence inputs:

- External storage configured and tested.
- Verified backup artifact.
- Verified checksum and encryption/decryptability.
- Restore validation result.
- Backup age and recent failure history.
- Provider availability.

Allowed recovery states:

- `healthy`
- `needs_review`
- `needs_attention`
- `critical`

Never show Protected, Passed, Successful, or Healthy unless supporting records exist.

## Callback Storm Protections

Button presses must never crash the bot worker.

Protections include:

- Per-user callback locking.
- Per-message edit locking.
- Short navigation debounce.
- Separate long-lived idempotency for state-changing actions.
- Safe edit-or-send wrapper.
- Global callback exception boundary.
- Stale navigation session/version handling.
- Token-scoped Telegram polling ownership through Redis, with `TelegramConflictError` surfaced as critical evidence in `/botstatus`, `/selftest`, and Production Observability.

Navigation idempotency must be narrow and short-lived. Back, Home, Help, Refresh, and Main Menu should not become stuck behind broad "Already handled" blocking.

## Reliability and Command Shortcuts

Fortuna must feel heard on every interaction:

- Telegram callback queries should be acknowledged quickly.
- Known slow routes should show a visible Working/Checking/Searching/Backing Up state before heavy work.
- AI, search, backup, restore, observability, callback scans, and reliability scans must not silently block the UI.
- Long-running work should use shared job state with queued, running, checking, uploading, verifying, summarizing, completed, failed, timed_out, and cancelled states.
- Completed jobs should update evidence-backed status or leave a safe result summary; failed jobs should never fake success.
- Recovery backup success still requires encrypted artifact, checksum, upload, and verification evidence.

Important screens must be reachable by command because Telegram Desktop automation can expose inline buttons as unlabeled controls. Command shortcuts should reuse the same renderers as buttons and bypass stale menu state:

- `/home`, `/more`, `/coo`, `/today`
- `/agency`, `/agency_active`, `/agency_missing`, `/agency_connected`
- `/ai`, `/ai_settings`, `/ai_critic`, `/ai_evidence`, `/ai_coo`
- `/search`, `/search_settings`, `/search_history`
- `/recovery`, `/backup_history`, `/run_backup`, `/restore_test`
- `/reliability`, `/verify_navigation`, `/callback_failures`, `/button_health`
- `/notifications`, `/platforms`, `/decision_memory`, `/reality`, `/intelligence`, `/observability`

Reliability Center is the owner-facing place for button reliability, callback speed, active failures, historical failures, stale menus, webhook delivery, and long-running jobs. Historical issues remain available in Details but should not count against current status after fresh revalidation passes.

Expensive safe summaries may be cached with a source evidence version, expiry, and commit. Caches must not contain secrets and must be invalidated when evidence changes.

## /start Cleanup Behavior

`/start` should make Fortuna feel like an app reset:

- Delete tracked temporary menu/navigation/help/status/error messages where Telegram permits.
- Preserve alerts, reports, exports, approvals, incidents, and delivery notifications.
- Create one fresh Home screen.
- Mark that message as the only active navigation session.
- Reject old buttons through active navigation session and navigation version checks.

Canonical message labels:

- `temporary_navigation`
- `temporary_help`
- `temporary_status`
- `temporary_error`
- `persistent_alert`
- `persistent_report`
- `persistent_export`
- `persistent_approval`
- `persistent_incident`
- `persistent_delivery`
- `unknown_preserve`

Only `temporary_*` labels are eligible for automatic cleanup.

Telegram Web and browser automation must target the latest active bot message, not the first visible button text. Old visible menu boxes can remain when Telegram refuses deletion or cleanup is still pending; those menus are historical UI and should be ignored unless specifically testing stale callback protection. See `docs/telegram_live_testing.md`.

## Social Intelligence Architecture

Fortuna may analyze compliant, human-provided, official, exported, or approved public social data. Fortuna must not scrape private data, bypass platform limits, or automate platform actions.

Module ownership:

- Comment Intelligence owns comment intake and observations.
- Profile Intelligence owns profile records and repeated-profile detection.
- Discovery owns approved source intake and discovery leads.
- Compliance owns validation gates and logs.
- Opportunity owns conversion, assignment, and outcome tracking.

Shared engines:

- Evaluation scores and ranks only after compliance passes.
- Learning updates memory and confidence from approved events.
- Alert routing sends or simulates approved alerts only.
- Evidence explains why Fortuna made a suggestion.

## Platform Connection Philosophy

Platform Connections use layered truth:

1. Website Reachability
2. Login / Session / API Connection
3. Stats Access
4. Notification Routing
5. Activation Readiness

Truth rules:

- Not connected yet does not mean broken.
- Reachable does not mean logged in.
- Logged in does not mean stats are available.
- Stats available does not mean fresh.
- Healthy is never assumed.

Fortuna may prepare Instagram, X, OnlyFans, Telegram, Email, Backup Storage, and System Alerts connections, but it must never mark a platform connected without successful verification evidence.

## UX Language Rules

Use calm, human wording:

- "Fortuna checked this for you."
- "Nothing urgent here."
- "Next best move..."
- "Ready when you are."
- "This needs your attention."

Avoid developer leakage on simple screens:

- snake_case
- raw IDs
- raw callback names
- raw enum names
- database table names
- metrics walls
- stack traces

Buttons should be emoji-first where practical.

## Status Truth Rules

Use shared status vocabulary where possible:

- `healthy`
- `needs_review`
- `needs_attention`
- `critical`

Overall status is the most severe active validated condition. Historical problems must not appear as current issues after live truth proves they are resolved.

## COO Briefing and Decision Engine

The COO Briefing turns current evidence into one calm executive answer: what matters, why it matters, and what should happen next.

Decision Engine rules:

- Every decision must include title, category, severity, priority rank, impact, risk, recommendation, confidence, evidence, source records, next best move, and whether it can wait.
- Allowed categories are recovery, system health, Telegram bot, navigation, notification, platform connection, opportunity, social intelligence, team, learning, friction, setup, deployment, security, and general.
- Do not create decisions without evidence. If evidence is missing, say "Not enough evidence yet."
- Low-value informational items belong in Details, not the main briefing.
- One top priority should lead the briefing and Today view.

Priority logic:

- Critical recovery gaps, Telegram polling conflicts, bot worker failures, database durability issues, restore verification failures, and broken critical notification routes outrank optional setup.
- Platform not connected during build or final activation planning is usually `can_wait`, unless the platform is required by an active workflow.
- Not connected yet is not a failure.
- The owner should see one next best move, not a pile of equal-looking tasks.

Evidence and confidence:

- High confidence requires direct current evidence, such as live health checks, SystemTruth, Recovery records, ButtonIssue records, notification delivery attempts, platform records, or deployment metadata.
- Medium confidence is partial or indirect evidence.
- Low confidence means weak, stale, or missing evidence and should not become top priority unless the severity is critical.

Decision learning:

- Track decision shown, opened, ignored, dismissed, acted on, failed, stale, and resolved in `DecisionMemory`.
- Outcomes may only move forward when an event or resolver evidence supports the change.
- Ignored does not mean bad; it means no action was observed.
- Resolved requires proof from the relevant system record or health check.
- Helpful, Not Helpful, Remind Later, Dismiss, and Learn From This tune future low-risk ranking gradually.
- Critical safety issues cannot be hidden only because they were ignored or dismissed.
- Platform login recommendations can move to Can Wait during build/final activation planning.
- Learning hooks must not auto-execute business actions.
- Fortuna recommends; humans decide.

Decision quality:

- `DecisionQualityEngine` audits whether Fortuna's decisions are accurate, useful, correctly prioritized, and supported by evidence.
- Recommendation quality is scored across why, impact, confidence, evidence, and next action.
- Recommendation accuracy and category accuracy come from Decision Memory outcomes and real system records; do not invent outcomes.
- Confidence accuracy checks whether high, medium, and low confidence matched evidence strength and later outcomes.
- Weak evidence must downgrade confidence rather than inflate it.
- Duplicate and stale recommendation suppression may quiet non-critical repeats when the recommendation hash and evidence version have not changed.
- Critical and safety-related recommendations must remain visible while unresolved, even if ignored or dismissed.
- Generic recommendations with no specific evidence should be downgraded or suppressed unless they are critical.
- Ranking-quality changes are gated by `DECISION_QUALITY_ENABLED`; if quality scoring fails, fall back to the previous Decision Engine ordering.
- If Decision Memory or quality checks are unavailable, COO Briefing and Today must still render from current evidence and say the quality check is unavailable.
- Quality failures should be logged safely in Observability and must not expose secrets, raw IDs, or stack traces on simple screens.

What not to break:

- Recovery must remain evidence-backed and cannot be hidden by a healthy operations status.
- Telegram polling conflicts must remain visible in decisioning, Observability, `/botstatus`, and `/selftest`.
- Platform Connections must keep the layered truth model: reachable is not connected, connected is not fresh stats.
- The COO Briefing, Today, Recommendations, and Help Brain should all use the same priority philosophy.

Decision quality trends and Predictive COO:

- `DecisionQualityTrend` aggregates Decision Memory by category and daily/weekly/monthly window.
- Trend directions are only `improving`, `stable`, `declining`, or `insufficient_data`.
- Insufficient data must be explicit; Fortuna must not invent improvement from thin records.
- `DecisionTrendEngine` is deterministic and uses Decision Memory plus quality metadata only.
- `PredictiveCOOEngine` creates conservative predictions from current evidence plus trends.
- Predictions are labeled as predictions, not facts, and never replace current verified status.
- Current critical issues outrank predictions.
- Prediction confidence must be conservative: low evidence means low confidence or no prediction.
- Prediction feedback uses prediction events: shown, opened, helpful, not_helpful, remind_later, dismissed, acted_on, proven_correct, proven_wrong.
- Proven correct or proven wrong requires later evidence; ignored does not mean wrong.
- `PREDICTIVE_COO_ENABLED` can disable prediction sections without breaking Decision Engine, COO Briefing, or Today.
- If trend or prediction calculation fails, show unavailable, log safely, and keep current evidence-based briefing screens working.

Reality calibration:

- `PredictionOutcome` tracks whether a prediction is pending, partially correct, proven correct, proven wrong, unresolved, expired, or not supported by enough evidence.
- Default prediction outcome is `pending`; no prediction may be marked correct or wrong without later evidence.
- `PredictionEvaluationEngine` compares predictions against later Recovery, Platform, Notification, Friction, ButtonIssue, Opportunity, and bot-status records.
- Owner feedback can record perceived usefulness, but feedback alone does not prove correctness unless supporting evidence is attached.
- Unsupported prediction types or failed evidence lookups become `not_enough_evidence`; they must not be treated as success.
- `CalibrationEngine` measures confidence accuracy by confidence level, category, prediction type, and time window.
- Calibration statuses are only `calibrated`, `overconfident`, `underconfident`, or `insufficient_data`.
- Confidence adjustment may make future wording more conservative or more precise, but it must never downgrade verified severity, hide current critical issues, or alter production truth.
- Recovery calibration example: restore-test-path predictions stay pending while backup is verified but full restore evidence is missing; they become correct only after later restore evidence confirms the blocker or after the restore path is addressed.
- `REALITY_CALIBRATION_ENABLED` can hide Reality Check screens without breaking Prediction Preview, COO Briefing, Today, or the Decision Engine.
- If evaluation or calibration fails, show Reality Check or Calibration unavailable, log safely, and keep current decisions visible.

Evidence capture and owner validation:

- `EvidenceRecord` stores traceable owner notes, owner validations, system records, uploaded references, and operational outcomes.
- Evidence strength is explicit: weak, medium, or strong.
- Weak evidence is owner opinion or limited notes. Medium evidence is owner context plus supporting records. Strong evidence is confirmed operational outcome, multiple records, or owner validation plus system outcome.
- Owner notes are evidence, but they are not automatically truth.
- Owner Validation can mark a prediction correct, incorrect, partially correct, too early to tell, or add evidence.
- `partially_correct` means evidence supports part of the prediction while uncertainty or contradiction remains.
- Owner feedback helps Fortuna learn, but it cannot override contradictory system records by itself.
- `KnowledgeMemory` stores durable lessons only when they originate from evidence and include confidence.
- Decision Review and Decision Timeline should show the chain from prediction to recommendation to evidence to validation to outcome to lesson.
- If evidence capture fails, prediction, decision, COO Briefing, and calibration should continue from system evidence and show evidence status as unavailable.

Search Intelligence and external evidence:

- Search Intelligence gives Fortuna safe public-world awareness through one approved provider first: Tavily.
- `SearchProvider` is the abstraction; `TavilySearchProvider` is the only implemented provider for now.
- Future providers such as Google Custom Search API, Brave Search API, Bing Web Search, SerpAPI, or Exa must plug into the provider abstraction instead of bypassing search safety.
- Search is controlled by `SEARCH_ENABLED`, `SEARCH_PROVIDER`, `TAVILY_API_KEY`, `SEARCH_DAILY_LIMIT`, `SEARCH_TIMEOUT_SECONDS`, and `SEARCH_DEFAULT_RECENCY_DAYS`.
- Missing `TAVILY_API_KEY` means Search Intelligence is not configured yet; it is not a production-critical failure unless an active search-dependent workflow requires it.
- Search workflows must pass the compliance gate before any provider call.
- Allowed search: public web research, public news, public platform pages available without login, compliant public niche/trend research, public competitor research, and source validation.
- Blocked search: private profiles, login-required pages, password/session scraping, private data harvesting, bot-detection evasion, doxxing, sensitive personal data collection, bulk profile scraping, or bypassing rate limits.
- Search result does not equal truth. Search result equals external evidence that must be URL/domain-backed, timestamped, scored, cited, and reviewed.
- Store search records in `ExternalSearchQuery` and `ExternalSearchResult`; never store raw HTML dumps or provider secrets.
- `EvidenceRecord.evidence_type=external_search` links public results into owner evidence while preserving source URL/domain/retrieved_at/query metadata.
- Evidence scoring uses relevance, freshness, credibility, and risk. Low credibility or high risk must lower confidence.
- One search result is usually weak or medium evidence; strong evidence should require official/reputable sources and low risk.
- Search may support Opportunity Intelligence, Notification Intelligence, COO Briefing, and Recommendations, but it must not auto-contact, auto-post, auto-comment, auto-like, or auto-follow.
- Weak external evidence must not create high-priority opportunities by itself.
- Search-triggered notifications require relevance and freshness thresholds and must explain why the signal matters.
- COO Briefing should include external context only when it changes what the owner should do; random or stale results belong in Details.
- Rate limits and cached repeated queries prevent search API spam and cost surprises.
- If search provider calls fail, show a safe reason, keep old results if useful, and never expose the API key.

AI Brain and grounded reasoning:

- AI Brain is optional and controlled by `AI_ENABLED`, `AI_PROVIDER`, `OPENAI_API_KEY`, `AI_MODEL`, `AI_TIMEOUT_SECONDS`, `AI_DAILY_LIMIT`, `AI_MAX_CONTEXT_RECORDS`, and `AI_CRITIC_ENABLED`.
- ChatGPT Pro does not automatically power Fortuna. Production AI requires an OpenAI API key configured safely in Railway.
- Missing `OPENAI_API_KEY` means AI Brain is not configured yet; it is not a production-critical failure unless an active AI-dependent workflow requires it.
- AI may explain, synthesize, compare, summarize, and improve wording. It may not mark systems healthy, verify backups, pass restores, approve compliance, change polling truth, or override deterministic status logic.
- Evidence always wins. If AI disagrees with verified Recovery, Bot Status, Observability, Search, or Decision Engine evidence, the deterministic evidence is shown and the AI output is blocked or replaced.
- `AIGroundingContextBuilder` must provide structured, redacted context for decision, COO, search, opportunity, and Help Brain use cases.
- AI calls must not receive secrets, backup credentials, Telegram tokens, raw environment dumps, private scraping data, or unnecessary sensitive/private data.
- AI output must follow the grounded reasoning contract: conclusion, evidence used, reasoning summary, confidence, limitations, next best move, and safety flags.
- `FortunaAICritic` reviews AI output for unsupported claims, exaggerated confidence, missing evidence, contradictions with system truth, unsafe recommendations, compliance violations, raw secret leaks, auto-action suggestions, and excessive verbosity.
- Critic-blocked output must fall back to deterministic Decision Engine text and create safe audit/observability events.
- AI Search summaries may only cite source titles/domains/results supplied by Search Intelligence. AI must not invent sources or external facts.
- AI audit logs store safe metadata only: use case, provider, model, status, evidence count, safe error summary, output hash, and estimates. They must not store API keys, raw secrets, or full unredacted production prompts.
- Rate limits, timeouts, cached repeated summaries, and disabled fallbacks prevent AI call loops and cost surprises.

Self-healing issue lifecycle:

- Fixed problems must fall out of active views after fresh evidence proves they no longer reproduce.
- Standard issue-like lifecycle states are `active`, `validating`, `resolved`, `historical`, `ignored`, `stale`, and `reappeared`.
- Callback failures, Button Health issues, callback recommendations, observability findings, notification alerts, friction findings, recovery findings, AI/search failures, and team UX findings should use those meanings even when the underlying table stores a smaller status vocabulary.
- Historical records are retained for audit and learning. Do not delete old callback logs, audit rows, events, or recommendations just because they are resolved.
- `IssueRevalidationEngine` classifies old callback failures against current callback scan evidence and deployment metadata. A route can become historical only after a targeted fresh check passes or a previously stored resolved recommendation contains revalidation evidence.
- Revalidation must be evidence-backed. If validation is unavailable, show `validating` or `needs review`; do not claim healthy.
- Old failures before the current deployment should not count as active if the same route passes after deploy. Failures after the current deploy, or failures that reproduce after resolution, remain active or `reappeared`.
- Button Health active counts must use only open/current ButtonIssue records. Resolved or historical issues stay in Details/history.
- Observability top-level issue counts must exclude historical issues and include only active, reappeared, or current validating issues.
- Recommendations tied to fixed callback failures should move to `resolved` when the callback route passes revalidation. If the same issue returns, create or reopen the recommendation with new evidence.

Team UX readiness and active screens:

- Fortuna should feel like one active Telegram app screen, not a stack of historical menus.
- The newest tracked temporary navigation screen is the active screen. It wins over older visible Telegram messages.
- Stale old-menu callbacks must not mutate or overwrite the current screen. They should redirect safely with human wording.
- Unknown or untracked temporary callbacks default to safe Home when active-session metadata is missing.
- Persistent alerts, reports, exports, approvals, incidents, delivery messages, verification reports, and backup/export instructions remain protected.
- Temporary menu cleanup is best effort. Telegram deletion failures must not block `/start`, `/clean`, Home, Back, `/botstatus`, or `/selftest`.
- Screens intended for real team use should answer: what this is, why it matters, and what to do next.
- Simple screens should hide raw IDs, stack traces, internal enum names, database constraints, and architecture terms unless the user opens Details.
- Prefer human wording: "Fortuna needs more information here" over "insufficient data" on simple screens.
- `UserTrustSignals` and `TeamUXReadiness` use existing callback, Button Health, Friction, and Chat Cleanup records to detect stale-menu confusion and navigation trust issues.
- Role metadata currently prepares four audiences: Owner, Manager, Chatter, and VA. It is metadata only until future role-specific UI permissions are implemented.
- The New Team Member Test asks whether a new hire can understand the screen in under 30 seconds.
- AI wording should pass a readability check: a manager or chatter should understand the point, the risk, and the next action.

Agency Awareness:

- Agency Awareness answers: what is happening inside the agency right now?
- It must separate active work, inactive work, not-connected sources, missing visibility, and temporarily unavailable external platforms.
- `AgencyDomain` definitions cover recovery, AI Brain, Search Intelligence, notifications, platform connections, Instagram, X, Reddit, OnlyFans, Chaturbate, creators, content, traffic sources, fans, whales, chatters, opportunities, operations, compliance, finance, and Knowledge Memory.
- Active status requires evidence. Manual notes are evidence, but they are not system truth and must not overwrite verified system records.
- `AgencyManualRecord` stores owner-supplied activity, blockers, notes, wins, losses, plans, and updates with explicit confidence.
- `AgencyAwarenessSnapshot` stores generated awareness summaries, visibility score, confidence score, top focus area, next best move, snapshot source, stale state, missing inputs, and degraded mode.
- `AgencyAwarenessEngine` must tolerate missing future modules and continue from healthy inputs. Missing creators, fans, whales, chatters, finance, or content data should become visibility gaps, not crashes.
- Visibility score is a coverage signal, not a health claim. Low visibility is acceptable when evidence is honestly missing.
- Stale snapshots can be used as fallback only when clearly labeled with timestamp and degraded/fallback wording.
- If no valid snapshot exists and live generation fails, return explicit insufficient data.
- External platform outages must not crash Awareness. Instagram, X, Reddit, OnlyFans, or Chaturbate being unavailable should pause live collection, lower confidence, keep historical/manual evidence available, and explain the impact in plain language.
- Not connected is not failure. It means a platform or data source is not approved and verified yet.
- Simple Agency Awareness screens should answer what this is, why it matters, what Fortuna can see, what Fortuna cannot see, top focus area, and next best move.
- Details may show deeper status/source/freshness metadata, but no secrets, raw IDs, or developer-first architecture.
- AI may summarize Agency Awareness only from supplied awareness context. It must not infer platform activity during outages or fill gaps with invented agency activity.
- COO Briefing and Today may mention Agency Awareness only when visibility gaps, degraded mode, or meaningful agency context changes what the owner should do.
- Observability should show Agency Awareness only when meaningful: missing inputs, stale snapshots, external outages, generation failures, or fallback usage.
- Future Agency Awareness path: Drift Detection, Opportunity Loss, Question Engine, and Digital Twin.

## Compliance Rules

Fortuna may observe, summarize, recommend, and route human-reviewed work.

Fortuna must not:

- auto-post
- auto-comment
- auto-like
- auto-follow
- scrape private data
- evade platform security
- bypass rate limits
- expose secrets
- fabricate connection, stats, backup, restore, notification, or readiness states

Humans execute.

## Protected Behaviors

Always preserve:

- Secrets and credentials.
- Telegram alerts, reports, approvals, exports, incident messages, and delivery notifications.
- Production data unless the owner explicitly approves destructive cleanup.
- Compliance gates around social workflows.
- Honest degraded states when evidence is missing.

## Roadmap

Near-term priorities:

- Finish platform connection activation with secure credential flows.
- Add official/approved connector integrations only when owner-approved.
- Continue mobile Telegram QA.
- Keep reducing developer leakage.
- Expand role-specific workflows once owner setup is stable.
- Strengthen live verification paths for Railway and Telegram.
