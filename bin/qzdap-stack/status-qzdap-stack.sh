#!/usr/bin/env bash
# Show QZDAP stack status.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/qzdap-env.sh"

echo "── QZDAP stack status ──"
echo "QZDAP_STACK_ROOT=$QZDAP_STACK_ROOT"
echo "QZDAP_LOG_DIR=$QZDAP_LOG_DIR"
echo ""

printf "%-15s %-7s %-9s %s\n" "service" "port" "status" "pid"
printf "%-15s %-7s %-9s %s\n" "-------" "----" "------" "---"

check() {
  local name="$1"
  local port="$2"
  local pidfile="$QZDAP_LOG_DIR/$name.pid"
  local status="DOWN" pid="-"
  if [ -f "$pidfile" ]; then
    pid=$(cat "$pidfile")
    if kill -0 "$pid" 2>/dev/null; then status="UP"; fi
  fi
  if [ "$status" = "DOWN" ]; then
    local live
    live=$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null | head -1 || true)
    if [ -n "$live" ]; then status="UP*"; pid="$live"; fi
  fi
  printf "%-15s %-7s %-9s %s\n" "$name" "$port" "$status" "$pid"
}

check qzdap-gateway "$QZDAP_LISTEN_PORT"
check qzdap-vite     "$QZDAP_FRONTEND_PORT"
check qzdap-app      "$QZDAP_APP_PORT"

echo ""
echo "── Health checks ──"
for u in \
  "http://127.0.0.1:$QZDAP_FRONTEND_PORT/" \
  "http://127.0.0.1:$QZDAP_LISTEN_PORT/healthz" \
  "http://127.0.0.1:$QZDAP_LISTEN_PORT/readyz" \
  "http://127.0.0.1:$QZDAP_LISTEN_PORT/api/auth/me"; do
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$u" 2>/dev/null || echo "ERR")
  printf "  %-60s → %s\n" "$u" "$code"
done