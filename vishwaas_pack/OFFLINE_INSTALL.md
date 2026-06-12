# VISHWAAS — Offline Installation Guide

This package contains everything needed to deploy VISHWAAS on a machine with
**no internet access**. All Python wheels are bundled. No npm or pip downloads required.

Tested on: Oracle Linux 8/9, RHEL 8/9, Rocky Linux 8/9 (x86_64, Python 3.11)

---

## Package Contents

```
vishwaas_pack/
├── controller/
│   ├── backend/           ← controller API source code
│   ├── frontend/dist/     ← pre-built dashboard (no Node.js needed on target)
│   ├── pip_packages/      ← all Python wheels (offline install)
│   ├── nginx.conf         ← production nginx config
│   ├── start_controller.sh
│   └── vishwaas-controller.service
├── agent/
│   ├── app/               ← agent source code
│   ├── pip_packages/      ← all Python wheels (offline install)
│   ├── agent_config.json.example
│   ├── requirements.txt
│   └── start_agent.sh
└── OFFLINE_INSTALL.md     ← this file
```

---

## System Prerequisites

These must be installed on the target machine before running VISHWAAS.
Install from your internal repo / ISO / USB:

```bash
# Oracle Linux / RHEL 8/9
sudo dnf install python3.11 python3.11-venv wireguard-tools nginx -y

# Verify
python3.11 --version   # must be 3.11.x
wg --version
```

> If Python 3.11 is not available, Python 3.10 also works — adjust the commands below
> to use `python3.10` instead.

---

## Part 1 — Controller

Deploy this on the central admin machine. Do this **before** setting up any agents.

### 1.1 — Copy files

```bash
sudo mkdir -p /opt/vishwaas/controller
sudo cp -r controller/ /opt/vishwaas/controller/
sudo cp -r controller/frontend/dist/ /opt/vishwaas/controller/frontend/dist/
```

### 1.2 — Install Python dependencies (offline)

```bash
cd /opt/vishwaas/controller/backend

# Create virtual environment
python3.11 -m venv .venv

# Install all packages from the bundled wheels — no internet needed
.venv/bin/pip install --no-index --find-links=../pip_packages -r requirements.txt
```

### 1.3 — Configure

```bash
cp backend/.env.example backend/.env
nano backend/.env
```

Set these values:

| Variable | Description | How to generate |
|---|---|---|
| `VISHWAAS_AGENT_TOKEN` | Shared secret — must match `master_token` in every agent config | `openssl rand -hex 32` |
| `VISHWAAS_JWT_SECRET` | JWT signing key | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `VISHWAAS_ADMIN_PASSWORD_HASH` | bcrypt hash of admin password | `python3 -c "from passlib.hash import bcrypt; print(bcrypt.hash('yourpassword'))"` |
| `VISHWAAS_ENVIRONMENT` | Set to `production` | `production` |
| `VISHWAAS_ALLOWED_ORIGINS` | Your dashboard URL | `http://192.168.10.15:8000` |

### 1.4 — Start (development / no nginx)

```bash
cd /opt/vishwaas/controller
./start_controller.sh
```

The backend API starts on port `8000`. Since the frontend is pre-built, serve it with nginx
(see Step 1.5) or directly open `frontend/dist/index.html` pointing to the API.

### 1.5 — Set up nginx (recommended for production)

```bash
# Edit nginx.conf — set server_name to the controller's IP or hostname
nano /opt/vishwaas/controller/nginx.conf

# For HTTP-only (no TLS) on a private network, replace the server block with:
#   server {
#       listen 80;
#       root /opt/vishwaas/controller/frontend/dist;
#       location /api/ { proxy_pass http://127.0.0.1:8000/; }
#   }

sudo cp /opt/vishwaas/controller/nginx.conf /etc/nginx/conf.d/vishwaas.conf
sudo nginx -t && sudo systemctl enable --now nginx
```

> **TLS note:** The bundled `nginx.conf` expects TLS certificates. For an internal/offline
> network without a CA, either use a self-signed cert or switch to plain HTTP by simplifying
> the server block as shown above.

### 1.6 — Run as systemd service

```bash
# Edit the service file if your install path differs from /opt/vishwaas
nano /opt/vishwaas/controller/vishwaas-controller.service

sudo cp /opt/vishwaas/controller/vishwaas-controller.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vishwaas-controller
sudo journalctl -u vishwaas-controller -f
```

### 1.7 — Verify

```bash
curl http://localhost:8000/health
# → {"status": "ok"}

curl http://localhost:8000/ready
# → {"status": "ready"}
```

Dashboard: `http://<controller-ip>/` (via nginx) or `http://<controller-ip>:8000/docs` (API)

---

## Part 2 — Agent

Repeat on **every node machine** that should join the VPN.

### 2.1 — Copy files

```bash
mkdir -p ~/vishwaas-agent
cp -r agent/ ~/vishwaas-agent/
cd ~/vishwaas-agent
```

### 2.2 — Configure

```bash
cp agent_config.json.example agent_config.json
nano agent_config.json
```

| Field | Value |
|---|---|
| `master_url` | `http://<controller-ip>:8000` |
| `master_token` | Same value as `VISHWAAS_AGENT_TOKEN` on the controller |
| `agent_advertise_url` | `http://<this-machine-ip>:9000` |
| `node_name` | `"auto"` (uses hostname) or a custom label |

### 2.3 — Install Python dependencies (offline)

`start_agent.sh` creates the venv automatically but will try to reach PyPI.
For offline use, pre-create the venv and install from bundled wheels:

```bash
cd ~/vishwaas-agent
python3.11 -m venv venv
venv/bin/pip install --no-index --find-links=pip_packages -r requirements.txt
```

### 2.4 — Start

```bash
sudo ./start_agent.sh
```

The agent will appear as a **Pending** join request on the dashboard.
An admin must approve it before the VPN becomes active.

### 2.5 — Open firewall ports

```bash
sudo firewall-cmd --permanent --add-port=9000/tcp   # agent API
sudo firewall-cmd --permanent --add-port=51820/udp  # WireGuard VPN
sudo firewall-cmd --reload
```

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| `pip install` fails with "No matching distribution" | The wheels were built for Python 3.11 x86_64. Confirm with `python3 --version` and `uname -m` |
| Backend exits at start | Check `.env` — `VISHWAAS_JWT_SECRET` must not be the default in production mode |
| `wg: command not found` | Install `wireguard-tools`: `dnf install wireguard-tools` |
| Agent can't reach controller | Check firewall — port 8000 must be reachable from agent machines |
| Dashboard blank / JS errors | Confirm nginx is serving from `frontend/dist/` and API is running on port 8000 |
| `python3.11-venv` not found | `dnf install python3.11` or `python3.11-libs` depending on your Oracle Linux version |

---

## Port Reference

| Port | Protocol | Component | Purpose |
|---|---|---|---|
| `8000` | TCP | Controller backend | API (bind to 127.0.0.1 in prod, proxied by nginx) |
| `80` / `443` | TCP | nginx | Dashboard (HTTP/HTTPS) |
| `9000` | TCP | Agent | Controller → agent callbacks |
| `51820` | UDP | Agent | WireGuard VPN data plane |
