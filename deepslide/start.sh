#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
ROOT_DIR="$(pwd)"

if [ -f "${ROOT_DIR}/stop.sh" ]; then
  bash "${ROOT_DIR}/stop.sh" || true
fi

set -a
if [ -f .env ]; then
  . .env
fi
set +a

mkdir -p .pids

BACKEND_PORT="${BACKEND_PORT:-8001}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
NEXT_AI_DRAWIO_PORT="${NEXT_AI_DRAWIO_PORT:-6002}"
AI_PROVIDER="${AI_PROVIDER:-${DEFAULT_MODEL_PLATFORM_TYPE:-openai}}"
AI_MODEL="${AI_MODEL:-${DEFAULT_MODEL_TYPE:-}}"
OPENAI_API_KEY="${OPENAI_API_KEY:-${DEFAULT_MODEL_API_KEY:-}}"
OPENAI_BASE_URL="${OPENAI_BASE_URL:-${DEFAULT_MODEL_API_URL:-}}"

echo "Starting next-ai-draw-io on :${NEXT_AI_DRAWIO_PORT}..."
(cd ../next-ai-draw-io && \
  DISABLE_OPENNEXT_CLOUDFLARE_DEV="${DISABLE_OPENNEXT_CLOUDFLARE_DEV:-1}" \
  NEXT_TELEMETRY_DISABLED=1 \
  AI_PROVIDER="${AI_PROVIDER}" \
  AI_MODEL="${AI_MODEL}" \
  OPENAI_API_KEY="${OPENAI_API_KEY}" \
  OPENAI_BASE_URL="${OPENAI_BASE_URL}" \
  WATCHPACK_POLLING=true \
  CHOKIDAR_USEPOLLING=1 \
  PORT="${NEXT_AI_DRAWIO_PORT}" \
  ./node_modules/.bin/next dev --webpack --port "${NEXT_AI_DRAWIO_PORT}" --hostname 0.0.0.0 & \
  echo $! > "${ROOT_DIR}/.pids/next_ai_drawio.pid")

echo "Starting backend on :${BACKEND_PORT}..."
BACKEND_RUN=()
if [ -x "${ROOT_DIR}/backend/.venv/bin/python" ]; then
  BACKEND_RUN=("${ROOT_DIR}/backend/.venv/bin/python" "-m" "uvicorn" "app.main:app")
elif [ -x "${ROOT_DIR}/backend/.venv/bin/uvicorn" ]; then
  BACKEND_RUN=("${ROOT_DIR}/backend/.venv/bin/uvicorn" "app.main:app")
else
  BACKEND_RUN=("uvicorn" "app.main:app")
fi

(cd backend && "${BACKEND_RUN[@]}" --host 0.0.0.0 --port "${BACKEND_PORT}" & echo $! > "${ROOT_DIR}/.pids/backend.pid")

echo "Starting frontend on :${FRONTEND_PORT}..."
(cd frontend && npm run dev -- --host 0.0.0.0 --port "${FRONTEND_PORT}" & echo $! > "${ROOT_DIR}/.pids/frontend.pid")

echo "All services started."
