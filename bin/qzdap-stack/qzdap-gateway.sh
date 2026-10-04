#!/usr/bin/env bash
# Wrapper to launch qzdap-gateway.py with the right env.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
source "$HERE/qzdap-env.sh"
exec python3 "$HERE/qzdap-gateway.py"