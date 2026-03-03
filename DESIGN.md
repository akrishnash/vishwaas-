# VISHWAAS – Simple VPN flow

## Idea

- **Agent**: Starts, requests to join the network (sends node name + agent URL; optionally its WireGuard public key).
- **Controller**: You approve → controller assigns a VPN IP and sends config to the agent (with retries if the agent was offline).
- **Connect two nodes**: Approve a connection between them → controller tells each agent to add the other as a peer.

No manual “push VPN IP” in the normal path; one Approve does it.

---

## Two ways to handle keys

### 1. Agent-generated keys (default)

- Agent generates its own WireGuard keypair and sends `public_key` in the join request.
- Controller only ever sees the public key; it assigns a VPN IP and pushes that IP to the agent.
- Agent brings up `wg0` with the assigned IP (either from the approve response or from a later push).

### 2. Controller-issued keys (optional)

- Agent has no keys. It sends a join request with **no** `public_key` (or empty).
- When you approve, the controller generates a keypair, creates the node with that public key, and pushes **VPN IP + private key** to the agent.
- Agent writes the key and brings up `wg0`. Simpler agent (no key generation), but the private key is sent over the wire once (use HTTPS and a secure token).

**Agent config:** set `"controller_issues_keys": true` in `agent_config.json` to use controller-issued keys.

### 3. TPM-bound key storage (optional)

- When `use_tpm_wg_key` is true in `agent_config.json`, the agent stores the WireGuard private key in a TPM 2.0 NV index (hardware-bound). The key is written to TPM when generated or when received from the controller; on each start the agent reads it from TPM to bring up the interface. If TPM is unavailable, the agent falls back to the key file. Recommended for defense and high-security deployments. Requires `tpm2-tools` and a TPM on the node.

---

## Flow summary

| Step | What happens |
|------|----------------|
| 1 | Agent starts → sends “request to join” (node name, agent URL, and public key if it has one). |
| 2 | Controller shows a pending join request; you click **Approve**. |
| 3 | Controller assigns a VPN IP, creates the node, and pushes config to the agent (VPN IP, and private key if controller-issued). If the agent is unreachable, controller retries in the background. |
| 4 | Agent receives config and brings up the WireGuard interface. |
| 5 | To connect two nodes: create a connection request between them and **Approve** → controller adds each node as a peer on the other. |

“Retry config” in the UI is only for when the agent was offline at approve time; normally you don’t need it.
