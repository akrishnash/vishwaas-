# How to run VISHWAAS

One controller (backend + frontend), one or more agents (one per machine that joins the VPN). Approve joins in the UI; approve connections to link two nodes.

---

## 1. Run the controller (one machine)

**Backend** (API on port 8000):

```bash
cd backend
source .venv/bin/activate   # or: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Or use the script:

```bash
cd backend && ./run.sh
```

**Frontend** (UI on port 3000; in another terminal):

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000** (or the controller machine’s IP:3000). Set `VISHWAAS_AGENT_TOKEN` in the backend (e.g. in `backend/.env` or env) to match each agent’s `master_token` so the controller can push config and add peers.

---

## 2. Run an agent (same machine for dev, or another machine)

**Option A – Run by hand (e.g. on your dev machine)**

```bash
cd vishwaas-agent
# Edit agent_config.json: master_url (controller URL), master_token (same as backend VISHWAAS_AGENT_TOKEN)
python3 -m venv venv
venv/bin/pip install -r requirements.txt
venv/bin/python -c "from app.main import run; run()"
```

The agent will request to join. In the controller UI go to **Join Requests** and click **Approve**.

**Option B – Install as a service (Linux, e.g. on the clone)**

```bash
cd vishwaas-agent
# Edit agent_config.json first
sudo ./install.sh
# Config is copied to /opt/vishwaas-agent/agent_config.json; edit there if needed, then:
sudo systemctl restart vishwaas-agent
```

---

## 3. Deploy agent to the clone machine

From the machine that has the vishwaas repo (e.g. the controller host):

```bash
cd vishwaas-agent
./deploy-to.sh cloneanurag@<clone-ip> ~/codex/vishwaas-agent
```

Example:

```bash
./deploy-to.sh 192.168.10.16
# or
./deploy-to.sh cloneanurag@192.168.10.16 ~/codex/vishwaas-agent
```

Then **on the clone machine**:

1. **Edit config** in the folder that was synced (e.g. `~/vishwaas-agent/agent_config.json` or `~/codex/vishwaas-agent/agent_config.json`):
   - **`master_url`**: Controller URL, e.g. `http://192.168.10.15:8000`
   - **`master_token`**: Same as the controller’s `VISHWAAS_AGENT_TOKEN`
   - **`agent_advertise_url`**: URL the controller uses to reach this agent, e.g. `http://192.168.10.16:9000` (cloneanurag machine IP, port 9000)

2. **Install and start** (recommended):

   ```bash
   cd ~/vishwaas-agent   # or the dest path you used
   sudo ./install.sh
   ```

   The agent is installed under `/opt/vishwaas-agent` and runs as a systemd service. To change config later: edit `/opt/vishwaas-agent/agent_config.json` and run `sudo systemctl restart vishwaas-agent`.

3. **Approve the node** in the controller UI (Join Requests → Approve). The controller will assign a VPN IP and push config to the agent (with retries if the agent was just starting).

**Requirements on the clone:** Python 3.10+, WireGuard tools (`sudo apt install wireguard-tools`). The install script runs the agent as root so it can create the WireGuard interface.

---

## Quick reference

| What              | Where        | Command / URL |
|-------------------|-------------|----------------|
| Controller API    | backend     | `cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| Controller UI     | frontend    | `cd frontend && npm run dev` → http://localhost:3000 |
| Agent (dev)       | vishwaas-agent | `venv/bin/python -c "from app.main import run; run()"` |
| Agent (service)   | cloneanurag | `sudo ./install.sh` then `systemctl status vishwaas-agent` |
| Deploy to clone   | from repo   | `./vishwaas-agent/deploy-to.sh cloneanurag@192.168.10.16`   |

See **DESIGN.md** for the flow (join, approve, connect). See **vishwaas-agent/README.md** and **vishwaas-agent/RUN_AGENT.md** for agent config and troubleshooting.
