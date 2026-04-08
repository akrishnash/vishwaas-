#!/usr/bin/env bash
# Deploy VISHWAAS agent to a remote machine from the controller machine.
#
# Usage:
#   ./deploy-agent.sh <user@host> [node_name]
#
# Examples:
#   ./deploy-agent.sh root@192.168.1.50
#   ./deploy-agent.sh ubuntu@192.168.1.50 edge-node-1
#
# What it does:
#   1. Reads VISHWAAS_AGENT_TOKEN from controller/backend/.env (auto-fills master_token)
#   2. Copies agent/ to the remote machine at /opt/vishwaas-agent
#   3. Writes agent_config.json with master_url, master_token, agent_advertise_url already filled in
#   4. Installs and starts the agent as a systemd service (via install.sh)
#
# Requirements:
#   - SSH access to the target machine (key-based recommended)
#   - Python 3.8+ and WireGuard tools on the target machine
#   - The controller must be reachable from the target machine on the configured port

set -euo pipefail

# ---- Args ----
if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <user@host> [node_name]"
  echo "  user@host  — SSH target (e.g. root@192.168.1.50 or ubuntu@my-server)"
  echo "  node_name  — optional name shown in dashboard (default: hostname of target machine)"
  exit 1
fi

SSH_TARGET="$1"
NODE_NAME="${2:-auto}"   # "auto" → agent uses hostname of the target machine

# ---- Paths ----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_DIR="$SCRIPT_DIR/agent"
ENV_FILE="$SCRIPT_DIR/controller/backend/.env"

# ---- Read controller config ----
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: controller/.env not found at $ENV_FILE"
  echo "       Copy controller/backend/.env.example to controller/backend/.env and fill in VISHWAAS_AGENT_TOKEN."
  exit 1
fi

AGENT_TOKEN="$(grep -E '^VISHWAAS_AGENT_TOKEN=' "$ENV_FILE" | cut -d= -f2- | tr -d '[:space:]')"
if [[ -z "$AGENT_TOKEN" || "$AGENT_TOKEN" == "your-secret-token-here" ]]; then
  echo "ERROR: VISHWAAS_AGENT_TOKEN is not set or still has the placeholder value in $ENV_FILE"
  echo "       Generate one: openssl rand -hex 32"
  exit 1
fi

# ---- Detect controller's outbound IP (used as master_url base if not overridden) ----
# You can override this by setting VISHWAAS_CONTROLLER_URL before running this script.
# e.g.: VISHWAAS_CONTROLLER_URL=https://dashboard.example.com ./deploy-agent.sh root@...
if [[ -n "${VISHWAAS_CONTROLLER_URL:-}" ]]; then
  CONTROLLER_URL="$VISHWAAS_CONTROLLER_URL"
else
  # Try to read from .env
  CONTROLLER_URL="$(grep -E '^VISHWAAS_MASTER_URL=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d '[:space:]')" || true
  if [[ -z "$CONTROLLER_URL" ]]; then
    # Auto-detect: use the IP of the interface that routes to the target host
    TARGET_HOST="${SSH_TARGET##*@}"
    CONTROLLER_IP="$(python3 -c "
import socket
try:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(('$TARGET_HOST', 80))
    print(s.getsockname()[0])
    s.close()
except Exception:
    print('')
" 2>/dev/null)"
    CONTROLLER_URL="http://${CONTROLLER_IP}:8000"
    echo "INFO: Auto-detected controller URL as $CONTROLLER_URL"
    echo "      Override with: VISHWAAS_CONTROLLER_URL=http://your-ip:8000 $0 $*"
  fi
fi

# ---- Detect target machine's IP for agent_advertise_url ----
TARGET_IP="$(ssh -o ConnectTimeout=10 -o BatchMode=yes "$SSH_TARGET" \
  "python3 -c \"import socket; s=socket.socket(); s.connect(('8.8.8.8',53)); print(s.getsockname()[0]); s.close()\" 2>/dev/null || hostname -I | awk '{print \$1}'")"

if [[ -z "$TARGET_IP" ]]; then
  echo "ERROR: Could not detect target machine IP. Set it manually in agent_config.json after deploy."
  TARGET_IP="REPLACE_WITH_THIS_MACHINE_IP"
fi

AGENT_ADVERTISE_URL="http://${TARGET_IP}:9000"

echo ""
echo "Deploying VISHWAAS agent:"
echo "  Target machine : $SSH_TARGET"
echo "  Node name      : $NODE_NAME"
echo "  Controller URL : $CONTROLLER_URL"
echo "  Agent URL      : $AGENT_ADVERTISE_URL"
echo ""

# ---- Copy agent files to remote ----
echo "[1/4] Copying agent files to $SSH_TARGET:/opt/vishwaas-agent ..."
ssh -o ConnectTimeout=10 "$SSH_TARGET" "mkdir -p /opt/vishwaas-agent"
rsync -az --delete \
  --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' \
  --exclude='keys' --exclude='*.json' \
  "$AGENT_DIR/" "$SSH_TARGET:/opt/vishwaas-agent/"

# ---- Write agent_config.json directly on remote (no manual editing needed) ----
echo "[2/4] Writing agent_config.json ..."
ssh "$SSH_TARGET" bash <<EOF
cat > /opt/vishwaas-agent/agent_config.json <<'CONF'
{
  "node_name": "${NODE_NAME}",
  "master_url": "${CONTROLLER_URL}",
  "master_token": "${AGENT_TOKEN}",
  "agent_advertise_url": "${AGENT_ADVERTISE_URL}",
  "wg_interface": "wg0",
  "listen_port": 51820,
  "subnet": "10.10.10.0/24",
  "keys_dir": "/etc/vishwaas",
  "agent_bind_host": "0.0.0.0",
  "agent_port": 9000,
  "use_tpm_wg_key": false,
  "tpm_nv_index_wg": 1
}
CONF
chmod 600 /opt/vishwaas-agent/agent_config.json
echo "  agent_config.json written."
EOF

# ---- Install Python venv and dependencies ----
echo "[3/4] Installing Python dependencies on remote ..."
ssh "$SSH_TARGET" bash <<'EOF'
cd /opt/vishwaas-agent
if [[ ! -d venv ]]; then
  python3 -m venv venv
fi
venv/bin/pip install --quiet --upgrade pip
venv/bin/pip install --quiet -r requirements.txt
EOF

# ---- Install systemd service ----
echo "[4/4] Installing systemd service ..."
ssh "$SSH_TARGET" bash <<'EOF'
cp /opt/vishwaas-agent/vishwaas-agent.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable vishwaas-agent
systemctl restart vishwaas-agent
sleep 2
systemctl is-active vishwaas-agent && echo "  Service is running." || echo "  WARNING: service may not have started; check: journalctl -u vishwaas-agent -n 30"
EOF

echo ""
echo "Done. Agent deployed to $SSH_TARGET."
echo ""
echo "The agent is now sending a join request to the controller."
echo "Approve it at: $CONTROLLER_URL  (Dashboard → Join Requests)"
echo ""
echo "To check agent logs:  ssh $SSH_TARGET journalctl -u vishwaas-agent -f"
echo "To redeploy later:    $0 $SSH_TARGET $NODE_NAME"
