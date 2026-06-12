#!/usr/bin/env bash
# VISHWAAS Pre-flight checker
# Usage: bash preflight.sh controller
#        bash preflight.sh agent
ROLE="${1:-agent}"
PASS='\033[0;32m[PASS]\033[0m'; FAIL='\033[0;31m[FAIL]\033[0m'; WARN='\033[1;33m[WARN]\033[0m'

echo "=== VISHWAAS Pre-flight ($ROLE) ==="

[[ "$(uname -m)" == "x86_64" ]] && echo -e "$PASS architecture: x86_64" \
    || echo -e "$FAIL architecture: $(uname -m) — need x86_64"

NEEDED=$([[ "$ROLE" == "controller" ]] && echo 500 || echo 200)
FREE=$(df /opt --output=avail -m 2>/dev/null | tail -1 | tr -d ' ')
[[ "$FREE" -ge "$NEEDED" ]] && echo -e "$PASS disk space: ${FREE}MB free on /opt" \
    || echo -e "$FAIL disk space: only ${FREE}MB free on /opt (need ${NEEDED}MB)"

python3 --version &>/dev/null && echo -e "$PASS python3: $(python3 --version)" \
    || echo -e "$WARN python3: not found (will be installed from repo/)"

python3 -m venv --help &>/dev/null && echo -e "$PASS python3-venv: available" \
    || echo -e "$WARN python3-venv: not found (will be installed from repo/)"

if [[ "$ROLE" == "controller" ]]; then
    ss -tlnp | grep -q ':80 '   && echo -e "$FAIL port 80: IN USE"   || echo -e "$PASS port 80: free"
    ss -tlnp | grep -q ':8000 ' && echo -e "$FAIL port 8000: IN USE" || echo -e "$PASS port 8000: free"
else
    ss -tlnp | grep -q ':9000 '  && echo -e "$FAIL port 9000: IN USE"  || echo -e "$PASS port 9000: free"
    ss -ulnp | grep -q ':51820 ' && echo -e "$FAIL port 51820: IN USE" || echo -e "$PASS port 51820: free"
    modinfo wireguard &>/dev/null && echo -e "$PASS wireguard: kernel module available" \
        || echo -e "$WARN wireguard: module not loaded (will try modprobe during install)"
fi

SE=$(getenforce 2>/dev/null || echo "unknown")
[[ "$SE" == "Enforcing" ]] && echo -e "$WARN SELinux: Enforcing — run: sudo setsebool -P httpd_can_network_connect 1" \
    || echo -e "$PASS SELinux: $SE"

[[ $EUID -eq 0 ]] && echo -e "$PASS running as root" \
    || echo -e "$FAIL not root — install.sh requires sudo"

echo "=== Done ==="
