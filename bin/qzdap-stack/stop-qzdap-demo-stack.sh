#!/usr/bin/env bash
# Stop the **demo** QZDAP stack (demo backend + demo frontend).
# Deliberately separate from stop-qzdap-stack.sh — 开发栈和演示栈互不影响.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/qzdap-env.sh"

stopped=0
for name in qzdap-demo-vite qzdap-demo-app; do
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

# 也清掉占用演示端口的残留进程 (pidfile 过期的情况)
for p in "$QZDAP_DEMO_FRONTEND_PORT" "$QZDAP_DEMO_APP_PORT"; do
  pids=$(lsof -tiTCP:"$p" -sTCP:LISTEN 2>/dev/null || true)
  for pid in $pids; do
    if kill -0 "$pid" 2>/dev/null; then
      cmdline=$(ps -p "$pid" -o command= 2>/dev/null || true)
      if [[ "$cmdline" == *qzdap.composition* ]] || [[ "$cmdline" == *"vite.js"* && "$cmdline" == *"--port $QZDAP_DEMO_FRONTEND_PORT"* ]]; then
        echo "stopping port :$p occupant (pid=$pid)"
        kill "$pid" 2>/dev/null || true
        stopped=$((stopped+1))
      fi
    fi
  done
done

echo "stopped $stopped demo process(es)"
sleep 1
