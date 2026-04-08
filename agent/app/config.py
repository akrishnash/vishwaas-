"""
VISHWAAS Agent - Configuration loader.

All deployment-specific values come from agent_config.json.
No hardcoded config; single source of truth for plug-and-play deployment.
"""

import json
import os
from pathlib import Path
from typing import Any

# Default config path: same directory as agent (e.g. /opt/vishwaas-agent/agent_config.json)
_CONFIG_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = os.environ.get("VISHWAAS_AGENT_CONFIG", str(_CONFIG_DIR / "agent_config.json"))


def _validate_config(data: dict[str, Any]) -> None:
    """
    Validate required and sensible config values.
    Raises ValueError with a clear message if invalid (e.g. "Please enter correct details in agent_config.json: ...").
    """
    errors: list[str] = []

    master_url = (data.get("master_url") or "").strip().rstrip("/")
    if not master_url:
        errors.append("master_url is required and must be the controller URL (e.g. http://192.168.1.1:8000)")
    elif not (master_url.startswith("http://") or master_url.startswith("https://")):
        errors.append("master_url must start with http:// or https://")

    master_token = (data.get("master_token") or "").strip()
    if not master_token:
        errors.append("master_token is required (must match the controller's VISHWAAS_AGENT_TOKEN)")

    agent_advertise_url = (data.get("agent_advertise_url") or "").strip().rstrip("/")
    if not agent_advertise_url:
        errors.append("agent_advertise_url is required so the controller can reach this agent (e.g. http://192.168.1.2:9000)")
    elif not (agent_advertise_url.startswith("http://") or agent_advertise_url.startswith("https://")):
        errors.append("agent_advertise_url must start with http:// or https://")

    if errors:
        msg = "Please enter correct details in agent_config.json:\n  - " + "\n  - ".join(errors)
        raise ValueError(msg)


def load_config() -> dict[str, Any]:
    """Load agent_config.json. Raises if file missing or invalid."""
    path = Path(CONFIG_PATH)
    if not path.exists():
        raise FileNotFoundError(
            f"Config not found: {path}\nPlease create agent_config.json (see agent_config.*.example) with correct details."
        )
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("agent_config.json must be a JSON object. Please enter correct details.")
    _validate_config(data)
    # Log config load once (avoid circular import by lazy log)
    try:
        from app.logger import get_logger
        get_logger().debug("Config loaded from %s master_url=%s", path, data.get("master_url", ""))
    except Exception:
        pass
    return data


def get_config() -> dict[str, Any]:
    """Return cached config or load once. Used at runtime."""
    if not hasattr(get_config, "_cache"):
        get_config._cache = load_config()  # type: ignore[attr-defined]
    return get_config._cache  # type: ignore[attr-defined]


def get_node_name() -> str:
    """Resolved node name: 'auto' means use hostname, else use configured value."""
    cfg = get_config()
    name = cfg.get("node_name", "auto")
    if name == "auto" or not name:
        import socket
        return socket.gethostname()
    return str(name)


def get_master_url() -> str:
    """MASTER base URL (e.g. http://MASTER_IP:8000)."""
    return get_config().get("master_url", "").rstrip("/")


def get_master_token() -> str:
    """Token used to authenticate this agent to MASTER."""
    return get_config().get("master_token", "")


def get_wg_interface() -> str:
    """WireGuard interface name (e.g. wg0)."""
    return get_config().get("wg_interface", "wg0")


def get_listen_port() -> int:
    """WireGuard listen port (e.g. 51820)."""
    return int(get_config().get("listen_port", 51820))


def get_subnet() -> str:
    """Subnet for this node (e.g. 10.10.10.0/24)."""
    return get_config().get("subnet", "10.10.10.0/24")


def get_agent_bind_host() -> str:
    """Bind address for agent API (default 0.0.0.0)."""
    return get_config().get("agent_bind_host", "0.0.0.0")


def get_agent_port() -> int:
    """Port for agent API (default 9000)."""
    return int(get_config().get("agent_port", 9000))


def get_agent_advertise_url() -> str:
    """
    URL this agent advertises to the controller (for callbacks).
    If set, the controller uses this to reach the agent (set-vpn-address, add peer).
    Use the IP/hostname that the controller can reach (e.g. 192.168.10.16 on the same LAN).
    If not set, we use the auto-detected local IP (which may be wrong for VMs/NAT).
    """
    return get_config().get("agent_advertise_url", "").rstrip("/")


def get_controller_issues_keys() -> bool:
    """If true, agent does not generate keys; controller will send private_key on approve."""
    return get_config().get("controller_issues_keys", False)


def get_keys_dir() -> Path:
    """Directory for WireGuard keys; must be writable by agent (e.g. /etc/vishwaas)."""
    raw = get_config().get("keys_dir", "./keys")
    return Path(raw)


def get_use_tpm_wg_key() -> bool:
    """If true, store and read WireGuard private key from TPM NV index (hardware-bound)."""
    return bool(get_config().get("use_tpm_wg_key", False))


def get_tpm_nv_index_wg() -> int:
    """TPM NV index used for WireGuard private key (default 1). Must be 0x01-0xFFFFFFFE."""
    return int(get_config().get("tpm_nv_index_wg", 1))
