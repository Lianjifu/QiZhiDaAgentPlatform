#!/usr/bin/env bash
# Start the QZDAP stack: qzdap-app API + gateway + Vite.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/qzdap-env.sh"
mkdir -p "$QZDAP_LOG_DIR"

REPO="$(cd "$HERE/../.." && pwd)"
log() { printf "[%s] %s\n" "$(date '+%H:%M:%S')" "$*"; }

# Stop existing QZDAP processes (do not touch Partner qzda-app :8100).
"$HERE/stop-qzdap-stack.sh" >/dev/null || true

if [ -f "$REPO/backend/.env.local" ]; then
  set -a
  # shellcheck disable=SC1091
  source "$REPO/backend/.env.local"
  set +a
fi

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

log "starting qzdap-app on :$QZDAP_APP_PORT — log: $QZDAP_LOG_DIR/qzdap-app.log"
QZDAP_SPAWN_LOG="$QZDAP_LOG_DIR/qzdap-app.log" QZDAP_SPAWN_CWD="$REPO/backend" \
  spawn "$QZDAP_LOG_DIR/qzdap-app.pid" \
  uv run uvicorn qzdap.composition.main:create_app --factory \
    --host "$QZDAP_APP_HOST" --port "$QZDAP_APP_PORT"
sleep 3

log "starting qzdap-gateway on :$QZDAP_LISTEN_PORT → :$QZDAP_APP_PORT — log: $QZDAP_LOG_DIR/qzdap-gateway.log"
QZDAP_SPAWN_LOG="$QZDAP_LOG_DIR/qzdap-gateway.log" QZDAP_SPAWN_CWD="$HERE" \
  spawn "$QZDAP_LOG_DIR/qzdap-gateway.pid" bash "$HERE/qzdap-gateway.sh"
sleep 2

log "starting qzdap-vite on :$QZDAP_FRONTEND_PORT (proxy → $QZDAP_VITE_PROXY_TARGET) — log: $QZDAP_LOG_DIR/qzdap-vite.log"
QZDAP_SPAWN_LOG="$QZDAP_LOG_DIR/qzdap-vite.log" QZDAP_SPAWN_CWD="$REPO/frontend/web" \
  spawn "$QZDAP_LOG_DIR/qzdap-vite.pid" \
  pnpm exec vite --port "$QZDAP_FRONTEND_PORT" --host "$QZDAP_FRONTEND_HOST" --strictPort
sleep 4

log "QZDAP stack ready."
echo ""
"$HERE/status-qzdap-stack.sh"
