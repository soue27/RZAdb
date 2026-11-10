# syntax=docker/dockerfile:1

FROM python:3.13.7-slim-bookworm

ARG APP_UID=10001
ARG APP_GID=10001

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

# PGDG supplies PostgreSQL 18 client utilities for Debian Bookworm. The
# runtime image gets only the client package, never the PostgreSQL server.
RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates curl \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl --fail --silent --show-error --location \
        https://www.postgresql.org/media/keys/ACCC4CF8.asc \
        --output /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && printf '%s\n' \
        'Types: deb' \
        'URIs: https://apt.postgresql.org/pub/repos/apt' \
        'Suites: bookworm-pgdg' \
        'Components: main' \
        'Signed-By: /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc' \
        > /etc/apt/sources.list.d/pgdg.sources \
    && apt-get update \
    && apt-get install --no-install-recommends -y postgresql-client-18 \
    && pg_dump --version | grep -E ' 18\.' \
    && pg_restore --version | grep -E ' 18\.' \
    && pg_isready --version | grep -E ' 18\.' \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.8 /uv /uvx /usr/local/bin/

COPY pyproject.toml uv.lock README.md ./
COPY app ./app
COPY data/document_templates ./data/document_templates
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini

RUN uv sync --locked --no-dev \
    && groupadd --gid "${APP_GID}" rzadb \
    && useradd --uid "${APP_UID}" --gid rzadb --create-home --shell /usr/sbin/nologin rzadb \
    && install -d --owner rzadb --group rzadb --mode 0750 \
        /app/data/uploads /app/data/backups

USER rzadb

EXPOSE 8000

CMD ["uvicorn", "app.presentation.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
