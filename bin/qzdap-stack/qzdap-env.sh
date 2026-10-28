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
# Redis —— 开发用 db 0, 演示用 db 1 (同一个实例, 不同库, 互不干扰).
export QZDAP_REDIS_PORT="${QZDAP_REDIS_PORT:-9154}"

# ── 演示环境 (demo) ────────────────────────────────────────────────────
# 演示跑的是**另一个后端实例 + 另一个库** —— 演示数据和开发数据彻底分开:
#   开发: qzdap-dev 实例 → qzdap_dev 库
#   演示: qzdap-demo 实例 → qzdap_demo 库
# 前端只要把 VITE_QZDAP_ENV 设成 demo, 并把 Vite 代理指向 demo 实例即可.
export QZDAP_DEMO_APP_PORT="${QZDAP_DEMO_APP_PORT:-9161}"
export QZDAP_DEMO_APP_HOST="${QZDAP_DEMO_APP_HOST:-127.0.0.1}"
export QZDAP_DEMO_DATABASE_URL="${QZDAP_DEMO_DATABASE_URL:-postgresql+asyncpg://postgres:postgres@127.0.0.1:${QZDAP_PG_PORT}/qzdap_demo}"
# 演示实例同样需要 Redis (事件总线 / 限流). 跟开发共用一个 Redis 实例,
# 但用不同的 key 前缀, 免得两边的消息串.
export QZDAP_DEMO_REDIS_URL="${QZDAP_DEMO_REDIS_URL:-redis://127.0.0.1:${QZDAP_REDIS_PORT:-9154}/1}"
export QZDAP_DEMO_EVENT_REDIS_STREAM_PREFIX="${QZDAP_DEMO_EVENT_REDIS_STREAM_PREFIX:-qzdap:events:demo:}"
export QZDAP_DEMO_EVENT_REDIS_DLQ_STREAM="${QZDAP_DEMO_EVENT_REDIS_DLQ_STREAM:-qzdap:events:demo:dlq}"
# 演示前端: VITE_QZDAP_ENV=demo + 代理指向 demo 实例
export QZDAP_DEMO_FRONTEND_PORT="${QZDAP_DEMO_FRONTEND_PORT:-9162}"
export QZDAP_DEMO_VITE_PROXY_TARGET="${QZDAP_DEMO_VITE_PROXY_TARGET:-http://127.0.0.1:${QZDAP_DEMO_APP_PORT}}"
