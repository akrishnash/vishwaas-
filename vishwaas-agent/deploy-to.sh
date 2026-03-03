#!/usr/bin/env bash
# Copy this agent (including TPM support) to a remote host. Run as your user (no sudo).
# Usage: ./deploy-to.sh [user@]host [remote-path]
# Example: ./deploy-to.sh cloneanurag@192.168.10.16
#          ./deploy-to.sh cloneanurag@192.168.10.16 ~/codex/vishwaas-agent
#
# Target 192.168.10.16 (user cloneanurag):
#   ./deploy-to.sh cloneanurag@192.168.10.16 ~/codex/vishwaas-agent
# Then on the remote: cd ~/codex/vishwaas-agent && sudo ./install.sh

set -e
TARGET="${1:?Usage: $0 [user@]host [remote-path]}"
REMOTE_PATH="${2:-~/codex/vishwaas-agent}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
rsync -avz --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' --exclude='keys' \
  -e ssh \
  "$SCRIPT_DIR/" \
  "$TARGET:$REMOTE_PATH/"
echo ""
echo "Done. On the remote ($TARGET) run:"
echo "  cd $REMOTE_PATH"
echo "  # Ensure agent_config.json: master_url, master_token, agent_advertise_url"
echo "  sudo ./install.sh"
echo "  # Or run manually: sudo ./venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 9000"
