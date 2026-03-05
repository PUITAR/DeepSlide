#!/usr/bin/env bash
set -euo pipefail

# 1. Stop processes
kill_if_exist() {
  local name="$1"
  if pgrep -f "$name" >/dev/null; then
    echo "Stopping $name..."
    pkill -f "$name" || true
  fi
}

echo "Stopping services..."

# Kill by PID files if they exist
if [ -d .pids ]; then
    for f in .pids/*.pid; do
      [ -f "$f" ] || continue
      pid="$(cat "$f" || true)"
      if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid" || true
      fi
    done
fi

# Fallback kill by name
kill_if_exist "uvicorn app.main:app"
# Be careful with 'node', only kill vite dev server if possible, but for dev env:
# pkill -f "vite" might be safer
if pgrep -f "vite" >/dev/null; then
    pkill -f "vite" || true
fi
if pgrep -f "tools/drawio-viewer/server.mjs" >/dev/null; then
    pkill -f "tools/drawio-viewer/server.mjs" || true
fi

# 2. Clear Cache and Temp Files
echo "Cleaning cache and temporary files..."

# Backend caches
rm -rf backend/__pycache__
rm -rf backend/app/__pycache__
rm -rf backend/app/services/__pycache__
rm -rf backend/app/services/core/__pycache__

# Project uploads and outputs (Adjust paths as needed)
# Assuming typical DeepSlide structure
rm -rf uploads/*
rm -rf projects/*
rm -rf storage/*
rm -rf backend/context_files/*
rm -rf backend/storage/asr_uploads/*
rm -rf backend/storage/voice_clones/*


# Logs
rm -f backend.log frontend.log

# PID files
rm -rf .pids

# Frontend caches (optional, node_modules/.vite)
# rm -rf frontend/node_modules/.vite

echo "All services stopped and caches cleaned."
