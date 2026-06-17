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
- Proxy session-string rotation, automation simulation mode, and self-healing are placeholders until concrete production workflows are defined.
