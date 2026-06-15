#!/usr/bin/env bash
# VISHWAAS Agent — start script.
# Run setup.sh first if this is a fresh install.
# Usage: sudo ./start_agent.sh
set -e

AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$AGENT_DIR/venv"

[[ $EUID -ne 0 ]] && { echo "ERROR: Run as root: sudo ./start_agent.sh"; exit 1; }

# Validate venv
[[ -x "$VENV/bin/python" ]] || { echo "ERROR: venv not found at $VENV. Run setup.sh first."; exit 1; }
"$VENV/bin/python" -c "import uvicorn" 2>/dev/null || { echo "ERROR: uvicorn missing. Re-run setup.sh."; exit 1; }

# Validate config
[[ -f "$AGENT_DIR/agent_config.json" ]] || {
    echo "ERROR: agent_config.json not found."
    echo "  cp $AGENT_DIR/agent_config.json.example $AGENT_DIR/agent_config.json"
    echo "  Then fill in master_url, master_token, agent_advertise_url"
    exit 1
}

# Quick config validation
"$VENV/bin/python" - <<'EOF'
import json, sys
data = json.load(open("agent_config.json"))
errors = []
for key in ("master_url", "master_token", "agent_advertise_url"):
    val = str(data.get(key, "")).strip()
    if not val:
        errors.append(f"{key} is required")
    elif key in ("master_url", "agent_advertise_url") and not val.startswith(("http://", "https://")):
        errors.append(f"{key} must start with http:// or https://")
if errors:
    print("ERROR: Fix agent_config.json:")
    [print(f"  - {e}") for e in errors]
    sys.exit(1)
EOF

# Keys dir
KEYS_DIR="$("$VENV/bin/python" -c "import json; c=json.load(open('agent_config.json')); print(c.get('keys_dir','./keys'))")"
mkdir -p "$KEYS_DIR" && chmod 700 "$KEYS_DIR"

echo "Starting VISHWAAS Agent on :9000..."
cd "$AGENT_DIR"
exec "$VENV/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port 9000
