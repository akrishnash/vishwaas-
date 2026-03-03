# VISHWAAS Master – Control Plane

Enterprise-grade VPN master controller and dashboard for managing WireGuard-based nodes with request-approval workflows. Built from scratch with clean architecture.

---

## Architecture Overview

- **Backend**: FastAPI, SQLite, REST API. Layers: API → Services → Persistence → Domain.
- **Frontend**: React (functional components, hooks), Vite. Dashboard with left nav, top bar, notification bell.
- **Lifecycle**: No node becomes ACTIVE without approval; no connection is created without approval.

### Node states

`PENDING` → `APPROVED` → `ACTIVE` | `REJECTED` | `OFFLINE`

### Connection states

`REQUESTED` → `APPROVED` → `ACTIVE` | `REJECTED` | `TERMINATED`

### Auth (simplified)

- **Join:** Agents send `POST /request-join` with no token. The controller gates by approve/reject only.
- **Controller → agent:** When the controller adds/removes peers on a node, it calls the agent with header `X-VISHWAAS-TOKEN`. Set `VISHWAAS_AGENT_TOKEN` (or `agent_token`) in the backend to the same value as each agent’s `master_token` so those calls succeed.

---

## Project Structure

```
vishwaas/
├── backend/
│   ├── app/
│   │   ├── api/           # Routes and Pydantic schemas
│   │   ├── core/          # Config
│   │   ├── domain/        # Enums, state machines
│   │   ├── persistence/   # SQLAlchemy models, DB session
│   │   ├── services/      # Join/connection approval logic, agent client
│   │   └── main.py
│   ├── requirements.txt
│   └── run.sh
├── frontend/
│   ├── src/
│   │   ├── api/           # API client
│   │   ├── components/    # Layout, TopBar, StatusBadge, Modal, etc.
│   │   ├── context/      # Toast, Stats
│   │   ├── hooks/        # usePolling
│   │   ├── pages/        # Overview, Nodes, JoinRequests, etc.
│   │   └── styles/       # Dark theme CSS
│   ├── package.json
│   └── vite.config.js
└── README_VISHWAAS_MASTER.md (this file)
```

---

## How to Run

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Or:

```bash
cd backend && chmod +x run.sh && ./run.sh
```

- API base: `http://127.0.0.1:8000`
- Docs: `http://127.0.0.1:8000/docs`
- SQLite DB is created at `./vishwaas_master.db` on first request.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

- Dashboard: `http://localhost:3000`
- Vite proxies `/api` to `http://127.0.0.1:8000`, so the UI talks to the backend via `/api/*`.

---

## API Summary

| Method | Path | Description |
|--------|------|-------------|
| POST | `/request-join` | Submit join request (node name, public_key, agent_url) |
| GET | `/join-requests` | List join requests |
| POST | `/join-requests/{id}/approve` | Approve join (assigns VPN IP, creates node) |
| POST | `/join-requests/{id}/reject` | Reject join |
| POST | `/request-connection` | Request connection (requester_id, target_id) |
| GET | `/connection-requests` | List connection requests |
| POST | `/connection-requests/{id}/approve` | Approve connection (calls agents, creates connection) |
| POST | `/connection-requests/{id}/reject` | Reject connection request |
| GET | `/nodes` | List nodes |
| GET | `/nodes/{id}` | Get node |
| DELETE | `/nodes/{id}` | Remove node |
| GET | `/connections` | List connections |
| DELETE | `/connections/{id}` | Terminate connection |
| GET | `/stats` | Dashboard stats |
| GET | `/notifications` | List notifications |
| POST | `/notifications/{id}/mark-read` | Mark notification read |
| GET | `/logs` | Audit logs (optional `?event_type=...`) |

---

## Example API Responses

**GET /stats**

```json
{
  "total_nodes": 5,
  "active_nodes": 3,
  "pending_join_requests": 1,
  "pending_connection_requests": 0,
  "active_connections": 2,
  "unread_notifications": 2
}
```

**GET /nodes**

```json
[
  {
    "id": 1,
    "name": "node-alpha",
    "public_key": "xYz...",
    "agent_url": "http://10.0.0.1:9000",
    "vpn_ip": "10.10.10.2",
    "status": "ACTIVE",
    "last_seen": "2025-02-18T12:00:00Z",
    "created_at": "2025-02-18T10:00:00Z"
  }
]
```

**GET /join-requests**

```json
[
  {
    "id": 1,
    "node_name": "node-beta",
    "public_key": "aBc...",
    "agent_url": "http://10.0.0.2:9000",
    "status": "PENDING",
    "requested_at": "2025-02-18T11:30:00Z"
  }
]
```

**POST /join-requests/1/approve**

```json
{
  "ok": true,
  "node_id": 2,
  "vpn_ip": "10.10.10.3"
}
```

---

## Approval Logic (Backend)

- **Join approval**: Next free VPN IP from `10.10.10.0/24` (configurable), insert into `nodes` with status `APPROVED`, log event, create notification. Optionally call agent (extensible).
- **Connection approval**: Call agent A to add peer B, agent B to add peer A, create `connections` record with status `ACTIVE`, log and notify.

---

## Dashboard Features

- **Overview**: Cards (total/active nodes, pending join/connection requests, active connections), system health bar, live stats (auto-refresh 5s).
- **Nodes**: Table (Name, VPN IP, Status, Last Seen, View/Remove/Restart). Status badges (green=Active, yellow=Pending, red=Offline). Confirmation modal before remove.
- **Join Requests**: Table with Approve (green) / Reject (red). Only PENDING rows show actions.
- **Connection Requests**: Table (From, To, Requested At, Approve/Reject).
- **Connections**: Table with Terminate for ACTIVE connections; confirmation modal.
- **Logs**: Timeline view, filter by event type.
- **Top bar**: Notification bell with unread count, refresh. Dark theme, toasts, loading spinners.

---

## Security Principles

- Central authority only; no auto-approval.
- Strict state transitions in domain enums.
- Every action is logged in `logs` table.
- Logic layer (services) separated from API layer (routes).

---

## TPM (agent nodes)

Node agents can store the WireGuard private key in a TPM 2.0 NV index so the key is bound to hardware. Set `use_tpm_wg_key: true` (and optionally `tpm_nv_index_wg`) in the agent’s `agent_config.json`. The agent then writes the key to TPM when it is generated or received from the controller, and reads from TPM when starting the WireGuard interface. Requires `tpm2-tools` on each node. See the agent README for one-time provisioning and index details.

## Extensibility

- Structure is ready for future ML-KEM integration (e.g. key exchange in join/connection flows).
- Agent client in `app/services/agent_client.py` can be extended for more operations (restart, health check).
