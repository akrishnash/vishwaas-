#!/usr/bin/env bash
# VISHWAAS Controller — start script.
# Run setup.sh first if this is a fresh install.
# Usage: ./start_controller.sh
set -e

CONTROLLER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$CONTROLLER_DIR/backend"
VENV="$BACKEND/.venv"
LOGS="$CONTROLLER_DIR/logs"
mkdir -p "$LOGS"

# Validate venv
[[ -x "$VENV/bin/python" ]] || { echo "ERROR: venv not found at $VENV. Run setup.sh first."; exit 1; }
"$VENV/bin/python" -c "import uvicorn" 2>/dev/null || { echo "ERROR: uvicorn missing. Re-run setup.sh."; exit 1; }

# Validate .env
[[ -f "$BACKEND/.env" ]] || { echo "ERROR: $BACKEND/.env not found. Run setup.sh first."; exit 1; }

echo "Starting VISHWAAS Controller..."
echo "  API:       http://0.0.0.0:8000"
echo "  Dashboard: http://$(hostname -I | awk '{print $1}')/"
echo "  Logs:      $LOGS/backend.log"
echo "  Ctrl+C to stop."
echo ""

cd "$BACKEND"
exec "$VENV/bin/python" -m uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 --no-access-log \
    2>&1 | tee "$LOGS/backend.log"
