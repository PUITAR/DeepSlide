#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
NEXT_AI_DRAWIO_DIR="$(cd ../next-ai-draw-io && pwd)"

if [ -d .pids ]; then
  for f in .pids/*.pid; do
    [ -f "$f" ] || continue
    pid="$(cat "$f" || true)"
    if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" || true
    fi
  done
fi

if pgrep -f "uvicorn app.main:app" >/dev/null; then
  pkill -f "uvicorn app.main:app" || true
fi
if pgrep -f "vite" >/dev/null; then
  pkill -f "vite" || true
fi
if pgrep -f "next dev" >/dev/null; then
  while read -r pid; do
    [ -n "${pid:-}" ] || continue
    cwd="$(readlink "/proc/${pid}/cwd" 2>/dev/null || true)"
    if echo "$cwd" | grep -q "${NEXT_AI_DRAWIO_DIR}"; then
      kill "$pid" || true
    fi
  done < <(pgrep -f "next dev" || true)
fi

# ss -ltnp | grep 8001
