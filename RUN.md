# How to run VISHWAAS

One **controller** (backend + frontend), one or more **agents** (one per machine that joins the VPN). Use the **controller** folder on the control-plane machine and the **agent** folder on each node. Approve joins in the UI; approve connections to link two nodes.

---

## 1. Run the controller (one machine)

From the repo root:

```bash
cd controller
./run_controller.sh
```

Or from repo root: `./controller/run_controller.sh`

This starts:

- **Backend** (API) on **http://0.0.0.0:8000**
- **Frontend** (UI) on **http://localhost:3000**
- Logs in `controller/logs/backend.log` and `controller/logs/frontend.log`

**Config:** Create `controller/backend/.env` and set:

- `VISHWAAS_AGENT_TOKEN` – same value as each agent’s `master_token`

If `VISHWAAS_AGENT_TOKEN` is not set, the controller logs a warning at startup: *"Please set it in .env ... so the controller can push config and peers to agents."*

**Manual run (optional):**

```bash
cd controller/backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
```

In another terminal:

```bash
cd controller/frontend
npm install && npm run dev
```

Open **http://localhost:3000** (or the controller machine’s IP:3000).

---

## 2. Run an agent (same machine for dev, or another machine)

**Option A – Run by hand (e.g. on your dev machine)**

1. Create or edit `agent/agent_config.json` (see `agent/agent_config.*.example`). Required:
   - **master_url** – controller URL (e.g. `http://192.168.10.15:8000`)
   - **master_token** – same as controller’s `VISHWAAS_AGENT_TOKEN`
   - **agent_advertise_url** – URL the controller uses to reach this agent (e.g. `http://192.168.10.16:9000`)

2. Run:

```bash
cd agent
sudo ./run_agent.sh
```

**Config validation:** Before starting, `run_agent.sh` checks `agent_config.json`. If anything is wrong (missing file, invalid JSON, or missing/invalid `master_url`, `master_token`, or `agent_advertise_url`), it prints **"Please enter correct details in agent_config.json"** and lists the issues, then exits. Fix the config and run again.

The agent will request to join. In the controller UI go to **Join Requests** and click **Approve**.

**Option B – Install as a service (Linux)**

```bash
cd agent
# Edit agent_config.json first
sudo ./install.sh
# Config is copied to /opt/vishwaas-agent/agent_config.json; edit there if needed, then:
sudo systemctl restart vishwaas-agent
```

---

## 3. Deploy agent to another machine

From the machine that has the vishwaas repo (e.g. the controller host):

```bash
cd agent
./deploy-agent-to-clone.sh [user@]clone-host [remote-path]
# Example: ./deploy-agent-to-clone.sh anurag@192.168.10.16
# Default remote path: /home/anurag/codex/vishwaas-agent-new
```

Or with `scp`: `scp -r agent user@<node-ip>:~/vishwaas-agent-new`

Then **on the node**:

1. Edit `agent_config.json` (or `~/vishwaas-agent/agent_config.json`):
   - **master_url** – controller URL (e.g. `http://192.168.10.15:8000`)
   - **master_token** – same as controller’s `VISHWAAS_AGENT_TOKEN`
   - **agent_advertise_url** – URL the controller uses to reach this agent (e.g. `http://<node-ip>:9000`)

2. Install and start:

   ```bash
   cd ~/vishwaas-agent   # or the path you used
   sudo ./run_agent.sh   # or sudo ./install.sh for systemd
   ```

3. **Approve the node** in the controller UI (Join Requests → Approve).

**Requirements on the node:** Python 3.10+, WireGuard tools (`sudo apt install wireguard-tools`).

---

## Quick reference

| What              | Where       | Command / URL |
|-------------------|-------------|----------------|
| Controller (all)  | controller/ | `cd controller && ./run_controller.sh` |
| Controller API    | controller/backend | :8000 |
| Controller UI     | controller/frontend | :3000 → http://localhost:3000 |
| Agent             | agent/      | `cd agent && sudo ./run_agent.sh` |
| Agent (service)   | agent/      | `sudo ./install.sh` then `systemctl status vishwaas-agent` |
| Deploy agent      | agent/      | `cd agent && ./deploy-agent-to-clone.sh user@host` |
| Capture logs      | controller/ | `cd controller && ./capture_log.sh` |

**Debug:** If agent config is wrong, `run_agent.sh` prints *"Please enter correct details in agent_config.json"* and what to fix. If controller token is missing, the backend logs a warning at startup.

See **DESIGN.md** for the flow. See **agent/README.md** and **agent/RUN_AGENT.md** for agent config and troubleshooting.
