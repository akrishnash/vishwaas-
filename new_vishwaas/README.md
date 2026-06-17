# VISHWAAS — One-Click Install Guide

VISHWAAS manages WireGuard VPN connections through a web dashboard.
One machine is the **controller** (dashboard + API). Every other machine
runs an **agent** that joins the VPN.

**Nothing needs to be pre-installed** — Python, nginx, and all libraries
are bundled in this package.

---

## Requirements

| | Controller | Agent |
|---|---|---|
| OS | CentOS 7/8/9 · RHEL 8/9/10 · Oracle Linux 8/9/10 | Same |
| CPU | x86_64 | x86_64 |
| RAM | 512 MB | 256 MB |
| Disk space | 500 MB free under `/opt` | 300 MB free under `/opt` |
| Root access | Yes | Yes |
| Internet | Not needed | Not needed |

---

## Step 1 — Get the package onto the machine

Transfer `new_vishwaas.tar.gz` via USB, SCP, or shared drive. Then extract:

```bash
tar -xzf new_vishwaas.tar.gz
cd new_vishwaas
chmod +x install.sh
```

---

## Step 2 — Install the controller (do this first)

Run on the admin/dashboard machine:

```bash
sudo ./install.sh controller
```

Wait for it to finish (~1–2 minutes). At the end you will see:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Install complete!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Dashboard:          http://192.168.10.15/
  API:                http://192.168.10.15:8000/health

  VISHWAAS_AGENT_TOKEN = a3f9c2e1b7d8...
  Install agent on each node:
    sudo ./install.sh agent 192.168.10.15 a3f9c2e1b7d8...
```

**Copy the `sudo ./install.sh agent ...` line** — paste it on every agent machine.

Open the dashboard in a browser: `http://<controller-ip>/`
Login with any username and any password.

---

## Step 3 — Install agents (one command per machine)

On each machine that should join the VPN, copy the package and run the command
printed by the controller install:

```bash
tar -xzf new_vishwaas.tar.gz
cd new_vishwaas
sudo ./install.sh agent <controller-ip> <token>
```

Example:

```bash
sudo ./install.sh agent 192.168.10.15 a3f9c2e1b7d8...
```

The agent installs, configures itself, and starts automatically.

---

## Step 4 — Approve nodes and connect them

1. Open the dashboard → **Join Requests**
2. Click **Approve** next to each machine name
3. Status changes to **Active** — WireGuard is configured automatically

To connect two nodes:

1. Dashboard → **Connections** → **New Connection**
2. Select two active nodes → **Create** → **Approve**
3. Test from either machine: `ping 10.10.10.x`

---

## Managing the services

### Controller

```bash
# Check if running
curl http://localhost:8000/health

# View logs (live)
tail -f /opt/vishwaas/controller/logs/backend.log

# Stop
pkill -f 'uvicorn app.main:app'

# Start manually (if stopped)
cd /opt/vishwaas/controller && ./start_controller.sh

# Restart (full reinstall if needed)
sudo ./install.sh controller
```

### Agent

```bash
# Check if running
curl http://localhost:9000/health

# View logs
tail -f /opt/vishwaas/agent/agent.log

# Stop
pkill -f 'uvicorn app.main:app'

# Start manually
cd /opt/vishwaas/agent && sudo ./start_agent.sh

# Restart
sudo ./install.sh agent <controller-ip> <token>
```

---

## Ports that must be open

| Machine | Port | Protocol | Purpose |
|---|---|---|---|
| Controller | 80 | TCP | Dashboard (nginx) |
| Controller | 8000 | TCP | API (agents connect here) |
| Agent | 9000 | TCP | Agent API (controller connects here) |
| Agent | 51820 | UDP | WireGuard VPN traffic |

`install.sh` opens these automatically if `firewalld` is running.
If you use a hardware firewall or different software, open them manually.

---

## Troubleshooting

### Install script fails immediately

```
[✗] ERROR: Must run as root.
```

**Fix:** Add `sudo`:
```bash
sudo ./install.sh controller
```

---

### Dashboard won't open after controller install

**Check 1 — Is the backend running?**
```bash
curl http://localhost:8000/health
# Expected: {"status":"ok"}
```

If it fails, check the log:
```bash
tail -50 /opt/vishwaas/controller/logs/backend.log
```

**Check 2 — Is nginx running?**
```bash
systemctl status nginx
sudo nginx -t              # test config syntax
sudo systemctl start nginx
```

**Check 3 — SELinux blocking nginx?** (common on RHEL / Oracle Linux)
```bash
sudo setsebool -P httpd_can_network_connect 1
sudo systemctl restart nginx
```

**Check 4 — Port 80 already in use?**
```bash
sudo ss -tlnp | grep ':80'
# If something else is using it, stop it first, then restart nginx
```

---

### Agent never appears on dashboard Join Requests

**Check 1 — Can the agent reach the controller?**
```bash
# Run on the agent machine:
curl http://<controller-ip>:8000/health
# Expected: {"status":"ok"}
```

If this fails, port 8000 is blocked on the controller or the IP is wrong.

**Check 2 — Is the config correct?**
```bash
cat /opt/vishwaas/agent/agent_config.json
```

Verify:
- `master_url` = `http://<controller-ip>:8000` (no trailing slash)
- `master_token` = matches `VISHWAAS_AGENT_TOKEN` shown during controller install
- `agent_advertise_url` = `http://<this-machine-ip>:9000`

**Check 3 — Is the agent actually running?**
```bash
curl http://localhost:9000/health
tail -50 /opt/vishwaas/agent/agent.log
```

---

### Controller shows agent as OFFLINE right after approval

The controller called back to the agent and got no response.

```bash
# On the controller machine — can it reach the agent?
curl http://<agent-ip>:9000/health
```

If it fails, open the port on the agent machine:
```bash
sudo firewall-cmd --permanent --add-port=9000/tcp
sudo firewall-cmd --reload
sudo ss -tlnp | grep ':9000'   # confirm it's listening
```

---

### WireGuard interface not coming up

**Check 1 — Kernel module loaded?**
```bash
lsmod | grep wireguard
sudo modprobe wireguard     # load it manually if missing
```

If `modprobe` fails, your kernel may need `kernel-modules-extra`:
```bash
uname -r    # note your kernel version
# Install the matching kernel-modules-extra RPM (requires internet or separate package)
```

**Check 2 — WireGuard status:**
```bash
sudo wg show          # shows peers and handshakes
ip addr show wg0      # shows VPN IP assigned to this node
```

---

### "uvicorn not found" or Python environment broken

The venv path fix did not apply. This usually happens if you moved or renamed
the `new_vishwaas` folder after extracting.

**Fix:** Re-run install from the exact extracted folder:
```bash
cd new_vishwaas
sudo ./install.sh controller   # or agent
```

Do not move `new_vishwaas/` between extracting and running `install.sh`.

---

### Port already in use

```bash
# Find what is using the port:
sudo ss -tlnp | grep ':8000\|:9000\|:80'

# Kill by PID (replace 12345):
sudo kill -9 12345

# Then re-run install:
sudo ./install.sh controller   # or agent
```

---

### Agent needs re-approval every time it restarts

This is intentional — every restart sends a new join request and the admin
must re-approve from the dashboard. This prevents stale nodes from silently
re-joining the VPN.

Dashboard → **Join Requests** → **Approve**.

---

### Set an admin password (optional)

By default any password is accepted. To lock it down:

```bash
/opt/vishwaas/python/bin/python3.11 -c \
  "from passlib.hash import bcrypt; print(bcrypt.hash('yourpassword'))"
```

Paste the output (starts with `$2b$`) into the controller config:

```bash
nano /opt/vishwaas/controller/backend/.env
# Line: VISHWAAS_ADMIN_PASSWORD_HASH=<paste here>
```

Restart the controller:
```bash
pkill -f 'uvicorn app.main:app'
cd /opt/vishwaas/controller && ./start_controller.sh
```

---

## Quick reference

```
CONTROLLER
  Install:   sudo ./install.sh controller
  Status:    curl http://localhost:8000/health
  Dashboard: http://<ip>/
  Logs:      tail -f /opt/vishwaas/controller/logs/backend.log
  Stop:      pkill -f 'uvicorn app.main:app'
  Restart:   cd /opt/vishwaas/controller && ./start_controller.sh
  Config:    nano /opt/vishwaas/controller/backend/.env

AGENT
  Install:   sudo ./install.sh agent <controller-ip> <token>
  Status:    curl http://localhost:9000/health
  Logs:      tail -f /opt/vishwaas/agent/agent.log
  Stop:      pkill -f 'uvicorn app.main:app'
  Restart:   cd /opt/vishwaas/agent && sudo ./start_agent.sh
  Config:    nano /opt/vishwaas/agent/agent_config.json
  VPN:       sudo wg show
```
