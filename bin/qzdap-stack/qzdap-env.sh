#!/usr/bin/env bash
# QZDAP stack environment. All knobs for this repo use QZDAP_*.
# Source this file before invoking qzdap-gateway.py / Vite / qzdap-app.

export QZDAP_STACK_ROOT="${QZDAP_STACK_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
export QZDAP_LOG_DIR="${QZDAP_LOG_DIR:-$QZDAP_STACK_ROOT/logs}"

# ── Frontend (Vite) ───────────────────────────────────────────────────
export QZDAP_FRONTEND_PORT="${QZDAP_FRONTEND_PORT:-5200}"
export QZDAP_FRONTEND_HOST="${QZDAP_FRONTEND_HOST:-127.0.0.1}"
export QZDAP_VITE_PROXY_TARGET="${QZDAP_VITE_PROXY_TARGET:-http://127.0.0.1:${QZDAP_LISTEN_PORT:-9200}}"

# ── Gateway ───────────────────────────────────────────────────────────
export QZDAP_LISTEN_PORT="${QZDAP_LISTEN_PORT:-9200}"
export QZDAP_BACKEND_HOST="${QZDAP_BACKEND_HOST:-127.0.0.1}"
# Fallback upstream (same process as qzdap-app unless overridden).
export QZDAP_BACKEND_PORT="${QZDAP_BACKEND_PORT:-8200}"

# ── qzdap-app (Python) ────────────────────────────────────────────────
export QZDAP_APP_PORT="${QZDAP_APP_PORT:-8200}"
export QZDAP_APP_HOST="${QZDAP_APP_HOST:-127.0.0.1}"
# Path prefixes the gateway forwards to qzdap-app. Remaining paths also
# go to QZDAP_BACKEND_* (default: the same qzdap-app instance).
export QZDAP_APP_PATH_PREFIXES="${QZDAP_APP_PATH_PREFIXES:-/v1/identity,/api/admin,/api/catalog,/api/sessions,/api/user/skills,/api/user/automations,/api/knowledge}"

# ── Postgres ──────────────────────────────────────────────────────────
export QZDAP_PG_PORT="${QZDAP_PG_PORT:-5434}"
export QZDAP_STACK_DATABASE_URL="${QZDAP_STACK_DATABASE_URL:-postgresql+asyncpg://postgres:postgres@127.0.0.1:${QZDAP_PG_PORT}/qzdap_dev}"
