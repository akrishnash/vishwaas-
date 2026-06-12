# VISHWAAS — Pre-flight Checks & Troubleshooting

Run these checks **before** installing VISHWAAS to confirm the machine is ready.
All commands work on Oracle Linux 10 (x86_64).

---

## Controller Machine Checks

### 1. OS and architecture
```bash
cat /etc/oracle-release || cat /etc/redhat-release
uname -m          # must be x86_64
```
Expected: `Oracle Linux Server release 10.x` / `x86_64`

---

### 2. Disk space
```bash
df -h /opt
```
Need at least **500 MB** free under `/opt` (install target).

---

### 3. Python 3 available
```bash
python3 --version
python3 -m venv --help > /dev/null && echo "venv OK" || echo "venv MISSING"
```
Expected: `Python 3.12.x` and `venv OK`
If missing — the installer will install it from `repo/`.

---

### 4. Port 80 (dashboard) is free
```bash
ss -tlnp | grep ':80 '
```
Expected: no output (nothing else listening on 80).
If occupied: stop the conflicting service or change the nginx port.

### 5. Port 8000 (backend API) is free
```bash
ss -tlnp | grep ':8000 '
```
Expected: no output.

### 6. Firewall — check open ports
```bash
firewall-cmd --list-ports
firewall-cmd --list-services
```
After install, ports `80/tcp` and `8000/tcp` must be open.
To open manually if needed:
```bash
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --reload
```

### 7. SELinux status
```bash
getenforce
```
If `Enforcing`, nginx may be blocked from proxying to the backend. Allow it:
```bash
sudo setsebool -P httpd_can_network_connect 1
```

### 8. Verify controller is reachable from agent machines
Run this from an **agent machine**:
```bash
curl -s http://<controller-ip>:8000/health
# Expected: {"status":"ok"}

curl -s http://<controller-ip>/
# Expected: HTML (dashboard)
```

---

## Agent Machine Checks

### 1. OS and architecture
```bash
cat /etc/oracle-release || cat /etc/redhat-release
uname -m          # must be x86_64
```

---

### 2. Disk space
```bash
df -h /opt
```
Need at least **200 MB** free.

---

### 3. Python 3 available
```bash
python3 --version
python3 -m venv --help > /dev/null && echo "venv OK" || echo "venv MISSING"
```
If missing — the installer will install it from `repo/`.

---

### 4. WireGuard kernel module
```bash
modinfo wireguard && echo "WireGuard module OK" || echo "WireGuard module MISSING"
```
If missing, try loading it:
```bash
sudo modprobe wireguard && echo "Loaded OK"
```
If that fails, the kernel may be too old (need 5.6+) or `kernel-modules-extra` is missing:
```bash
uname -r          # check kernel version — must be 5.6 or newer
```

---

### 5. Port 9000 (agent API) is free
```bash
ss -tlnp | grep ':9000 '
```
Expected: no output.

### 6. Port 51820 (WireGuard VPN) is free
```bash
ss -ulnp | grep ':51820 '
```
Expected: no output.

### 7. Firewall — check open ports
```bash
firewall-cmd --list-ports
```
After install, `9000/tcp` and `51820/udp` must be open.
To open manually:
```bash
sudo firewall-cmd --permanent --add-port=9000/tcp
sudo firewall-cmd --permanent --add-port=51820/udp
sudo firewall-cmd --reload
```

### 8. Verify agent can reach the controller
```bash
curl -s http://<controller-ip>:8000/health
# Expected: {"status":"ok"}
```
If this fails — fix network/firewall before starting the agent.

### 9. Verify controller can reach this agent (run from controller)
```bash
curl -s http://<agent-ip>:9000/health
# Expected: {"status":"ok", "state":"..."}
```

---

## Full Pre-flight Script

Copy-paste this block on either machine — it prints PASS/FAIL for each check:

```bash
#!/usr/bin/env bash
ROLE="${1:-agent}"   # pass "controller" or "agent"
PASS='\033[0;32m[PASS]\033[0m'; FAIL='\033[0;31m[FAIL]\033[0m'; WARN='\033[1;33m[WARN]\033[0m'

echo "=== VISHWAAS Pre-flight ($ROLE) ==="

# Architecture
[[ "$(uname -m)" == "x86_64" ]] && echo -e "$PASS architecture: x86_64" \
    || echo -e "$FAIL architecture: $(uname -m) — need x86_64"

# Disk space (need 500MB for controller, 200MB for agent)
NEEDED=$([[ "$ROLE" == "controller" ]] && echo 500 || echo 200)
FREE=$(df /opt --output=avail -m 2>/dev/null | tail -1 | tr -d ' ')
[[ "$FREE" -ge "$NEEDED" ]] && echo -e "$PASS disk space: ${FREE}MB free on /opt" \
    || echo -e "$FAIL disk space: only ${FREE}MB free on /opt (need ${NEEDED}MB)"

# Python
python3 --version &>/dev/null && echo -e "$PASS python3: $(python3 --version)" \
    || echo -e "$WARN python3: not found (will be installed from repo/)"

# venv
python3 -m venv --help &>/dev/null && echo -e "$PASS python3-venv: available" \
    || echo -e "$WARN python3-venv: not found (will be installed from repo/)"

# Ports
if [[ "$ROLE" == "controller" ]]; then
    ss -tlnp | grep -q ':80 '  && echo -e "$FAIL port 80: IN USE"   || echo -e "$PASS port 80: free"
    ss -tlnp | grep -q ':8000 ' && echo -e "$FAIL port 8000: IN USE" || echo -e "$PASS port 8000: free"
else
    ss -tlnp | grep -q ':9000 '  && echo -e "$FAIL port 9000: IN USE"  || echo -e "$PASS port 9000: free"
    ss -ulnp | grep -q ':51820 ' && echo -e "$FAIL port 51820: IN USE" || echo -e "$PASS port 51820: free"
    modinfo wireguard &>/dev/null && echo -e "$PASS wireguard: kernel module available" \
        || echo -e "$WARN wireguard: module not loaded (will try modprobe during install)"
fi

# SELinux
SE=$(getenforce 2>/dev/null || echo "unknown")
[[ "$SE" == "Enforcing" ]] && echo -e "$WARN SELinux: Enforcing — run: sudo setsebool -P httpd_can_network_connect 1" \
    || echo -e "$PASS SELinux: $SE"

# Root
[[ $EUID -eq 0 ]] && echo -e "$PASS running as root" \
    || echo -e "$FAIL not root — install.sh requires sudo"

echo "=== Done ==="
```

Run it:
```bash
bash preflight.sh controller   # on controller machine
bash preflight.sh agent        # on agent machine
```

---

## Troubleshooting

### Controller won't start — "insecure defaults" error
```bash
grep VISHWAAS_ENVIRONMENT /opt/vishwaas/controller/backend/.env
# If set to "production", JWT_SECRET and ADMIN_PASSWORD_HASH must also be set
# Quickest fix for internal use: set VISHWAAS_ENVIRONMENT=development
```

### Dashboard loads but shows no data / API errors
```bash
# Check backend is running
curl http://localhost:8000/health

# Check nginx is proxying correctly
curl http://localhost/api/health

# Check nginx error log
sudo tail -50 /var/log/nginx/error.log
```

### nginx fails to start
```bash
sudo nginx -t                        # test config syntax
sudo cat /var/log/nginx/error.log    # read errors
# SELinux blocking? Check:
sudo ausearch -m avc -ts recent | grep nginx
sudo setsebool -P httpd_can_network_connect 1
```

### Agent stuck as PENDING on dashboard
The admin must manually approve it:
1. Open dashboard → **Join Requests** tab
2. Click **Approve** next to the node

### Agent starts but controller says it's OFFLINE
```bash
# From controller machine — can it reach the agent?
curl http://<agent-ip>:9000/health

# If this fails, the agent port 9000 is blocked
# On agent machine:
sudo firewall-cmd --list-ports          # should show 9000/tcp
ss -tlnp | grep 9000                    # should show uvicorn listening
```

### WireGuard interface won't come up
```bash
# Check module is loaded
lsmod | grep wireguard

# Check wg interface state
sudo wg show

# Check for errors in agent output
# (look for "wg" or "ip link" errors in the terminal running start_agent.sh)

# Kernel version check — WireGuard built-in requires 5.6+
uname -r
```

### "No matching distribution" during pip install (offline)
```bash
# Confirm Python version matches what wheels were built for
python3 --version    # must be 3.12.x

# Confirm architecture
uname -m             # must be x86_64

# List available wheels
ls vishwaas_pack/controller/pip_packages/
ls vishwaas_pack/agent/pip_packages/
```

### Port already in use
```bash
# Find what's using the port
sudo ss -tlnp | grep ':8000\|:9000\|:80'

# Kill it (replace PID)
sudo kill -9 <PID>
```

### DNF install fails with "nothing to do" or dependency errors
```bash
# Force install all RPMs in repo/ ignoring repo config
sudo rpm -Uvh --nodeps vishwaas_pack/repo/*.rpm

# Or try dnf with explicit local paths
sudo dnf install -y --nogpgcheck vishwaas_pack/repo/*.rpm
```
