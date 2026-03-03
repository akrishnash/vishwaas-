#!/usr/bin/env bash
# Run this on the agent machine to check if the controller is reachable.
# Usage: ./test-controller-reach.sh

set -e
cd "$(dirname "$0")"

echo "=== Agent machine ==="
echo "Hostname: $(hostname)"
echo ""

if [[ ! -f agent_config.json ]]; then
  echo "ERROR: agent_config.json not found in $(pwd)"
  exit 1
fi

MASTER_URL=$(python3 -c "
import json
with open('agent_config.json') as f:
    c = json.load(f)
print(c.get('master_url', '') or '(not set)')
")
echo "master_url from agent_config.json: $MASTER_URL"
echo ""

if [[ -z "$MASTER_URL" || "$MASTER_URL" == "(not set)" ]]; then
  echo "ERROR: Set master_url in agent_config.json to the controller address (e.g. http://192.168.10.15:8000)"
  exit 1
fi

echo "Testing connectivity to controller..."
if curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 "$MASTER_URL/" 2>/dev/null | grep -q 200; then
  echo "OK: Controller at $MASTER_URL is reachable (HTTP 200)."
else
  echo "FAIL: Cannot reach $MASTER_URL from this machine."
  echo "Check:"
  echo "  1. Controller is running: on the controller machine run: uvicorn app.main:app --host 0.0.0.0 --port 8000"
  echo "  2. Firewall on controller allows port 8000 (e.g. sudo ufw allow 8000)"
  echo "  3. master_url is correct for this network (controller IP as seen from here)"
  exit 1
fi
