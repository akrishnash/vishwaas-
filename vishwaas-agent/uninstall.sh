#!/usr/bin/env bash
# VISHWAAS Node Agent - uninstall script
# Run as root. Stops service, removes /opt/vishwaas-agent and systemd unit.
# Does not remove /etc/vishwaas (keys) or log file unless requested.

set -e

INSTALL_DIR="/opt/vishwaas-agent"
SERVICE_NAME="vishwaas-agent"

if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root (e.g. sudo ./uninstall.sh)"
  exit 1
fi

echo "Stopping and disabling service..."
systemctl stop "${SERVICE_NAME}" 2>/dev/null || true
systemctl disable "${SERVICE_NAME}" 2>/dev/null || true

echo "Removing systemd unit..."
rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
systemctl daemon-reload

echo "Removing install directory..."
rm -rf "${INSTALL_DIR}"

echo "Uninstall complete."
echo "  Keys (if any): /etc/vishwaas (kept)"
echo "  Log:           /var/log/vishwaas-agent.log (kept)"
echo "  User:          vishwaas (kept; remove with: userdel vishwaas)"
