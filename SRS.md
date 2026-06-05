# Software Requirements Specification
# VISHWAAS — WireGuard VPN Orchestration System

**Version:** 1.0  
**Date:** 2026-05-11  
**Author:** Anurag (akrishnash)  
**Status:** Draft

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Overall Description](#2-overall-description)
3. [Stakeholders and User Classes](#3-stakeholders-and-user-classes)
4. [System Context and Constraints](#4-system-context-and-constraints)
5. [Functional Requirements](#5-functional-requirements)
   - 5.1 [Agent — Node Enrollment](#51-agent--node-enrollment)
   - 5.2 [Controller — Join Request Management](#52-controller--join-request-management)
   - 5.3 [Controller — Connection Management](#53-controller--connection-management)
   - 5.4 [Controller — Dashboard](#54-controller--dashboard)
   - 5.5 [Controller — Heartbeat and Node Health](#55-controller--heartbeat-and-node-health)
   - 5.6 [Controller — Authentication and Session Management](#56-controller--authentication-and-session-management)
   - 5.7 [Agent — WireGuard Interface Management](#57-agent--wireguard-interface-management)
   - 5.8 [Controller — Observability](#58-controller--observability)
6. [Non-Functional Requirements](#6-non-functional-requirements)
   - 6.1 [Security](#61-security)
   - 6.2 [Reliability](#62-reliability)
   - 6.3 [Performance](#63-performance)
   - 6.4 [Maintainability and Operability](#64-maintainability-and-operability)
   - 6.5 [Scalability](#65-scalability)
7. [External Interface Requirements](#7-external-interface-requirements)
   - 7.1 [Controller REST API](#71-controller-rest-api)
   - 7.2 [Agent REST API](#72-agent-rest-api)
   - 7.3 [Dashboard UI](#73-dashboard-ui)
8. [Data Requirements](#8-data-requirements)
9. [State Machines](#9-state-machines)
   - 9.1 [Node Lifecycle](#91-node-lifecycle)
   - 9.2 [Connection Lifecycle](#92-connection-lifecycle)
   - 9.3 [Agent State Machine](#93-agent-state-machine)
10. [Configuration Requirements](#10-configuration-requirements)
11. [Deployment Requirements](#11-deployment-requirements)
12. [Assumptions and Dependencies](#12-assumptions-and-dependencies)
13. [Known Limitations and Future Work](#13-known-limitations-and-future-work)

---

## 1. Introduction

### 1.1 Purpose

This document specifies the software requirements for **VISHWAAS**, a WireGuard VPN orchestration system. It is the authoritative reference for functional behavior, non-functional properties, interfaces, and constraints of the system.

### 1.2 Scope

VISHWAAS eliminates the need to manually edit WireGuard configuration files on each machine in a private network. A lightweight agent process runs on every node; a central controller with a web dashboard lets an administrator approve join requests and peer connections. All WireGuard configuration is pushed to agents automatically. **Nothing becomes active without explicit admin approval.**

The system does not replace WireGuard itself — it orchestrates it. WireGuard handles all actual VPN packet forwarding.

### 1.3 Definitions

| Term | Definition |
|------|------------|
| **Agent** | FastAPI process running on each VPN node machine (port 9000). Manages the local WireGuard interface. |
| **Controller** | Central service consisting of a FastAPI backend (port 8000) and a React dashboard (port 3000). Deployed on one admin machine. |
| **Node** | A machine that has been approved to join the VPN. Identified by a WireGuard public key and assigned a VPN IP. |
| **Join Request** | An enrollment request sent by an agent to the controller. Status: PENDING → APPROVED or REJECTED. |
| **Connection Request** | An admin-initiated request to peer two nodes. Status: PENDING → APPROVED or REJECTED. |
| **Connection** | An active WireGuard peer relationship between two nodes. Status: ACTIVE → TERMINATED. |
| **VPN Subnet** | The IP range from which VPN addresses are assigned (default: `10.10.10.0/24`). |
| **Heartbeat** | Periodic controller-initiated health probe sent to each registered agent. |
| **TPM** | Trusted Platform Module — optional hardware for binding WireGuard private keys to a physical device. |

### 1.4 References

- WireGuard protocol documentation: https://www.wireguard.com/protocol/
- FastAPI: https://fastapi.tiangolo.com/
- SQLAlchemy / Alembic: https://alembic.sqlalchemy.org/
- `DESIGN.md` — high-level flow and key design decisions
- `CLAUDE.md` — implementation history and architectural rationale

---

## 2. Overall Description

### 2.1 Product Perspective

VISHWAAS is a self-hosted, intranet-only system. There is no cloud dependency. All components run on machines within the operator's LAN. The system manages WireGuard directly via OS-level commands (`wg`, `ip`).

```
  [Machine A]          [Controller machine]         [Machine B]
  agent :9000 ──────► backend :8000  ◄──────────── agent :9000
                       frontend :3000  (admin browser)
```

### 2.2 Product Functions (Summary)

- **Enrollment**: agents self-register; admins approve or reject.
- **IP assignment**: controller assigns VPN IPs from a configured pool.
- **Peering**: admin approves connection between any two nodes; controller configures both agents atomically.
- **Monitoring**: dashboard shows live node status, network topology, and an audit log.
- **Health management**: heartbeat automatically marks unreachable nodes offline and purges long-absent ones.

### 2.3 Operating Environment

- Linux only (Ubuntu 20.04+ recommended for both controller and agent machines).
- WireGuard kernel module must be available on agent machines.
- Agent process requires root or `CAP_NET_ADMIN` capability.
- Controller backend requires Python 3.10+. Controller frontend requires Node.js 18+.

---

## 3. Stakeholders and User Classes

| Class | Description | Interaction |
|-------|-------------|-------------|
| **Network Administrator** | Single admin who manages the VPN. Reviews join requests, approves/rejects connections, monitors node health. | Dashboard UI via browser. |
| **Agent (automated)** | Software process on each node machine. Makes join requests, receives configuration pushes. | REST API calls to controller. |
| **Controller (automated)** | Backend service. Pushes config to agents, runs heartbeat, serves dashboard API. | REST API calls to agents. |
| **External Monitoring System** | Optional: uptime monitors, Prometheus scrapers. | `GET /health`, `GET /ready`, `GET /metrics` endpoints. |

---

## 4. System Context and Constraints

### 4.1 Network Topology Constraint

All agents and the controller must be on the same LAN (or otherwise reachable at the IP level) for the management plane. The system does not currently support agents behind NAT relative to the controller.

### 4.2 Single Administrator

The system supports one admin account. There is no role-based access control or multi-user auth in the current version.

### 4.3 Admin-Approval Gate

Every operation that alters network topology (join, peer connection) requires explicit admin approval through the dashboard. Automated approval is not supported.

### 4.4 WireGuard Interface Name

Each agent manages exactly one WireGuard interface (default: `wg0`). Multiple interfaces per agent are not supported.

### 4.5 Storage

The controller uses SQLite by default. PostgreSQL is supported via `VISHWAAS_DATABASE_URL` environment variable change and Alembic migrations.

---

## 5. Functional Requirements

### 5.1 Agent — Node Enrollment

**FR-A01** — On startup, the agent MUST read `agent_config.json` and load or generate a WireGuard keypair, storing the private key in `keys_dir` (or TPM if `use_tpm_wg_key` is true).

**FR-A02** — The agent MUST send `POST /request-join` to the controller on every startup, regardless of whether the WireGuard interface is already up.

**FR-A03** — The join request payload MUST include: `node_name` (string, hostname if `"auto"`), `agent_url` (the URL the controller uses to reach this agent), and `public_key` (WireGuard public key in base64). If `controller_issues_keys` is true, `public_key` may be omitted.

**FR-A04** — If the join request is not approved, the agent MUST retry `POST /request-join` every 10 seconds until approval is received.

**FR-A05** — The agent state MUST be persisted to `agent_state.json` in `keys_dir` so that the state survives process restarts. On startup, if the file is missing or corrupt, the state defaults to `WAITING`.

### 5.2 Controller — Join Request Management

**FR-C01** — The controller MUST accept `POST /request-join` and create a join request record with status `PENDING`.

**FR-C02** — If a join request arrives from an agent whose public key matches an existing node, the controller MUST:
1. Tear down all active connections on peer agents (call `remove_peer` on each connected node).
2. Delete the stale node and its connection records from the database.
3. Create a fresh `PENDING` join request.
The admin must re-approve every restart. This prevents stale state from accumulating.

**FR-C03** — The `POST /request-join` endpoint MUST be rate-limited to **10 requests per minute per source IP**.

**FR-C04** — The controller MUST validate the join request fields:
- `node_name`: matches pattern `^[a-zA-Z0-9_-]{1,64}$`
- `public_key`: valid WireGuard base64-encoded 32-byte key
- `agent_url`: URL with scheme `http` or `https`

**FR-C05** — When the admin approves a join request, the controller MUST:
1. Assign the next available VPN IP from the configured pool (`VISHWAAS_VPN_START` to `VISHWAAS_VPN_END`).
2. Insert a `nodes` record with status `APPROVED` and stamp `last_seen = now`.
3. Call `POST /set_vpn_address` on the agent (with retries if unreachable).
4. On agent confirmation, update node status to `ACTIVE`.

**FR-C06** — If the agent is unreachable at approval time, the controller MUST schedule background retries for `set_vpn_address` until the agent responds or the request is superseded.

**FR-C07** — When the admin rejects a join request, its status MUST be set to `REJECTED`. No node record is created.

**FR-C08** — Stale `PENDING` join requests from agents unreachable for more than **120 seconds** MUST be automatically set to `REJECTED` by the heartbeat sweep.

**FR-C09** — List endpoints for join requests MUST support `skip` and `limit` query parameters for pagination.

### 5.3 Controller — Connection Management

**FR-C10** — The admin MUST be able to create a connection request between any two `ACTIVE` or `APPROVED` nodes.

**FR-C11** — When the admin approves a connection request, the controller MUST call `POST /add_peer` on node A's agent and then on node B's agent, in that order.

**FR-C12** — If `add_peer` on node A fails, the controller MUST return HTTP 502 and create no connection record.

**FR-C13** — If `add_peer` on node A succeeds but `add_peer` on node B fails, the controller MUST call `remove_peer` on node A (rollback) before returning HTTP 502. No connection record is created. This prevents half-broken connection state.

**FR-C14** — On both agent calls succeeding, the controller MUST create a `connections` record with status `ACTIVE`.

**FR-C15** — When the admin terminates a connection, the controller MUST call `remove_peer` on both agents and set the connection status to `TERMINATED`.

**FR-C16** — After termination, the WireGuard interface (`wg0`) on both nodes MUST remain up with their VPN IPs intact. Only the peer entry is removed — the interface is NOT brought down.

**FR-C17** — When a node is deleted (manually or by heartbeat), the controller MUST call `remove_peer` on all agents that had a connection with that node, then delete the connection records.

**FR-C18** — `add_peer` and `remove_peer` calls to agents MUST use the shared HTTP connection pool with exponential-backoff retry (2 retries, delays 1s and 2s).

### 5.4 Controller — Dashboard

**FR-D01** — The dashboard MUST provide the following pages:

| Page | Function |
|------|----------|
| Overview | Live counts: active nodes, pending join requests, active connections, unread notifications. |
| Nodes | Tabular list of all approved nodes with VPN IP and status. |
| Join Requests | List of PENDING join requests with Approve / Reject actions. |
| Connections | List of ACTIVE connections with Terminate action. |
| Connection Requests | List of PENDING connection requests with Approve / Reject actions. |
| Network Map | Force-directed graph of ACTIVE and APPROVED nodes and their connections. Clicking a node shows live WireGuard stats. |
| Logs | Immutable audit trail. Searchable/filterable. |

**FR-D02** — The Network Map MUST display only nodes with status `ACTIVE` or `APPROVED`. Offline and deleted nodes MUST NOT appear.

**FR-D03** — The Overview stats MUST count `total_nodes` and `active_nodes` as nodes with status `ACTIVE` or `APPROVED` only. OFFLINE nodes are NOT counted.

**FR-D04** — Dashboard state MUST refresh automatically (polling interval). The exact interval is a UI implementation detail; updates MUST reflect within a few seconds.

### 5.5 Controller — Heartbeat and Node Health

**FR-H01** — The controller MUST run a heartbeat sweep every **60 seconds** against all nodes with status `ACTIVE`, `APPROVED`, or `OFFLINE`.

**FR-H02** — On controller startup, the heartbeat MUST run an immediate sweep that marks unreachable nodes `OFFLINE` without waiting for the 60-second cycle.

**FR-H03** — If a node has not responded for more than **90 seconds**, its status MUST be changed to `OFFLINE`.

**FR-H04** — If a node has not responded for more than **5 minutes**, the controller MUST auto-delete the node and all its connection records, calling `remove_peer` on any connected agents.

**FR-H05** — If a node that was `OFFLINE` successfully responds to a heartbeat, its status MUST be restored to `ACTIVE`.

**FR-H06** — Nodes with `last_seen = NULL` (freshly approved but never confirmed) MUST be skipped during the offline/delete threshold logic. They MUST NOT be auto-deleted immediately after approval.

**FR-H07** — After each heartbeat sweep, the controller MUST update Prometheus gauges for active node count, offline node count, and pending join request count.

### 5.6 Controller — Authentication and Session Management

**FR-S01** — All controller API endpoints except `/auth/login`, `/auth/logout`, `/health`, `/ready`, and `/metrics` MUST require a valid JWT Bearer token in the `Authorization` header.

**FR-S02** — `POST /auth/login` MUST accept `username` and `password`.
- In development mode (no `VISHWAAS_ADMIN_PASSWORD_HASH` set): any credentials are accepted.
- In production mode: password MUST be verified against the bcrypt hash stored in `VISHWAAS_ADMIN_PASSWORD_HASH`.

**FR-S03** — On successful login, the controller MUST return a signed JWT containing a `jti` (unique token ID) claim.

**FR-S04** — `POST /auth/logout` MUST add the token's `jti` to the `revoked_tokens` table. Subsequent requests using the same token MUST be rejected with HTTP 401.

**FR-S05** — On startup, the controller MUST prune expired entries from the `revoked_tokens` table.

**FR-S06** — In production mode (`VISHWAAS_ENVIRONMENT=production`), the controller MUST refuse to start if:
- `VISHWAAS_JWT_SECRET` is set to the default placeholder value.
- `VISHWAAS_ALLOWED_ORIGINS` is `*`.

### 5.7 Agent — WireGuard Interface Management

**FR-W01** — When the agent receives `POST /set_vpn_address`, it MUST:
1. Generate or load the WireGuard keypair.
2. Create the WireGuard interface if it does not exist.
3. Remove any existing IP addresses on the interface that differ from the assigned VPN IP.
4. Add the assigned VPN IP to the interface.
5. Bring the interface up.

**FR-W02** — When the agent receives `POST /add_peer`, it MUST add the specified public key and allowed IP to the WireGuard interface.

**FR-W03** — When the agent receives `POST /remove_peer`, it MUST remove the specified public key from the WireGuard interface.

**FR-W04** — On process shutdown (SIGTERM), the agent MUST bring down the WireGuard interface if it is up, so it does not linger after the process exits.

**FR-W05** — `GET /health` on the agent MUST return: `status`, `state`, `wg_interface`, `wg_up` (bool), `peer_count` (int), and `vpn_ip` (string or null). This endpoint MUST be reachable without the controller IP restriction (exempt from `ControllerIPMiddleware`).

**FR-W06** — All other agent endpoints (except `/health`) MUST be restricted to requests originating from the controller IP (derived from `master_url`) plus any IPs listed in `allowed_controller_ips`. All loopback addresses are always allowed.

**FR-W07** — If `controller_issues_keys` is true, the agent MUST accept and store a private key delivered by the controller in the `set_vpn_address` call.

**FR-W08** — If `use_tpm_wg_key` is true, the WireGuard private key MUST be stored in a TPM 2.0 NV index using `tpm2-tools`. The agent MUST fall back to file-based key storage if the TPM is unavailable.

### 5.8 Controller — Observability

**FR-O01** — The controller MUST expose `GET /health` returning `{"status": "ok"}` (HTTP 200). This endpoint does not require authentication.

**FR-O02** — The controller MUST expose `GET /ready` which runs `SELECT 1` against the database. Returns HTTP 200 if the DB is reachable, HTTP 503 otherwise. Does not require authentication.

**FR-O03** — The controller MUST expose `GET /metrics` in Prometheus text format, restricted to private network IPs in production (via nginx `geo` block).

**FR-O04** — The following Prometheus metrics MUST be maintained:

| Metric | Type | Description |
|--------|------|-------------|
| `vishwaas_http_requests_total` | Counter | HTTP requests by method, path, status |
| `vishwaas_http_request_duration_seconds` | Histogram | Request latency |
| `vishwaas_agent_calls_total` | Counter | Controller→agent calls by endpoint and result |
| `vishwaas_nodes_active_total` | Gauge | Current count of ACTIVE+APPROVED nodes |
| `vishwaas_nodes_offline_total` | Gauge | Current count of OFFLINE nodes |
| `vishwaas_join_requests_pending_total` | Gauge | Current count of PENDING join requests |

**FR-O05** — Every HTTP request MUST be assigned a correlation ID (`X-Request-ID` header). If the request already carries one, it MUST be preserved; otherwise a UUID is generated. The ID MUST be forwarded to all downstream agent calls.

**FR-O06** — Log output MUST be configurable: plain text (default) or structured JSON via `VISHWAAS_LOG_JSON=true` on the controller and `VISHWAAS_AGENT_LOG_JSON=true` on the agent. JSON logs MUST include `service` and `level` fields.

**FR-O07** — An immutable audit log MUST be written to the `logs` database table for every significant event: join approved/rejected, connection approved/terminated, node deleted.

---

## 6. Non-Functional Requirements

### 6.1 Security

**NFR-S01** — The agent API MUST NOT be exposed to public internet IP addresses. The `ControllerIPMiddleware` enforces this at the application layer; nginx enforces it at the reverse-proxy layer for the controller.

**NFR-S02** — WireGuard private keys MUST never be transmitted in plaintext over an unencrypted channel except when the controller issues keys to an agent (a one-time operation). Production deployments SHOULD use HTTPS between controller and agents.

**NFR-S03** — JWT secrets and agent tokens MUST NOT be stored in version control. The `.env` file and `agent_config.json` are gitignored.

**NFR-S04** — The controller API (`/api/*`) MUST be restricted to private network addresses (RFC 1918) via the nginx `geo` block in production. Only `/api/health` and `/api/ready` are publicly reachable.

**NFR-S05** — CORS origins MUST be explicitly whitelisted in production. `VISHWAAS_ALLOWED_ORIGINS=*` causes the controller to refuse startup in production mode.

**NFR-S06** — Input to `POST /request-join` MUST be validated for node name pattern, public key format, and agent URL scheme before any database operation.

**NFR-S07** — The agent token (`X-VISHWAAS-TOKEN` header) MUST be required on all controller→agent calls except `/health`.

### 6.2 Reliability

**NFR-R01** — All controller→agent HTTP calls MUST use a shared connection pool (not a new client per call).

**NFR-R02** — All controller→agent HTTP calls MUST be retried with exponential backoff on transient failure (2 retries, 1s and 2s delays).

**NFR-R03** — Connection approval MUST be atomic with respect to the peer configuration: either both agents are configured and a connection record is created, or neither agent is changed and no record is created (via rollback).

**NFR-R04** — Agent state (WAITING/APPROVED/ACTIVE/ERROR) MUST survive process restarts via the `agent_state.json` file.

**NFR-R05** — Database schema changes MUST be managed with Alembic migrations. `create_all()` MUST NOT be used in production.

### 6.3 Performance

**NFR-P01** — The heartbeat sweep interval is 60 seconds. A node going offline MUST be reflected on the dashboard within at most 90 seconds (one sweep period plus the threshold).

**NFR-P02** — The controller startup sweep MUST mark unreachable nodes OFFLINE within ~5 seconds of the backend process starting, so the dashboard reflects reality immediately after a controller restart.

**NFR-P03** — Join request endpoints MUST respond within 2 seconds under normal load.

**NFR-P04** — The system is designed for small-to-medium networks (up to ~50 nodes with SQLite). For larger deployments, a PostgreSQL backend is required.

### 6.4 Maintainability and Operability

**NFR-M01** — The controller MUST be installable as a systemd unit (`vishwaas-controller.service`) for automatic restart on failure.

**NFR-M02** — The agent MUST be installable as a systemd unit (`vishwaas-agent.service`) via `install.sh`.

**NFR-M03** — A `deploy-agent.sh` script MUST exist to deploy the agent directory to remote machines via SSH, requiring key-based authentication.

**NFR-M04** — A `start_controller.sh` convenience script MUST start both the backend and frontend together in development mode.

### 6.5 Scalability

**NFR-SC01** — The VPN address pool MUST be configurable (`VISHWAAS_VPN_NETWORK`, `VISHWAAS_VPN_START`, `VISHWAAS_VPN_END`). Default pool supports up to 253 nodes (`10.10.10.2`–`10.10.10.254`).

**NFR-SC02** — The architecture is single-controller. Horizontal scaling of the controller is not supported in the current version.

---

## 7. External Interface Requirements

### 7.1 Controller REST API

Base URL: `http://<controller-ip>:8000`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/auth/login` | None | Issue JWT. Body: `{username, password}` |
| `POST` | `/auth/logout` | JWT | Revoke current token |
| `GET` | `/health` | None | Liveness probe |
| `GET` | `/ready` | None | Readiness probe (DB check) |
| `GET` | `/metrics` | None (private net) | Prometheus metrics |
| `POST` | `/request-join` | None (rate-limited) | Agent: request to join VPN |
| `GET` | `/join-requests` | JWT | List join requests (paginated) |
| `POST` | `/join-requests/{id}/approve` | JWT | Approve a join request |
| `POST` | `/join-requests/{id}/reject` | JWT | Reject a join request |
| `GET` | `/nodes` | JWT | List nodes (paginated) |
| `DELETE` | `/nodes/{id}` | JWT | Delete a node |
| `POST` | `/connections` | JWT | Create a connection request |
| `GET` | `/connections` | JWT | List connections (paginated) |
| `POST` | `/connections/{id}/approve` | JWT | Approve a connection request |
| `POST` | `/connections/{id}/reject` | JWT | Reject a connection request |
| `DELETE` | `/connections/{id}` | JWT | Terminate a connection |
| `GET` | `/stats` | JWT | Overview counts |
| `GET` | `/topology` | JWT | Graph data for network map |
| `GET` | `/logs` | JWT | Audit log entries (paginated) |
| `GET` | `/notifications` | JWT | Dashboard notifications |

### 7.2 Agent REST API

Base URL: `http://<agent-ip>:9000` (controller→agent calls only, except `/health`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/health` | None | Agent health + WireGuard state |
| `POST` | `/set_vpn_address` | Token | Assign VPN IP (and optionally private key) |
| `POST` | `/add_peer` | Token | Add a WireGuard peer |
| `POST` | `/remove_peer` | Token | Remove a WireGuard peer |
| `POST` | `/wg_down` | Token | Bring down the WireGuard interface |

Authentication for agent endpoints: `X-VISHWAAS-TOKEN: <master_token>` header. All endpoints except `/health` additionally restrict by source IP (`ControllerIPMiddleware`).

### 7.3 Dashboard UI

- Technology: React + Vite (port 3000 in development).
- Browser requirements: modern browser with ES2020+ support.
- All API calls are made to the backend at port 8000. CORS is enforced by `VISHWAAS_ALLOWED_ORIGINS`.
- No WebSocket support — dashboard polls the backend REST API.

---

## 8. Data Requirements

### 8.1 Database Tables

| Table | Key Columns | Notes |
|-------|-------------|-------|
| `nodes` | `id`, `node_name`, `public_key`, `vpn_ip`, `agent_url`, `status`, `last_seen` | Status: PENDING → APPROVED → ACTIVE → OFFLINE |
| `join_requests` | `id`, `node_name`, `public_key`, `agent_url`, `status`, `created_at` | Status: PENDING → APPROVED / REJECTED |
| `connection_requests` | `id`, `node_a_id`, `node_b_id`, `status`, `created_at` | Status: PENDING → APPROVED / REJECTED |
| `connections` | `id`, `node_a_id`, `node_b_id`, `status`, `created_at` | Status: ACTIVE → TERMINATED |
| `notifications` | `id`, `message`, `read`, `created_at` | Dashboard alerts |
| `logs` | `id`, `event`, `detail`, `created_at` | Append-only audit trail |
| `revoked_tokens` | `id`, `jti`, `expires_at` | JWT blacklist; pruned at startup |

### 8.2 File-Based State (Agent)

| File | Location | Contents |
|------|----------|----------|
| `privatekey` | `keys_dir/` | WireGuard private key (PEM/base64). If TPM: stored in TPM NV index. |
| `publickey` | `keys_dir/` | WireGuard public key. |
| `agent_state.json` | `keys_dir/` | Current agent state: `{"state": "WAITING"|"APPROVED"|"ACTIVE"|"ERROR"}` |

---

## 9. State Machines

### 9.1 Node Lifecycle

```
                  POST /request-join received
                          │
                          ▼
                       PENDING ──► (admin rejects) ──► REJECTED
                          │
                   admin approves
                          │
                          ▼
                       APPROVED  ◄──────────────────── OFFLINE (node comes back)
                    (controller pushes                        ▲
                     VPN IP to agent)                        │
                          │                          heartbeat: 5+ min gone
                   agent confirms                    (auto-delete; exits state machine)
                          │
                          ▼
                        ACTIVE
                          │
                   heartbeat: 90s no response
                          │
                          ▼
                        OFFLINE
```

**Re-enrollment**: When an agent restarts and sends a new join request with the same public key, the existing node (regardless of status) is torn down and a fresh PENDING request is created. Admin must re-approve.

### 9.2 Connection Lifecycle

```
  Admin creates connection request
                │
                ▼
             PENDING ──► (admin rejects) ──► REJECTED
                │
         admin approves
                │
                ├─ add_peer(node_a) fails ──► HTTP 502, no record created
                │
                ├─ add_peer(node_b) fails ──► rollback remove_peer(node_a), HTTP 502
                │
                ▼
              ACTIVE
                │
         admin terminates
         (or node deleted)
                │
                ▼
           TERMINATED
       (both wg0 interfaces remain up)
```

### 9.3 Agent State Machine

```
   Startup
      │
      ▼
  WAITING ──► (POST /request-join every 10s)
      │
  admin approves; controller calls /set_vpn_address
      │
      ▼
  APPROVED
      │
  wg0 comes up successfully
      │
      ▼
  ACTIVE
      │
  (any error bringing up wg0)
      │
      ▼
  ERROR

  On any restart → returns to WAITING (sends new join request)
```

---

## 10. Configuration Requirements

### 10.1 Controller Environment Variables

File: `controller/backend/.env`

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `VISHWAAS_AGENT_TOKEN` | Yes | — | Shared secret for controller→agent authentication |
| `VISHWAAS_JWT_SECRET` | Production | `change-me-in-production` | JWT signing key. Startup aborts if default in production. |
| `VISHWAAS_ADMIN_PASSWORD_HASH` | No | `""` | bcrypt hash of admin password. Empty = accept any login (dev only). |
| `VISHWAAS_ENVIRONMENT` | No | `development` | `development` or `production`. Production enables startup guards. |
| `VISHWAAS_ALLOWED_ORIGINS` | Production | `http://localhost:3000` | CORS whitelist (comma-separated). `*` blocked in production. |
| `VISHWAAS_VPN_NETWORK` | No | `10.10.10.0/24` | VPN subnet |
| `VISHWAAS_VPN_START` | No | `10.10.10.2` | First assignable VPN IP |
| `VISHWAAS_VPN_END` | No | `10.10.10.254` | Last assignable VPN IP |
| `VISHWAAS_DATABASE_URL` | No | `sqlite:///./vishwaas.db` | SQLAlchemy database URL |
| `VISHWAAS_LOG_JSON` | No | `false` | Set `true` for JSON structured logging |

### 10.2 Agent Configuration File

File: `agent/agent_config.json`

| Key | Required | Default | Description |
|-----|----------|---------|-------------|
| `master_url` | Yes | — | Controller base URL (e.g. `http://192.168.10.15:8000`) |
| `master_token` | Yes | — | Must match `VISHWAAS_AGENT_TOKEN` on the controller |
| `agent_advertise_url` | Yes | — | URL the controller uses to call back to this agent |
| `node_name` | No | `"auto"` | `"auto"` uses the machine hostname |
| `wg_interface` | No | `wg0` | WireGuard interface name |
| `listen_port` | No | `51820` | WireGuard UDP listen port |
| `keys_dir` | No | `./keys` | Directory for WireGuard keys and state file |
| `use_tpm_wg_key` | No | `false` | Store private key in TPM 2.0 NV index |
| `controller_issues_keys` | No | `false` | Agent accepts private key from controller |
| `allowed_controller_ips` | No | `[]` | Additional IPs allowed to call agent (beyond `master_url` IP) |

---

## 11. Deployment Requirements

### 11.1 Controller Machine

- Linux (Ubuntu 20.04+)
- Python 3.10+, pip, venv
- Node.js 18+, npm
- nginx (production)
- Open inbound ports: 8000 (backend, LAN only), 3000 (frontend, LAN only), 443/80 (nginx, if used)

**Startup sequence:**
1. Run `alembic upgrade head` (first run or after upgrade).
2. Start backend via `uvicorn` or `start_controller.sh`.
3. Start frontend via `npm run dev` (dev) or serve via nginx (production).

### 11.2 Agent Machine

- Linux (Ubuntu 20.04+)
- Python 3.10+, pip, venv
- `wireguard-tools` package installed
- Root or `CAP_NET_ADMIN` capability for the agent process
- Open inbound ports: 9000 (agent API, accessible from controller only), 51820/UDP (WireGuard)

**Startup sequence:**
1. Copy and configure `agent_config.json`.
2. Run `sudo ./start_agent.sh` (dev) or `sudo ./install.sh` + `systemctl start vishwaas-agent` (production).

### 11.3 Production nginx Configuration

The included `nginx.conf` enforces:
- All `/api/*` management endpoints return HTTP 403 for public internet IPs (via `geo $private_network`).
- `/api/health` and `/api/ready` are publicly reachable (monitoring probes).
- `/api/request-join` and `/api/auth/login` are restricted to private network IPs.
- `/metrics` is restricted to a configurable VPN subnet (e.g., `10.10.10.0/24`).
- Rate limiting applied at the nginx layer.

---

## 12. Assumptions and Dependencies

| # | Assumption / Dependency |
|---|------------------------|
| A1 | All agent machines are reachable from the controller on TCP port 9000. |
| A2 | The controller machine is reachable from all agent machines on TCP port 8000. |
| A3 | UDP port 51820 is open between any two nodes that will be peered. |
| A4 | The WireGuard kernel module is available on all agent machines. |
| A5 | The agent process runs with root or `CAP_NET_ADMIN`. |
| A6 | The operator provides a unique, random value for `VISHWAAS_AGENT_TOKEN` shared across all agents. |
| A7 | IP addresses of machines do not change after initial configuration (no dynamic IP support). |
| A8 | `tpm2-tools` is installed on agent machines that use TPM key storage. |
| A9 | The system relies on WireGuard for actual VPN packet encryption and routing; VISHWAAS does not implement its own cryptography. |

---

## 13. Known Limitations and Future Work

| Item | Description |
|------|-------------|
| No push notifications | Dashboard uses polling. Changes are not instant; updates appear within a few seconds on the next poll cycle. |
| Single admin account | No multi-user support, no roles or permissions. |
| No NAT traversal | Agents behind NAT relative to the controller are not supported in the management plane. |
| No TLS on management plane | Controller→agent calls use plain HTTP. Production deployments should place agents behind a TLS-terminating proxy or use the VPN tunnel for management traffic. |
| SQLite scalability limit | Recommended for ≤50 nodes. Larger deployments require PostgreSQL (`VISHWAAS_DATABASE_URL`). |
| Manual `alembic stamp head` | Existing databases created before Alembic was introduced require a one-time manual migration stamp. |
| Single WireGuard interface | Each agent manages exactly one `wg0` interface. Multiple VPN memberships per machine are not supported. |
| `agent_config.json` manually configured | The `deploy-agent.sh` script automates copying the agent directory via SSH, but the config values must be set by the operator. |
| No WebSocket / server-push | Dashboard relies on REST polling; a future version may add WebSocket support for instant updates. |
| Horizontal controller scaling | The controller is a single-instance service. High-availability or load-balanced controller deployments are not supported. |
