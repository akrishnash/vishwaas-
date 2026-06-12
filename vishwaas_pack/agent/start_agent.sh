#!/usr/bin/env bash
# VISHWAAS Agent - start script.
# Self-contained: works from any directory this agent folder is placed on any machine.
# Usage: sudo ./.start_agent
set -e

AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$AGENT_DIR"

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: Run as root: sudo ./.start_agent"
  exit 1
fi

# Validate agent_config.json
python3 - <<'EOF'
import json, sys
from pathlib import Path

path = Path("agent_config.json")
if not path.exists():
    print("ERROR: agent_config.json not found. Copy agent_config.json.example and fill in the required fields.")
    sys.exit(1)
try:
    data = json.load(open(path))
    errors = []
    for key in ("master_url", "master_token", "agent_advertise_url"):
        val = str(data.get(key, "")).strip()
        if not val:
            errors.append(f"{key} is required")
        elif key in ("master_url", "agent_advertise_url") and not val.startswith(("http://", "https://")):
            errors.append(f"{key} must start with http:// or https://")
    if errors:
        print("ERROR: Fix agent_config.json:")
        for e in errors:
            print("  -", e)
        sys.exit(1)
except json.JSONDecodeError as e:
    print("ERROR: agent_config.json is invalid JSON:", e)
    sys.exit(1)
EOF

# Setup venv
if [[ ! -d "venv" ]]; then
  echo "Setting up Python venv..."
  python3 -m venv venv
  venv/bin/pip install --quiet --upgrade pip
  venv/bin/pip install --quiet -r requirements.txt
fi

# Ensure keys dir exists
KEYS_DIR="$(python3 -c "import json; c=json.load(open('agent_config.json')); print(c.get('keys_dir','./keys'))" 2>/dev/null || echo "./keys")"
mkdir -p "$KEYS_DIR"
chmod 700 "$KEYS_DIR"

echo "Starting VISHWAAS agent on :9000"
exec venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 9000
