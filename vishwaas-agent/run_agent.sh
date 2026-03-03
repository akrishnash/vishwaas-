#!/usr/bin/env bash
# Run VISHWAAS Node Agent from this folder.
# - Requires root (sudo) so WireGuard interface and keys can be created.
# - Ensures venv exists and installs dependencies.
# - Starts FastAPI/uvicorn on :9000
# - Logs to ./agent_dev.log
#
# Usage: sudo ./run_agent.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/agent_dev.log"

if [[ $EUID -ne 0 ]]; then
  echo "[run_agent] ERROR: This script must be run as root (WireGuard needs CAP_NET_ADMIN, keys dir must be writable)."
  echo "[run_agent] Run: sudo ./run_agent.sh"
  exit 1
fi

cd "$SCRIPT_DIR"

# If port 9000 is in use (e.g. previous agent), we cannot bind. Tell user to free it.
if command -v ss &>/dev/null; then
  if ss -tlnp 2>/dev/null | grep -q ':9000 '; then
    echo "[run_agent] ERROR: Port 9000 is already in use. Stop the other process first:"
    echo "  sudo pkill -f 'uvicorn app.main:app'"
    echo "  # or: sudo ss -tlnp | grep 9000   then  sudo kill <PID>"
    exit 1
  fi
elif command -v lsof &>/dev/null; then
  if lsof -i :9000 &>/dev/null; then
    echo "[run_agent] ERROR: Port 9000 is already in use. Stop the other process first:"
    echo "  sudo pkill -f 'uvicorn app.main:app'"
    echo "  # or: sudo lsof -i :9000   then  sudo kill <PID>"
    exit 1
  fi
fi

if [[ ! -d "venv" ]]; then
  echo "[run_agent] Creating venv"
  python3 -m venv venv
  venv/bin/pip install --quiet --upgrade pip
  venv/bin/pip install --quiet -r requirements.txt
fi

# Ensure keys dir exists and is writable (agent writes privatekey, publickey, vpn_ip here or to keys_dir from config)
KEYS_DIR="${KEYS_DIR:-./keys}"
if [[ -f agent_config.json ]]; then
  KEYS_DIR="$(python3 -c "
import json
with open('agent_config.json') as f:
    c = json.load(f)
print(c.get('keys_dir', './keys'))
" 2>/dev/null)" || true
fi
mkdir -p "$KEYS_DIR"
chmod 700 "$KEYS_DIR"

echo "[run_agent] Starting agent on :9000 (log: $LOG_FILE)"
exec venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 9000 2>&1 | tee "$LOG_FILE"

