# VISHWAAS Node Agent

Production-style, plug-and-play node agent for the VISHWAAS distributed system. Installable on any Linux (Ubuntu-based) machine without modifying source code.

## Requirements

- Linux (Ubuntu-based)
- Python 3.10+
- **WireGuard installed** (`wireguard-tools`, `ip`)
- Root for installation
- **Optional (TPM):** `tpm2-tools` and a TPM 2.0 device for hardware-bound key storage

## Deployment (plug-and-play)

1. **Copy** the entire `vishwaas-agent/` folder to the target machine.

2. **Edit** only `agent_config.json`:
   - `master_url`: Controller API base URL (e.g. `http://MASTER_IP:8000`) — required for join
   - `master_token`: Same value as controller’s `agent_token` — required only so the controller can add/remove peers on this node (not used for join)
   - `node_name`: `"auto"` (use hostname) or a fixed name
   - `wg_interface`, `listen_port`, `subnet`, `keys_dir` as needed

3. **Install** (as root):
   ```bash
   sudo ./install.sh
   ```

4. **Done.** The agent runs as a systemd service, auto-starts on boot, generates its own WireGuard keys, and registers with MASTER.

No code edits. No manual key exchange. No manual WireGuard config editing.

## What install.sh does

1. Copies agent to `/opt/vishwaas-agent`
2. Creates virtual environment and installs Python dependencies
3. Creates `/etc/vishwaas` for keys (optional; set `keys_dir` in config)
4. Installs and enables `vishwaas-agent.service` (runs as root so it can create the WireGuard interface)
5. Starts the service

## Startup flow

1. On start: ensure WireGuard keypair exists (generate if not).
2. Send `POST /request-join` to the controller with `node_name`, `public_key`, `agent_url` (no token — the controller gates by approve/reject).
3. When the controller returns **APPROVED** with `vpn_ip`, the agent sets that IP on the WireGuard interface and brings up `wg0` (no need for the controller to call back).
4. Enter **WAITING** or **ACTIVE** state. If the controller is unreachable, retry every 10 seconds.

## Agent API (controller → agent only)

All endpoints except `/health` require header **X-VISHWAAS-TOKEN** (must match `master_token`). So only the controller can add/remove peers; join requests do not use a token.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Liveness; returns `state` |
| POST | `/wg/start` | Start WireGuard interface |
| POST | `/wg/stop` | Stop WireGuard interface |
| POST | `/wg/add-peer` | Body: `public_key`, `allowed_ips`, optional `endpoint` |
| POST | `/wg/remove-peer` | Body: `public_key` |
| GET | `/wg/status` | Interface status (no private key) |
| POST | `/peer` | **Controller-compatible:** add peer. Body: `public_key`, `allowed_ip` (auto /32 if omitted) |
| DELETE | `/peer` | **Controller-compatible:** remove peer. Body: `public_key` |

The VISHWAAS Master backend calls `POST /peer` and `DELETE /peer` when approving/terminating connections. Set the same token in the backend as `VISHWAAS_AGENT_TOKEN` (or `agent_token` in config) so agent calls succeed.

Unauthorized requests are rejected and logged.

## Configuration (agent_config.json)

| Key | Description | Example |
|-----|-------------|---------|
| `node_name` | `"auto"` or hostname | `"auto"` |
| `master_url` | Controller API base (for join) | `"http://192.168.10.15:8000"` (use your controller IP) |
| `master_token` | Same as controller’s `agent_token`; needed so controller can call /peer | `"SECRET_TOKEN"` |
| `wg_interface` | WireGuard interface | `"wg0"` |
| `listen_port` | WG listen port | `51820` |
| `subnet` | Node subnet | `"10.10.10.0/24"` |
| `keys_dir` | Key storage | `"/etc/vishwaas"` |
| `agent_advertise_url` | URL controller uses to reach this agent (set VPN IP, add peers). Use IP controller can reach, e.g. `http://192.168.10.16:9000`. If empty, auto-detect is used (can be wrong on VMs). | `""` or `"http://192.168.10.16:9000"` |
| `agent_bind_host` | Bind address | `"0.0.0.0"` |
| `agent_port` | Agent API port | `9000` |
| `use_tpm_wg_key` | If `true`, store and read WireGuard private key from TPM NV (hardware-bound). Requires `tpm2-tools` and TPM 2.0. | `false` |
| `tpm_nv_index_wg` | TPM NV index for the WG key (default `1`). Must match one-time provisioning. | `1` |

## TPM (optional)

When `use_tpm_wg_key` is `true`, the agent stores the WireGuard private key in a TPM NV index so the key is bound to the machine’s hardware. This is recommended for defense and high-security deployments.

**Requirements:** Install `tpm2-tools` and ensure the node has a TPM 2.0 device.

**Flow:**

1. **Agent-generated keys:** On first run the agent generates the keypair as usual, then writes the private key to TPM NV (index 1 by default). On later runs it reads the key from TPM when bringing up the interface; the on-disk key file is optional.
2. **Controller-issued keys:** If the controller sends a private key (e.g. when `controller_issues_keys` is true), the agent writes it to disk and to TPM so future restarts can use TPM.

**One-time provisioning (alternative):** You can pre-load the key into TPM using the scripts under `tpm_scripts/TPM_NV/` (e.g. `load_wgkey.sh`), pointing the input to your `keys_dir/privatekey`. The agent will then read from TPM when `use_tpm_wg_key` is true.

If TPM read fails (e.g. no TPM or wrong index), the agent falls back to the key file in `keys_dir`.

## Logs and service

- **Log file:** `/var/log/vishwaas-agent.log`
- **Service:** `systemctl status vishwaas-agent`
- **Restart after config change:** `sudo systemctl restart vishwaas-agent`

## Uninstall

```bash
sudo ./uninstall.sh
```

Removes service and `/opt/vishwaas-agent`. Keeps `/etc/vishwaas` (keys) and log file.

## State model

- **WAITING** – Joined, awaiting MASTER commands
- **APPROVED** – Approved by MASTER
- **ACTIVE** – WireGuard running
- **ERROR** – Error (e.g. wg command failed)

Transitions are driven only by MASTER (e.g. `/wg/start` sets ACTIVE).

## Design

- **Self-contained:** single folder, no source edits per machine.
- **Externally configurable:** only `agent_config.json` changes per deployment.
- **Centralized authority:** MASTER controls join and WireGuard commands.
- **Hardened:** token auth, suspicious access logging, private key never exposed via API.
