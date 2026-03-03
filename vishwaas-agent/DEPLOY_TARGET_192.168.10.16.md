# Deploy agent to 192.168.10.16 (user: cloneanurag)

Target machine: **192.168.10.16** (user `cloneanurag`, path `~/codex/vishwaas-agent`).

## 1. From the machine that has the vishwaas repo (with TPM-integrated agent)

Run from the **vishwaas-agent** folder:

```bash
cd /path/to/vishwaas/vishwaas-agent
./deploy-to.sh cloneanurag@192.168.10.16 ~/codex/vishwaas-agent
```

If SSH asks for a password, enter cloneanurag's password. To avoid that, use an SSH key:

```bash
ssh-copy-id cloneanurag@192.168.10.16
```

Then run `./deploy-to.sh` again.

## 2. On 192.168.10.16 after deploy

```bash
cd ~/codex/vishwaas-agent
# Edit config if needed (master_url, master_token, agent_advertise_url)
nano agent_config.json
# Install and start (creates venv, systemd service)
sudo ./install.sh
```

Optional: if this machine has a TPM and you want the WireGuard key in TPM, add to `agent_config.json`:

```json
"use_tpm_wg_key": true,
"tpm_nv_index_wg": 1
```

Install `tpm2-tools` on that machine if you use TPM: `sudo apt install tpm2-tools`.

## 3. If you're already on 192.168.10.16 and have the repo elsewhere

Pull or copy the updated agent from your other machine (e.g. where you develop):

```bash
# From 192.168.10.16, pull from git (if you use git)
cd ~/codex/vishwaas
git pull
# Then re-run install if needed
cd vishwaas-agent && sudo ./install.sh
```

Or from your dev machine (with SSH access):

```bash
scp -r /path/to/vishwaas/vishwaas-agent/* cloneanurag@192.168.10.16:~/codex/vishwaas-agent/
```

(Exclude `venv` and `keys` when copying so you don’t overwrite local venv/keys.)
