# VISHWAAS Offline Deployment Guide

This guide walks through the complete deployment of VISHWAAS on machines with
no internet access — from receiving the package to a fully running VPN management
system. Follow it top to bottom.

---

## What You Are Setting Up

VISHWAAS has two components:

| Component | Machine | What it does |
|---|---|---|
| **Controller** | One central machine | Runs the admin dashboard and API. Manages all nodes. |
| **Agent** | Every VPN node machine | Connects the machine to the VPN. Takes orders from the controller. |

Deploy the **controller first**, then the **agent** on each node machine.

---

## What You Received

A single file: `vishwaas_pack.tar.gz`

When extracted it contains:

```
vishwaas_pack/
├── setup.sh                        ← run once per machine to install everything
├── python/                         ← Python 3.11 standalone (no system Python needed)
├── repo/                           ← nginx + wireguard RPMs for offline install
├── controller/
│   ├── backend/                    ← controller API source code
│   ├── frontend/dist/              ← pre-built web dashboard
│   ├── pip_packages/               ← all Python libraries (offline)
│   └── start_controller.sh        ← start the controller
└── agent/
    ├── app/                        ← agent source code
    ├── pip_packages/               ← all Python libraries (offline)
    ├── agent_config.json.example   ← config template
    └── start_agent.sh             ← start the agent
```

> **Node.js / npm not required.** The dashboard is pre-built. You only need what is
> in this package.

---

## System Requirements

| Requirement | Controller | Agent |
|---|---|---|
| OS | CentOS 7/8/9, RHEL 8/9/10, Oracle Linux 8/9/10 | Same |
| Architecture | x86_64 only | x86_64 only |
| RAM | 512 MB minimum | 256 MB minimum |
| Disk | 500 MB free under `/opt` | 200 MB free under `/opt` |
| Python | Not required — bundled | Not required — bundled |
| Network | Reachable from agent machines on port 80 and 8000 | Must reach controller on port 8000; port 9000 open inbound |

---

## Part 1 — Controller Setup

Do this on the **central admin machine** only.

### 1.1 Copy and extract the package

Transfer `vishwaas_pack.tar.gz` to the machine (USB, SCP, shared drive — any method).

```bash
tar -xzf vishwaas_pack.tar.gz
cd vishwaas_pack
ls
# You should see: setup.sh  python/  repo/  controller/  agent/  README.md
```

### 1.2 Run setup

```bash
sudo ./setup.sh controller
```

This will:
- Install Python 3.11 from the bundled `python/` folder to `/opt/vishwaas/python`
- Install nginx from the bundled RPMs in `repo/`
- Copy the controller code to `/opt/vishwaas/controller/`
- Create a Python virtual environment and install all packages — fully offline
- Generate a random `VISHWAAS_AGENT_TOKEN` and `JWT_SECRET` and write them to `.env`
- Configure nginx to serve the dashboard on port 80

At the end you will see output like:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Setup complete!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  VISHWAAS_AGENT_TOKEN = a3f9c2e1...
  (copy this into each agent's agent_config.json as master_token)

  ── Start the controller ──────────────────────────────
  cd /opt/vishwaas/controller && ./start_controller.sh

  Dashboard: http://192.168.x.x/
```

**Write down the `VISHWAAS_AGENT_TOKEN`** — you will need it when setting up each agent.

### 1.3 Set an admin password (recommended)

By default, any username and password is accepted (dev mode). To lock it down:

```bash
# Generate a bcrypt hash of your password
/opt/vishwaas/python/bin/python3.11 -c \
  "from passlib.hash import bcrypt; print(bcrypt.hash('yourpassword'))"
```

Copy the output (starts with `$2b$...`) and add it to the config:

```bash
nano /opt/vishwaas/controller/backend/.env
```

Find the line:
```
VISHWAAS_ADMIN_PASSWORD_HASH=
```

Paste your hash after the `=` sign. Save and close.

### 1.4 Start the controller

```bash
cd /opt/vishwaas/controller
./start_controller.sh
```

You should see:

```
Starting VISHWAAS Controller...
  API:       http://0.0.0.0:8000
  Dashboard: http://192.168.x.x/
  Logs:      /opt/vishwaas/controller/logs/backend.log
  Ctrl+C to stop.
```

### 1.5 Verify it is working

Open a browser on any machine on the same network and go to:

```
http://<controller-ip>/
```

You should see the VISHWAAS login page. Log in with any username and the password
you set (or any password if you skipped 1.3).

Also test the API directly:

```bash
curl http://localhost:8000/health
# Expected: {"status":"ok"}

curl http://localhost:8000/ready
# Expected: {"status":"ready"}
```

If either fails, check the logs:

```bash
tail -50 /opt/vishwaas/controller/logs/backend.log
```

### 1.6 Keep it running (optional — run in background)

To keep it running after you close the terminal:

```bash
# Using screen
sudo dnf install screen -y
screen -dmS vishwaas-controller bash -c 'cd /opt/vishwaas/controller && ./start_controller.sh'

# Reattach later with:
screen -r vishwaas-controller
```

---

## Part 2 — Agent Setup

Repeat this on **every machine** that should join the VPN. Do the controller first.

### 2.1 Copy and extract the package

Same package as the controller — copy `vishwaas_pack.tar.gz` to the agent machine.

```bash
tar -xzf vishwaas_pack.tar.gz
cd vishwaas_pack
```

### 2.2 Run setup

```bash
sudo ./setup.sh agent
```

This will:
- Install Python 3.11 from the bundled `python/` folder
- Install `wireguard-tools` from the bundled RPMs
- Copy the agent code to `/opt/vishwaas/agent/`
- Create a Python virtual environment and install all packages offline
- Create a default `agent_config.json` pre-filled with this machine's IP
- Open firewall ports 9000/tcp and 51820/udp

### 2.3 Edit the agent config

```bash
nano /opt/vishwaas/agent/agent_config.json
```

Change these three fields:

```json
{
  "master_url": "http://<controller-ip>:8000",
  "master_token": "<paste VISHWAAS_AGENT_TOKEN from controller setup>",
  "agent_advertise_url": "http://<this-machine-ip>:9000",
  ...
}
```

| Field | What to put |
|---|---|
| `master_url` | IP of the controller machine, port 8000 |
| `master_token` | The token printed at the end of `setup.sh controller` |
| `agent_advertise_url` | This machine's IP, port 9000 |

Leave everything else as-is.

### 2.4 Start the agent

```bash
cd /opt/vishwaas/agent
sudo ./start_agent.sh
```

You should see:

```
Starting VISHWAAS Agent on :9000...
```

### 2.5 Approve the node on the dashboard

1. Open the VISHWAAS dashboard on the controller: `http://<controller-ip>/`
2. Go to **Join Requests**
3. Click **Approve** next to this machine's name

Once approved, the node status will change to **Active** and WireGuard will be configured automatically.

### 2.6 Keep it running (optional)

```bash
screen -dmS vishwaas-agent bash -c 'cd /opt/vishwaas/agent && sudo ./start_agent.sh'
```

---

## Part 3 — Connecting Nodes

Once two or more agents are approved and active:

1. Open the dashboard → **Connections**
2. Click **New Connection**
3. Select two nodes and click **Create**
4. Approve the connection request

The controller will automatically push the WireGuard peer config to both machines.
They will be able to reach each other over the VPN IP (e.g. `10.10.10.2` ↔ `10.10.10.3`).

Test the connection from one node:

```bash
ping 10.10.10.x   # the VPN IP of the other node
```

---

## Firewall Reference

Open these ports on each machine. If `firewalld` is running, `setup.sh` does this
automatically. If you use a different firewall or hardware ACL, open them manually.

### Controller machine

| Port | Protocol | Direction | Purpose |
|---|---|---|---|
| 80 | TCP | Inbound | Dashboard (nginx) |
| 8000 | TCP | Inbound | Controller API (agents and admin browser) |

### Agent machines

| Port | Protocol | Direction | Purpose |
|---|---|---|---|
| 9000 | TCP | Inbound | Agent API (controller calls back on this) |
| 51820 | UDP | Inbound + Outbound | WireGuard VPN traffic |

---

## Config File Reference

### Controller: `/opt/vishwaas/controller/backend/.env`

| Variable | Description |
|---|---|
| `VISHWAAS_AGENT_TOKEN` | Shared secret — must match `master_token` in all agent configs |
| `VISHWAAS_JWT_SECRET` | Signs login tokens — keep secret, do not change after deployment |
| `VISHWAAS_ADMIN_PASSWORD_HASH` | bcrypt hash of admin password. Empty = accept any password |
| `VISHWAAS_ENVIRONMENT` | `development` (default) or `production` |
| `VISHWAAS_ALLOWED_ORIGINS` | CORS whitelist — set to dashboard URL in production |

Restart the controller after any `.env` change.

### Agent: `/opt/vishwaas/agent/agent_config.json`

| Field | Description |
|---|---|
| `master_url` | Controller URL e.g. `http://192.168.10.15:8000` |
| `master_token` | Must match `VISHWAAS_AGENT_TOKEN` on controller |
| `agent_advertise_url` | This machine's URL e.g. `http://192.168.10.16:9000` |
| `node_name` | `"auto"` uses hostname, or set a custom label |
| `wg_interface` | WireGuard interface name (default: `wg0`) |
| `listen_port` | WireGuard UDP port (default: `51820`) |
| `keys_dir` | Where WireGuard keys are stored (default: `./keys`) |

Restart the agent after any config change.

---

## Troubleshooting

### setup.sh fails — "venv not found" or pip errors

```bash
# Check Python was installed correctly
/opt/vishwaas/python/bin/python3.11 --version
# Expected: Python 3.11.x

# Re-run setup
sudo ./setup.sh controller   # or agent
```

### Controller won't start — "insecure defaults" error

```bash
nano /opt/vishwaas/controller/backend/.env
# Set VISHWAAS_ENVIRONMENT=development
# OR set VISHWAAS_JWT_SECRET to a real secret
```

### Dashboard loads but shows no data

```bash
# Is the backend running?
curl http://localhost:8000/health

# Is nginx proxying correctly?
curl http://localhost/api/health

# nginx error log
sudo tail -50 /var/log/nginx/error.log

# SELinux blocking nginx proxy?
sudo setsebool -P httpd_can_network_connect 1
sudo systemctl reload nginx
```

### Agent says "uvicorn not found"

setup.sh was not run, or the venv was not created at the expected path.

```bash
# Check the venv exists
ls /opt/vishwaas/agent/venv/bin/python

# Re-run setup
cd /path/to/vishwaas_pack
sudo ./setup.sh agent
```

### Agent starts but never appears on dashboard

```bash
# Can the agent reach the controller?
curl http://<controller-ip>:8000/health

# Check master_url and master_token in config
cat /opt/vishwaas/agent/agent_config.json

# Check agent logs (terminal where start_agent.sh is running)
```

### Controller shows agent as OFFLINE immediately after approval

```bash
# Can the controller reach the agent?
# Run this from the controller machine:
curl http://<agent-ip>:9000/health

# If it fails — port 9000 is blocked on the agent
sudo firewall-cmd --permanent --add-port=9000/tcp
sudo firewall-cmd --reload
```

### WireGuard interface not coming up

```bash
# Is the kernel module loaded?
lsmod | grep wireguard

# If not, load it
sudo modprobe wireguard

# Check wg status
sudo wg show

# Check kernel version — built-in WireGuard needs 5.6+
uname -r
```

### Port already in use

```bash
# Find what is using the port
sudo ss -tlnp | grep ':8000\|:9000\|:80'

# Kill the process (replace PID)
sudo kill -9 <PID>

# Then restart VISHWAAS
```

### Agent keeps rejecting its own join request

This happens when the agent restarts — by design, the admin must re-approve each restart.
Go to the dashboard → **Join Requests** and approve again.

---

## Day-2 Operations

### Restart the controller

```bash
# Kill the existing process (Ctrl+C if running in terminal, or:)
pkill -f "uvicorn app.main:app"

cd /opt/vishwaas/controller
./start_controller.sh
```

### Restart an agent

```bash
pkill -f "uvicorn app.main:app"

cd /opt/vishwaas/agent
sudo ./start_agent.sh
# Then re-approve on the dashboard
```

### View live logs

```bash
# Controller
tail -f /opt/vishwaas/controller/logs/backend.log

# Agent (if running in screen)
screen -r vishwaas-agent
```

### Check VPN status on an agent

```bash
sudo wg show           # WireGuard peers and handshakes
ip addr show wg0       # VPN IP assigned to this node
```

### Remove a node from the VPN

1. Dashboard → **Nodes** → click the node → **Delete**
2. The controller will automatically remove the WireGuard peer from all connected nodes.

---

## Quick Reference Card

```
CONTROLLER MACHINE
──────────────────
Setup:   sudo ./setup.sh controller
Start:   cd /opt/vishwaas/controller && ./start_controller.sh
Config:  nano /opt/vishwaas/controller/backend/.env
Logs:    tail -f /opt/vishwaas/controller/logs/backend.log
Health:  curl http://localhost:8000/health

AGENT MACHINE
─────────────
Setup:   sudo ./setup.sh agent
Config:  nano /opt/vishwaas/agent/agent_config.json
Start:   cd /opt/vishwaas/agent && sudo ./start_agent.sh
Health:  curl http://localhost:9000/health
WG:      sudo wg show
```
