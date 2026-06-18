FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir ".[dev]"

COPY alembic.ini ./
COPY railway.json ./
COPY alembic ./alembic
COPY app ./app
COPY docs ./docs
COPY tests ./tests

CMD ["python", "-m", "app.runtime.railway_start"]
