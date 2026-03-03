# How to run the VISHWAAS agent on this machine

This machine will act as a **node** in the VPN. The **controller** runs on another machine (the master). You only need to run the agent here.

---

## What you need

- **Python 3.10 or newer**  
  Check: `python3 --version`

- **Network access** to the controller (e.g. `192.168.10.15` on port `8000`)

- **(Optional, for full VPN)** WireGuard tools: `sudo apt install wireguard-tools`  
  The agent can run without it; WireGuard is needed when the controller approves connections.

---

## Step 1: Put the agent folder on this machine

You should have a folder named **`vishwaas-agent`** (with `app/`, `agent_config.json`, `requirements.txt`, etc.).

Example location: `~/codex/vishwaas-agent`  
If it’s somewhere else, use your path in the commands below.

---

## Step 2: Edit the config (one time)

Open **`agent_config.json`** in the agent folder.

You **must** set:

| Field          | Meaning                    | Example                          |
|----------------|----------------------------|----------------------------------|
| `master_url`   | Controller API address     | `"http://192.168.10.15:8000"`    |
| `master_token` | Same secret as the controller | `"your-shared-secret"`       |
| `agent_advertise_url` | **Important.** URL the controller uses to call this agent (set VPN IP, add peers). Use the IP the controller can reach (e.g. `"http://192.168.10.16:9000"` on the same LAN). If empty, the agent auto-detects an IP (often wrong on VMs/NAT), so the controller may not reach it and the WireGuard interface won’t get the VPN IP or peers. | `"http://192.168.10.16:9000"` or `""` |

- **`master_url`**: Use the **real IP or hostname** of the machine where the controller runs, and port `8000`.  
  Get the correct value from whoever runs the controller.

- **`master_token`**: Must be **exactly** the same as the controller’s `VISHWAAS_AGENT_TOKEN`.  
  Get it from whoever runs the controller.

- **`agent_advertise_url`**: Set this to **the URL at which the controller can reach this machine** (same network), e.g. `http://<this-machine-IP>:9000`. If you leave it empty and the auto-detected IP is wrong (e.g. VM NAT 10.0.2.x), the controller will not be able to push the VPN IP or peers to this agent, and you will not see the WireGuard interface or addresses.

Other fields (e.g. `node_name`, `agent_port`) can stay as in the example unless you were told to change them.

Save the file.

---

## Step 3: One-time setup (venv + dependencies)

In a terminal, go into the agent folder and create a virtual environment and install dependencies:

```bash
cd ~/codex/vishwaas-agent
```

*(If your folder is elsewhere, use that path instead of `~/codex/vishwaas-agent`.)*

**Important: each machine must have its own WireGuard keys.** If you copied this folder from another machine (or copied the `keys/` folder), delete `keys/` so this agent generates a new keypair and gets its own VPN IP:

```bash
rm -rf keys
```

Then run:

```bash
python3 -m venv venv
venv/bin/pip install -r requirements.txt
```

You only need to do this once (or after updating the agent code).

---

## Step 4: Start the agent

From the **same** agent folder:

```bash
cd ~/codex/vishwaas-agent
venv/bin/python -c "from app.main import run; run()"
```

Leave this terminal open. You should see lines like:

- `VISHWAAS agent starting; log file: ...`
- `Join request sent to MASTER http://192.168.10.15:8000 as node <name>`

That means the agent is running and is asking the controller to join the VPN.

---

## Step 5: Approve this node on the controller

The controller does **not** auto-approve. Someone must:

1. Open the **controller UI** (in a browser, e.g. `http://192.168.10.15:3000`).
2. Go to **Join Requests**.
3. Find this node and click **Approve**.

After approval you should see something like:

- `Join approved by MASTER (vpn_ip=10.10.10.x); stopping join requests`
- `Join loop finished (approved or rejected)`

The agent will then wait for the controller to add VPN connections (peers) when needed.

---

## Stopping the agent

In the terminal where the agent is running, press **Ctrl+C**.

---

## Test connectivity (before or after starting the agent)

On **this** machine, from the agent folder:

```bash
cd ~/codex/vishwaas-agent
./test-controller-reach.sh
```

This checks that `agent_config.json` has a valid `master_url` and that the controller responds. If it fails, fix the config or network before starting the agent.

Or manually:

```bash
# Replace with your controller IP if different
curl -s http://192.168.10.15:8000/
# Should return something like {"service":"VISHWAAS Master",...}
```

---

## Troubleshooting

- **“MASTER unreachable”**  
  The agent cannot reach the controller. On the **agent machine** run `./test-controller-reach.sh`. Ensure the **controller** is started with `--host 0.0.0.0` (not just 127.0.0.1) and that the firewall allows port 8000 from the agent’s network (e.g. `sudo ufw allow 8000` or equivalent).

- **“Join rejected by MASTER”**  
  The controller may still be using old logic. Whoever runs the controller should restart the controller backend and try again. After that, restart the agent (Step 4).

- **“Permission denied” when running**  
  Run the commands from Step 3 and 4 as the same user that owns the agent folder; don’t use `sudo` for `venv/bin/python ...`.

- **WireGuard / `wg` errors later**  
  Install WireGuard tools: `sudo apt install wireguard-tools` (or equivalent). The agent can still run and “join”; WireGuard is needed when the controller sets up connections.

---

## Optional: run as a service (Linux)

To start the agent at boot and run it in the background **on this (agent) machine**, run the install script as root:

```bash
cd ~/vishwaas-agent   # or wherever you put the agent
sudo ./install.sh
```

Then edit `/opt/vishwaas-agent/agent_config.json` if needed and `sudo systemctl restart vishwaas-agent`.

For a one-off “run in background” without systemd you can use:

```bash
cd ~/codex/vishwaas-agent
nohup venv/bin/python -c "from app.main import run; run()" > agent.log 2>&1 &
```

To stop it later: `pkill -f "app.main import run"`.
