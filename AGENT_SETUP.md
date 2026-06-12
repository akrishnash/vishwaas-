# VISHWAAS Agent — Setup Guide

This guide explains how to install and run the VISHWAAS VPN agent on a new machine.
The agent connects your machine to a VISHWAAS-managed WireGuard VPN network.
Once running, it sends a join request to the controller and waits for admin approval.

---

## Prerequisites

- Linux (Ubuntu 20.04+, Debian 11+, Fedora 36+, RHEL 8+, or equivalent)
- Python 3.10 or newer
- WireGuard kernel module
- Root / sudo access

Install dependencies:

```bash
# Ubuntu / Debian
sudo apt install wireguard python3 python3-venv -y

# Fedora / RHEL
sudo dnf install wireguard-tools python3 -y
```

---

## Step 1 — Extract the package

```bash
tar -xzf vishwaas-agent-v1.0.tar.gz
cd agent
```

---

## Step 2 — Configure

```bash
cp agent_config.json.example agent_config.json
nano agent_config.json
```

Fill in the following fields:

| Field | Description | Example |
|---|---|---|
| `master_url` | URL of the VISHWAAS controller | `http://192.168.10.15:8000` |
| `master_token` | Shared secret — get this from your admin | `changeme` |
| `agent_advertise_url` | This machine's IP and port (controller calls back here) | `http://192.168.10.20:9000` |
| `node_name` | `"auto"` uses hostname, or set a custom label | `"auto"` |

Everything else can stay as default.

> **Note:** `master_token` must exactly match the `VISHWAAS_AGENT_TOKEN` value set on the controller.

---

## Step 3 — Open firewall ports

The agent needs two ports reachable from the controller and peers:

```bash
# ufw (Ubuntu/Debian)
sudo ufw allow 9000/tcp    # agent API — controller calls back on this
sudo ufw allow 51820/udp   # WireGuard VPN traffic

# firewalld (Fedora/RHEL)
sudo firewall-cmd --permanent --add-port=9000/tcp --add-port=51820/udp
sudo firewall-cmd --reload
```

---

## Step 4 — Start the agent

```bash
sudo ./start_agent.sh
```

On first run this automatically:
1. Creates a Python virtual environment under `venv/`
2. Installs all required packages from `requirements.txt`
3. Starts the agent on port `9000`

The agent will register with the controller and appear as a **Pending** join request on the admin dashboard. An admin must approve it before the VPN connection becomes active.

---

## Checking status

```bash
# Is the agent process running?
sudo ./start_agent.sh        # runs in foreground — use screen/tmux for persistent sessions

# Quick health check (from another terminal)
curl http://localhost:9000/health
```

Expected response once approved and active:
```json
{"status": "ok", "state": "ACTIVE", "wg_up": true, "peer_count": 1, "vpn_ip": "10.10.10.x"}
```

---

## Running persistently (optional)

To keep the agent running across reboots without the systemd installer, use `screen` or `tmux`:

```bash
sudo apt install screen -y
sudo screen -dmS vishwaas-agent bash -c 'cd /path/to/agent && ./start_agent.sh'
```

Or register the included systemd service manually:

```bash
sudo cp vishwaas-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vishwaas-agent
sudo journalctl -u vishwaas-agent -f    # view logs
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `agent_config.json not found` | Config not created | `cp agent_config.json.example agent_config.json` |
| `master_url is required` | Config field empty | Edit `agent_config.json` and fill in the required fields |
| `python3-venv` not found | Package missing | `sudo apt install python3-venv` |
| Node stuck as **Pending** | Awaiting admin approval | Ask the admin to approve on the dashboard |
| Controller can't reach agent | Firewall blocking port 9000 | Open port 9000 TCP to the controller IP |
| WireGuard errors on start | `wg` not installed | `sudo apt install wireguard` |
| Agent keeps restarting | Bad config or controller unreachable | Check logs: `journalctl -u vishwaas-agent -n 50` |

---

## Uninstall

If you used `install.sh` to set up a systemd service:

```bash
sudo ./uninstall.sh
```

To remove everything manually:

```bash
sudo systemctl stop vishwaas-agent
sudo systemctl disable vishwaas-agent
sudo rm /etc/systemd/system/vishwaas-agent.service
sudo rm -rf /opt/vishwaas-agent
```
