#!/usr/bin/env bash
# VISHWAAS Controller start script.
#
# Usage:
#   ./start_controller.sh           — development mode (0.0.0.0, reload, Vite dev server)
#   ./start_controller.sh --prod    — production mode (127.0.0.1, no reload, built frontend)
#
# Production prerequisites:
#   - Set VISHWAAS_ENVIRONMENT=production in backend/.env
#   - Set VISHWAAS_JWT_SECRET to a random secret in backend/.env
#   - Set VISHWAAS_ALLOWED_ORIGINS to your dashboard URL in backend/.env
#   - nginx handles TLS and proxies /api/ to 127.0.0.1:8000 (see nginx.conf)
set -e

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
LOGS="$ROOT/logs"
mkdir -p "$LOGS"

PROD=false
if [[ "${1:-}" == "--prod" ]]; then
  PROD=true
fi

# Backend
cd "$BACKEND"
if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements.txt
fi

if $PROD; then
  BIND_HOST="127.0.0.1"
  RELOAD_FLAG=""
  echo "Starting controller in PRODUCTION mode (bind=127.0.0.1, no reload)"
else
  BIND_HOST="0.0.0.0"
  RELOAD_FLAG="--reload"
  echo "Starting controller in DEVELOPMENT mode (bind=0.0.0.0, reload enabled)"
fi

.venv/bin/python -m uvicorn app.main:app $RELOAD_FLAG --host "$BIND_HOST" --port 8000 --no-access-log \
  2>&1 | tee "$LOGS/backend.log" &
BACKEND_PID=$!

# Frontend
cd "$FRONTEND"
if $PROD; then
  # Build and serve via nginx (this script just builds; nginx serves dist/)
  npm install --silent
  npm run build
  echo "Frontend built to $FRONTEND/dist/ — serve with nginx (see controller/nginx.conf)"
  FRONTEND_PID=""
else
  npm install --silent
  npm run dev 2>&1 | tee "$LOGS/frontend.log" &
  FRONTEND_PID=$!
  echo "Frontend: http://localhost:5173  (PID $FRONTEND_PID)"
fi

echo "Backend:  http://${BIND_HOST}:8000  (PID $BACKEND_PID)"
echo "Logs: controller/logs/  |  Ctrl+C to stop."

cleanup() {
  kill "$BACKEND_PID" ${FRONTEND_PID:-} 2>/dev/null || true
}
trap cleanup INT TERM
wait "$BACKEND_PID"
