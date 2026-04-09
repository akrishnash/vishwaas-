"""
VISHWAAS Agent - FastAPI application and startup flow.

Startup: ensure keypair -> detect local IP -> POST join to MASTER -> WAITING.
Background: retry join every 10s if MASTER unreachable.

Join: no token sent; controller decides via approve/reject.
Controller→agent (add/remove peer): requires X-VISHWAAS-TOKEN so only the
controller can push peer changes. Private key never exposed.
"""

import asyncio
import socket
import sys
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app import wireguard, state
from app.config import (
    get_agent_advertise_url,
    get_agent_bind_host,
    get_agent_port,
    get_controller_issues_keys,
    get_master_token,
    get_master_url,
    get_node_name,
)
from app.logger import (
    get_logger,
    log_command,
    log_startup,
    log_join_request,
    log_error,
)
from app.security import require_master_token, log_unauthorized, get_client_ip
from app.state import get_state, set_waiting, set_active, set_error

logger = get_logger()

# Retry interval when MASTER is unreachable (seconds)
JOIN_RETRY_INTERVAL = 10

# Set when controller returns APPROVED or REJECTED; join loop then stops
_join_decided = False


def _detect_local_ip() -> str:
    """Detect local IP for agent_url (prefer non-loopback)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 53))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _agent_url() -> str:
    """Base URL this agent advertises to MASTER (controller uses this to call back)."""
    advertised = get_agent_advertise_url()
    if advertised:
        logger.debug("Agent URL from config (advertise): %s", advertised)
        return advertised
    host = get_agent_bind_host()
    port = get_agent_port()
    if host == "0.0.0.0":
        host = _detect_local_ip()
    url = f"http://{host}:{port}"
    logger.debug("Agent URL (detected): %s", url)
    return url


def _send_join_request() -> bool:
    """POST /request-join to MASTER. No token; controller gates by approve/reject.
    Returns True if request was sent and status is still PENDING.
    Sets _join_decided and returns False when controller returns APPROVED or REJECTED.
    When controller_issues_keys and no keypair yet, send public_key="" so controller generates and pushes keys.
    """
    global _join_decided
    import urllib.request
    import urllib.error
    import json as _json

    master = get_master_url()
    if not master:
        logger.warning("master_url not configured")
        return False
    controller_issues_keys = get_controller_issues_keys()
    if controller_issues_keys and not wireguard.keypair_exists():
        # Agent has no keys; controller will issue them on approve. Send request without public_key.
        public_key = ""
        logger.info("Sending join request (controller will issue keys): node_name=%s", get_node_name())
    else:
        try:
            wireguard.generate_keypair()
            public_key = wireguard.get_public_key()
        except Exception as e:
            log_error("Key generation or read failed", e)
            return False
    node_name = get_node_name()
    agent_url = _agent_url()
    payload = {
        "node_name": node_name,
        "public_key": public_key,
        "agent_url": agent_url,
    }
    logger.info("Sending join request to %s: node_name=%s agent_url=%s public_key=%s", master, node_name, agent_url, (public_key[:12] + "..." if len(public_key) > 12 else "(controller issues)"))
    data = _json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{master}/request-join",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.getcode() != 200:
                logger.warning("Join request returned %s", resp.getcode())
                return False
            body = _json.loads(resp.read().decode("utf-8"))
            status = (body.get("status") or "").upper()
            logger.debug("Join response: status=%s body=%s", status, body)
            if status == "APPROVED":
                _join_decided = True
                state.set_approved()
                log_join_request(master, node_name)
                vpn_ip = body.get("vpn_ip")
                if vpn_ip:
                    try:
                        wireguard.set_assigned_vpn_ip(vpn_ip)
                        result = wireguard.wg_up()
                        if result.get("success"):
                            state.set_active()
                            logger.info("WireGuard interface up with VPN IP %s", vpn_ip)
                        else:
                            logger.warning("wg_up failed: %s", result.get("detail") or result.get("message"))
                    except Exception as e:
                        log_error("Setting VPN IP / wg_up failed", e)
                logger.info("Join approved by MASTER (vpn_ip=%s); stopping join requests", vpn_ip or "")
                return False
            if status == "REJECTED":
                _join_decided = True
                logger.info("Join rejected by MASTER; stopping join requests")
                return False
            # PENDING: keep sending periodically
            log_join_request(master, node_name)
            return True
    except urllib.error.HTTPError as e:
        logger.warning("Join request HTTP error: %s %s", e.code, e.reason)
        return False
    except urllib.error.URLError as e:
        logger.warning("MASTER unreachable (%s): %s", master, e.reason)
        return False
    except Exception as e:
        log_error("Join request failed", e)
        return False


async def _join_loop():
    """Background: send join until MASTER approves or rejects; then stop."""
    set_waiting()
    master = get_master_url()
    logger.info("Join loop started; master_url=%s (requests will be sent every %ss)", master or "(not set)", JOIN_RETRY_INTERVAL)
    while not _join_decided:
        if _send_join_request():
            set_waiting()
        await asyncio.sleep(JOIN_RETRY_INTERVAL)
    logger.info("Join loop finished (approved or rejected)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: generate keys, send join, start background join loop. Shutdown: no-op."""
    global _join_decided
    log_startup()
    logger.debug("Lifespan: generating keypair (if needed)")
    try:
        wireguard.generate_keypair()
    except Exception as e:
        log_error("Startup key generation failed", e)
        set_error()
    # Always send a fresh join request on startup so controller sees it as pending.
    # Controller will re-approve and push VPN config again.
    logger.info("Lifespan: starting join loop")
    task = asyncio.create_task(_join_loop())
    yield
    logger.info("Lifespan: shutting down, cancelling join loop")
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="VISHWAAS Node Agent",
    description="WireGuard node agent; MASTER-controlled.",
    lifespan=lifespan,
)


# ---- Health (no auth for readiness probes; optional: restrict in firewall)
@app.get("/health")
def health() -> dict[str, Any]:
    """
    Deep liveness/readiness check.
    Returns agent state, WireGuard interface status, peer count, and assigned VPN IP.
    """
    state_val = get_state().value
    iface = wireguard.get_wg_interface() if hasattr(wireguard, "get_wg_interface") else "wg0"
    iface_up = wireguard.interface_is_up()
    vpn_ip = wireguard.get_assigned_vpn_ip()

    peer_count = 0
    if iface_up:
        try:
            status = wireguard.wg_status()
            peer_count = len(status.get("peers", []))
        except Exception:
            pass

    logger.debug("Health check: state=%s wg_up=%s peers=%s vpn_ip=%s", state_val, iface_up, peer_count, vpn_ip)
    return {
        "status": "ok",
        "state": state_val,
        "wg_interface": iface,
        "wg_up": iface_up,
        "peer_count": peer_count,
        "vpn_ip": vpn_ip,
    }


# ---- Controller assigns VPN IP (provision_node: ensure wg0 exists and is up, idempotent)
@app.post("/set-vpn-address", dependencies=[Depends(require_master_token)])
def set_vpn_address(body: dict[str, Any]) -> dict[str, Any]:
    """
    Provision node: ensure wg0 exists and is up with the assigned VPN IP.
    If wg0 already exists: do NOT recreate it, do NOT regenerate private key; verify IP, ensure up.
    If wg0 does not exist: create interface, set private key, assign IP, bring up.
    """
    global _join_decided
    vpn_ip = body.get("vpn_ip")
    if not vpn_ip or not isinstance(vpn_ip, str):
        logger.warning("set-vpn-address rejected: vpn_ip missing or invalid")
        raise HTTPException(status_code=400, detail="vpn_ip required")
    vpn_ip = vpn_ip.strip()
    private_key = body.get("private_key")
    if private_key and isinstance(private_key, str):
        logger.info("set-vpn-address: received vpn_ip=%s and controller-issued private key", vpn_ip)
        try:
            wireguard.set_private_key(private_key.strip())
        except Exception as e:
            log_error("set-vpn-address: writing controller key failed", e)
            return {"success": False, "message": str(e), "detail": None}
    else:
        logger.info("set-vpn-address: received vpn_ip=%s", vpn_ip)
    result = wireguard.provision_interface(vpn_ip)
    if result.get("success"):
        # Controller has approved and pushed VPN config — stop the join loop
        _join_decided = True
        state.set_active()
        logger.info("set-vpn-address: WireGuard provisioned with vpn_ip=%s, join loop stopped", vpn_ip)
    else:
        logger.warning("set-vpn-address: provision_interface failed: %s", result.get("detail") or result.get("message"))
    return result


# ---- Protected API (MASTER only via X-VISHWAAS-TOKEN)
@app.post("/wg/start", dependencies=[Depends(require_master_token)])
def wg_start() -> dict[str, Any]:
    """Start WireGuard interface. Transitions to ACTIVE on success."""
    logger.info("Command: /wg/start")
    result = wireguard.wg_up()
    log_command("/wg/start", result.get("success", False), result.get("detail", ""))
    if result.get("success"):
        state.set_active()
    else:
        state.set_error()
    return result


@app.post("/wg/stop", dependencies=[Depends(require_master_token)])
def wg_stop() -> dict[str, Any]:
    """Stop WireGuard interface."""
    logger.info("Command: /wg/stop")
    result = wireguard.wg_down()
    log_command("/wg/stop", result.get("success", False), result.get("detail", ""))
    return result


@app.post("/wg/add-peer", dependencies=[Depends(require_master_token)])
def wg_add_peer(body: dict[str, Any]) -> dict[str, Any]:
    """Add peer. Body: public_key, allowed_ips, endpoint (optional)."""
    pk = body.get("public_key")
    allowed = body.get("allowed_ips")
    if not pk or not allowed:
        raise HTTPException(status_code=400, detail="public_key and allowed_ips required")
    logger.info("Command: /wg/add-peer allowed_ips=%s peer_key=%s...", allowed, (pk[:12] + "..." if len(pk) > 12 else pk))
    result = wireguard.wg_add_peer(pk, allowed, body.get("endpoint"))
    log_command("/wg/add-peer", result.get("success", False), result.get("detail", ""))
    return result


@app.post("/wg/remove-peer", dependencies=[Depends(require_master_token)])
def wg_remove_peer(body: dict[str, Any]) -> dict[str, Any]:
    """Remove peer. Body: public_key."""
    pk = body.get("public_key")
    if not pk:
        raise HTTPException(status_code=400, detail="public_key required")
    logger.info("Command: /wg/remove-peer peer_key=%s...", (pk[:12] + "..." if len(pk) > 12 else pk))
    result = wireguard.wg_remove_peer(pk)
    log_command("/wg/remove-peer", result.get("success", False), result.get("detail", ""))
    return result


@app.get("/wg/status", dependencies=[Depends(require_master_token)])
def wg_status() -> dict[str, Any]:
    """Return WireGuard interface status (no private key)."""
    return wireguard.wg_status()


@app.post("/wg/down", dependencies=[Depends(require_master_token)])
def wg_down() -> dict[str, Any]:
    """Bring down WireGuard interface (e.g. when last connection is terminated)."""
    result = wireguard.wg_down()
    log_command("/wg/down", result.get("success", False), result.get("detail", ""))
    return result


# ---- Controller-compatible API (same semantics as backend agent_client)
# POST /peer (add), DELETE /peer (remove). Do not restart interface for peer changes.
@app.post("/peer", dependencies=[Depends(require_master_token)])
def peer_add(body: dict[str, Any]) -> dict[str, Any]:
    """
    Add or update peer. Interface must already exist (provisioned via set-vpn-address).
    Does not call wg_up. Uses persistent-keepalive 25. Idempotent: if peer exists, updates it.
    """
    pk = body.get("public_key")
    allowed = body.get("allowed_ips") or body.get("allowed_ip")
    if not pk or not allowed:
        raise HTTPException(status_code=400, detail="public_key and allowed_ip (or allowed_ips) required")
    if "/" not in allowed:
        allowed = f"{allowed}/32"
    endpoint = body.get("endpoint")
    keepalive = body.get("persistent_keepalive", 25)
    if not wireguard.interface_exists():
        logger.warning("POST /peer: interface does not exist")
        return {"success": False, "message": "Interface not provisioned; approve join first", "detail": None}
    result = wireguard.wg_add_peer(pk, allowed, endpoint=endpoint, persistent_keepalive=keepalive)
    log_command("/peer (add)", result.get("success", False), result.get("detail", ""))
    if result.get("success"):
        state.set_active()
    return result


@app.delete("/peer", dependencies=[Depends(require_master_token)])
def peer_remove(body: dict[str, Any]) -> dict[str, Any]:
    """Remove peer. Idempotent: if peer not present, return success. Interface stays up."""
    pk = body.get("public_key")
    if not pk:
        raise HTTPException(status_code=400, detail="public_key required")
    logger.info("Command: DELETE /peer peer_key=%s...", (pk[:12] + "..." if len(pk) > 12 else pk))
    result = wireguard.wg_remove_peer(pk)
    log_command("/peer (delete)", result.get("success", False), result.get("detail", ""))
    return result


@app.post("/ip-forward/enable", dependencies=[Depends(require_master_token)])
def ip_forward_enable() -> dict[str, Any]:
    """Enable IPv4 IP forwarding (required for gateway/hub nodes to route VPN traffic)."""
    import subprocess
    logger.info("Command: POST /ip-forward/enable")
    try:
        result = subprocess.run(
            ["sysctl", "-w", "net.ipv4.ip_forward=1"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            logger.info("ip-forward/enable: success")
            return {"success": True, "message": "IP forwarding enabled"}
        else:
            logger.warning("ip-forward/enable: failed: %s", result.stderr.strip())
            return {"success": False, "message": result.stderr.strip()}
    except Exception as e:
        log_error("ip-forward/enable failed", e)
        return {"success": False, "message": str(e)}


@app.post("/remove-node", dependencies=[Depends(require_master_token)])
def remove_node() -> dict[str, Any]:
    """
    Remove this node: remove all peers, delete wg0 interface, clean vpn_ip file.
    Does not regenerate or delete private key.
    """
    logger.info("Command: POST /remove-node")
    result = wireguard.wg_remove_node()
    log_command("/remove-node", result.get("success", False), result.get("detail", ""))
    return result


# ---- Global exception handler: never crash, return JSON
@app.exception_handler(Exception)
def global_exception_handler(request, exc):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": "Internal error", "detail": None},
    )


# ---- 401 handler: log suspicious, then return same response
@app.exception_handler(HTTPException)
def http_exception_handler(request, exc):
    if exc.status_code == 401:
        log_unauthorized(request, "invalid or missing token")
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


def run():
    """Entry point for uvicorn (systemd)."""
    host = get_agent_bind_host()
    port = get_agent_port()
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        log_config=None,
        access_log=True,
    )


if __name__ == "__main__":
    run()
    sys.exit(0)
