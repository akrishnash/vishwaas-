# VISHWAAS Agent — Clone and run

Use one of the options below to get the agent code, then install and run it on each node.

---

## Option A: Git clone (if the repo is in Git)

```bash
# Clone the full vishwaas repo, then use the agent folder
git clone <REPO_URL> vishwaas
cd vishwaas/vishwaas-agent
```

Replace `<REPO_URL>` with your actual repo URL (e.g. `https://github.com/you/vishwaas.git`).

---

## Option B: Copy from your machine (rsync)

From the machine that already has the agent code:

```bash
cd /path/to/vishwaas
./vishwaas-agent/deploy-to.sh user@TARGET_HOST
```

Then on **TARGET_HOST**:

```bash
cd ~/vishwaas-agent
# 1. Edit agent_config.json: master_url, master_token, agent_advertise_url
# 2. Install and start:
sudo ./install.sh
```

---

## Option C: Tarball (no git, no rsync)

On the machine that has the agent:

```bash
cd /path/to/vishwaas
tar --exclude='vishwaas-agent/venv' --exclude='vishwaas-agent/keys' --exclude='vishwaas-agent/__pycache__' \
  -czvf vishwaas-agent.tar.gz vishwaas-agent/
# Send vishwaas-agent.tar.gz (e.g. scp, USB, download link)
```

On the target machine:

```bash
tar -xzvf vishwaas-agent.tar.gz
cd vishwaas-agent
# 1. Edit agent_config.json: master_url, master_token, agent_advertise_url
# 2. Install and start:
sudo ./install.sh
```

---

## After you have the code

1. **Edit `agent_config.json`** (required):
   - `master_url`: controller API base (e.g. `http://CONTROLLER_IP:8000`)
   - `master_token`: same as controller’s `VISHWAAS_AGENT_TOKEN`
   - `agent_advertise_url`: URL the controller uses to reach this agent (e.g. `http://THIS_NODE_IP:9000`)

2. **Install and start** (as root):
   ```bash
   sudo ./install.sh
   ```

3. **Check** (optional):
   ```bash
   sudo ./check-clone.sh
   systemctl status vishwaas-agent
   ```

See **README.md** in this folder for full details.
