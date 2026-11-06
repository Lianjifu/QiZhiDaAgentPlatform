#!/usr/bin/env bash
# QZDAP stack environment. All knobs for this repo use QZDAP_*.
# Source this file before invoking qzdap-gateway.py / Vite / qzdap-app.

export QZDAP_STACK_ROOT="${QZDAP_STACK_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
export QZDAP_LOG_DIR="${QZDAP_LOG_DIR:-$QZDAP_STACK_ROOT/logs}"

# ── Frontend (Vite) ───────────────────────────────────────────────────
export QZDAP_FRONTEND_PORT="${QZDAP_FRONTEND_PORT:-9152}"
export QZDAP_FRONTEND_HOST="${QZDAP_FRONTEND_HOST:-127.0.0.1}"
export QZDAP_VITE_PROXY_TARGET="${QZDAP_VITE_PROXY_TARGET:-http://127.0.0.1:${QZDAP_LISTEN_PORT:-9150}}"

# ── Gateway ───────────────────────────────────────────────────────────
export QZDAP_LISTEN_PORT="${QZDAP_LISTEN_PORT:-9150}"
export QZDAP_BACKEND_HOST="${QZDAP_BACKEND_HOST:-127.0.0.1}"
# Fallback upstream (same process as qzdap-app unless overridden).
export QZDAP_BACKEND_PORT="${QZDAP_BACKEND_PORT:-9151}"

# ── qzdap-app (Python) ────────────────────────────────────────────────
export QZDAP_APP_PORT="${QZDAP_APP_PORT:-9151}"
export QZDAP_APP_HOST="${QZDAP_APP_HOST:-127.0.0.1}"
# Path prefixes the gateway forwards to qzdap-app. Remaining paths also
# go to QZDAP_BACKEND_* (default: the same qzdap-app instance).
export QZDAP_APP_PATH_PREFIXES="${QZDAP_APP_PATH_PREFIXES:-/v1/identity,/api/admin,/api/catalog,/api/sessions,/api/user/skills,/api/user/automations,/api/knowledge}"

# ── Postgres ──────────────────────────────────────────────────────────
export QZDAP_PG_PORT="${QZDAP_PG_PORT:-9153}"
export QZDAP_STACK_DATABASE_URL="${QZDAP_STACK_DATABASE_URL:-postgresql+asyncpg://postgres:postgres@127.0.0.1:${QZDAP_PG_PORT}/qzdap_dev}"
# ── 沙箱运行时（mock sidecar）────────────────────────────────────────
# ⚠️ **沙箱是能力, 不是环境** ✓ —— agent 的 sandbox_exec 工具与 Skill 脚本
# 执行都靠它 ✓。开发环境用仓库自带的 mock sidecar
# (``backend/dev/qzdap_mock_sandbox.py`` ✓) —— 本地起子进程跑 python ✓。
export QZDAP_SANDBOX_PORT="${QZDAP_SANDBOX_PORT:-9158}"

# Redis —— 开发用 db 0.
export QZDAP_REDIS_PORT="${QZDAP_REDIS_PORT:-9154}"
