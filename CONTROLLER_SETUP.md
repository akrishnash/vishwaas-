# VISHWAAS Controller — Setup Guide

The controller is the central component of VISHWAAS. It runs the admin dashboard and the API
that all agents talk to. Install it on one machine on your network — every agent node points to it.

---

## Prerequisites

- Linux (Ubuntu 20.04+, Debian 11+, Fedora 36+, RHEL 8+)
- Python 3.10+
- Node.js 18+ and npm
- Root / sudo access

```bash
# Ubuntu / Debian
sudo apt install python3 python3-venv nodejs npm -y

# Fedora / RHEL
sudo dnf install python3 nodejs npm -y
```

---

## Step 1 — Get the code

Clone or copy the repository to the controller machine:

```bash
git clone <repo-url> vishwaas
cd vishwaas/controller
```

Or extract from a tarball if provided:

```bash
tar -xzf vishwaas-controller.tar.gz
cd vishwaas/controller
```

---

## Step 2 — Configure

```bash
cp backend/.env.example backend/.env
nano backend/.env
```

### Required fields

| Variable | Description | How to generate |
|---|---|---|
| `VISHWAAS_AGENT_TOKEN` | Shared secret for controller ↔ agent auth. Must match `master_token` in every agent's config. | `openssl rand -hex 32` |
| `VISHWAAS_JWT_SECRET` | Signs admin login tokens. Required in production. | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `VISHWAAS_ADMIN_PASSWORD_HASH` | bcrypt hash of the admin password. Leave empty to skip auth (dev only). | `python3 -c "from passlib.hash import bcrypt; print(bcrypt.hash('yourpassword'))"` |

### Other settings

| Variable | Default | Description |
|---|---|---|
| `VISHWAAS_ENVIRONMENT` | `development` | Set to `production` to enable security startup guards |
| `VISHWAAS_ALLOWED_ORIGINS` | `http://localhost:3000` | CORS whitelist — set to your dashboard URL in production |
| `VISHWAAS_DATABASE_URL` | `sqlite:///./vishwaas_master.db` | Leave as-is for SQLite; change to Postgres for larger deployments |
| `VISHWAAS_VPN_NETWORK` | `10.10.10` | VPN subnet prefix |
| `VISHWAAS_LOG_JSON` | `false` | Set `true` for structured JSON logs (Loki, ELK, Splunk) |

---

## Step 3 — Start (development)

```bash
./start_controller.sh
```

This will:
1. Create a Python venv and install all backend dependencies automatically
2. Install frontend npm packages
3. Start the backend API on `http://0.0.0.0:8000`
4. Start the Vite dev server on `http://localhost:5173`

Dashboard: `http://<controller-ip>:5173`
API: `http://<controller-ip>:8000`

Login with any username and password when `VISHWAAS_ADMIN_PASSWORD_HASH` is not set.

---

## Step 4 — Start (production)

Production mode binds the backend to `127.0.0.1` only (nginx handles public traffic)
and builds the frontend as static files.

```bash
# 1. Set production env vars in backend/.env
#    VISHWAAS_ENVIRONMENT=production
#    VISHWAAS_JWT_SECRET=<generated secret>
#    VISHWAAS_ADMIN_PASSWORD_HASH=<bcrypt hash>
#    VISHWAAS_ALLOWED_ORIGINS=https://dashboard.yourdomain.com

# 2. Build and start the backend
./start_controller.sh --prod

# 3. Set up nginx (see below)
```

---

## Step 5 — nginx (production only)

nginx serves the frontend, proxies `/api/` to the backend, and handles TLS.

```bash
sudo apt install nginx certbot python3-certbot-nginx -y

# Get a TLS certificate (replace with your domain)
sudo certbot certonly --nginx -d dashboard.yourdomain.com

# Install the provided nginx config
sudo cp nginx.conf /etc/nginx/sites-available/vishwaas
sudo ln -s /etc/nginx/sites-available/vishwaas /etc/nginx/sites-enabled/vishwaas

# Edit the config — update server_name and cert paths
sudo nano /etc/nginx/sites-available/vishwaas

# Test and reload
sudo nginx -t && sudo systemctl reload nginx
```

Key things to update in `nginx.conf`:
- `server_name dashboard.example.com;` → your actual domain
- `ssl_certificate` / `ssl_certificate_key` paths → your certbot paths
- Frontend `root` path → where `controller/frontend/dist/` lives

---

## Running persistently (systemd)

```bash
sudo cp vishwaas-controller.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vishwaas-controller
sudo journalctl -u vishwaas-controller -f    # live logs
```

---

## First run — existing database

If you are upgrading from a previous installation, stamp the database before starting:

```bash
cd backend
.venv/bin/alembic stamp head
```

Skip this on a fresh install — migrations run automatically.

---

## Firewall

| Port | Protocol | Purpose |
|---|---|---|
| `8000` | TCP | Backend API (dev mode only — block in production, nginx proxies it) |
| `5173` | TCP | Frontend dev server (dev mode only) |
| `80` | TCP | nginx HTTP → HTTPS redirect (production) |
| `443` | TCP | nginx HTTPS dashboard (production) |

```bash
# Development
sudo ufw allow 8000/tcp
sudo ufw allow 5173/tcp

# Production
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw deny 8000/tcp    # backend should not be publicly reachable
```

---

## Verifying it works

```bash
# Backend health
curl http://localhost:8000/health
# → {"status": "ok"}

# Backend ready (DB check)
curl http://localhost:8000/ready
# → {"status": "ready"}

# Dashboard reachable
curl -s -o /dev/null -w "%{http_code}" http://localhost:5173
# → 200
```

---

## Connecting agents

Once the controller is running, configure each agent machine with:
- `master_url` = `http://<this-machine-ip>:8000` (dev) or `https://dashboard.yourdomain.com` (prod)
- `master_token` = the value of `VISHWAAS_AGENT_TOKEN` from `backend/.env`

Approved agents appear in the **Nodes** section of the dashboard.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Backend exits immediately | Insecure defaults in production mode | Check `.env` — `JWT_SECRET` and `ADMIN_PASSWORD_HASH` must be set |
| `python3-venv` not found | Package missing | `sudo apt install python3-venv` |
| Frontend npm errors | Node.js too old | Upgrade to Node.js 18+: `nvm install 18` |
| Dashboard shows no nodes | Agents not yet approved | Check **Join Requests** tab on dashboard |
| `alembic stamp head` fails | DB file missing | Let the backend create it on first start, then stamp |
| 502 from nginx | Backend not running | Check `systemctl status vishwaas-controller` |
| CORS errors in browser | `VISHWAAS_ALLOWED_ORIGINS` mismatch | Add your dashboard URL to the allowed origins list |

---

## Directory layout after install

```
controller/
├── backend/
│   ├── .env              ← your secrets (never commit this)
│   ├── .venv/            ← Python venv (auto-created by start_controller.sh)
│   ├── vishwaas_master.db  ← SQLite database
│   └── app/              ← backend source
├── frontend/
│   ├── dist/             ← built frontend (production only)
│   └── src/              ← frontend source
├── logs/
│   ├── backend.log
│   └── frontend.log
├── nginx.conf
├── start_controller.sh
└── vishwaas-controller.service
```
