# Enterprise-Agent-OS — prod runtime image
# Multi-stage build: deps via uv sync --no-dev, entrypoint picks
# gunicorn vs uvicorn based on QZDAP_GUNICORN_WORKERS.

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/backend/src \
    QZDAP_ENV=production

# libpq5 = asyncpg runtime; libssl3 = cryptography/tls deps.
# curl / tini intentionally omitted:
#   - HEALTHCHECK uses python urllib (no shell binary)
#   - PID 1 is /entrypoint.sh which uses ``exec`` so zombie reaping is
#     handled by docker run --init (default on Docker Desktop) or the
#     container runtime's init.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 libssl3 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

# 1. copy workspace metadata first to maximize Docker layer cache
COPY backend/pyproject.toml backend/uv.lock /app/backend/

# 2. copy sources (libs + modules + composition + runtimes + migrations)
COPY backend/libs       /app/backend/libs
COPY backend/modules    /app/backend/modules
COPY backend/composition /app/backend/composition
COPY backend/migrations /app/backend/migrations
COPY backend/runtimes   /app/backend/runtimes

# 3. install deps (no-dev, frozen lock)
WORKDIR /app/backend
RUN uv sync --no-dev --frozen --no-install-project || \
    uv sync --no-dev --frozen

COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

WORKDIR /app

EXPOSE 8102

# python urllib replaces the curl binary — same semantics, one fewer
# apt package and ~3 MB smaller image.
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8102/livez', timeout=3).status == 200 else 1)" || exit 1

ENTRYPOINT ["/entrypoint.sh"]