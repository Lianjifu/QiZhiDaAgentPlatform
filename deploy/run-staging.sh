#!/usr/bin/env bash
# Staging sandbox launcher — single-machine.
# Two modes:
#   docker   (default) — postgres + qzdap-app:prod in two docker containers;
#                        entrypoint picks gunicorn vs uvicorn per QZDAP_GUNICORN_WORKERS.
#   uvicorn            — postgres in docker, app runs on the host via
#                        ``uv run uvicorn --reload`` (no image build, hot reload,
#                        debugger attach, ~150 MB less memory).
#
# No compose, no ingress, no canary, no MinIO, no Vault / k8s.
#
# Port policy — staging uses ports decoupled from prod defaults (5432 /
# 8102 / 9102) so a colocated dev box can run both without conflicts:
#   - PG container host port:  ${QZDAP_PG_HOST_PORT:-5433}
#   - App host port:           ${QZDAP_APP_HOST_PORT:-8103}
#   - Metrics host port:       ${QZDAP_METRICS_HOST_PORT:-9103}
# Override any of them via env if your local box needs something else.
#
# Mirrors doc/burn-in-preflight.md A.1 / A.5 / A.6 / A.7 (and A.2 in env).
#
# Usage:
#   ./deploy/run-staging.sh up [docker|uvicorn]
#   ./deploy/run-staging.sh stop
#   ./deploy/run-staging.sh logs
#   ./deploy/run-staging.sh ps
#   ./deploy/run-staging.sh migrate          # run alembic against the running PG
set -euo pipefail
# Absolute-path resolution — works regardless of the caller's CWD.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

cmd="${1:-up}"
sub="${2:-docker}"

PG_HOST_PORT="${QZDAP_PG_HOST_PORT:-5433}"
APP_HOST_PORT="${QZDAP_APP_HOST_PORT:-8103}"
METRICS_HOST_PORT="${QZDAP_METRICS_HOST_PORT:-9103}"

start_postgres() {
    docker network create qzdap-staging >/dev/null 2>&1 || true
    docker rm -f qzdap-postgres 2>/dev/null || true
    docker run -d --name qzdap-postgres --network qzdap-staging \
        -p "${PG_HOST_PORT}:5432" \
        -e POSTGRES_DB=qzdap \
        -e POSTGRES_USER=qzdap \
        -e POSTGRES_PASSWORD=qzdap \
        -v qzdap-pgdata:/var/lib/postgresql/data \
        --health-cmd "pg_isready -U qzdap" \
        --health-interval 5s \
        --health-timeout 3s \
        --health-retries 10 \
        pgvector/pgvector:pg16
    for _ in $(seq 1 30); do
        s=$(docker inspect -f '{{.State.Health.Status}}' qzdap-postgres 2>/dev/null || echo starting)
        [[ "$s" == healthy ]] && { echo "[run-staging] postgres healthy on host port ${PG_HOST_PORT}"; return; }
        sleep 1
    done
    echo "[run-staging] postgres failed health check" >&2
    exit 1
}

wait_for_app() {
    for _ in $(seq 1 30); do
        if curl -fsS "http://localhost:${APP_HOST_PORT}/readyz" >/dev/null 2>&1; then
            echo "[run-staging] qzdap-app ready"
            return
        fi
        sleep 2
    done
    echo "[run-staging] qzdap-app /readyz did not return 200 in 60s" >&2
    return 1
}

run_migrate() {
    if [[ "$sub" == "uvicorn" ]]; then
        # ``--all-packages`` makes uv materialise every workspace member
        # (qzdap-persistence, qzdap-vault, …) into the venv; without it only
        # the root project's deps land and ``alembic`` (a transitive
        # dep of qzdap-persistence) is missing. ``--no-dev`` is fine here
        # because alembic / sqlalchemy / asyncpg come transitively from
        # the persistence workspace member, not from the dev extras.
        (cd "${REPO_ROOT}/backend" && uv sync --all-packages)
        (cd "${REPO_ROOT}/backend/migrations" && uv run alembic upgrade head)
    else
        docker exec qzdap-app alembic upgrade head
    fi
}

# ── ps ──────────────────────────────────────────────────────────────────────
if [[ "$cmd" == "ps" ]]; then
    docker ps --filter name=qzdap- --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
    exit 0
fi

# ── stop ───────────────────────────────────────────────────────────────────
if [[ "$cmd" == "stop" ]]; then
    docker rm -f qzdap-app qzdap-postgres 2>/dev/null || true
    docker network rm qzdap-staging 2>/dev/null || true
    pkill -f 'uvicorn qzdap.composition.main' 2>/dev/null || true
    echo "[run-staging] stopped"
    exit 0
fi

# ── logs ───────────────────────────────────────────────────────────────────
if [[ "$cmd" == "logs" ]]; then
    if [[ "$sub" == "uvicorn" ]]; then
        echo "[run-staging] uvicorn mode logs stream to stdout of the foreground process" >&2
        exit 1
    fi
    docker logs -f qzdap-app
    exit 0
fi

# ── migrate ─────────────────────────────────────────────────────────────────
if [[ "$cmd" == "migrate" ]]; then
    run_migrate
    exit 0
fi

# ── up ──────────────────────────────────────────────────────────────────────

# 0. env file (gitignored)
if [[ ! -f "${REPO_ROOT}/deploy/env.staging" ]]; then
    cp "${REPO_ROOT}/deploy/env.staging.example" "${REPO_ROOT}/deploy/env.staging"
    echo "[run-staging] created deploy/env.staging — review and re-run"
    exit 0
fi

start_postgres

# ── uvicorn mode: app on host ──────────────────────────────────────────────
if [[ "$sub" == "uvicorn" ]]; then
    echo "[run-staging] mode=uvicorn — running alembic + app on host"
    cd "${REPO_ROOT}/backend"
    set -a
    # shellcheck disable=SC1091
    source "${REPO_ROOT}/deploy/env.staging"
    set +a
    # Override DB URL to point at the docker-mapped host port.
    export QZDAP_DATABASE_URL="postgresql+asyncpg://qzdap:qzdap@localhost:${PG_HOST_PORT}/qzdap"
    # Force single-worker uvicorn path.
    export QZDAP_GUNICORN_WORKERS=1
    run_migrate
    exec uv run --frozen --no-dev \
        uvicorn qzdap.composition.main:create_app \
        --factory --host 0.0.0.0 --port "${APP_HOST_PORT}" --reload
fi

# ── docker mode (default) ──────────────────────────────────────────────────
echo "[run-staging] mode=docker — building image"
docker build -t qzdap-app:prod -f "${REPO_ROOT}/infra/docker/Dockerfile.app" "${REPO_ROOT}"

# Single-worker sandbox default for the container's entrypoint path.
# Override by exporting QZDAP_GUNICORN_WORKERS=4 in deploy/env.staging.
if ! grep -q '^QZDAP_GUNICORN_WORKERS=' "${REPO_ROOT}/deploy/env.staging"; then
    echo "QZDAP_GUNICORN_WORKERS=1" >> "${REPO_ROOT}/deploy/env.staging"
fi

docker rm -f qzdap-app 2>/dev/null || true
docker run -d --name qzdap-app --network qzdap-staging \
    --env-file "${REPO_ROOT}/deploy/env.staging" \
    -p "${APP_HOST_PORT}:8102" \
    -p "${METRICS_HOST_PORT}:9102" \
    qzdap-app:prod

wait_for_app
run_migrate

echo
echo "[run-staging] done (mode=docker)."
echo "  live:     http://localhost:${APP_HOST_PORT}"
echo "  metrics:  http://localhost:${METRICS_HOST_PORT}/metrics"
echo "  logs:     ./deploy/run-staging.sh logs"
echo "  teardown: ./deploy/run-staging.sh stop"