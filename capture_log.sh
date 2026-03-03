#!/usr/bin/env bash
# Capture VISHWAAS logs into a time-stamped archive under ./logs/.
# Collects:
# - logs/backend.log          (run_controller.sh backend output)
# - logs/frontend.log         (run_controller.sh frontend output)
# - vishwaas-agent/agent_dev.log (run_agent.sh output, if used)
# - /var/log/vishwaas-agent.log  (systemd agent, if present)

set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="$ROOT_DIR/logs"
mkdir -p "$OUT_DIR"

TS="$(date +%Y%m%d_%H%M%S)"
ARCHIVE="$OUT_DIR/vishwaas_logs_$TS.tar.gz"

FILES=()

add_if_exists() {
  if [[ -f "$1" ]]; then
    FILES+=("$1")
  fi
}

add_if_exists "$ROOT_DIR/logs/backend.log"
add_if_exists "$ROOT_DIR/logs/frontend.log"
add_if_exists "$ROOT_DIR/vishwaas-agent/agent_dev.log"
add_if_exists "/var/log/vishwaas-agent.log"

if [[ ${#FILES[@]} -eq 0 ]]; then
  echo "[capture_log] No known log files found."
  exit 0
fi

echo "[capture_log] Archiving logs to $ARCHIVE"
tar -czf "$ARCHIVE" "${FILES[@]}"

echo "[capture_log] Included:"
for f in "${FILES[@]}"; do
  echo "  - $f"
done
echo "[capture_log] Done."

