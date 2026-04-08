#!/usr/bin/env bash
# VISHWAAS Node Agent - install script
# Run as root. Copies agent to /opt/vishwaas-agent, creates venv, installs systemd service.
# Usage: ./install.sh

set -e

INSTALL_DIR="/opt/vishwaas-agent"
SERVICE_NAME="vishwaas-agent"

# Resolve source directory (where install.sh lives)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root (e.g. sudo ./install.sh)"
  exit 1
fi

echo "[1/7] Creating install directory ${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"

echo "[2/7] Copying agent files (app/, agent_config.json, requirements.txt, service file)"
rsync -a --exclude='venv' --exclude='__pycache__' --exclude='*.pyc' \
  "${SCRIPT_DIR}/app" "${INSTALL_DIR}/"
cp "${SCRIPT_DIR}/agent_config.json" "${INSTALL_DIR}/"
cp "${SCRIPT_DIR}/requirements.txt" "${INSTALL_DIR}/"
cp "${SCRIPT_DIR}/vishwaas-agent.service" "${INSTALL_DIR}/"

echo "[3/7] Creating virtual environment and installing dependencies"
if [[ ! -d "${INSTALL_DIR}/venv" ]]; then
  python3 -m venv "${INSTALL_DIR}/venv"
fi
"${INSTALL_DIR}/venv/bin/pip" install --quiet --upgrade pip
"${INSTALL_DIR}/venv/bin/pip" install --quiet -r "${INSTALL_DIR}/requirements.txt"

echo "[4/7] Creating key directory (agent runs as root to manage WireGuard)"
mkdir -p /etc/vishwaas
chmod 700 /etc/vishwaas

echo "[5/7] Setting ownership of install directory (root for agent; keys in /etc/vishwaas if configured)"
chown -R root:root "${INSTALL_DIR}"

echo "[6/7] Installing systemd service"
cp "${INSTALL_DIR}/vishwaas-agent.service" /etc/systemd/system/
systemctl daemon-reload

echo "[7/7] Enabling and starting service"
systemctl enable "${SERVICE_NAME}"
systemctl start "${SERVICE_NAME}"

echo ""
echo "VISHWAAS Agent installed and running."
echo "  Config: ${INSTALL_DIR}/agent_config.json"
echo "  Log:    /var/log/vishwaas-agent.log"
echo "  Status: systemctl status ${SERVICE_NAME}"
echo ""
echo "Edit agent_config.json (master_url, master_token, etc.) then: systemctl restart ${SERVICE_NAME}"
