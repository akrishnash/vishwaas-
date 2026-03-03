#!/usr/bin/env bash
# Run VISHWAAS controller (backend + frontend) from the repo root.
# - Starts backend (FastAPI/uvicorn) on :8000
# - Starts frontend (Vite) on :3000
# - Writes logs to ./logs/backend.log and ./logs/frontend.log

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT_DIR/logs"
mkdir -p "$LOG_DIR"

BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

echo "[run_controller] Root: $ROOT_DIR"
echo "[run_controller] Logs: $LOG_DIR"

###############################################################################
# Backend
###############################################################################

cd "$BACKEND_DIR"

if [[ ! -d ".venv" ]]; then
  echo "[run_controller] Creating backend venv (.venv)"
  python -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r requirements.txt
fi

echo "[run_controller] Starting backend on :8000"
(
  .venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 \
    2>&1 | tee "$LOG_DIR/backend.log"
) &
BACKEND_PID=$!

###############################################################################
# Frontend
###############################################################################

cd "$FRONTEND_DIR"

echo "[run_controller] Installing frontend deps (npm install)"
npm install >/dev/null 2>&1 || {
  echo "[run_controller] npm install failed"
  kill "$BACKEND_PID" 2>/dev/null || true
  exit 1
}

echo "[run_controller] Starting frontend on :3000"
(
  npm run dev \
    2>&1 | tee "$LOG_DIR/frontend.log"
) &
FRONTEND_PID=$!

echo "[run_controller] Backend PID:  $BACKEND_PID"
echo "[run_controller] Frontend PID: $FRONTEND_PID"
echo "[run_controller] Press Ctrl+C to stop both."

cleanup() {
  echo "[run_controller] Stopping..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}

trap cleanup INT TERM

wait

