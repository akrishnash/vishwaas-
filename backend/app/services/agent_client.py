"""
Agent client: call node agent endpoints (add peer, remove peer).
Uses X-VISHWAAS-TOKEN when agent_token is set (plug-and-play agent compatibility).
"""
import logging
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


def _agent_headers() -> dict[str, str]:
    """Headers for agent calls; include token when configured."""
    h = {"Content-Type": "application/json"}
    if settings.agent_token:
        h["X-VISHWAAS-TOKEN"] = settings.agent_token
    return h


def _endpoint_from_agent_url(agent_url: str, wg_port: int = 51820) -> str | None:
    """Derive WireGuard endpoint (host:port) from agent URL so the other node knows where to send UDP."""
    if not agent_url or not agent_url.strip():
        return None
    from urllib.parse import urlparse
    o = urlparse(agent_url.strip() if agent_url.startswith("http") else f"http://{agent_url.strip()}")
    if not o.hostname:
        return None
    return f"{o.hostname}:{wg_port}"


async def add_peer(
    agent_base_url: str,
    peer_public_key: str,
    peer_vpn_ip: str,
    peer_endpoint: str | None = None,
) -> bool:
    """
    Call agent at agent_base_url to add a peer (or update if exists).
    Agent uses wg set peer ... allowed-ips ... endpoint ... persistent-keepalive 25.
    Does not restart interface.
    Returns True if agent responded successfully.
    """
    url = f"{agent_base_url.rstrip('/')}/peer"
    allowed_ip = f"{peer_vpn_ip}/32" if "/" not in peer_vpn_ip else peer_vpn_ip
    pk_short = (peer_public_key[:12] + "...") if len(peer_public_key) > 12 else peer_public_key
    payload = {
        "public_key": peer_public_key,
        "allowed_ip": allowed_ip,
        "persistent_keepalive": 25,
    }
    if peer_endpoint:
        payload["endpoint"] = peer_endpoint
    logger.info("agent_client add_peer: url=%s allowed_ip=%s endpoint=%s peer_key=%s", url, allowed_ip, peer_endpoint, pk_short)
    try:
        async with httpx.AsyncClient(timeout=settings.agent_timeout) as client:
            r = await client.post(
                url,
                json=payload,
                headers=_agent_headers(),
            )
            if r.is_success:
                logger.info("agent_client add_peer: success url=%s", url)
            else:
                logger.warning("add_peer failed %s %s: %s", agent_base_url, r.status_code, r.text[:200])
            return r.is_success
    except Exception as e:
        logger.warning("add_peer failed %s: %s", agent_base_url, e)
        return False


async def set_vpn_address(agent_base_url: str, vpn_ip: str, private_key: str | None = None) -> bool:
    """Tell the agent its assigned VPN IP (and optional controller-issued private_key) so it can configure wg0."""
    url = f"{agent_base_url.rstrip('/')}/set-vpn-address"
    payload: dict = {"vpn_ip": vpn_ip}
    if private_key:
        payload["private_key"] = private_key
    logger.info("agent_client set_vpn_address: url=%s vpn_ip=%s has_key=%s", url, vpn_ip, bool(private_key))
    try:
        async with httpx.AsyncClient(timeout=settings.agent_timeout) as client:
            r = await client.post(
                url,
                json=payload,
                headers=_agent_headers(),
            )
            if r.is_success:
                logger.info("agent_client set_vpn_address: success url=%s vpn_ip=%s", url, vpn_ip)
            else:
                logger.warning("set_vpn_address failed %s %s: %s", agent_base_url, r.status_code, r.text[:200])
            return r.is_success
    except Exception as e:
        logger.warning("set_vpn_address failed %s: %s", agent_base_url, e)
        return False


async def remove_peer(agent_base_url: str, peer_public_key: str) -> bool:
    """Call agent to remove a peer (DELETE /peer). Idempotent: agent ignores if peer not present."""
    url = f"{agent_base_url.rstrip('/')}/peer"
    pk_short = (peer_public_key[:12] + "...") if len(peer_public_key) > 12 else peer_public_key
    logger.info("agent_client remove_peer: url=%s peer_key=%s", url, pk_short)
    try:
        async with httpx.AsyncClient(timeout=settings.agent_timeout) as client:
            r = await client.request(
                "DELETE",
                url,
                json={"public_key": peer_public_key},
                headers=_agent_headers(),
            )
            if r.is_success:
                logger.info("agent_client remove_peer: success url=%s", url)
            else:
                logger.warning("remove_peer failed %s %s: %s", agent_base_url, r.status_code, r.text[:200])
            return r.is_success
    except Exception as e:
        logger.warning("remove_peer failed %s: %s", agent_base_url, e)
        return False


async def remove_node(agent_base_url: str) -> bool:
    """
    Tell the agent to remove its WireGuard interface and clean up.
    Agent removes all peers, deletes wg0, cleans config. Does not regenerate keys.
    Returns True if agent responded successfully.
    """
    url = f"{agent_base_url.rstrip('/')}/remove-node"
    logger.info("agent_client remove_node: url=%s", url)
    try:
        async with httpx.AsyncClient(timeout=settings.agent_timeout) as client:
            r = await client.post(url, json={}, headers=_agent_headers())
            if r.is_success:
                logger.info("agent_client remove_node: success url=%s", url)
            else:
                logger.warning("remove_node failed %s %s: %s", agent_base_url, r.status_code, r.text[:200])
            return r.is_success
    except Exception as e:
        logger.warning("remove_node failed %s: %s", agent_base_url, e)
        return False


async def fetch_wg_status(agent_base_url: str) -> dict | None:
    """Fetch WireGuard status from agent (GET /wg/status). Returns parsed JSON or None on failure."""
    url = f"{agent_base_url.rstrip('/')}/wg/status"
    try:
        async with httpx.AsyncClient(timeout=settings.agent_timeout) as client:
            r = await client.get(url, headers=_agent_headers())
            if r.is_success:
                return r.json()
            return None
    except Exception as e:
        logger.warning("fetch_wg_status failed %s: %s", agent_base_url, e)
        return None


async def wg_down(agent_base_url: str) -> bool:
    """Tell agent to bring down WireGuard interface (POST /wg/down). Returns True if successful."""
    url = f"{agent_base_url.rstrip('/')}/wg/down"
    try:
        async with httpx.AsyncClient(timeout=settings.agent_timeout) as client:
            r = await client.post(url, headers=_agent_headers())
            if r.is_success:
                logger.info("agent_client wg_down: success url=%s", url)
            else:
                logger.warning("wg_down failed %s %s: %s", agent_base_url, r.status_code, r.text[:200])
            return r.is_success
    except Exception as e:
        logger.warning("wg_down failed %s: %s", agent_base_url, e)
        return False
