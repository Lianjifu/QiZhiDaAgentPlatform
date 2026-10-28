#!/usr/bin/env bash
# 启动**演示环境** —— 与开发环境完全分开的另一套后端实例 + 另一个库.
#
#   开发: qzdap-dev  实例 (:9151) → qzdap_dev  库
#   演示: qzdap-demo 实例 (:9161) → qzdap_demo 库
#
# 演示前端跑在 :9162, VITE_QZDAP_ENV=demo, 代理指向 demo 实例 ——
# **前端代码跟开发环境是同一套**, 只有后端实例和库不同. 这正是"演示数据
# 与真实 API 对齐"的落地方式: 没有第二份手写的数据.
#
# 首次跑会: 建 demo 库 → 跑迁移 → 种演示数据 → 起 demo 后端 → 起演示前端.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/qzdap-env.sh"
mkdir -p "$QZDAP_LOG_DIR"

REPO="$(cd "$HERE/../.." && pwd)"
log() { printf "[%s] %s\n" "$(date '+%H:%M:%S')" "$*"; }

log "waiting for postgres on :$QZDAP_PG_PORT to accept connections"
pg_ready=0
for _ in $(seq 1 30); do
  if nc -z 127.0.0.1 "$QZDAP_PG_PORT" 2>/dev/null; then pg_ready=1; break; fi
  sleep 1
done
if [ "$pg_ready" = 1 ]; then
  log "postgres is accepting connections"
else
  log "WARN: postgres not reachable after 30s — demo stack will likely fail to start"
fi

# ── demo 库: 建库 → 迁移 → 种演示数据 ────────────────────────────────
# 三步都是幂等的, 重复跑不会把演示数据搞乱.
log "ensuring demo database exists: $QZDAP_DEMO_DATABASE_URL"
(cd "$REPO/backend" && uv run python scripts/ensure_database.py --url "$QZDAP_DEMO_DATABASE_URL")

log "applying migrations to the demo database"
(cd "$REPO/backend" && QZDAP_DATABASE_URL="$QZDAP_DEMO_DATABASE_URL" \
  uv run alembic -c migrations/alembic.ini upgrade head)

log "seeding demo data (demo tenant + demo accounts + built-in tools)"
(cd "$REPO/backend" && QZDAP_ENV=demo QZDAP_DATABASE_URL="$QZDAP_DEMO_DATABASE_URL" \
  uv run python scripts/seed_demo_data.py)

spawn() {
  local pidfile="$1"
  shift
  python3 - "$pidfile" "$@" <<'PY'
import os, subprocess, sys
pidfile = sys.argv[1]
cmd = sys.argv[2:]
log_path = os.environ["QZDAP_SPAWN_LOG"]
cwd = os.environ.get("QZDAP_SPAWN_CWD") or None
os.makedirs(os.path.dirname(log_path), exist_ok=True)
with open(log_path, "ab") as log:
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        env=os.environ.copy(),
    )
with open(pidfile, "w", encoding="utf-8") as handle:
    handle.write(str(proc.pid))
PY
}

log "starting qzdap-app (demo) on :$QZDAP_DEMO_APP_PORT → $QZDAP_DEMO_DATABASE_URL — log: $QZDAP_LOG_DIR/qzdap-demo-app.log"
QZDAP_ENV=demo \
QZDAP_DATABASE_URL="$QZDAP_DEMO_DATABASE_URL" \
QZDAP_REDIS_URL="$QZDAP_DEMO_REDIS_URL" \
QZDAP_EVENT_REDIS_STREAM_PREFIX="$QZDAP_DEMO_EVENT_REDIS_STREAM_PREFIX" \
QZDAP_EVENT_REDIS_DLQ_STREAM="$QZDAP_DEMO_EVENT_REDIS_DLQ_STREAM" \
QZDAP_SPAWN_LOG="$QZDAP_LOG_DIR/qzdap-demo-app.log" QZDAP_SPAWN_CWD="$REPO/backend" \
  spawn "$QZDAP_LOG_DIR/qzdap-demo-app.pid" \
    uv run uvicorn qzdap.composition.main:create_app --factory \
      --host "$QZDAP_DEMO_APP_HOST" --port "$QZDAP_DEMO_APP_PORT"
sleep 3

log "starting qzdap-vite (demo) on :$QZDAP_DEMO_FRONTEND_PORT (proxy → $QZDAP_DEMO_VITE_PROXY_TARGET) — log: $QZDAP_LOG_DIR/qzdap-demo-vite.log"
VITE_QZDAP_ENV=demo \
QZDAP_VITE_PROXY_TARGET="$QZDAP_DEMO_VITE_PROXY_TARGET" \
QZDAP_SPAWN_LOG="$QZDAP_LOG_DIR/qzdap-demo-vite.log" QZDAP_SPAWN_CWD="$REPO/frontend/web" \
  spawn "$QZDAP_LOG_DIR/qzdap-demo-vite.pid" \
    pnpm exec vite --port "$QZDAP_DEMO_FRONTEND_PORT" --host "$QZDAP_FRONTEND_HOST" --strictPort
sleep 4

log "QZDAP demo stack ready → http://$QZDAP_FRONTEND_HOST:$QZDAP_DEMO_FRONTEND_PORT"
echo ""
echo "demo accounts (see backend/composition/.../settings.py for the password):"
echo "  admin@acme.com  (admin)"
echo "  user@acme.com   (member)"
