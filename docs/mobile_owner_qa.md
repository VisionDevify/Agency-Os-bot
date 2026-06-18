# Sprint 35 Mobile Owner QA

Sprint goal: stop adding systems and validate whether a real owner can open Fortuna OS on mobile and know what to do next.

## Verification Method

This report combines:

- renderer and callback coverage from the test suite
- production health checks
- prior Telegram Web/Railway diagnostics
- a mobile-first product review of the owner path

True mobile tactile QA still needs owner execution on Telegram mobile. Codex cannot physically operate the owner's phone, so this document is both a checklist and a friction report for that session.

## Owner QA Checklist

For each screen, answer:

- Clear in 10 seconds?
- Useful right now?
- Any dead end?
- Too many taps?
- One obvious next action?

Screens to test on Telegram mobile:

1. `/start`
2. Home
3. Start Here
4. Today's Priorities
5. Setup
6. Fortuna Activation
7. Models
8. Accounts
9. Proxy Vault
10. Opportunities
11. Help
12. Advanced
13. Settings
14. Owner Management

## Pass Criteria

- The owner can identify the next action within 10 seconds.
- Every screen has Back/Home.
- No raw JSON, code output, stack traces, secrets, or internal enum labels.
- Proxy Vault explains simulated versus real checks.
- The first workspace path is understandable without reading docs.
- Help Brain answers "What should I do next?" using live state.

## Top 20 UX Issues

1. Home can still feel like a status board instead of an assistant when readiness is low.
   - Severity: high
   - Fix: keep one dominant next action and hide secondary metrics under Today or Advanced.

2. Start Here and Setup overlap conceptually.
   - Severity: high
   - Fix: Start Here should be "do the next thing"; Setup should be "see all setup areas."

3. Proxy Vault depends on owner understanding provider language.
   - Severity: high
   - Fix: keep "Paste Olympix Proxy String" as primary and explain everything else in one sentence.

4. Real proxy checks can sound like they run automatically.
   - Severity: high
   - Fix: show "On demand only" and "Last checked" on every proxy status view.

5. "Advanced" contains too many powerful areas without a plain warning.
   - Severity: medium
   - Fix: add a short header: "Advanced tools are for diagnostics and admin work."

6. Today's Priorities risks becoming another list if all blockers are displayed.
   - Severity: medium
   - Fix: show Top 5 only and collapse the rest.

7. Recommendations are useful but can repeat the same model setup issue.
   - Severity: medium
   - Fix: group duplicate model blockers under one model completion card.

8. Placeholder cleanup is owner-safe, but easy to miss.
   - Severity: medium
   - Fix: show Cleanup only when placeholders exist.

9. Owner Management may not explain "final owner protection" clearly enough.
   - Severity: medium
   - Fix: add one plain line before owner actions.

10. Help Brain is powerful, but the owner may not know what to ask.
    - Severity: medium
    - Fix: add three prompt chips on Help: "What first?", "Why low readiness?", "How add proxy?"

11. Opportunities and Creator Watch are split mentally for new owners.
    - Severity: medium
    - Fix: make Opportunities home say "Creators feed opportunities."

12. Account setup can feel blocked if no model exists.
    - Severity: medium
    - Fix: "Create model first" should include the direct button.

13. Team setup has no real value until team users press `/start`.
    - Severity: medium
    - Fix: show Invite Team before Assign Team when there are no approved users.

14. Notification targets still need external Telegram group setup.
    - Severity: medium
    - Fix: keep the group setup guide and sandbox test as the only visible path.

15. Production Observability is useful but too technical for daily owner use.
    - Severity: low
    - Fix: keep under Advanced and summarize only Healthy/Degraded/Unsafe on Home.

16. What Fortuna Did may not distinguish "scan" from "action".
    - Severity: low
    - Fix: label passive scans separately from changes/tasks.

17. Daily Autopilot can sound more autonomous than it is.
    - Severity: low
    - Fix: say "safe scans only unless approved."

18. Model completion needs to feel like one wizard, not several admin pages.
    - Severity: high
    - Fix: keep the Model Completion Wizard as the main fix path for model blockers.

19. Proxy rotation needs a stronger "what happens before I confirm" message.
    - Severity: medium
    - Fix: pre-confirm copy: "This changes only the session suffix. Password is unchanged."

20. Mobile button density still needs real thumb testing.
    - Severity: high
    - Fix: owner should screen-record the mobile session and mark every screen where scrolling hides the next action.

## Top 10 Confusion Points

1. Difference between Start Here, Setup, and Activation.
2. Whether proxy checks use real network traffic.
3. Whether a proxy password is ever shown again.
4. Why accounts require a model first.
5. What to do when no team users exist yet.
6. Whether opportunities are automatic or human-only.
7. Whether Daily Autopilot changes data or only scans.
8. Why notification groups cannot be auto-created safely.
9. What "readiness" means in plain business terms.
10. Which screens are daily use versus admin diagnostics.

## Top 10 Click Reductions

1. Home -> Continue/Fix Top Blocker should open the exact blocker flow, not a list.
2. Proxy Vault -> Add Proxy should default to one-paste Olympix import.
3. Account missing proxy -> Add Proxy First should return directly to that account after save.
4. Model missing country/timezone/platform should be one model completion wizard.
5. No team users -> Invite Team should replace Assign Team.
6. Opportunity from creator should inherit platform, niche, model, and assignee.
7. Help -> What should I do next should use the same next action as Home.
8. Setup Progress -> Fix should open the exact fix page for each row.
9. Placeholder Cleanup should be shown only when placeholders exist.
10. Proxy Detail -> Test should show cached last result first, then "Run Check" on demand.

## Proxy Vault Reality Test

Task: Add a proxy

- Current state: one-paste import exists and is the right primary path.
- Remaining risk: owner may not know which part is "the Olympix proxy string."
- Fix recommendation: first step should say "Paste the whole host:port:username:password line."

Task: Assign a proxy to an account

- Current state: Accounts Missing Proxy and Assign Account flows exist.
- Remaining risk: if no accounts exist, owner needs a direct Add Account path.
- Fix recommendation: show "Create account first" with direct button.

Task: Rotate or replace a proxy

- Current state: rotation and rollback exist.
- Remaining risk: owner may not understand that only session suffix changes.
- Fix recommendation: add pre-confirm text and show old/new masked suffix.

Task: Check proxy status

- Current state: simulated mode and real-check flags exist.
- Remaining risk: data usage expectations need to be explicit.
- Fix recommendation: show "Checks run only when you tap Test" and "Last checked: never/relative time."

## First Workspace Test

Target flow:

Start Here -> Complete Model -> Add Account -> Add Proxy -> Assign Proxy -> Assign Team -> Add Creator -> Create Opportunity -> Run Daily Cycle

Current assessment:

- The flow exists through First Workspace Guide.
- The main friction is conceptual overlap with Setup and Activation.
- The owner should not have to choose among three setup surfaces. Home should always choose the next one.

## Fortuna Feels Alive Test

Each major screen should answer:

- What happened?
- What needs attention?
- What should I do next?

Current assessment:

- Home, Start Here, First Workspace Guide, Proxy Vault, and Help Brain are closest.
- Advanced, Observability, Intelligence, and some report screens are still intentionally admin-like and should stay behind Advanced.

## Most Valuable Improvement

Make Home's primary button always route to the single highest-impact fix path, not a hub. If the model is incomplete, Home should open model completion. If no proxy exists, Home should open one-paste proxy import. If no team exists, Home should show Invite Team.

## Biggest Remaining Blocker

True mobile owner feedback. The product now has tests and public production health, but the next decisive signal is a 5-minute owner mobile screen recording using:

1. `/start`
2. Start Here
3. Proxy Vault
4. Help -> What should I do next?
5. First Workspace Guide
