#!/usr/bin/env bash
# Stop all QZDAP stack processes.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/qzdap-env.sh"

stopped=0
for name in qzdap-gateway qzdap-vite qzdap-app; do
  pidfile="$QZDAP_LOG_DIR/$name.pid"
  if [ -f "$pidfile" ]; then
    pid=$(cat "$pidfile")
    if kill -0 "$pid" 2>/dev/null; then
      echo "stopping $name (pid=$pid)"
      kill "$pid" 2>/dev/null || true
      stopped=$((stopped+1))
    fi
    rm -f "$pidfile"
  fi
done

# also kill anything listening on QZDAP ports (in case pidfile is stale)
for p in "$QZDAP_FRONTEND_PORT" "$QZDAP_LISTEN_PORT" "$QZDAP_APP_PORT"; do
  pids=$(lsof -tiTCP:"$p" -sTCP:LISTEN 2>/dev/null || true)
  for pid in $pids; do
    if kill -0 "$pid" 2>/dev/null; then
      cmdline=$(ps -p "$pid" -o command= 2>/dev/null || true)
      if [[ "$cmdline" == *qzdap-* ]] || [[ "$cmdline" == *qzdap.composition* ]] || [[ "$cmdline" == *"vite.js"* && "$cmdline" == *"--port $QZDAP_FRONTEND_PORT"* ]]; then
        echo "stopping port :$p occupant (pid=$pid)"
        kill "$pid" 2>/dev/null || true
        stopped=$((stopped+1))
      fi
    fi
  done
done

echo "stopped $stopped process(es)"
sleep 1