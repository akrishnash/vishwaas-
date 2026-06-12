# VISHWAAS — Offline Deployment Package

Built for: Oracle Linux 10, x86_64, Python 3.12

## Quick Start

### 1. Copy this folder to the target machine

```bash
scp -r vishwaas_pack/ user@target-machine:~/
# or copy via USB
```

### 2. On the controller machine (dashboard + API)

```bash
cd vishwaas_pack
sudo ./install.sh controller
```

Then start it:

```bash
cd /opt/vishwaas/controller
./start_controller.sh
```

Dashboard is available at `http://<machine-ip>/`

### 3. On each agent/node machine

```bash
cd vishwaas_pack
sudo ./install.sh agent
```

Edit the config, then start:

```bash
nano /opt/vishwaas/agent/agent_config.json   # fill in master_url and master_token
cd /opt/vishwaas/agent
sudo ./start_agent.sh
```

The node appears as **Pending** on the dashboard — approve it to bring it onto the VPN.

---

## What's included

```
vishwaas_pack/
├── install.sh                    ← single installer for both controller and agent
├── README.md                     ← this file
├── OFFLINE_INSTALL.md            ← detailed manual setup guide
├── repo/                         ← offline RPMs (python3, python3-pip, nginx,
│                                    wireguard-tools + all dependencies)
├── controller/
│   ├── backend/                  ← controller API source
│   ├── frontend/dist/            ← pre-built dashboard (no Node.js needed)
│   ├── pip_packages/             ← all Python wheels for controller
│   ├── nginx.conf
│   └── start_controller.sh
└── agent/
    ├── app/                      ← agent source
    ├── pip_packages/             ← all Python wheels for agent
    ├── agent_config.json.example
    ├── requirements.txt
    └── start_agent.sh
```

## Useful commands after install

```bash
# Controller — start
cd /opt/vishwaas/controller && ./start_controller.sh

# Controller — config
nano /opt/vishwaas/controller/backend/.env

# Agent — start (requires root for WireGuard)
cd /opt/vishwaas/agent && sudo ./start_agent.sh

# Agent — config
nano /opt/vishwaas/agent/agent_config.json
```
