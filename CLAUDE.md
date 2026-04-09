# VISHWAAS – Claude's Technical Notes

This file is written and maintained by Claude (AI assistant). It documents what was built,
what was changed from the original code, architectural decisions, and context needed to
continue work in future sessions without losing state.

---

## What VISHWAAS Is

A WireGuard VPN orchestration system. Instead of manually editing WireGuard configs on every
machine, each machine runs a lightweight **agent** that requests to join the VPN. A central
**controller** (with a web dashboard) lets an admin approve/reject join requests and create
connections between nodes. The controller pushes all WireGuard config to agents automatically.

**Key principle**: nothing becomes active without explicit admin approval.

---

## Repository Structure

```
vishwaas/
├── controller/                  ← Deploy on the central/admin machine
│   ├── backend/                 ← FastAPI Python backend (port 8000)
│   │   ├── app/
│   │   │   ├── api/routes/      ← HTTP endpoints
│   │   │   ├── core/            ← config, security, heartbeat, metrics, logging, http_client
│   │   │   ├── services/        ← business logic (join_service, connection_service, agent_client)
│   │   │   ├── persistence/     ← SQLAlchemy models + database.py
│   │   │   └── domain/          ← enums (NodeStatus, etc.)
│   │   ├── alembic/             ← DB migrations
│   │   ├── requirements.txt
│   │   └── .env                 ← secrets (gitignored)
│   ├── frontend/                ← React + Vite dashboard (port 3000)
│   ├── start_controller.sh      ← start both backend + frontend
│   ├── nginx.conf               ← production nginx config
│   └── vishwaas-controller.service  ← systemd unit
│
├── agent/                       ← Deploy on each VPN node machine
│   ├── app/
│   │   ├── main.py              ← FastAPI agent + join loop + all endpoints
│   │   ├── config.py            ← loads agent_config.json
│   │   ├── state.py             ← state machine (WAITING/APPROVED/ACTIVE/ERROR)
│   │   ├── wireguard.py         ← all wg/ip commands
│   │   ├── security.py          ← token validation for controller→agent calls
│   │   ├── logger.py            ← structured logging
│   │   └── tpm.py               ← optional TPM key storage
│   ├── agent_config.json        ← per-machine config (gitignored)
│   ├── agent_config.json.example
│   ├── requirements.txt
│   ├── start_agent.sh           ← dev start
│   ├── install.sh               ← installs as systemd service
│   └── vishwaas-agent.service
│
├── deploy-agent.sh              ← automated SSH deploy from controller to agent machine
├── README.md                    ← user-facing README
├── DESIGN.md                    ← flow + key design decisions
└── CLAUDE.md                    ← this file
```

---

## Original Code vs What Was Changed

The original code (commit `08ee1a1`) had a working but insecure/fragile foundation.
Below is every meaningful change made.

### Controller — What Was There Before

- `main.py`: `allow_origins=["*"]`, no auth on any route, `logging.basicConfig` plain text only,
  `create_all()` for DB schema, no startup validation, no metrics, no heartbeat
- `config.py`: no `jwt_secret`, `allowed_origins`, `environment` fields
- `agent_client.py`: new `httpx.AsyncClient` per call (no connection reuse), no retries,
  no correlation ID forwarding
- `join_service.py`: node inserted as `ACTIVE` directly — no two-phase approval
- `connection_service.py`: if `add_peer` to node A succeeded but node B failed, connection
  record was still created (half-broken state)
- `routes/join.py`: no rate limiting, no pagination
- No auth routes, no health endpoints, no metrics, no heartbeat, no Alembic

### Controller — What Was Added / Changed

**Security (`core/`)**
- `security.py` — JWT create/verify with `jti` claim; `RevokedToken` DB lookup on every
  request; `prune_revoked_tokens()` on startup
- `config.py` — added `jwt_secret`, `allowed_origins`, `environment`, `admin_password_hash`
- `main.py` — CORS whitelist from env; production startup guard (exits if insecure defaults);
  `CorrelationMiddleware` (X-Request-ID); `PrometheusMiddleware`; JWT pruning on startup;
  heartbeat task in lifespan; shared HTTP pool init/close

**Auth (`api/routes/auth.py`)**
- `POST /auth/login` — dev mode accepts any creds when no password hash set; production
  checks bcrypt hash
- `POST /auth/logout` — adds token's `jti` to `revoked_tokens` table
- All routes except `/auth/*`, `/health`, `/ready`, `/metrics` require valid JWT

**Reliability (`services/`)**
- `agent_client.py` — shared httpx pool (`core/http_client.py`); `_call_with_retry()` with
  exponential backoff (2 retries, 1s/2s delays); per-call `timeout` param; `X-Request-ID`
  forwarded to agents; Prometheus counter incremented on success/failure
- `join_service.py` — node inserted as `APPROVED` (not `ACTIVE`); only upgraded to `ACTIVE`
  after agent confirms VPN config received
- `connection_service.py` — if `add_peer(node_a)` succeeds but `add_peer(node_b)` fails,
  rollback with `remove_peer(node_a)` — no half-broken connections created
- `connection_service.py` — `terminate_connection_and_teardown` now only calls `remove_peer`
  on both agents; does NOT call `wg_down`. WireGuard interface stays up on both nodes after
  termination. Previous behavior called `wg_down` when a node had no remaining connections,
  which tore down the whole interface — wrong, since the node should remain on the VPN.

**Join lifecycle (`api/routes/join.py`)**
- Rate limited: `@limiter.limit("10/minute")`
- Input validation on `RequestJoinBody`: `node_name` pattern, WireGuard base64 public key,
  `agent_url` scheme check
- **Industry-grade restart handling**: when an agent restarts with the same key, the
  controller tears down all active connections on peer agents, deletes the stale node,
  and creates a fresh `PENDING` request — admin must re-approve every time
- Bug fix: on approval, stamps `node.last_seen = now` before commit — prevents heartbeat from
  immediately auto-deleting a freshly approved node (heartbeat treated `last_seen=None` as
  `seconds_since = infinity > DELETE_THRESHOLD`)

**Heartbeat (`core/heartbeat.py`)**
- Runs every 60 seconds, pings all `ACTIVE`/`APPROVED`/`OFFLINE` nodes
- Stage 1 (90s offline): marks node `OFFLINE` — visible on dashboard
- Stage 2 (5min offline): auto-deletes node + its connections from DB
- Restores `OFFLINE` → `ACTIVE` when node comes back
- Updates Prometheus gauges after each sweep
- **Startup sweep** (`startup=True`): on controller start, runs one immediate sweep that marks
  unreachable nodes OFFLINE right away (no 90s threshold) — dashboard reflects reality instantly
- **Stale join request expiry**: after each sweep, pings agents with PENDING join requests;
  if unreachable for >120s, marks the request REJECTED so it doesn't clutter the dashboard
- Bug fix: nodes with `last_seen=None` (just approved, never seen) are skipped during
  offline/delete logic — prevents immediate auto-delete of freshly approved nodes

**Observability**
- `core/logging_config.py` — `VISHWAAS_LOG_JSON=true` switches to `pythonjsonlogger`
  with `service`/`level` fields; plain text by default
- `core/metrics.py` — `vishwaas_http_requests_total`, `vishwaas_http_request_duration_seconds`,
  `vishwaas_agent_calls_total`, `vishwaas_nodes_active_total`, `vishwaas_nodes_offline_total`,
  `vishwaas_join_requests_pending_total`
- `core/correlation.py` — `ContextVar` for `X-Request-ID`; propagated to all agent calls
- `api/routes/health.py` — `GET /health` (liveness), `GET /ready` (runs `SELECT 1`, 503 if DB down)
- All list endpoints: `skip` + `limit` pagination
- `routes/monitoring.py` — `GET /stats`: fixed `total_nodes` and `active_nodes` to count only
  ACTIVE+APPROVED (previously `total_nodes` counted all nodes including OFFLINE)
- `routes/monitoring.py` — `GET /topology`: fixed to return only ACTIVE+APPROVED nodes
  (previously returned all nodes including OFFLINE, so network map showed stale/dead nodes)

**Database**
- `alembic/` — full migration setup replacing `create_all()`
- `alembic/versions/0001_initial_schema.py` — baseline capturing all tables including
  `revoked_tokens`
- On existing DBs: `alembic stamp head` to mark as already migrated

**Deployment files**
- `controller/nginx.conf` — HTTPS, rate limits, `/metrics` restricted to VPN subnet
- `controller/vishwaas-controller.service` — systemd unit, runs as `vishwaas` user
- `controller/start_controller.sh` — dev/prod launcher
- `controller/backend/.env.example` — documented config template

### Agent — What Was Changed

**`app/state.py`**
- Before: state in-memory only, lost on restart
- After: `set_state()` writes `agent_state.json` to `keys_dir`; `get_state()` reads from
  disk on first call; falls back to `WAITING` if missing/corrupt

**`app/logger.py`**
- Before: plain text only
- After: `VISHWAAS_AGENT_LOG_JSON=true` enables `pythonjsonlogger` with `service`/`level`
  extra fields; falls back to plain text gracefully if package missing

**`app/main.py`**
- Before: `_already_active()` check — if WireGuard was already up, agent skipped join loop
  entirely, never sent a new join request after restart
- After: always starts join loop on startup; controller handles the re-join logic
- `/health` endpoint: before returned `{"status": "ok", "state": "..."}` only; now returns
  `{"status", "state", "wg_interface", "wg_up": bool, "peer_count": int, "vpn_ip": str|null}`

**`app/wireguard.py`** (added in bug-fix session)
- Added `_interface_is_up(iface)` — parses `ip link show` flags between `<` and `>`; returns
  True only if `UP` flag is present. Previous `interface_exists()` returned True for DOWN
  interfaces (only checked return code).
- Added public `interface_is_up()` wrapper (called from `main.py` health endpoint and lifespan).
- Fixed `provision_interface()` when interface already exists: reads all `inet` addresses via
  `ip address show dev <iface>`, removes any that don't match the newly assigned IP before
  adding the correct one — prevents two IPs coexisting on wg0.

**`app/main.py`** (further changes in bug-fix session)
- Removed dead `_already_active()` function (leftover, was not called).
- Fixed `/health` endpoint: uses `wireguard.interface_is_up()` instead of `interface_exists()`.
- Fixed `set_vpn_address` endpoint: always sets `_join_decided = True` when
  `provision_interface()` succeeds, regardless of whether a private key was issued. Previously
  only set when private_key was present — caused infinite join loop re-submissions.
- Added WireGuard teardown in lifespan shutdown: if `interface_is_up()`, calls `wg_down()` so
  the interface doesn't linger after the agent process exits.

**Unchanged in agent**: `config.py`, `security.py`, `tpm.py`

---

## Data Models (SQLite via SQLAlchemy + Alembic)

| Table | Purpose |
|---|---|
| `nodes` | Approved VPN nodes. Status: PENDING→APPROVED→ACTIVE→OFFLINE |
| `join_requests` | Every join attempt. Status: PENDING→APPROVED/REJECTED |
| `connection_requests` | Admin-initiated peer connections. Status: PENDING→APPROVED/REJECTED |
| `connections` | Active WireGuard peer relationships. Status: ACTIVE→TERMINATED |
| `notifications` | Dashboard alerts (join approved, connection approved, etc.) |
| `logs` | Immutable audit trail of all events |
| `revoked_tokens` | JWT blacklist. Pruned at startup of expired entries |

---

## Node Lifecycle (State Machine)

```
Agent starts
    │
    ▼
POST /request-join ──► PENDING join request created
    │                   (if node existed before: old connections torn down first)
    │
Admin approves
    │
    ▼
Node inserted as APPROVED ──► controller pushes VPN IP to agent
    │                          (retries in background if agent unreachable)
    │
Agent confirms
    │
    ▼
Node → ACTIVE

Heartbeat misses node for 90s → OFFLINE (visible on dashboard)
Heartbeat misses node for 5min → auto-deleted from DB

Agent restarts → sends new join request → cycle repeats from PENDING
```

---

## Connection Lifecycle

```
Admin requests connection (node A ↔ node B)
    │
    ▼
ConnectionRequest PENDING
    │
Admin approves
    │
    ▼
add_peer(node_a.agent, node_b.pubkey) ──► if fails: return 502, no record created
    │
add_peer(node_b.agent, node_a.pubkey) ──► if fails: rollback remove_peer(node_a), return 502
    │
Both succeed
    │
    ▼
Connection record ACTIVE

Admin terminates → remove_peer on both agents → Connection TERMINATED
    Both nodes keep their WireGuard interface UP with their VPN IPs intact.
    They return to the same state as "approved but no connections" — still on
    the VPN, just no longer peered with each other.
Node deleted → remove_peer on all connected peers → connections deleted
```

---

## Key Configuration

### Controller (`controller/backend/.env`)
| Variable | Required | Description |
|---|---|---|
| `VISHWAAS_AGENT_TOKEN` | Yes | Shared secret for controller→agent calls |
| `VISHWAAS_JWT_SECRET` | Prod | JWT signing key. Startup aborts if default in production |
| `VISHWAAS_ADMIN_PASSWORD_HASH` | No | bcrypt hash. Empty = accept any login (dev only) |
| `VISHWAAS_ENVIRONMENT` | No | `development` or `production`. Production enables startup guards |
| `VISHWAAS_ALLOWED_ORIGINS` | Prod | CORS whitelist. `*` not allowed in production |
| `VISHWAAS_LOG_JSON` | No | `true` for JSON log output |

### Agent (`agent/agent_config.json`)
| Key | Required | Description |
|---|---|---|
| `master_url` | Yes | Controller base URL e.g. `http://192.168.10.15:8000` |
| `master_token` | Yes | Must match `VISHWAAS_AGENT_TOKEN` on controller |
| `agent_advertise_url` | Yes | This machine's URL so controller can call back |
| `node_name` | No | `"auto"` uses hostname |
| `keys_dir` | No | Where WireGuard keys + state file are stored |
| `use_tpm_wg_key` | No | Store private key in TPM NV index |

---

## How to Run (Dev)

```bash
# Terminal 1 — Backend
cd controller/backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
# First run on existing DB: .venv/bin/alembic stamp head
.venv/bin/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — Frontend
cd controller/frontend
npm install && npm run dev

# Terminal 3 — Agent (on same or different machine)
cd agent
sudo ./start_agent.sh
```

Dashboard: `http://<controller-ip>:3000`  
Login: any username/password in dev mode (no password hash set)

---

## Known Issues / TODOs

- **agent_config.json on agent machines must be manually configured** — `deploy-agent.sh`
  exists to automate this via SSH but requires key-based auth to the target machine
- **No WebSocket / push notifications** — frontend polls every few seconds; dashboard updates
  are not instant
- **Single admin account** — no multi-user auth, no roles
- **SQLite** — fine for small networks (<50 nodes); for larger deployments switch to Postgres
  by changing `VISHWAAS_DATABASE_URL`
- **No TLS between controller and agents** — agent calls use plain HTTP; for production
  put agents behind nginx with TLS or use a VPN tunnel for the management plane itself
- **`alembic stamp head`** must be run manually on existing DBs before first upgrade

---

## Machines in the Current Lab

| Machine | IP | Role |
|---|---|---|
| machine1 | 192.168.10.15 | Controller + agent |
| machine2 | 192.168.10.16 | Agent |
| machine3 | 192.168.10.17 | Agent |

VPN subnet: `10.10.10.0/24`, nodes get IPs from `.2` to `.254`
