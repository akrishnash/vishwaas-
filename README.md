## VISHWAAS – Controller + Agent VPN

**VISHWAAS** is a simple but robust WireGuard-based VPN with an explicit **request / approve** flow:

- **Agents** run on your machines and ask to join the VPN.
- A central **Controller** lets you approve nodes and connections in a clean web UI.
- No node becomes ACTIVE and no connection is created without an approval step.

This repo contains both halves of the system, organized into separate folders for clarity.

---

### High-level flow

- **Join**: An agent starts and sends a *join request* (node name, agent URL, and optionally its WireGuard public key) to the controller.
- **Approve node**: In the controller UI you approve the request, assign a VPN IP, and the controller pushes config back to the agent.
- **Connect nodes**: To link two machines, you request a connection between them and approve; the controller updates both agents’ WireGuard peers.
- **Retry handling**: If an agent is offline when you approve, the controller retries delivering config in the background.

See `DESIGN.md` for a deeper design walkthrough, including key-handling variants and TPM notes.

---

### Repository layout

```text
vishwaas/
├── controller/                 # Control plane (API + web UI)
│   ├── backend -> ../backend   # FastAPI backend (symlink)
│   ├── frontend -> ../frontend # React/Vite frontend (symlink)
│   └── run_controller.sh -> ../run_controller.sh
│
├── agent/                      # Node agent
│   └── vishwaas-agent -> ../vishwaas-agent
│
├── backend/                    # Actual backend source (FastAPI)
├── frontend/                   # Actual frontend source (React/Vite)
├── vishwaas-agent/             # Actual agent implementation (Python)
├── run_controller.sh           # Helper script: start backend + frontend together
├── README_VISHWAAS_MASTER.md   # Controller-focused documentation
├── RUN.md                      # End-to-end “how to run controller + agent”
├── DESIGN.md                   # VPN flow and key-management design
└── tpm_scripts/                # TPM helpers for secure key storage on agents
```

You can work either from the grouped folders (`controller/`, `agent/`) or directly in `backend/`, `frontend/`, and `vishwaas-agent/`.

---

### Quick start – run everything locally

#### 1. Start the controller (API + UI)

From the repo root:

```bash
./run_controller.sh
```

This script will:

- Create and reuse a Python virtualenv in `backend/.venv`.
- Start the FastAPI backend on `http://0.0.0.0:8000`.
- Install frontend dependencies and start Vite on `http://localhost:3000`.
- Stream logs into `logs/backend.log` and `logs/frontend.log`.

You can also run the pieces by hand; see `README_VISHWAAS_MASTER.md` for details.

#### 2. Start an agent (same machine or another box)

From the repo root:

```bash
cd vishwaas-agent
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# Edit agent_config.json:
# - master_url   → controller URL, e.g. http://127.0.0.1:8000
# - master_token → must match backend VISHWAAS_AGENT_TOKEN
# - agent_advertise_url → how the controller calls this agent

venv/bin/python -c "from app.main import run; run()"
```

The agent will send a join request to the controller. Open the controller UI at `http://localhost:3000`, go to **Join Requests**, and click **Approve**.

For installing the agent as a systemd service or deploying to another machine, see `vishwaas-agent/README.md` and `vishwaas-agent/RUN_AGENT.md`.

---

### Controller vs agent responsibilities

- **Controller (this machine, central brain)**
  - Exposes REST API for join and connection workflows.
  - Persists nodes, connections, and logs (SQLite by default).
  - Hosts the dashboard UI (React/Vite).
  - Pushes WireGuard configuration to agents after approvals.

- **Agent (each VPN node)**
  - Registers itself with the controller.
  - Brings up and manages the WireGuard interface (`wg0` by default).
  - Applies configuration pushed by the controller (VPN IP, peers).
  - Can optionally keep its private key in a TPM-backed NV index.

---

### Security notes

- No “auto-join” or “auto-connect”: everything is approval-based.
- Strict node / connection state machines in the controller backend.
- Every action is logged for auditability.
- Agents can be configured to store WireGuard private keys in a TPM 2.0 NV index (`use_tpm_wg_key` in `agent_config.json`) for hardware-bound key protection.

For the full architecture and API reference, start with:

- `README_VISHWAAS_MASTER.md` – controller internals, API endpoints, and dashboard features.
- `DESIGN.md` – VPN/key flow and security model at a higher level.

---

### GitHub remote

This project is wired to the remote repository at `https://github.com/akrishnash/vishwaas-.git`.  
To publish your local work:

```bash
git add .
git commit -m "Initial VISHWAAS controller + agent"
git branch -M main           # optional: use 'main' as default branch
git push -u origin main
```

You now have a clean, two-part layout (controller and agent) with a single repo that describes and runs the whole system.

