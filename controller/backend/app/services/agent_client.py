"""
Agent client: call node agent endpoints.

Uses a shared httpx.AsyncClient (initialised in main.py lifespan) with:
  - Per-call timeout override
  - Exponential-backoff retry (2 retries, 1s / 2s delay)
  - X-VISHWAAS-TOKEN authentication
  - X-Request-ID correlation ID forwarding
  - Prometheus agent_calls_total counter increments
"""
import asyncio
import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _agent_headers() -> dict[str, str]:
    """Build headers for agent requests."""
    h: dict[str, str] = {"Content-Type": "application/json"}
    if settings.agent_token:
        h["X-VISHWAAS-TOKEN"] = settings.agent_token
    try:
        from app.core.correlation import get_correlation_id
        cid = get_correlation_id()
        if cid:
            h["X-Request-ID"] = cid
    except Exception:
        pass
    return h


def _endpoint_from_agent_url(agent_url: str, wg_port: int = 51820) -> Optional[str]:
    """Derive WireGuard endpoint (host:port) from agent URL."""
    if not agent_url or not agent_url.strip():
        return None
    from urllib.parse import urlparse
    o = urlparse(
        agent_url.strip() if agent_url.startswith("http") else f"http://{agent_url.strip()}"
    )
    if not o.hostname:
        return None
    return f"{o.hostname}:{wg_port}"


def _get_client() -> httpx.AsyncClient:
    """Return the shared client, falling back to a one-shot client if not initialised."""
    try:
        from app.core.http_client import get_client
        return get_client()
    except RuntimeError:
        # Fallback for tests or early-startup callers
        return httpx.AsyncClient(timeout=settings.agent_timeout)


def _inc_metric(operation: str, success: bool) -> None:
    try:
        from app.core.metrics import agent_calls_total
        agent_calls_total.labels(operation=operation, success=str(success)).inc()
    except Exception:
        pass


async def _call_with_retry(coro_fn, retries: int = 2, base_delay: float = 1.0):
    """
    Call async coro_fn(); on transient failure retry up to `retries` times
    with exponential back-off (1 s, 2 s). Raises the last exception on exhaustion.
    """
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return await coro_fn()
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                delay = base_delay * (2 ** attempt)
                logger.debug("_call_with_retry: attempt %s failed (%s), retrying in %.1fs", attempt + 1, exc, delay)
                await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def add_peer(
    agent_base_url: str,
    peer_public_key: str,
    peer_vpn_ip: str,
    peer_endpoint: Optional[str] = None,
    allowed_ips: Optional[str] = None,
    timeout: Optional[float] = None,
) -> bool:
    """Call agent to add / update a WireGuard peer. Returns True on success."""
    url = f"{agent_base_url.rstrip('/')}/peer"
    allowed_ip = allowed_ips if allowed_ips else (
        f"{peer_vpn_ip}/32" if "/" not in peer_vpn_ip else peer_vpn_ip
    )
    pk_short = (peer_public_key[:12] + "...") if len(peer_public_key) > 12 else peer_public_key
    payload = {
        "public_key": peer_public_key,
        "allowed_ip": allowed_ip,
        "persistent_keepalive": 25,
    }
    if peer_endpoint:
        payload["endpoint"] = peer_endpoint
    _t = timeout if timeout is not None else settings.agent_timeout
    logger.info("agent_client add_peer: url=%s allowed_ip=%s endpoint=%s peer_key=%s", url, allowed_ip, peer_endpoint, pk_short)

    async def _do():
        client = _get_client()
        return await client.post(url, json=payload, headers=_agent_headers(), timeout=_t)

    try:
        r = await _call_with_retry(_do)
        ok = r.is_success
        if not ok:
            logger.warning("add_peer failed %s %s: %s", agent_base_url, r.status_code, r.text[:200])
        else:
            logger.info("agent_client add_peer: success url=%s", url)
        _inc_metric("add_peer", ok)
        return ok
    except Exception as e:
        logger.warning("add_peer failed %s: %s", agent_base_url, e)
        _inc_metric("add_peer", False)
        return False


async def set_vpn_address(
    agent_base_url: str,
    vpn_ip: str,
    private_key: Optional[str] = None,
    timeout: Optional[float] = None,
) -> bool:
    """Tell the agent its assigned VPN IP (and optional private key)."""
    url = f"{agent_base_url.rstrip('/')}/set-vpn-address"
    payload: dict = {"vpn_ip": vpn_ip}
    if private_key:
        payload["private_key"] = private_key
    _t = timeout if timeout is not None else settings.agent_timeout
    logger.info("agent_client set_vpn_address: url=%s vpn_ip=%s has_key=%s", url, vpn_ip, bool(private_key))

    async def _do():
        client = _get_client()
        return await client.post(url, json=payload, headers=_agent_headers(), timeout=_t)

    try:
        r = await _call_with_retry(_do)
        ok = r.is_success
        if not ok:
            logger.warning("set_vpn_address failed %s %s: %s", agent_base_url, r.status_code, r.text[:200])
        else:
            logger.info("agent_client set_vpn_address: success url=%s vpn_ip=%s", url, vpn_ip)
        _inc_metric("set_vpn_address", ok)
        return ok
    except Exception as e:
        logger.warning("set_vpn_address failed %s: %s", agent_base_url, e)
        _inc_metric("set_vpn_address", False)
        return False


async def remove_peer(
    agent_base_url: str,
    peer_public_key: str,
    timeout: Optional[float] = None,
) -> bool:
    """Call agent to remove a peer by public key. Idempotent."""
    url = f"{agent_base_url.rstrip('/')}/peer"
    pk_short = (peer_public_key[:12] + "...") if len(peer_public_key) > 12 else peer_public_key
    _t = timeout if timeout is not None else settings.agent_timeout
    logger.info("agent_client remove_peer: url=%s peer_key=%s", url, pk_short)

    async def _do():
        client = _get_client()
        return await client.request(
            "DELETE", url, json={"public_key": peer_public_key}, headers=_agent_headers(), timeout=_t
        )

    try:
        r = await _call_with_retry(_do)
        ok = r.is_success
        if not ok:
            logger.warning("remove_peer failed %s %s: %s", agent_base_url, r.status_code, r.text[:200])
        else:
            logger.info("agent_client remove_peer: success url=%s", url)
        _inc_metric("remove_peer", ok)
        return ok
    except Exception as e:
        logger.warning("remove_peer failed %s: %s", agent_base_url, e)
        _inc_metric("remove_peer", False)
        return False


async def remove_node(
    agent_base_url: str,
    timeout: Optional[float] = None,
) -> bool:
    """Tell the agent to remove its WireGuard interface and clean up."""
    url = f"{agent_base_url.rstrip('/')}/remove-node"
    _t = timeout if timeout is not None else settings.agent_timeout
    logger.info("agent_client remove_node: url=%s", url)

    async def _do():
        client = _get_client()
        return await client.post(url, json={}, headers=_agent_headers(), timeout=_t)

    try:
        r = await _call_with_retry(_do)
        ok = r.is_success
        if not ok:
            logger.warning("remove_node failed %s %s: %s", agent_base_url, r.status_code, r.text[:200])
        else:
            logger.info("agent_client remove_node: success url=%s", url)
        _inc_metric("remove_node", ok)
        return ok
    except Exception as e:
        logger.warning("remove_node failed %s: %s", agent_base_url, e)
        _inc_metric("remove_node", False)
        return False


async def fetch_wg_status(
    agent_base_url: str,
    timeout: Optional[float] = None,
) -> Optional[dict]:
    """Fetch WireGuard status from agent. Returns parsed JSON or None."""
    url = f"{agent_base_url.rstrip('/')}/wg/status"
    _t = timeout if timeout is not None else settings.agent_timeout

    async def _do():
        client = _get_client()
        return await client.get(url, headers=_agent_headers(), timeout=_t)

    try:
        r = await _call_with_retry(_do)
        if r.is_success:
            _inc_metric("fetch_wg_status", True)
            return r.json()
        _inc_metric("fetch_wg_status", False)
        return None
    except Exception as e:
        logger.warning("fetch_wg_status failed %s: %s", agent_base_url, e)
        _inc_metric("fetch_wg_status", False)
        return None


async def enable_ip_forward(
    agent_base_url: str,
    timeout: Optional[float] = None,
) -> bool:
    """Tell agent to enable IPv4 forwarding (hub/gateway nodes)."""
    url = f"{agent_base_url.rstrip('/')}/ip-forward/enable"
    _t = timeout if timeout is not None else settings.agent_timeout
    logger.info("agent_client enable_ip_forward: url=%s", url)

    async def _do():
        client = _get_client()
        return await client.post(url, json={}, headers=_agent_headers(), timeout=_t)

    try:
        r = await _call_with_retry(_do)
        ok = r.is_success
        if not ok:
            logger.warning("enable_ip_forward failed %s %s: %s", agent_base_url, r.status_code, r.text[:200])
        else:
            logger.info("agent_client enable_ip_forward: success url=%s", url)
        _inc_metric("enable_ip_forward", ok)
        return ok
    except Exception as e:
        logger.warning("enable_ip_forward failed %s: %s", agent_base_url, e)
        _inc_metric("enable_ip_forward", False)
        return False


async def get_agent_logs(
    agent_base_url: str,
    n: int = 200,
    timeout: Optional[float] = None,
) -> Optional[dict]:
    """Fetch last N log lines from agent. Returns parsed JSON or None."""
    url = f"{agent_base_url.rstrip('/')}/logs"
    _t = timeout if timeout is not None else 5.0

    async def _do():
        client = _get_client()
        return await client.get(url, params={"n": n}, headers=_agent_headers(), timeout=_t)

    try:
        r = await _call_with_retry(_do, retries=0)
        if r.is_success:
            return r.json()
        return None
    except Exception as e:
        logger.debug("get_agent_logs failed %s: %s", agent_base_url, e)
        return None


async def wg_down(
    agent_base_url: str,
    timeout: Optional[float] = None,
) -> bool:
    """Tell agent to bring down the WireGuard interface."""
    url = f"{agent_base_url.rstrip('/')}/wg/down"
    _t = timeout if timeout is not None else settings.agent_timeout

    async def _do():
        client = _get_client()
        return await client.post(url, headers=_agent_headers(), timeout=_t)

    try:
        r = await _call_with_retry(_do)
        ok = r.is_success
        if not ok:
            logger.warning("wg_down failed %s %s: %s", agent_base_url, r.status_code, r.text[:200])
        else:
            logger.info("agent_client wg_down: success url=%s", url)
        _inc_metric("wg_down", ok)
        return ok
    except Exception as e:
        logger.warning("wg_down failed %s: %s", agent_base_url, e)
        _inc_metric("wg_down", False)
        return False
