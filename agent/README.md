# VISHWAAS Node Agent

The agent runs on every node that joins the VISHWAAS WireGuard mesh.  
On startup it sends a join request to the controller and waits for approval.  
Once approved, the controller assigns a VPN IP and pushes peer configurations automatically.

---

## Prerequisites

On each new machine, install:

```bash
sudo apt update
sudo apt install -y python3 python3-venv wireguard-tools
```

Root (or sudo) is required because the agent manages WireGuard interfaces.

---

## How to connect a new machine

### Step 1 — Copy the agent

From any machine that already has the agent folder:

```bash
rsync -av --exclude='venv' --exclude='__pycache__' --exclude='keys/' \
  /path/to/vishwaas/agent/ \
  <user>@<new-machine-ip>:~/vishwaas-agent/
```

> **Important:** Always exclude `keys/` when copying. Each machine must generate its own WireGuard keypair. Sharing keys causes both machines to appear as the same node to the controller.

### Step 2 — Edit the config

On the new machine, always start from the example config — never reuse another machine's `agent_config.json`:

```bash
cp ~/vishwaas-agent/agent_config.json.example ~/vishwaas-agent/agent_config.json
```

Then open it and set:

| Field | What to set |
|---|---|
| `node_name` | Unique name for this machine, or `"auto"` to use the hostname |
| `master_url` | Controller address, e.g. `http://192.168.10.15:8000` |
| `master_token` | Shared secret — must match `VISHWAAS_AGENT_TOKEN` on the controller |
| `agent_advertise_url` | This machine's reachable address, e.g. `http://192.168.10.17:9000` |
| `agent_port` | Port the agent listens on (default `9000`) |
| `wg_interface` | WireGuard interface name (default `wg0`) |
| `listen_port` | WireGuard UDP listen port (default `51820`) |
| `use_tpm_wg_key` | `true` if WireGuard private key is stored in TPM, `false` otherwise |

Example for a new node at `192.168.10.17`:

```json
{
  "node_name": "machine3",
  "master_url": "http://192.168.10.15:8000",
  "master_token": "<same token as controller>",
  "agent_advertise_url": "http://192.168.10.17:9000",
  "wg_interface": "wg0",
  "listen_port": 51820,
  "subnet": "10.10.10.0/24",
  "keys_dir": "./keys",
  "agent_bind_host": "0.0.0.0",
  "agent_port": 9000,
  "use_tpm_wg_key": false,
  "tpm_nv_index_wg": 1
}
```

### Step 3 — Install and start

```bash
cd ~/vishwaas-agent
sudo ./install.sh
```

This will:
- Copy files to `/opt/vishwaas-agent`
- Create a Python venv and install dependencies
- Register and start the `vishwaas-agent` systemd service

The agent starts sending join requests to the controller immediately.

### Step 4 — Approve on the controller

Open the controller UI (default `http://192.168.10.15:3000`) and go to **Join Requests**.  
The new node will appear with status **PENDING**. Click **Approve**.

---

## How VPN IPs are assigned

VPN IPs are assigned by the controller from the subnet defined in controller config (default `10.10.10.0/24`).

- The controller allocates the next free IP in the subnet when a join request is approved.
- The assigned VPN IP is pushed to the agent via `POST /set-vpn-address`.
- The agent brings up the WireGuard interface with that IP automatically.
- The controller then pushes peer entries to all other active nodes so they can reach the new node.

You do **not** need to configure VPN IPs manually on the nodes.

---

## Checking agent status

```bash
# Service status
systemctl status vishwaas-agent

# Live logs
journalctl -u vishwaas-agent -f

# Health check (from any machine that can reach port 9000)
curl http://<node-ip>:9000/health
```

---

## Uninstalling

```bash
cd ~/vishwaas-agent
sudo ./uninstall.sh
```

---

## File layout after install

```
/opt/vishwaas-agent/
  app/           Agent source (FastAPI)
  venv/          Python virtual environment
  agent_config.json
  keys/          WireGuard keypair (generated on first run if not present)
```

Logs: `/var/log/vishwaas-agent.log`
