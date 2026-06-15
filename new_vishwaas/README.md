# VISHWAAS — Installation Guide

VISHWAAS is a WireGuard VPN management system. One machine runs the **controller**
(web dashboard + API). Every other machine runs an **agent** that joins the VPN.

---

## What You Need

- A USB drive or file transfer method to get this package onto the target machine
- Root / sudo access on each machine
- Machines running CentOS 7/8/9, RHEL 8/9/10, or Oracle Linux 8/9/10 (x86_64)
- No internet connection required — everything is bundled

---

## Step 1 — Copy the package to the target machine

Transfer `vishwaas_pack.tar.gz` via USB, SCP, or any method, then extract it:

```bash
tar -xzf vishwaas_pack.tar.gz
cd vishwaas_pack
```

---

## Step 2 — Run setup (once per machine)

**On the controller machine** (the admin/dashboard machine — do this first):

```bash
sudo ./setup.sh controller
```

**On each agent machine** (every machine that should join the VPN):

```bash
sudo ./setup.sh agent
```

Setup will:
- Install Python 3.11 (bundled — no download needed)
- Install nginx (controller) or wireguard-tools (agent) from bundled RPMs
- Copy all code to `/opt/vishwaas/`
- Set up the Python environment — no pip install, packages are pre-built
- Generate secret tokens and write config files
- Open the required firewall ports

At the end of controller setup, you will see:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Setup complete!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  VISHWAAS_AGENT_TOKEN = a3f9c2e1b7...
  (copy this into each agent's agent_config.json as master_token)

  ── Start the controller ──────────────────────────────
  cd /opt/vishwaas/controller && ./start_controller.sh

  Dashboard: http://192.168.x.x/
```

**Write down the `VISHWAAS_AGENT_TOKEN`** — you will paste it into every agent config.

---

## Step 3 — Start the controller

```bash
cd /opt/vishwaas/controller
./start_controller.sh
```

Open a browser on any machine on the same network and go to:

```
http://<controller-ip>/
```

Log in with any username and password (default dev mode).

---

## Step 4 — Configure and start each agent

On each agent machine, edit the config:

```bash
nano /opt/vishwaas/agent/agent_config.json
```

Set these three fields:

```json
{
  "master_url": "http://<controller-ip>:8000",
  "master_token": "<paste VISHWAAS_AGENT_TOKEN here>",
  "agent_advertise_url": "http://<this-machine-ip>:9000"
}
```

Then start the agent:

```bash
cd /opt/vishwaas/agent
sudo ./start_agent.sh
```

---

## Step 5 — Approve the node on the dashboard

1. Open the dashboard → **Join Requests**
2. Click **Approve** next to the machine's name
3. The node status will change to **Active** — WireGuard is configured automatically

---

## Step 6 — Connect nodes

1. Dashboard → **Connections** → **New Connection**
2. Select two nodes and approve
3. Test from either node: `ping 10.10.10.x`

---

## Ports Required

| Machine    | Port  | Protocol | Direction |
|------------|-------|----------|-----------|
| Controller | 80    | TCP      | Inbound   |
| Controller | 8000  | TCP      | Inbound   |
| Agent      | 9000  | TCP      | Inbound   |
| Agent      | 51820 | UDP      | Both      |

`setup.sh` opens these automatically if `firewalld` is running.

---

## Quick Reference

```
CONTROLLER
  Setup:   sudo ./setup.sh controller
  Start:   cd /opt/vishwaas/controller && ./start_controller.sh
  Config:  nano /opt/vishwaas/controller/backend/.env
  Logs:    tail -f /opt/vishwaas/controller/logs/backend.log
  Health:  curl http://localhost:8000/health

AGENT
  Setup:   sudo ./setup.sh agent
  Config:  nano /opt/vishwaas/agent/agent_config.json
  Start:   cd /opt/vishwaas/agent && sudo ./start_agent.sh
  Health:  curl http://localhost:9000/health
  VPN:     sudo wg show
```

---

## Troubleshooting

**Agent never appears on dashboard**
```bash
# From the agent machine — can it reach the controller?
curl http://<controller-ip>:8000/health
# Check master_url and master_token in agent_config.json
```

**Dashboard loads but shows no data**
```bash
curl http://localhost:8000/health   # is the backend running?
sudo tail -20 /var/log/nginx/error.log
sudo setsebool -P httpd_can_network_connect 1  # if SELinux is blocking nginx
```

**WireGuard not starting**
```bash
lsmod | grep wireguard   # check kernel module
sudo modprobe wireguard  # load it manually if missing
sudo wg show             # show current VPN state
```

**"venv not found" or "uvicorn missing"**
```bash
# setup.sh was not run, or ran with an error — run it again:
sudo ./setup.sh controller   # or agent
```

For full details see `DEPLOYMENT_GUIDE.md` in this package.
