# VISHWAAS — Offline Package

Two steps. That's it.

---

## Step 1 — Setup (run once)

```bash
sudo ./setup.sh controller    # on the admin/dashboard machine
sudo ./setup.sh agent         # on each VPN node machine
```

This installs Python 3.11, creates the venv, and installs all packages — fully offline.

---

## Step 2 — Run

**Controller:**
```bash
cd /opt/vishwaas/controller
./start_controller.sh
```

**Agent** (fill in config first):
```bash
nano /opt/vishwaas/agent/agent_config.json
# Set: master_url, master_token, agent_advertise_url

cd /opt/vishwaas/agent
sudo ./start_agent.sh
```

---

## What's in the package

```
vishwaas_pack/
├── setup.sh                  ← run once per machine
├── python/                   ← Python 3.11 standalone (no system Python needed)
├── repo/                     ← nginx + wireguard RPMs
├── controller/
│   ├── backend/              ← API source + pip_packages/
│   ├── frontend/dist/        ← pre-built dashboard (no Node.js needed)
│   └── start_controller.sh  ← just run this
└── agent/
    ├── app/                  ← agent source + pip_packages/
    └── start_agent.sh        ← just run this
```
