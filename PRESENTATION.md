# VISHWAAS — Complete Technical Reference
### For Presentation Preparation

---

## 1. What is VISHWAAS?

**VISHWAAS** is a **WireGuard VPN orchestration system**.

Instead of manually editing WireGuard config files on every machine every time you want two machines to talk to each other, VISHWAAS automates everything through a central admin dashboard.

> **Core principle: Nothing becomes active without explicit admin approval.**

**The problem it solves:**  
Managing a WireGuard mesh manually means editing config files on every machine, distributing public keys by hand, and keeping track of which machines can talk to which. As the network grows, this becomes unmanageable and error-prone.

**What VISHWAAS does instead:**  
- Every machine runs a small agent that asks to join the VPN
- Admin approves/rejects from a web dashboard
- Controller pushes all WireGuard config automatically
- Admin connects two nodes from the dashboard — done, no SSH needed

---

## 2. Big Picture: How Everything Fits Together

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              ADMIN'S BROWSER                                    │
│                                                                                  │
│                     ┌──────────────────────────┐                                │
│                     │   React Dashboard (3000)  │                                │
│                     │  Join Requests | Nodes    │                                │
│                     │  Connections  | Network   │                                │
│                     └───────────┬──────────────┘                                │
└───────────────────────────────  │  ─────────────────────────────────────────────┘
                                  │  HTTPS / HTTP
                            ┌─────▼──────────────────────────────────────────────┐
                            │          CONTROLLER MACHINE (192.168.10.15)         │
                            │                                                      │
                            │  ┌────────────────────────────────────────────────┐ │
                            │  │         FastAPI Backend (port 8000)             │ │
                            │  │                                                  │ │
                            │  │  ┌──────────┐  ┌───────────┐  ┌─────────────┐ │ │
                            │  │  │ Auth     │  │ Join      │  │ Connections │ │ │
                            │  │  │ Routes   │  │ Routes    │  │ Routes      │ │ │
                            │  │  └──────────┘  └───────────┘  └─────────────┘ │ │
                            │  │                                                  │ │
                            │  │  ┌──────────────────────────────────────────┐  │ │
                            │  │  │  Core Services                            │  │ │
                            │  │  │  • Heartbeat loop (60s)                  │  │ │
                            │  │  │  • JWT Security                          │  │ │
                            │  │  │  • Prometheus Metrics                    │  │ │
                            │  │  │  • Correlation ID middleware              │  │ │
                            │  │  └──────────────────────────────────────────┘  │ │
                            │  │                                                  │ │
                            │  │  ┌──────────────────────────────────────────┐  │ │
                            │  │  │  SQLite DB (via SQLAlchemy + Alembic)     │  │ │
                            │  │  │  nodes | join_requests | connections      │  │ │
                            │  │  │  revoked_tokens | logs | notifications    │  │ │
                            │  │  └──────────────────────────────────────────┘  │ │
                            │  └────────────────────────────────────────────────┘ │
                            └───────────────────┬────────────────────────────────┘
                                                 │  X-VISHWAAS-TOKEN (shared secret)
                       ┌─────────────────────────┼──────────────────────────┐
                       │                          │                          │
              ┌────────▼──────────┐   ┌──────────▼────────┐   ┌────────────▼──────┐
              │  AGENT MACHINE 1  │   │  AGENT MACHINE 2  │   │  AGENT MACHINE 3  │
              │  (192.168.10.15)  │   │  (192.168.10.16)  │   │  (192.168.10.17)  │
              │  Agent port 9000  │   │  Agent port 9000  │   │  Agent port 9000  │
              │                   │   │                   │   │                   │
              │  ┌─────────────┐  │   │  ┌─────────────┐ │   │  ┌─────────────┐  │
              │  │  wg0        │  │   │  │  wg0        │ │   │  │  wg0        │  │
              │  │ 10.10.10.2  │  │   │  │ 10.10.10.3  │ │   │  │ 10.10.10.4  │  │
              │  └──────┬──────┘  │   │  └──────┬──────┘ │   │  └──────┬──────┘  │
              └─────────│─────────┘   └──────────│────────┘   └─────────│─────────┘
                        │                         │                       │
                        └─────────── WireGuard UDP :51820 ───────────────┘
                                    (encrypted peer-to-peer traffic)
```

---

## 3. The Two Components

### 3A. The CONTROLLER

Deployed on **one central machine**. Has two parts:

| Part | Tech | Port | Purpose |
|------|------|------|---------|
| Backend API | Python + FastAPI | 8000 | All business logic, DB, agent communication |
| Frontend Dashboard | React + Vite | 3000 | Admin web UI |

The controller:
- Stores all state in a SQLite database
- Receives join requests from agents
- Lets admin approve/reject via the web UI
- Pushes WireGuard config to agents over HTTP
- Runs a heartbeat loop to detect dead nodes
- Exposes Prometheus metrics at `/metrics`

### 3B. The AGENT

Deployed on **every machine** that should join the VPN. It is a small FastAPI app.

```
┌──────────────────────────────────────────────────────────────┐
│                    AGENT (port 9000)                          │
│                                                               │
│  On startup:                                                  │
│  1. Generate WireGuard keypair (if not exists)                │
│  2. If wg0 already up: mark ACTIVE, skip join loop            │
│  3. Otherwise: start join loop (POST to controller every 10s) │
│                                                               │
│  Endpoints (all except /health require X-VISHWAAS-TOKEN):     │
│  POST /set-vpn-address   ← controller assigns VPN IP          │
│  POST /peer              ← controller adds a peer             │
│  DELETE /peer            ← controller removes a peer          │
│  POST /wg/start          ← bring up wg0                       │
│  POST /wg/stop           ← bring down wg0                     │
│  GET  /wg/status         ← status and peer info               │
│  POST /remove-node       ← full node teardown                 │
│  GET  /logs              ← last N log lines                   │
│  GET  /health            ← state + wg_up + peer_count + vpn_ip│
└──────────────────────────────────────────────────────────────┘
```

---

## 4. Repository Structure (Annotated)

```
vishwaas/
│
├── controller/
│   ├── backend/
│   │   ├── app/
│   │   │   ├── api/
│   │   │   │   ├── routes/
│   │   │   │   │   ├── auth.py         ← POST /auth/login, POST /auth/logout
│   │   │   │   │   ├── join.py         ← POST /request-join, GET/PATCH join requests
│   │   │   │   │   ├── nodes.py        ← GET/DELETE nodes
│   │   │   │   │   ├── connections.py  ← connection requests + connections CRUD
│   │   │   │   │   ├── monitoring.py   ← GET /stats, GET /topology
│   │   │   │   │   └── health.py       ← GET /health, GET /ready
│   │   │   │   └── schemas.py          ← Pydantic request/response models
│   │   │   │
│   │   │   ├── core/
│   │   │   │   ├── config.py           ← Settings (reads .env via pydantic-settings)
│   │   │   │   ├── security.py         ← JWT create/verify/revoke, require_auth dep
│   │   │   │   ├── heartbeat.py        ← Background task: ping all nodes every 60s
│   │   │   │   ├── metrics.py          ← Prometheus counters/histograms/gauges
│   │   │   │   ├── correlation.py      ← ContextVar for X-Request-ID propagation
│   │   │   │   ├── logging_config.py   ← Plain text or JSON logging (env-controlled)
│   │   │   │   ├── http_client.py      ← Shared httpx pool (created once, reused)
│   │   │   │   └── rate_limiter.py     ← slowapi limiter instance
│   │   │   │
│   │   │   ├── services/
│   │   │   │   ├── join_service.py         ← approve_join, reject_join, IP allocation
│   │   │   │   ├── connection_service.py   ← approve/reject/terminate connections
│   │   │   │   ├── agent_client.py         ← HTTP calls to agents (with retry)
│   │   │   │   └── log_notify.py           ← Create audit log + notification records
│   │   │   │
│   │   │   ├── persistence/
│   │   │   │   ├── models.py               ← SQLAlchemy ORM models (7 tables)
│   │   │   │   └── database.py             ← Engine, SessionLocal, init_db, get_db
│   │   │   │
│   │   │   ├── domain/
│   │   │   │   └── enums.py                ← NodeStatus, ConnectionStatus, etc.
│   │   │   │
│   │   │   └── main.py                     ← FastAPI app, middleware, lifespan
│   │   │
│   │   ├── alembic/                        ← DB migration history
│   │   │   └── versions/
│   │   │       └── 0001_initial_schema.py  ← Baseline migration
│   │   │
│   │   ├── tests/                          ← 87-test pytest suite
│   │   └── .env                            ← Secrets (gitignored)
│   │
│   ├── frontend/                           ← React + Vite
│   ├── nginx.conf                          ← Production nginx (HTTPS + rate limits)
│   └── vishwaas-controller.service         ← systemd unit
│
├── agent/
│   ├── app/
│   │   ├── main.py         ← FastAPI app, join loop, all endpoints
│   │   ├── config.py       ← Loads agent_config.json
│   │   ├── state.py        ← State machine persisted to disk (agent_state.json)
│   │   ├── wireguard.py    ← All wg/ip commands (keypair, provision, peers, status)
│   │   ├── security.py     ← Token check + ControllerIPMiddleware
│   │   ├── logger.py       ← Structured logging + rotating file log
│   │   └── tpm.py          ← Optional: store private key in TPM NV index
│   │
│   ├── agent_config.json.example
│   ├── requirements.txt
│   ├── start_agent.sh          ← Dev start (sudo python -m uvicorn)
│   └── install.sh              ← Installs as systemd service
│
├── deploy-agent.sh             ← SSH-based automated deploy from controller
├── vishwaas_paper.tex          ← Academic paper (LaTeX)
└── SRS.md                      ← Software Requirements Specification
```

---

## 5. Database: 7 Tables

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                             DATABASE SCHEMA                                  │
│                                                                               │
│  ┌─────────────────────────────────┐                                         │
│  │ nodes                           │                                         │
│  │─────────────────────────────────│                                         │
│  │ id         INTEGER PK           │                                         │
│  │ name       VARCHAR(255)         │                                         │
│  │ public_key VARCHAR(512) UNIQUE  │  ← WireGuard public key                 │
│  │ agent_url  VARCHAR(512)         │  ← How controller reaches this agent    │
│  │ vpn_ip     VARCHAR(45)  UNIQUE  │  ← Assigned VPN IP (10.10.10.x)        │
│  │ status     ENUM                 │  ← APPROVED|ACTIVE|OFFLINE              │
│  │ is_gateway INTEGER              │  ← 1 = hub node for spoke routing       │
│  │ last_seen  DATETIME             │  ← Updated by heartbeat                 │
│  │ created_at DATETIME             │                                         │
│  └─────────────────────────────────┘                                         │
│                                                                               │
│  ┌─────────────────────────────────┐                                         │
│  │ join_requests                   │                                         │
│  │─────────────────────────────────│                                         │
│  │ id          INTEGER PK          │                                         │
│  │ node_name   VARCHAR(255)        │                                         │
│  │ public_key  VARCHAR(512)        │                                         │
│  │ agent_url   VARCHAR(512)        │                                         │
│  │ status      ENUM                │  ← PENDING|APPROVED|REJECTED            │
│  │ requested_at DATETIME           │                                         │
│  └─────────────────────────────────┘                                         │
│                                                                               │
│  ┌──────────────────────────────────────────────────────────┐                │
│  │ connection_requests                                       │                │
│  │──────────────────────────────────────────────────────────│                │
│  │ id           INTEGER PK                                   │                │
│  │ requester_id INTEGER FK → nodes.id                       │                │
│  │ target_id    INTEGER FK → nodes.id                       │                │
│  │ status       ENUM   PENDING|APPROVED|REJECTED             │                │
│  │ requested_at DATETIME                                     │                │
│  └──────────────────────────────────────────────────────────┘                │
│                                                                               │
│  ┌──────────────────────────────────────────────────────────┐                │
│  │ connections                                               │                │
│  │──────────────────────────────────────────────────────────│                │
│  │ id         INTEGER PK                                     │                │
│  │ node_a_id  INTEGER FK → nodes.id                         │                │
│  │ node_b_id  INTEGER FK → nodes.id                         │                │
│  │ status     ENUM   ACTIVE|TERMINATED                       │                │
│  │ created_at DATETIME                                       │                │
│  └──────────────────────────────────────────────────────────┘                │
│                                                                               │
│  ┌────────────────────┐  ┌────────────────────┐  ┌──────────────────────┐   │
│  │ notifications      │  │ logs               │  │ revoked_tokens       │   │
│  │────────────────────│  │────────────────────│  │──────────────────────│   │
│  │ id                 │  │ id                 │  │ jti    VARCHAR PK    │   │
│  │ type  ENUM         │  │ event_type ENUM    │  │ revoked_at DATETIME  │   │
│  │ message TEXT       │  │ description TEXT   │  │ expires_at DATETIME  │   │
│  │ is_read INTEGER    │  │ performed_by TEXT  │  └──────────────────────┘   │
│  │ created_at         │  │ created_at         │                             │
│  └────────────────────┘  └────────────────────┘                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Node Status Lifecycle

```
                    ┌─────────────────────────────┐
                    │   Agent starts / restarts    │
                    └──────────────┬──────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │  POST /request-join           │
                    │  every 10 seconds until       │
                    │  controller responds          │
                    └──────────────┬───────────────┘
                                   │
                          ┌────────▼────────┐
                          │    PENDING       │  ← Join request in DB
                          └────────┬────────┘
                                   │
               ┌───────────────────┴───────────────────┐
               │ Admin clicks APPROVE                   │ Admin clicks REJECT
               ▼                                        ▼
   ┌─────────────────────────┐              ┌────────────────────┐
   │        APPROVED          │              │      REJECTED       │
   │  Node added to DB        │              │  No node created    │
   │  VPN IP assigned         │              │  Agent stops trying │
   │  Controller pushes IP    │              └────────────────────┘
   │  to agent                │
   └────────────┬────────────┘
                │
                │ Agent receives /set-vpn-address
                │ wg0 comes up with assigned IP
                ▼
   ┌─────────────────────────┐
   │         ACTIVE           │  ← Normal running state
   │  WireGuard interface up  │  ← Peers can be added/removed
   │  last_seen updated by    │
   │  heartbeat every 60s     │
   └────────────┬────────────┘
                │
                │ Heartbeat can't reach agent for 90 seconds
                ▼
   ┌─────────────────────────┐
   │         OFFLINE          │  ← Visible on dashboard
   └────────────┬────────────┘
                │
      ┌─────────┴──────────────────────┐
      │ Agent comes back               │ Still offline after 5 minutes
      ▼                                ▼
   ACTIVE again               Auto-deleted from DB
   (connections restored)     (all connections deleted too)
```

---

## 7. Join Flow — Step by Step

```
  AGENT MACHINE                    CONTROLLER                      ADMIN
       │                                │                             │
       │  (startup)                     │                             │
       │  generate keypair              │                             │
       │  (if not exists)               │                             │
       │                                │                             │
       │──── POST /request-join ───────►│                             │
       │     {node_name, public_key,    │                             │
       │      agent_url}                │                             │
       │                                │  Creates JoinRequest        │
       │                                │  status=PENDING             │
       │◄──── {status: "PENDING"} ─────│                             │
       │                                │                             │
       │  (wait 10s, retry...)          │  Dashboard shows request ──►│
       │──── POST /request-join ───────►│                             │
       │◄──── {status: "PENDING"} ─────│                             │
       │                                │                             │
       │  (wait 10s...)                 │◄── Admin clicks APPROVE ───│
       │                                │                             │
       │                                │  1. Assign next free VPN IP │
       │                                │     (e.g. 10.10.10.3)       │
       │                                │  2. Create Node in DB        │
       │                                │     status=APPROVED          │
       │                                │  3. Stamp last_seen=now      │
       │                                │     (prevents immediate      │
       │                                │      heartbeat deletion)     │
       │                                │                             │
       │◄──── POST /set-vpn-address ───│                             │
       │      {vpn_ip: "10.10.10.3",   │                             │
       │       private_key: ...}        │                             │
       │                                │                             │
       │  provision_interface():        │                             │
       │  • create wg0                  │                             │
       │  • set private key             │                             │
       │  • assign 10.10.10.3/24       │                             │
       │  • ip link set wg0 up          │                             │
       │  • _join_decided = True        │                             │
       │  • state = ACTIVE              │                             │
       │                                │                             │
       │────── 200 OK ─────────────────►│                             │
       │                                │  Node status → ACTIVE       │
       │                                │  Notification created ─────►│
       │                                │                             │
```

**Key details:**
- Agent sends join request every **10 seconds** until controller responds with APPROVED or REJECTED
- Controller rate-limits join requests to **10 per minute per IP**
- If agent restarts with the same key, controller **tears down all old connections first**, then creates a fresh PENDING request — admin must re-approve
- Input validation: node name pattern, WireGuard base64 key format, agent URL must use HTTP/HTTPS

---

## 8. Connection Flow — Step by Step

```
  AGENT A (10.10.10.2)            CONTROLLER              AGENT B (10.10.10.3)     ADMIN
          │                           │                           │                   │
          │                           │◄──── Admin creates ──────────────────────────│
          │                           │      connection request                       │
          │                           │      NodeA ↔ NodeB                           │
          │                           │                                               │
          │                           │      ConnectionRequest                        │
          │                           │      status=PENDING                           │
          │                           │                                               │
          │                           │◄──── Admin APPROVES ─────────────────────────│
          │                           │                                               │
          │                           │  1. Call agent A: add peer B                 │
          │◄── POST /peer ────────────│                                               │
          │    {public_key: B's key,  │                                               │
          │     allowed_ips: B's IP,  │                                               │
          │     endpoint: B's addr}   │                                               │
          │                           │                                               │
          │  wg set wg0 peer B...     │                                               │
          │  (peer added to kernel)   │                                               │
          │────── 200 OK ─────────────►│                                               │
          │                           │                                               │
          │                           │  2. Call agent B: add peer A                 │
          │                           │──── POST /peer ──────────────────────────────►│
          │                           │     {public_key: A's key,                     │
          │                           │      allowed_ips: A's IP,                     │
          │                           │      endpoint: A's addr}                      │
          │                           │                                               │
          │                           │                    wg set wg0 peer A...       │
          │                           │◄────── 200 OK ────────────────────────────────│
          │                           │                                               │
          │                           │  3. Create Connection record                  │
          │                           │     status=ACTIVE                             │
          │                           │                                               │
          │◄══════════════════ WireGuard UDP tunnel established ═════════════════════►│
          │                (encrypted, direct peer-to-peer)                           │
```

**Atomic rollback:** If step 2 (agent B) fails, the controller immediately calls agent A to **remove** the peer it just added. No half-broken connections are ever committed to the DB.

---

## 9. Connection Termination

```
  AGENT A                         CONTROLLER                  AGENT B
      │                               │                           │
      │                               │◄── Admin clicks TERMINATE │
      │                               │                           │
      │◄── DELETE /peer ──────────────│                           │
      │    {public_key: B's key}      │                           │
      │  wg set wg0 peer B remove     │                           │
      │──── 200 OK ───────────────────►│                           │
      │                               │──── DELETE /peer ─────────►│
      │                               │     {public_key: A's key}  │
      │                               │◄─── 200 OK ───────────────│
      │                               │                           │
      │                               │  Connection → TERMINATED  │
      │                               │                           │
      │  wg0 stays UP                 │                   wg0 stays UP
      │  VPN IP kept (10.10.10.2)     │         VPN IP kept (10.10.10.3)
      │  (no more peer B though)      │         (no more peer A though)
```

**Important:** WireGuard interface is NOT torn down. Both machines stay on the VPN, just no longer peered with each other. Admin can re-create the connection later.

---

## 10. Heartbeat System

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      HEARTBEAT LOOP (core/heartbeat.py)                      │
│                                                                               │
│  Runs forever in background:                                                  │
│                                                                               │
│  On controller startup:                                                       │
│  ┌─ startup sweep ──────────────────────────────────────────────────────┐   │
│  │  Ping ALL ACTIVE/APPROVED nodes immediately                           │   │
│  │  Any node that doesn't respond → OFFLINE right away (no 90s wait)    │   │
│  │  Dashboard reflects reality within seconds of controller starting     │   │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                               │
│  Then every 60 seconds:                                                       │
│                                                                               │
│  ┌─ regular sweep ──────────────────────────────────────────────────────┐   │
│  │                                                                        │   │
│  │  For each ACTIVE/APPROVED/OFFLINE node:                                │   │
│  │                                                                        │   │
│  │    GET /health ────────────────────────────────────────────────────   │   │
│  │       │                                                                │   │
│  │       ├── 2xx ──► update last_seen = now                               │   │
│  │       │           if was OFFLINE: restore to ACTIVE                   │   │
│  │       │                                                                │   │
│  │       └── fail ─► check last_seen:                                    │   │
│  │                   • last_seen=None (just approved): skip               │   │
│  │                   • > 90s ago: mark OFFLINE                           │   │
│  │                   • > 300s ago: AUTO-DELETE node + all connections     │   │
│  │                                                                        │   │
│  │  For each PENDING join request:                                        │   │
│  │    GET /health on agent                                                │   │
│  │    If unreachable for >120s: mark REJECTED (clears stale UI)          │   │
│  │                                                                        │   │
│  │  Prune audit logs older than retention period                          │   │
│  │  Update Prometheus gauges                                              │   │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘

  Timeline:
  t=0s   Agent goes offline
  t=90s  Marked OFFLINE (admin sees yellow/red on dashboard)
  t=300s Auto-deleted (all connections removed too)
```

---

## 11. Agent Restart Handling

```
  Before restart                    On restart                  After
  ─────────────                     ──────────                  ─────

  Node A: ACTIVE                    Agent starts               Node A: PENDING
  Connections: A↔B, A↔C            ↓                          (fresh slate)
                                    wg0 already up?
                                    vpn_ip file exists?
                                    ↓ Yes → skip join loop    → ACTIVE (resume)
                                    ↓ No  →
                                    POST /request-join
                                    ↓
                                    Controller checks:
                                    "Does this public_key exist
                                     in nodes table already?"
                                    ↓ Yes →
                                    1. Call remove_peer on B, C
                                       (tear down old connections)
                                    2. Delete old node from DB
                                    3. Delete old connections from DB
                                    4. Create fresh PENDING request
                                    ↓
                                    Admin must re-approve
```

**Why full re-approval?** A restart might mean the machine rebooted, got a new IP, or was compromised. Admin explicitly re-authorizes every time.

---

## 12. Security Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SECURITY LAYERS                                       │
│                                                                               │
│  Layer 1: Network perimeter (nginx.conf)                                     │
│  ────────────────────────────────────────────────────────────────────────   │
│  • RFC-1918 private IP check (geo module)                                    │
│  • All /api/* management endpoints: 403 for public internet IPs              │
│  • /api/health and /api/ready: public (load balancer probes)                 │
│  • /metrics: restricted to VPN subnet (10.10.10.0/24)                       │
│  • Rate limiting at nginx level (10r/s burst 20)                             │
│                                                                               │
│  Layer 2: Agent IP whitelist (ControllerIPMiddleware)                        │
│  ────────────────────────────────────────────────────────────────────────   │
│  • Every request to the agent (except /health) checked against               │
│    controller's IP (parsed from master_url in config)                        │
│  • 403 if source IP doesn't match                                            │
│  • 127.0.0.1 and ::1 always allowed (same-machine deployments)              │
│                                                                               │
│  Layer 3: Controller API authentication (JWT)                                │
│  ────────────────────────────────────────────────────────────────────────   │
│  • Dashboard login → POST /auth/login → JWT token (HS256)                   │
│  • JWT contains: sub (username), exp (expiry), jti (unique ID)              │
│  • All routes except /auth/*, /health, /ready, /metrics require JWT         │
│  • Logout → jti added to revoked_tokens table → token immediately invalid   │
│  • On startup: prune expired entries from revoked_tokens                    │
│  • Production: refuses to start with default JWT secret                     │
│                                                                               │
│  Layer 4: Controller → Agent authentication (shared token)                  │
│  ────────────────────────────────────────────────────────────────────────   │
│  • VISHWAAS_AGENT_TOKEN (set on controller)                                  │
│  • master_token (set on each agent, must match)                              │
│  • Every call controller makes to agent: X-VISHWAAS-TOKEN header            │
│  • Agent rejects (401) any request without valid token                      │
│                                                                               │
│  Layer 5: Input validation                                                   │
│  ────────────────────────────────────────────────────────────────────────   │
│  • node_name: pattern check (alphanumeric + hyphen/underscore)               │
│  • public_key: WireGuard base64 format validated                             │
│  • agent_url: must use http:// or https:// scheme                           │
│  • Rate limit: 10 join requests per minute per IP                           │
│                                                                               │
│  Layer 6: Private key protection                                             │
│  ────────────────────────────────────────────────────────────────────────   │
│  • Private key generated locally on agent machine                           │
│  • Stored in keys_dir (chmod 600)                                           │
│  • NEVER exposed via any API endpoint                                       │
│  • Optional: store in TPM NV index (tpm.py)                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 13. Agent — Internal State Machine

```
  State persisted to disk: agent_state.json (survives restarts)

  ┌─────────┐    generate_keypair()     ┌─────────┐
  │  (start) │ ──────────────────────► │ WAITING │
  └─────────┘                           └────┬────┘
                                              │
                                   POST /request-join
                                   every 10s
                                              │
                              ┌───────────────┼───────────────┐
                              │ APPROVED       │ REJECTED       │ error
                              ▼               ▼               ▼
                          ┌────────┐     ┌────────┐      ┌───────┐
                          │APPROVED│     │(stops) │      │ ERROR │
                          └────┬───┘     └────────┘      └───────┘
                               │
              /set-vpn-address received,
              wg0 successfully provisioned
                               │
                               ▼
                          ┌────────┐
                          │ ACTIVE │ ◄─── /peer add called (stays ACTIVE)
                          └────────┘
```

---

## 14. WireGuard Layer — What Actually Happens in the Kernel

```
  Before connection approval:
  ┌──────────────────────────────┐      ┌──────────────────────────────┐
  │  Machine A (10.10.10.2)       │      │  Machine B (10.10.10.3)       │
  │                               │      │                               │
  │  wg0: UP                      │      │  wg0: UP                      │
  │  IP: 10.10.10.2/24           │      │  IP: 10.10.10.3/24           │
  │  listen_port: 51820           │      │  listen_port: 51820           │
  │  peers: (none)                │      │  peers: (none)                │
  └──────────────────────────────┘      └──────────────────────────────┘

  After connection approval:
  ┌──────────────────────────────┐      ┌──────────────────────────────┐
  │  Machine A (10.10.10.2)       │      │  Machine B (10.10.10.3)       │
  │                               │      │                               │
  │  wg0: UP                      │      │  wg0: UP                      │
  │  IP: 10.10.10.2/24           │      │  IP: 10.10.10.3/24           │
  │  listen_port: 51820           │      │  listen_port: 51820           │
  │  peers:                       │      │  peers:                       │
  │    pubkey: B's key            │      │    pubkey: A's key            │
  │    allowed-ips: 10.10.10.3/32 │      │    allowed-ips: 10.10.10.2/32 │
  │    endpoint: 192.168.10.16:   │      │    endpoint: 192.168.10.15:   │
  │             51820             │      │             51820             │
  │    keepalive: 25s             │      │    keepalive: 25s             │
  └──────────────────────────────┘      └──────────────────────────────┘

  What the controller actually runs (via agent HTTP calls):
    POST /peer on Agent A:
      wg set wg0 peer <B_pubkey> allowed-ips 10.10.10.3/32
                                  endpoint 192.168.10.16:51820
                                  persistent-keepalive 25

    POST /peer on Agent B:
      wg set wg0 peer <A_pubkey> allowed-ips 10.10.10.2/32
                                  endpoint 192.168.10.15:51820
                                  persistent-keepalive 25
```

---

## 15. Hub-and-Spoke Routing (Gateway Mode)

```
  Standard peer-to-peer (default):          Hub-and-spoke (is_gateway=1):
  Each node knows only its direct peers.     Spoke routes ALL VPN traffic via hub.

  A ──── B                                   A ────────► HUB ◄──────── B
  │      │                                   │          │ │              │
  └── C  │                                   C ─────────┘ └──────────── D
         └── D
                                             HUB has: is_gateway=1
                                             ip_forward enabled (sysctl)
                                             Spokes get: allowed-ips 10.10.10.0/24 (full subnet)
                                             Hub gets: /32 per spoke

  When is_gateway is set on node_b:
    Agent A (spoke) gets: allowed_ips = vpn_subnet (routes full /24 via hub)
    Agent B (hub)   gets: allowed_ips = A's IP /32 (normal peer entry)
    Controller also calls: POST /ip-forward/enable on hub's agent
      → sysctl -w net.ipv4.ip_forward=1
```

---

## 16. Controller Agent Client — Reliability

```
  agent_client.py (services layer)

  Every outbound HTTP call to an agent:
  ┌──────────────────────────────────────────────────────────────┐
  │  Shared httpx.AsyncClient (created once at startup,          │
  │  reused for all agent calls — connection pooling)            │
  │                                                              │
  │  _call_with_retry(url, method, body, timeout):               │
  │    Attempt 1 ──────────────────────────────────────────────► │
  │       │ failure                                              │
  │    wait 1s                                                   │
  │    Attempt 2 ──────────────────────────────────────────────► │
  │       │ failure                                              │
  │    wait 2s                                                   │
  │    Attempt 3 ──────────────────────────────────────────────► │
  │       │ failure → return False                               │
  │                                                              │
  │  On every call:                                              │
  │  • X-VISHWAAS-TOKEN header attached                         │
  │  • X-Request-ID header forwarded (correlation)              │
  │  • Prometheus counter incremented (success/fail)            │
  └──────────────────────────────────────────────────────────────┘
```

---

## 17. Observability Stack

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           OBSERVABILITY                                       │
│                                                                               │
│  Structured Logging                                                           │
│  ──────────────────────────────────────────────────────────────────────────  │
│  VISHWAAS_LOG_JSON=false  →  plain text (default)                            │
│  VISHWAAS_LOG_JSON=true   →  JSON lines with service/level/timestamp fields  │
│  Same env var on agent:   VISHWAAS_AGENT_LOG_JSON=true                       │
│  Agent also writes rotating log to keys_dir/agent.log                       │
│  Admin can read it via:   GET /logs?n=200                                    │
│                                                                               │
│  Request Correlation (core/correlation.py)                                   │
│  ──────────────────────────────────────────────────────────────────────────  │
│  Every incoming request:                                                     │
│    X-Request-ID header present? → use it                                    │
│    Not present? → generate UUID4                                             │
│  Stored in Python ContextVar (thread-safe async)                             │
│  Forwarded to every agent call the controller makes                          │
│  Returns in X-Request-ID response header                                    │
│  Result: one request traceable across controller + all agent calls           │
│                                                                               │
│  Prometheus Metrics (GET /metrics)                                           │
│  ──────────────────────────────────────────────────────────────────────────  │
│  vishwaas_http_requests_total          Counter  {method, path, status_code}  │
│  vishwaas_http_request_duration_seconds Histogram {method, path}             │
│  vishwaas_agent_calls_total            Counter  {operation, success}         │
│  vishwaas_nodes_active_total           Gauge    (updated by heartbeat)       │
│  vishwaas_nodes_offline_total          Gauge    (updated by heartbeat)       │
│  vishwaas_join_requests_pending_total  Gauge    (updated by heartbeat)       │
│                                                                               │
│  Health Endpoints                                                             │
│  ──────────────────────────────────────────────────────────────────────────  │
│  GET /health   → liveness (always 200)                                      │
│  GET /ready    → readiness (runs SELECT 1; 503 if DB down)                  │
│                                                                               │
│  Dashboard (React frontend)                                                   │
│  ──────────────────────────────────────────────────────────────────────────  │
│  Overview    → live stats (nodes, pending requests, connections)             │
│  Nodes       → all nodes with VPN IPs + status                              │
│  Join Req.   → approve/reject pending machines                              │
│  Connections → view + terminate active connections                          │
│  Conn Req.   → approve/reject pending connection requests                  │
│  Network Map → force-directed graph; click node for WireGuard live stats    │
│  Logs        → immutable audit trail of all admin actions                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 18. Authentication Flow

```
  LOGIN:
  ┌──────────┐           ┌────────────────────────────────────────┐
  │  Browser  │           │  Controller backend                     │
  │           │           │                                         │
  │ POST      │           │  DEV mode (no password hash set):       │
  │ /auth/    │──────────►│  → accept any credentials              │
  │ login     │           │  → return JWT                          │
  │           │           │                                         │
  │           │           │  PROD mode (hash set):                 │
  │           │           │  → bcrypt.checkpw(plain, hash)         │
  │           │           │  → return JWT if match                 │
  │           │           │  → 401 if no match                     │
  │           │◄──────────│                                         │
  │  JWT      │           │  JWT payload:                          │
  │  token    │           │  { sub: "admin",                       │
  │           │           │    exp: now + 480min,                  │
  │           │           │    jti: "abc123..." (random) }         │
  └──────────┘           └────────────────────────────────────────┘

  Every subsequent request:
  Authorization: Bearer <jwt>  ──► _decode_token() verifies signature + expiry
                                   + checks jti NOT in revoked_tokens table

  LOGOUT:
  POST /auth/logout  ──► extract jti from token
                         INSERT INTO revoked_tokens (jti, expires_at)
                         token is immediately unusable even before expiry
```

---

## 19. Controller Startup Sequence

```
  Controller starts
  │
  ├─ 1. Configure logging (plain text or JSON)
  │
  ├─ 2. Validate config:
  │      • Is VISHWAAS_AGENT_TOKEN set? (warning if not)
  │      • If environment=production:
  │           abort if JWT secret = default
  │           abort if no admin_password_hash
  │           abort if CORS = *
  │           abort if CORS contains localhost
  │
  ├─ 3. init_db():
  │      • Connect to SQLite
  │      • Alembic handles schema (not create_all)
  │
  ├─ 4. prune_revoked_tokens():
  │      • Delete expired JWT blacklist entries from last session
  │
  ├─ 5. init_client():
  │      • Create shared httpx.AsyncClient (agent HTTP pool)
  │
  ├─ 6. heartbeat_loop() as background task:
  │      • Immediate startup sweep (marks dead nodes OFFLINE fast)
  │      • Then every 60s
  │
  └─ 7. Accept HTTP traffic
```

---

## 20. Agent Startup Sequence

```
  Agent starts
  │
  ├─ 1. Load agent_config.json
  │
  ├─ 2. Set up rotating log file (keys_dir/agent.log)
  │
  ├─ 3. generate_keypair():
  │      • Run: wg genkey → private key
  │      • Run: wg pubkey → public key
  │      • Store both files (chmod 600 / 644)
  │      • Optionally: write private key to TPM NV
  │
  ├─ 4. Check if already provisioned:
  │      • vpn_ip file exists in keys_dir?
  │      • wg0 interface is UP?
  │      └─ YES: set state=ACTIVE, skip join loop
  │      └─ NO: start join loop
  │
  ├─ 5. Join loop (background task):
  │      • POST /request-join every 10s
  │      • Parse response status
  │      • PENDING: keep looping
  │      • APPROVED: provision interface, stop loop
  │      • REJECTED: stop loop
  │
  └─ 6. ControllerIPMiddleware on all requests
         (blocks non-controller IPs from reaching agent API)

  On shutdown:
  • Cancel join loop task
  • If wg0 is UP: wg_down() (clean teardown)
```

---

## 21. API Endpoint Reference

### Controller Backend

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/login` | None | Get JWT token |
| POST | `/auth/logout` | JWT | Revoke current token |
| GET | `/health` | None | Liveness probe |
| GET | `/ready` | None | Readiness probe (checks DB) |
| GET | `/metrics` | None* | Prometheus metrics |
| POST | `/request-join` | None** | Agent sends join request |
| GET | `/join-requests` | JWT | List join requests (paginated) |
| PATCH | `/join-requests/{id}/approve` | JWT | Approve a join request |
| PATCH | `/join-requests/{id}/reject` | JWT | Reject a join request |
| GET | `/nodes` | JWT | List all nodes |
| DELETE | `/nodes/{id}` | JWT | Delete a node |
| POST | `/connection-requests` | JWT | Create connection request |
| GET | `/connection-requests` | JWT | List connection requests |
| PATCH | `/connection-requests/{id}/approve` | JWT | Approve → push peers to agents |
| PATCH | `/connection-requests/{id}/reject` | JWT | Reject |
| GET | `/connections` | JWT | List active connections |
| DELETE | `/connections/{id}` | JWT | Terminate + remove peers |
| GET | `/stats` | JWT | Node + connection counts |
| GET | `/topology` | JWT | Network graph data |
| GET | `/logs` | JWT | Audit log entries |
| GET | `/notifications` | JWT | Dashboard notifications |

\* nginx restricts to VPN subnet in production  
\*\* Rate limited 10/minute; individual approve/reject require JWT

### Agent

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | None | State + wg_up + peer count + vpn_ip |
| POST | `/set-vpn-address` | Token | Provision wg0 with assigned IP |
| POST | `/peer` | Token | Add WireGuard peer |
| DELETE | `/peer` | Token | Remove WireGuard peer |
| POST | `/wg/start` | Token | Bring up wg0 |
| POST | `/wg/stop` | Token | Bring down wg0 |
| GET | `/wg/status` | Token | Show peers + transfer stats |
| POST | `/wg/add-peer` | Token | Add peer (legacy path) |
| POST | `/wg/remove-peer` | Token | Remove peer (legacy path) |
| POST | `/wg/down` | Token | Bring down wg0 |
| POST | `/ip-forward/enable` | Token | Enable IPv4 forwarding (hub nodes) |
| POST | `/remove-node` | Token | Full teardown: remove all peers + delete interface |
| GET | `/logs` | Token | Last N lines from agent.log |

---

## 22. Configuration Reference

### Controller (`controller/backend/.env`)

```env
VISHWAAS_AGENT_TOKEN=<shared secret — must match agent master_token>
VISHWAAS_JWT_SECRET=<32+ char random hex>
VISHWAAS_ADMIN_PASSWORD_HASH=<bcrypt hash>  # empty = dev mode (accept any login)
VISHWAAS_ENVIRONMENT=development            # or "production"
VISHWAAS_ALLOWED_ORIGINS=http://localhost:3000
VISHWAAS_VPN_NETWORK=10.10.10.0/24
VISHWAAS_VPN_START=10.10.10.2
VISHWAAS_VPN_END=10.10.10.254
VISHWAAS_LOG_JSON=false
VISHWAAS_JWT_EXPIRE_MINUTES=480
VISHWAAS_LOG_RETENTION_DAYS=30
```

### Agent (`agent/agent_config.json`)

```json
{
  "master_url": "http://192.168.10.15:8000",
  "master_token": "<same as VISHWAAS_AGENT_TOKEN>",
  "agent_advertise_url": "http://192.168.10.16:9000",
  "node_name": "auto",
  "wg_interface": "wg0",
  "listen_port": 51820,
  "keys_dir": "./keys",
  "use_tpm_wg_key": false,
  "allowed_controller_ips": []
}
```

---

## 23. Deployment Architecture (Production)

```
  Internet
     │
     ▼
  ┌──────────────────────────────────────────────┐
  │  nginx (HTTPS termination)                    │
  │  • TLS with Let's Encrypt cert               │
  │  • Rate limiting: 10r/s burst 20             │
  │  • geo $private_network: blocks public IPs   │
  │    from all /api/* management routes         │
  │  • /metrics: only from 10.10.10.0/24        │
  │  • Reverse proxy:                            │
  │    /api/* → localhost:8000 (FastAPI)         │
  │    /* → localhost:3000 (React)               │
  └──────────────────────────────────────────────┘
     │
     ▼
  ┌──────────────────────────────────────────────┐
  │  systemd: vishwaas-controller.service         │
  │  • Runs as vishwaas user (not root)          │
  │  • RestartAlways                             │
  │  • Loads .env for secrets                   │
  └──────────────────────────────────────────────┘

  Agent machines:
  ┌──────────────────────────────────────────────┐
  │  systemd: vishwaas-agent.service             │
  │  • Runs as root (needs CAP_NET_ADMIN)        │
  │  • RestartAlways                             │
  │  • Loads agent_config.json                  │
  └──────────────────────────────────────────────┘

  Database: SQLite at controller/backend/vishwaas.db
  • Suitable for <50 nodes
  • Swap VISHWAAS_DATABASE_URL for Postgres to scale
  • Schema managed by Alembic migrations
```

---

## 24. Test Suite

87 tests covering:

| File | What it tests |
|------|--------------|
| `test_auth.py` | Login/logout, JWT creation/revocation, dev mode bypass |
| `test_health.py` | /health and /ready endpoints, DB connectivity check |
| `test_join.py` | Join request creation, approval, rejection, rate limiting, input validation |
| `test_connections.py` | Connection request lifecycle, peer push, atomic rollback, termination |
| `test_services.py` | IP allocation, join_service, connection_service unit tests |
| `conftest.py` | Shared fixtures: in-memory SQLite DB, mock agent HTTP server, FastAPI test client |

Run tests:
```bash
cd controller/backend
.venv/bin/pytest tests/ -v
```

---

## 25. Key Engineering Decisions

| Decision | Why |
|----------|-----|
| Admin must re-approve after agent restart | Restart could mean new IP, rekey, or compromise — safety over convenience |
| Node inserted as APPROVED (not ACTIVE) until agent confirms | Prevents race: heartbeat would immediately delete a node it can't reach |
| Atomic peer push with rollback | Never leave half-broken connection state in DB or on agents |
| wg0 stays up on connection termination | Nodes keep their VPN IPs; can be re-peered without full rejoin |
| Startup sweep marks nodes OFFLINE immediately | Dashboard shows reality at once, not stale ACTIVE for 90s after restart |
| Shared httpx pool with retry + exponential backoff | Connection reuse; transient agent hiccups don't fail critical operations |
| JWT + jti revocation blacklist | Logout is immediate and real, not just client-side |
| ControllerIPMiddleware on agent | Agent API never exposed to public internet even without firewall rules |
| state.py persists to disk | Agent survives restarts without losing state (no orphan loops) |
| Alembic instead of create_all() | Enables safe schema upgrades without data loss |

---

## 26. Lab Setup (Your Machines)

```
Physical network: 192.168.10.0/24
VPN network:      10.10.10.0/24

┌─────────────────┐        ┌─────────────────┐        ┌─────────────────┐
│    machine1      │        │    machine2      │        │    machine3      │
│  192.168.10.15  │        │  192.168.10.16  │        │  192.168.10.17  │
│                 │        │                 │        │                 │
│  Controller     │        │  Agent only     │        │  Agent only     │
│  (backend 8000) │        │                 │        │                 │
│  (frontend 3000)│        │                 │        │                 │
│  Agent (9000)   │        │  Agent (9000)   │        │  Agent (9000)   │
│                 │        │                 │        │                 │
│  VPN: 10.10.10.2│        │  VPN: 10.10.10.3│        │  VPN: 10.10.10.4│
│  wg0 UP         │        │  wg0 UP         │        │  wg0 UP         │
└────────┬────────┘        └────────┬────────┘        └────────┬────────┘
         │                          │                           │
         └────── WireGuard encrypted UDP tunnels ───────────────┘
                         (10.10.10.0/24 VPN subnet)
```

After full setup:
- `machine1 ↔ machine2`: ping 10.10.10.3 from machine1 works
- `machine1 ↔ machine3`: ping 10.10.10.4 from machine1 works
- `machine2 ↔ machine3`: ping 10.10.10.4 from machine2 works (if connected)

---

## 27. Known Limitations and Future Work

| Limitation | Current workaround | Proper fix |
|------------|-------------------|------------|
| No real-time push to dashboard | Frontend polls every few seconds | WebSocket / SSE |
| Single admin account | Dev mode: no creds; Prod mode: one bcrypt hash | Multi-user auth + roles |
| SQLite | Fine for <50 nodes | Switch VISHWAAS_DATABASE_URL to Postgres |
| No TLS between controller and agents | Trust LAN; use VPN for management plane | nginx TLS on agent or mTLS |
| Manual `alembic stamp head` on existing DBs | One-time step | Auto-detect and stamp |
| agent_config.json hand-configured | deploy-agent.sh SSH script | GUI or Ansible playbook |
| WireGuard UDP 51820 must be open between nodes | Document in setup guide | STUN/NAT traversal |

---

## 28. Glossary

| Term | Meaning |
|------|---------|
| **Agent** | The lightweight FastAPI process running on each VPN node machine |
| **Controller** | The central backend (FastAPI) + web dashboard (React) |
| **wg0** | The WireGuard virtual network interface created on each node |
| **VPN IP** | The IP address assigned to a node within the VPN subnet (e.g. 10.10.10.3) |
| **Join request** | An agent's first contact with the controller, asking to join the VPN |
| **Connection** | An approved peer relationship between two nodes |
| **PENDING** | Waiting for admin decision |
| **ACTIVE** | Running normally, reachable by heartbeat |
| **OFFLINE** | Unreachable for >90s; not yet deleted |
| **X-VISHWAAS-TOKEN** | Shared secret header used by controller when calling agents |
| **jti** | JWT ID — unique per token, stored in revoked_tokens on logout |
| **Heartbeat** | Background task that pings all nodes every 60s to check liveness |
| **Alembic** | SQLAlchemy migration tool — manages DB schema changes safely |
| **is_gateway** | Flag on a node meaning it acts as a routing hub (hub-and-spoke topology) |
| **TPM** | Trusted Platform Module — optional hardware key storage for the WireGuard private key |
