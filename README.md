# Agency OS Bot

Secure foundation for the existing Telegram bot and GitHub repo.

## Stack

- Python 3.12
- FastAPI
- aiogram
- PostgreSQL with SQLAlchemy and Alembic
- Redis
- Docker Compose
- pytest

## Setup

1. Copy `.env.example` to `.env`.
2. Fill in the required secrets locally. Never commit `.env`.
3. Start services:

```bash
docker compose up --build
```

4. Run migrations:

```bash
alembic upgrade head
```

5. Run tests:

```bash
pytest
```

## Required Environment Variables

- `TELEGRAM_BOT_TOKEN`: existing Telegram bot token.
- `DATABASE_URL`: PostgreSQL SQLAlchemy URL, for example `postgresql+psycopg://agency:agency@db:5432/agency_os`.
- `REDIS_URL`: Redis URL, for example `redis://redis:6379/0`.
- `APP_SECRET_KEY`: application signing secret.
- `ENCRYPTION_KEY`: application encryption secret for future sensitive payloads.
- `OWNER_TELEGRAM_ID`: Telegram numeric ID allowed to perform owner-only setup.

## Security Notes

- Tokens and secrets belong only in `.env` or the deployment secret store.
- Logging must never print raw tokens, session strings, or secret values.
- Owner setup is restricted to `OWNER_TELEGRAM_ID`.
- Permission checks and audit logging are centralized in `app.services`.
- Proxy session-string rotation, automation simulation mode, notification routing, and self-healing stay safety-gated until concrete production workflows are approved.

## Current Modules

- Telegram owner setup, users, roles, permissions, and audits.
- Models/Brands command center.
- Account inventory with secure auth-session and hashed 2FA-code flow.
- Proxy Vault with encrypted proxy passwords, rotation placeholders, health scoring, incidents, and simulation mode.
- Tasks and incidents operations layer.
- Executive Command Center, Daily Company Briefings, Team Accountability, Operations Dashboard, Chatter Dashboard placeholder, and VA Dashboard placeholder.
- Notification Routing V1 with encrypted/masked Notification Targets and testing-only safe sends.
- Automation Simulation Runs for non-mutating impact previews.
- Deterministic Recommendations engine for missing proxies, auth attention, critical incidents, overdue work, and staffing gaps.
- Bot Status and system heartbeat records for API, bot, db, redis, and Railway deployment state.
- Lightweight EventLog persistence for report and operational event feeds.
- Notification delivery attempt records for sent/failed/skipped test deliveries, with safe audit/event output and failure recommendations.
- Agency operations activation: task ownership/escalation, incident timelines, user availability/localization, Daily Digest delivery, Manager Command View, and duplicate polling guard.
- Agency Intelligence Brain V1: deterministic signals, issue patterns, trend snapshots, workload intelligence, executive insights, intelligence runs, Recommendation V2 metadata, and manual opportunity intelligence.
- Automation Builder and Simulation Engine: no-code rules, built-in templates, trigger/condition/action registries, durable simulations, approvals, run/step records, rollback planning, and automation health metrics.
- Agency Learning Engine and Playbook Memory: learning events, outcome memory, seeded recovery playbooks, playbook runs, confidence records, recommendation/playbook feedback, automation learning, opportunity learning, and executive memory briefing.
- Team Rollout and Human Experience Layer: role-specific homes, personalized dashboards, Daily Experience, Help Center, Team QA readiness checklist, notification digest mode, and safe scheduled automation execution for low-risk rules.
- Team Activation and Opportunity Command Center: guided Creator Watch intake, guided Opportunity intake, Own Post Watch intake, opportunity assignment, result recording, suggested human-only comment strategies, chatter workspace, manager opportunity view, Help Copilot, activation QA, and opportunity notification routing keys.

## Railway Deployment

Railway production activation has been started for Agency OS after owner approval.

Current Railway services:

- API service from this repo using `railway.json`.
- Bot worker service from this repo with start command `python -m app.bot.runner`.
- PostgreSQL.
- Redis.

API start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Bot worker start command:

```bash
python -m app.bot.runner
```

Migrations run at API and bot startup. A manual migration command is still safe if needed:

```bash
alembic upgrade head
```

Health check:

```bash
GET /health
```

The health endpoint returns safe status labels for API, database, and Redis and writes heartbeat records. It never returns secret values.

See `docs/railway_deployment.md` for the full production checklist and blockers.

Production smoke testing checklist:

- `docs/production_smoke_test.md`

## Architecture Docs

- `docs/agency_os_master_spec.md`
- `docs/database_schema.md`
- `docs/event_architecture.md`
- `docs/railway_deployment.md`
- `docs/notification_routing.md`
- `docs/production_operations.md`
- `docs/automation_simulation.md`
- `docs/recommendations_engine.md`
- `docs/team_operations.md`
- `docs/onboarding_localization.md`
- `docs/daily_digest.md`
- `docs/intelligence_brain.md`
- `docs/pattern_recognition.md`
- `docs/opportunity_intelligence.md`
- `docs/recommendation_engine_v2.md`
- `docs/automation_builder.md`
- `docs/simulation_engine.md`
- `docs/approval_workflows.md`
- `docs/rollback_planning.md`
- `docs/learning_engine.md`
- `docs/playbook_memory.md`
- `docs/confidence_engine.md`
- `docs/outcome_memory.md`
- `docs/team_rollout.md`
- `docs/user_experience.md`
- `docs/onboarding.md`
- `docs/role_dashboards.md`
- `docs/creator_watch.md`
- `docs/opportunity_command_center.md`
- `docs/help_copilot.md`
- `docs/team_activation.md`
- `docs/opportunity_workflows.md`
- `docs/chatter_workflows.md`
- `docs/manager_activation.md`
- `docs/setup_wizard.md`
- `docs/first_day_plan.md`
- `docs/ui_structure.md`

## First Agency Setup

Owners and admins should start in Telegram with:

```text
Owner Home -> Setup Agency
```

The setup wizard guides the first useful production setup:

- create a Model/Brand
- add Instagram, X, OnlyFans, Email, or Other accounts
- assign manager/chatter/VA team members
- add starter creators to watch
- create starter opportunities
- review missing setup items before finishing

If no model exists yet, account and own-post screens intentionally explain that the model comes first. Demo Seed Mode is owner-only and creates records marked as demo data so the UI can be tested without mixing sample records with real operations.
