# VISHWAAS

A WireGuard VPN orchestration system. Run agents on each machine, approve joins and connections from a central dashboard — the controller handles all WireGuard configuration automatically. Nothing becomes active without explicit admin approval.

---

## Table of Contents

1. [How it works](#how-it-works)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [Installation](#installation)
   - [Controller setup](#controller-setup)
   - [Agent setup](#agent-setup)
5. [Configuration](#configuration)
   - [Controller env vars](#controller-env-vars)
   - [Agent config file](#agent-config-file)
6. [Running the system](#running-the-system)
7. [Operational workflow](#operational-workflow)
8. [Dashboard pages](#dashboard-pages)
9. [Security model](#security-model)
10. [Troubleshooting](#troubleshooting)
11. [Lab machines (example)](#lab-machines-example)

---

## How it works

```
  Machine A               Controller               Machine B
  (agent)                 (dashboard)               (agent)
     │                        │                        │
     │── POST /request-join ──►│                        │
     │                        │  Admin approves         │
     │◄── set_vpn_address ────│  (assigns 10.10.10.x)  │
     │  wg0 comes up          │                        │
     │                        │  Admin creates          │
     │                        │  connection A ↔ B       │
     │                        │  Admin approves it      │
     │◄── add_peer(B) ────────│── add_peer(A) ─────────►│
     │  wg0 peers with B      │                  wg0 peers with A
     │◄══════════════ WireGuard tunnel ═══════════════►│
```

1. Each machine runs a lightweight **agent** (FastAPI on port 9000).
2. On startup the agent calls `POST /request-join` on the controller.
3. The admin sees the request in the dashboard and **approves** it — the controller assigns a VPN IP and pushes the config to the agent, which brings up `wg0`.
4. To connect two nodes, the admin creates a **connection request** and approves it — the controller calls both agents to add each other as WireGuard peers.
5. Terminating a connection removes the peer keys from both agents; the `wg0` interface stays up.

---

## Architecture

```
vishwaas/
├── controller/              ← Deploy on the admin/central machine
│   ├── backend/             ← FastAPI (port 8000)
│   │   └── app/
│   │       ├── api/routes/  ← HTTP endpoints (join, connections, nodes, monitoring, auth, health)
│   │       ├── core/        ← config, security, heartbeat, metrics, http_client, logging
│   │       ├── services/    ← business logic (join_service, connection_service, agent_client)
│   │       ├── persistence/ ← SQLAlchemy models + SQLite DB + Alembic migrations
│   │       └── domain/      ← enums (NodeStatus, ConnectionStatus, etc.)
│   ├── frontend/            ← React + Vite dashboard (port 3000)
│   ├── start_controller.sh  ← starts backend + frontend
│   ├── nginx.conf           ← production nginx config
│   └── vishwaas-controller.service  ← systemd unit
│
├── agent/                   ← Deploy on each VPN node machine
│   ├── app/
│   │   ├── main.py          ← FastAPI agent + join loop + all endpoints
│   │   ├── config.py        ← loads agent_config.json
│   │   ├── state.py         ← state machine (WAITING → APPROVED → ACTIVE)
│   │   ├── wireguard.py     ← all wg/ip commands
│   │   ├── security.py      ← token validation for controller→agent calls
│   │   ├── logger.py        ← structured logging (JSON optional)
│   │   └── tpm.py           ← optional TPM key storage
│   ├── agent_config.json.example
│   ├── requirements.txt
│   ├── start_agent.sh       ← dev start script
│   └── install.sh           ← installs as systemd service
│
├── deploy-agent.sh          ← SSH-based automated deploy to agent machines
├── CLAUDE.md                ← AI assistant notes (technical, for LLMs continuing work)
└── README.md                ← this file
```

---

## Prerequisites

### Controller machine
- Linux (Ubuntu 20.04+ recommended)
- Python 3.10+
- Node.js 18+ and npm
- `sudo apt install python3 python3-venv nodejs npm`

### Agent machines
- Linux (Ubuntu 20.04+ recommended)
- Python 3.10+
- WireGuard tools: `sudo apt install wireguard-tools`
- Root/sudo access (needed to manage the `wg0` interface)
- Network reachability: agent machine must be reachable from the controller on port 9000

---

## Installation

### Controller setup

```bash
# 1. Clone the repository on the controller machine
git clone <repo-url> vishwaas
cd vishwaas

# 2. Set up the Python virtual environment
cd controller/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 3. Create the environment config file
cp .env.example .env
# Edit .env — at minimum set VISHWAAS_AGENT_TOKEN (see Configuration section)
nano .env

# 4. Initialize the database
.venv/bin/alembic upgrade head
# (If you have an existing DB from before Alembic was added: .venv/bin/alembic stamp head)

# 5. Install frontend dependencies
cd ../../frontend
npm install
```

### Agent setup

On each machine that will join the VPN:

```bash
# 1. Copy the agent directory to the machine (or clone the full repo)
#    From the controller machine you can use the deploy script:
cd vishwaas
./deploy-agent.sh user@192.168.10.16   # requires SSH key auth

# 2. Or manually copy:
scp -r agent/ user@192.168.10.16:~/vishwaas-agent/

# 3. On the agent machine: install Python deps
cd ~/vishwaas-agent   # or wherever you put it
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 4. Create the config file
cp agent_config.json.example agent_config.json
nano agent_config.json
```

---

## Configuration

### Controller env vars

File: `controller/backend/.env`

```env
# Required: shared secret used for all controller→agent calls
VISHWAAS_AGENT_TOKEN=change-me-to-a-random-secret

# JWT signing key for dashboard login tokens (change in production)
VISHWAAS_JWT_SECRET=change-me-in-production

# Set to "production" to enable startup safety guards
VISHWAAS_ENVIRONMENT=development

# CORS origin whitelist (comma-separated). * is blocked in production mode.
VISHWAAS_ALLOWED_ORIGINS=http://localhost:3000

# bcrypt hash of the admin password. Empty = accept any login (dev only).
# Generate: python3 -c "import bcrypt; print(bcrypt.hashpw(b'yourpass', bcrypt.gensalt()).decode())"
VISHWAAS_ADMIN_PASSWORD_HASH=

# VPN address pool assigned to nodes
VISHWAAS_VPN_NETWORK=10.10.10.0/24
VISHWAAS_VPN_START=10.10.10.2
VISHWAAS_VPN_END=10.10.10.254

# Optional: JSON structured logging
VISHWAAS_LOG_JSON=false
```

### Agent config file

File: `agent/agent_config.json`

```json
{
  "master_url": "http://192.168.10.15:8000",
  "master_token": "change-me-to-a-random-secret",
  "agent_advertise_url": "http://192.168.10.16:9000",
  "node_name": "auto",
  "wg_interface": "wg0",
  "listen_port": 51820,
  "keys_dir": "./keys",
  "use_tpm_wg_key": false
}
```

| Key | Required | Description |
|-----|----------|-------------|
| `master_url` | Yes | Controller base URL |
| `master_token` | Yes | Must match `VISHWAAS_AGENT_TOKEN` on the controller |
| `agent_advertise_url` | Yes | URL the controller uses to call back to this agent |
| `node_name` | No | `"auto"` uses the machine hostname |
| `wg_interface` | No | WireGuard interface name (default `wg0`) |
| `listen_port` | No | WireGuard UDP listen port (default `51820`) |
| `keys_dir` | No | Directory where WireGuard keys + state are stored |
| `use_tpm_wg_key` | No | Store private key in TPM NV index (requires `tpm2-tools`) |

---

## Running the system

### Start the controller (development)

```bash
cd vishwaas/controller
./start_controller.sh
```

This starts:
- **Backend API**: `http://0.0.0.0:8000`
- **Frontend dashboard**: `http://localhost:3000`

Or start them separately:

```bash
# Terminal 1 — backend
cd controller/backend
.venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — frontend
cd controller/frontend
npm run dev
```

### Start an agent

```bash
cd agent
sudo ./start_agent.sh
```

The agent starts on port 9000. It must run as root (or have CAP_NET_ADMIN) to manage the WireGuard interface.

### Install agent as systemd service (persistent across reboots)

```bash
cd agent
sudo ./install.sh
sudo systemctl status vishwaas-agent
```

---

## Operational workflow

### Step 1 — Start agents on all machines

Each machine runs `sudo ./start_agent.sh`. On startup the agent:
1. Reads `agent_config.json`
2. Generates or loads a WireGuard key pair
3. Sends `POST /request-join` to the controller every 10 seconds until approved

### Step 2 — Approve join requests

1. Open the dashboard: `http://<controller-ip>:3000`
2. Log in (any credentials in dev mode; bcrypt password in production)
3. Go to **Join Requests**
4. Click **Approve** next to each machine
5. The controller assigns a VPN IP (e.g. `10.10.10.2`) and pushes the config to the agent
6. The agent brings up `wg0` with the assigned IP
7. Node status changes to **ACTIVE** on the dashboard

### Step 3 — Connect nodes

By default approved nodes have `wg0` up but no peers — they can't reach each other yet.

1. Go to **Connections** in the dashboard
2. Click **New Connection**
3. Select two nodes and submit
4. Go to **Connection Requests** and approve it
5. The controller calls both agents to add each other as WireGuard peers
6. The nodes can now ping each other on their VPN IPs

### Step 4 — Verify connectivity

From machine A:
```bash
ping 10.10.10.3   # machine B's VPN IP
wg show           # shows peers, handshake time, transfer stats
```

### Terminating a connection

Go to **Connections** → click **Terminate** on a connection.
- The peer keys are removed from both agents
- The `wg0` interface stays up on both machines (they keep their VPN IPs)
- You can reconnect them later by creating a new connection request

### Node lifecycle

```
Agent starts
    │
    ▼
POST /request-join → PENDING join request on dashboard
    │
Admin approves
    │
    ▼
Node = APPROVED → controller pushes VPN IP to agent
    │                (background retries if agent temporarily unreachable)
Agent confirms
    │
    ▼
Node = ACTIVE

Agent goes offline → heartbeat marks OFFLINE after 90s
Agent offline >5min → auto-deleted from DB

Agent restarts → sends new join request → admin must re-approve
```

---

## Dashboard pages

| Page | Purpose |
|------|---------|
| **Overview** | Live stats: active nodes, pending requests, connections, notifications |
| **Nodes** | List of all approved nodes with VPN IPs and status |
| **Join Requests** | Approve or reject machines trying to join the VPN |
| **Connections** | View active connections; terminate them |
| **Connection Requests** | Approve or reject pending connection requests |
| **Network Map** | Force-directed graph of all nodes and their connections; click a node to see live WireGuard stats |
| **Logs** | Immutable audit trail of all events (approvals, rejections, terminations) |

---

## Security model

| Layer | Mechanism |
|-------|-----------|
| Dashboard login | JWT tokens (signed with `VISHWAAS_JWT_SECRET`); logout invalidates the token via a revocation blacklist |
| Controller → Agent calls | `X-VISHWAAS-TOKEN` header; agent rejects calls without a matching token |
| Agent → Controller (join) | No token required — public endpoint; rate-limited to 10 requests/minute per IP |
| Input validation | Node name pattern, WireGuard public key format, agent URL scheme enforced on join |
| CORS | Configured via `VISHWAAS_ALLOWED_ORIGINS`; wildcard blocked in production mode |
| Startup guards | In `VISHWAAS_ENVIRONMENT=production`, the controller refuses to start with default `jwt_secret` or `*` CORS |
| Private keys | Generated locally on each agent; optionally stored in TPM NV index |

---

## Troubleshooting

### Agent keeps sending join requests after approval

Check that the controller successfully pushed the VPN IP. Look at the backend logs:
```
approve_join_request: node_id=X now ACTIVE
```
If you see `set_vpn_address failed, scheduling background retry`, the agent was unreachable at approval time — wait for the retry or restart the agent.

### Node shows as OFFLINE on dashboard

The heartbeat couldn't reach the agent for >90 seconds. Check:
- Is the agent running? `systemctl status vishwaas-agent`
- Is port 9000 open? `curl http://<agent-ip>:9000/health`
- Is `agent_advertise_url` in `agent_config.json` correct (the IP the controller uses to reach this machine)?

### `wg0` has wrong IP after restart

This is handled automatically. When the controller pushes a new VPN IP, the agent removes the old IP from `wg0` before adding the new one.

### Two nodes can't ping each other after connection approval

1. Check both nodes show **ACTIVE** on the dashboard
2. Run `wg show` on both — each should list the other as a peer with a recent handshake
3. Check that UDP port 51820 is open between the two machines (firewall rules)
4. If `wg show` shows no handshake, check that the WireGuard endpoint IPs are correct — these come from `agent_advertise_url` in the agent config

### Controller dashboard shows stale nodes after restart

The heartbeat runs an immediate sweep on startup and marks unreachable nodes OFFLINE within seconds. Wait ~5 seconds after the backend starts.

### Join requests still showing after agent shutdown

Stale PENDING join requests are automatically expired after 120 seconds if the agent is unreachable.

### Database errors after upgrade

If you get Alembic errors on startup, run:
```bash
cd controller/backend
.venv/bin/alembic upgrade head
```
If the DB was created before Alembic was added:
```bash
.venv/bin/alembic stamp head
```

---

## Lab machines (example)

| Machine | IP | Role |
|---------|----|----- |
| machine1 | 192.168.10.15 | Controller + agent |
| machine2 | 192.168.10.16 | Agent |
| machine3 | 192.168.10.17 | Agent |

VPN subnet: `10.10.10.0/24` — nodes get IPs from `.2` upward.

After all three join and connect:
- machine1: `10.10.10.2`
- machine2: `10.10.10.3`
- machine3: `10.10.10.4`
