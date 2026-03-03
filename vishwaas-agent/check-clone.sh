#!/usr/bin/env bash
# Run this ON THE CLONE to see why it might not get a VPN IP.
# Usage: sudo ./check-clone.sh

set -e
echo "=== 1. Service running as? (should be root) ==="
systemctl show vishwaas-agent --property=User --value 2>/dev/null || true
echo ""
echo "=== 2. Last 25 agent log lines ==="
journalctl -u vishwaas-agent -n 25 --no-pager 2>/dev/null || tail -25 /var/log/vishwaas-agent.log 2>/dev/null || echo "No log found"
echo ""
echo "=== 3. WireGuard interface? ==="
ip link show wg0 2>/dev/null && ip addr show wg0 || echo "wg0 not present"
echo ""
echo "=== 4. Config (master_url, agent_advertise_url) ==="
python3 -c "
import json
try:
    with open('/opt/vishwaas-agent/agent_config.json') as f:
        c = json.load(f)
    print('master_url:', c.get('master_url'))
    print('agent_advertise_url:', c.get('agent_advertise_url') or '(empty!)')
except Exception as e:
    print(e)
" 2>/dev/null || true
