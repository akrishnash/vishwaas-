"""
VISHWAAS Agent - WireGuard key generation and wg CLI wrapper.

Keys stored under configurable keys_dir (e.g. /etc/vishwaas).
Private key never exposed via API. All wg operations return structured JSON on failure.
"""

import os
import re
import subprocess
from pathlib import Path
from typing import Any

from app.config import (
    get_keys_dir,
    get_wg_interface,
    get_listen_port,
    get_subnet,
    get_use_tpm_wg_key,
    get_tpm_nv_index_wg,
)
from app.logger import get_logger
from app import tpm as tpm_module

logger = get_logger()

# Key file names under keys_dir
PRIVATE_KEY_FILE = "privatekey"
PUBLIC_KEY_FILE = "publickey"
VPN_IP_FILE = "vpn_ip"  # Controller-assigned VPN address (set via /set-vpn-address)


def _keys_dir() -> Path:
    d = get_keys_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


def keypair_exists() -> bool:
    """Return True if both private and public key files exist."""
    d = _keys_dir()
    return (d / PRIVATE_KEY_FILE).exists() and (d / PUBLIC_KEY_FILE).exists()


def generate_keypair() -> None:
    """
    Generate WireGuard keypair and write to keys_dir.
    Idempotent if keypair_exists() is True.
    """
    if keypair_exists():
        logger.debug("Keypair already exists, skipping generation")
        return
    d = _keys_dir()
    logger.debug("Generating WireGuard keypair in %s", d)
    priv_path = d / PRIVATE_KEY_FILE
    pub_path = d / PUBLIC_KEY_FILE
    try:
        result = subprocess.run(
            ["wg", "genkey"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        priv_key = result.stdout.strip()
        if not priv_key:
            raise RuntimeError("wg genkey produced empty output")
        priv_path.write_text(priv_key, encoding="utf-8")
        os.chmod(priv_path, 0o600)
        # Public key from private
        proc = subprocess.run(
            ["wg", "pubkey"],
            input=priv_key,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        pub_key = proc.stdout.strip()
        pub_path.write_text(pub_key, encoding="utf-8")
        os.chmod(pub_path, 0o644)
        from app.logger import log_key_generation
        log_key_generation()
        if get_use_tpm_wg_key():
            if tpm_module.write_wg_key_to_tpm(priv_key, get_tpm_nv_index_wg()):
                logger.info("WireGuard private key stored in TPM NV")
            else:
                logger.warning("TPM write failed; key remains only on disk")
    except subprocess.CalledProcessError as e:
        logger.exception("WireGuard key generation failed: %s", e)
        raise
    except FileNotFoundError:
        logger.error("WireGuard (wg) not found; install wireguard-tools")
        raise


def set_private_key(priv_key: str) -> None:
    """Write controller-issued private key and derive/write public key. Used when controller_issues_keys."""
    d = _keys_dir()
    priv_path = d / PRIVATE_KEY_FILE
    pub_path = d / PUBLIC_KEY_FILE
    priv_key = priv_key.strip()
    priv_path.write_text(priv_key, encoding="utf-8")
    os.chmod(priv_path, 0o600)
    ok, out, err = _run_wg(["pubkey"], input_text=priv_key)
    if not ok:
        raise RuntimeError(f"wg pubkey failed: {err or out}")
    pub_key = (out or "").strip()
    if not pub_key:
        raise RuntimeError("wg pubkey produced empty output")
    pub_path.write_text(pub_key, encoding="utf-8")
    os.chmod(pub_path, 0o644)
    logger.info("Controller-issued key written and public key derived")
    if get_use_tpm_wg_key():
        if tpm_module.write_wg_key_to_tpm(priv_key, get_tpm_nv_index_wg()):
            logger.info("Controller-issued key stored in TPM NV")
        else:
            logger.warning("TPM write failed; key remains only on disk")


def _private_key_available() -> bool:
    """Return True if we have a private key (on disk or in TPM)."""
    if ( _keys_dir() / PRIVATE_KEY_FILE ).exists():
        return True
    if get_use_tpm_wg_key() and tpm_module.read_wg_key_from_tpm(get_tpm_nv_index_wg()):
        return True
    return False


def get_public_key() -> str:
    """Read public key from keys_dir. Raises if not present."""
    path = _keys_dir() / PUBLIC_KEY_FILE
    if not path.exists():
        logger.error("Public key not found at %s", path)
        raise FileNotFoundError("Public key not found; ensure keypair is generated")
    key = path.read_text(encoding="utf-8").strip()
    logger.debug("Read public key from %s", path)
    return key


def _run_wg(args: list[str], input_text: str | None = None) -> tuple[bool, str, str]:
    """Run wg command. Returns (success, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["wg"] + args,
            capture_output=True,
            text=True,
            timeout=30,
            input=input_text,
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "timeout"
    except FileNotFoundError:
        return False, "", "wg not found"


def _interface_exists(iface: str) -> bool:
    """Return True if the WireGuard interface exists."""
    result = subprocess.run(
        ["ip", "link", "show", iface],
        capture_output=True,
        text=True,
        timeout=5,
    )
    return result.returncode == 0


def interface_exists() -> bool:
    """Return True if the configured WireGuard interface exists (node is provisioned)."""
    return _interface_exists(get_wg_interface())


def wg_show_peers(iface: str) -> list[str]:
    """Return list of peer public keys on the interface. Empty if interface missing or error."""
    ok, out, err = _run_wg(["show", iface, "peers"])
    if not ok:
        return []
    return [line.strip() for line in out.strip().splitlines() if line.strip()]


def provision_interface(vpn_ip: str) -> dict[str, Any]:
    """
    Ensure wg0 exists and is up with the given VPN IP. Idempotent:
    - If interface does not exist: create, set private key, assign IP, bring up.
    - If interface exists: do NOT regenerate private key; verify IP matches, ensure link is up.
    Never call wg-quick down before creating.
    """
    iface = get_wg_interface()
    port = get_listen_port()
    subnet = get_subnet()
    if not _private_key_available():
        logger.warning("provision_interface: private key not found (file or TPM)")
        return {"success": False, "message": "Private key not found", "detail": None}
    priv_path, cleanup = tpm_module.get_private_key_path_for_wg()
    if not priv_path.exists():
        logger.warning("provision_interface: private key path not found at %s", priv_path)
        return {"success": False, "message": "Private key not found", "detail": None}
    vpn_ip = vpn_ip.strip()
    addr = vpn_ip if "/" in vpn_ip else f"{vpn_ip}/24"
    try:
        if not _interface_exists(iface):
            # Full bring-up: create interface, set key, assign IP, up
            logger.info("provision_interface: creating interface %s with %s", iface, addr)
            result = subprocess.run(
                ["ip", "link", "add", "dev", iface, "type", "wireguard"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return {"success": False, "message": "ip link add failed", "detail": result.stderr}
            try:
                ok, out, err = _run_wg(["set", iface, "private-key", str(priv_path)])
            finally:
                cleanup()
            if not ok:
                return {"success": False, "message": "wg set private-key failed", "detail": err or out}
            ok, out, err = _run_wg(["set", iface, "listen-port", str(port)])
            if not ok:
                return {"success": False, "message": "wg set listen-port failed", "detail": err or out}
            subprocess.run(
                ["ip", "address", "add", addr, "dev", iface],
                capture_output=True,
                text=True,
                timeout=10,
            )
            result = subprocess.run(["ip", "link", "set", iface, "up"], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                return {"success": False, "message": "ip link set up failed", "detail": result.stderr}
            set_assigned_vpn_ip(vpn_ip)
            return {"success": True, "message": "WireGuard started", "detail": None}
        # Interface exists: do not touch private key. Verify IP and ensure up.
        set_assigned_vpn_ip(vpn_ip)
        result = subprocess.run(
            ["ip", "address", "add", addr, "dev", iface],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0 and "File exists" not in result.stderr:
            pass  # Address may already be correct
        result = subprocess.run(["ip", "link", "set", iface, "up"], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return {"success": False, "message": "ip link set up failed", "detail": result.stderr}
        logger.info("provision_interface: interface %s already exists, ensured up", iface)
        return {"success": True, "message": "Interface up", "detail": None}
    except Exception as e:
        logger.exception("provision_interface failed")
        return {"success": False, "message": str(e), "detail": None}


def _node_address_from_subnet(subnet: str) -> str:
    """Return first usable host address (e.g. 10.10.10.0/24 -> 10.10.10.1/24)."""
    parts = subnet.split("/")
    prefix = parts[0]
    mask = parts[1] if len(parts) > 1 else "24"
    octets = prefix.split(".")
    if len(octets) == 4:
        octets[-1] = "1"
        return ".".join(octets) + "/" + mask
    return prefix + "/" + mask


def get_assigned_vpn_ip() -> str | None:
    """Return controller-assigned VPN IP if set (from /set-vpn-address), else None."""
    path = _keys_dir() / VPN_IP_FILE
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip() or None


def set_assigned_vpn_ip(vpn_ip: str) -> None:
    """Store controller-assigned VPN IP so wg_up() uses it for the interface address."""
    path = _keys_dir() / VPN_IP_FILE
    path.write_text(vpn_ip.strip(), encoding="utf-8")
    os.chmod(path, 0o600)


def wg_up() -> dict[str, Any]:
    """
    Bring up WireGuard interface with configured subnet and listen port.
    Creates interface if missing. Returns { "success": bool, "message": str, "detail": str? }.
    """
    iface = get_wg_interface()
    port = get_listen_port()
    subnet = get_subnet()
    logger.info("wg_up: iface=%s port=%s subnet=%s", iface, port, subnet)
    if not _private_key_available():
        logger.warning("wg_up: private key not found (file or TPM)")
        return {"success": False, "message": "Private key not found", "detail": None}
    priv_path, cleanup = tpm_module.get_private_key_path_for_wg()
    if not priv_path.exists():
        logger.warning("wg_up: private key path not found at %s", priv_path)
        return {"success": False, "message": "Private key not found", "detail": None}
    try:
        # Ensure interface exists
        check = subprocess.run(
            ["ip", "link", "show", iface],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if check.returncode != 0:
            logger.debug("wg_up: creating interface %s", iface)
            result = subprocess.run(
                ["ip", "link", "add", "dev", iface, "type", "wireguard"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                logger.warning("wg_up: ip link add failed: %s", result.stderr)
                return {"success": False, "message": "ip link add failed", "detail": result.stderr}
        # Set private key (wg expects a file path) and listen port
        try:
            ok, out, err = _run_wg(["set", iface, "private-key", str(priv_path)])
        finally:
            cleanup()
        if not ok:
            return {"success": False, "message": "wg set private-key failed", "detail": err or out}
        ok, out, err = _run_wg(["set", iface, "listen-port", str(port)])
        if not ok:
            return {"success": False, "message": "wg set listen-port failed", "detail": err or out}
        # Assign address: use controller-assigned VPN IP if set, else first host in subnet
        assigned = get_assigned_vpn_ip()
        if assigned:
            addr = assigned if "/" in assigned else f"{assigned}/24"
            logger.info("wg_up: using assigned VPN address %s", addr)
        else:
            addr = _node_address_from_subnet(subnet)
            logger.debug("wg_up: using subnet address %s", addr)
        result = subprocess.run(
            ["ip", "address", "add", addr, "dev", iface],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0 and "File exists" not in result.stderr:
            return {"success": False, "message": "ip address add failed", "detail": result.stderr}
        result = subprocess.run(["ip", "link", "set", iface, "up"], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            logger.warning("wg_up: ip link set up failed: %s", result.stderr)
            return {"success": False, "message": "ip link set up failed", "detail": result.stderr}
        logger.info("wg_up: interface %s is up with address %s", iface, addr)
        return {"success": True, "message": "WireGuard started", "detail": None}
    except Exception as e:
        logger.exception("wg up failed")
        return {"success": False, "message": str(e), "detail": None}


def wg_down() -> dict[str, Any]:
    """Bring down WireGuard interface. Returns structured result."""
    iface = get_wg_interface()
    logger.info("wg_down: bringing down %s", iface)
    try:
        result = subprocess.run(["ip", "link", "set", iface, "down"], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            logger.warning("wg_down: ip link set down failed: %s", result.stderr)
            return {"success": False, "message": "ip link set down failed", "detail": result.stderr}
        logger.info("wg_down: interface %s is down", iface)
        return {"success": True, "message": "WireGuard stopped", "detail": None}
    except Exception as e:
        logger.exception("wg down failed")
        return {"success": False, "message": str(e), "detail": None}


def wg_add_peer(
    public_key: str,
    allowed_ips: str,
    endpoint: str | None = None,
    persistent_keepalive: int | None = 25,
) -> dict[str, Any]:
    """Add or update peer on interface. Idempotent: if peer exists, updates allowed-ips/endpoint/keepalive."""
    iface = get_wg_interface()
    logger.debug("wg_add_peer: iface=%s allowed_ips=%s endpoint=%s keepalive=%s", iface, allowed_ips, endpoint, persistent_keepalive)
    args = ["set", iface, "peer", public_key.strip(), "allowed-ips", allowed_ips.strip()]
    if endpoint:
        args.extend(["endpoint", endpoint.strip()])
    if persistent_keepalive is not None:
        args.extend(["persistent-keepalive", str(persistent_keepalive)])
    ok, out, err = _run_wg(args)
    if not ok:
        logger.warning("wg_add_peer failed: %s", err or out)
        return {"success": False, "message": "add peer failed", "detail": err or out}
    logger.info("wg_add_peer: peer added/updated allowed_ips=%s", allowed_ips)
    return {"success": True, "message": "Peer added", "detail": None}


def wg_remove_peer(public_key: str) -> dict[str, Any]:
    """Remove peer. Idempotent: if peer does not exist, return success."""
    iface = get_wg_interface()
    pk = public_key.strip()
    peers = wg_show_peers(iface)
    if pk not in peers:
        logger.debug("wg_remove_peer: peer not present, ignoring")
        return {"success": True, "message": "Peer removed", "detail": None}
    logger.debug("wg_remove_peer: iface=%s removing peer", iface)
    ok, out, err = _run_wg(["set", iface, "peer", pk, "remove"])
    if not ok:
        logger.warning("wg_remove_peer failed: %s", err or out)
        return {"success": False, "message": "remove peer failed", "detail": err or out}
    logger.info("wg_remove_peer: peer removed")
    return {"success": True, "message": "Peer removed", "detail": None}


def wg_remove_node() -> dict[str, Any]:
    """
    Remove WireGuard interface and clean config. Used when controller removes this node.
    Removes all peers, deletes interface (ip link delete wg0), removes vpn_ip file.
    Does not delete or regenerate private key.
    """
    iface = get_wg_interface()
    if not _interface_exists(iface):
        # Already gone; clean vpn_ip file if present
        vpn_path = _keys_dir() / VPN_IP_FILE
        if vpn_path.exists():
            try:
                vpn_path.unlink()
            except OSError:
                pass
        logger.info("wg_remove_node: interface %s already absent", iface)
        return {"success": True, "message": "Node removed", "detail": None}
    try:
        peers = wg_show_peers(iface)
        for pk in peers:
            _run_wg(["set", iface, "peer", pk, "remove"])
        result = subprocess.run(
            ["ip", "link", "delete", iface],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            logger.warning("wg_remove_node: ip link delete failed: %s", result.stderr)
            return {"success": False, "message": "ip link delete failed", "detail": result.stderr}
        vpn_path = _keys_dir() / VPN_IP_FILE
        if vpn_path.exists():
            try:
                vpn_path.unlink()
            except OSError:
                pass
        logger.info("wg_remove_node: interface %s deleted", iface)
        return {"success": True, "message": "Node removed", "detail": None}
    except Exception as e:
        logger.exception("wg_remove_node failed")
        return {"success": False, "message": str(e), "detail": None}


def _parse_transfer(text: str) -> tuple[int, int]:
    """Parse '1.23 KiB received, 4.56 KiB sent' -> (rx_bytes, tx_bytes)."""
    rx, tx = 0, 0
    m = re.search(r"([\d.]+)\s*(B|KiB|MiB|GiB|KB|MB|GB)\s+received", text, re.IGNORECASE)
    if m:
        v = float(m.group(1))
        u = m.group(2).lower()
        mult = {"b": 1, "kib": 1024, "mib": 1024**2, "gib": 1024**3, "kb": 1000, "mb": 1000**2, "gb": 1000**3}
        rx = int(v * mult.get(u, 1))
    m = re.search(r"([\d.]+)\s*(B|KiB|MiB|GiB|KB|MB|GB)\s+sent", text, re.IGNORECASE)
    if m:
        v = float(m.group(1))
        u = m.group(2).lower()
        mult = {"b": 1, "kib": 1024, "mib": 1024**2, "gib": 1024**3, "kb": 1000, "mb": 1000**2, "gb": 1000**3}
        tx = int(v * mult.get(u, 1))
    return rx, tx


def _parse_latest_handshake(text: str) -> int | None:
    """Parse '45 seconds ago' -> seconds. Returns None if never."""
    m = re.search(r"(\d+)\s+second", text)
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+)\s+minute", text)
    if m:
        return int(m.group(1)) * 60
    m = re.search(r"(\d+)\s+hour", text)
    if m:
        return int(m.group(1)) * 3600
    m = re.search(r"(\d+)\s+day", text)
    if m:
        return int(m.group(1)) * 86400
    return None


def _wg_dump_transfers(iface: str) -> dict[str, tuple[int, int]]:
    """Get transfer_rx, transfer_tx per peer from 'wg show dump' (raw bytes, reliable)."""
    ok, out, err = _run_wg(["show", iface, "dump"])
    result: dict[str, tuple[int, int]] = {}
    if not ok:
        return result
    # Dump format: first line = interface (4 fields); peer lines = pubkey\tpreshared\tendpoint\tallowed_ips\tlast_handshake\trx\ttx\tkeepalive
    lines = out.strip().split("\n")
    for line in lines[1:]:  # skip interface line
        parts = line.split("\t")
        if len(parts) >= 8:
            try:
                pubkey = parts[0]
                rx = int(parts[6])
                tx = int(parts[7])
                result[pubkey] = (rx, tx)
            except (ValueError, IndexError):
                pass
    return result


def wg_status() -> dict[str, Any]:
    """Return WireGuard status. Uses wg show dump for reliable transfer bytes."""
    iface = get_wg_interface()
    ok, out, err = _run_wg(["show", iface])
    if not ok:
        return {"success": False, "message": "wg show failed", "detail": err or out, "interface": iface, "peers": []}
    # Get raw transfer bytes from dump (more reliable than human format)
    dump_transfers = _wg_dump_transfers(iface)
    lines = out.strip().split("\n")
    info = {"interface": iface, "public_key": None, "listen_port": None, "peers": [], "total_rx": 0, "total_tx": 0}
    current_peer = None
    for line in lines:
        if line.startswith("interface:"):
            continue
        if line.startswith("public key:"):
            info["public_key"] = line.split(":", 1)[1].strip()
        elif line.startswith("listening port:"):
            info["listen_port"] = line.split(":", 1)[1].strip()
        elif line.startswith("peer:"):
            pk = line.split(":", 1)[1].strip()
            rx, tx = dump_transfers.get(pk, (0, 0))
            current_peer = {
                "public_key": pk,
                "allowed_ips": "",
                "endpoint": "",
                "transfer_rx": rx,
                "transfer_tx": tx,
                "latest_handshake_ago": None,
            }
            info["peers"].append(current_peer)
            info["total_rx"] += rx
            info["total_tx"] += tx
        elif current_peer and line.strip().startswith("allowed ips:"):
            current_peer["allowed_ips"] = line.split(":", 1)[1].strip()
        elif current_peer and line.strip().startswith("endpoint:"):
            current_peer["endpoint"] = line.split(":", 1)[1].strip()
        elif current_peer and line.strip().startswith("transfer:"):
            pass  # use dump values (already set); human format kept for backward compat only
        elif current_peer and line.strip().startswith("latest handshake:"):
            current_peer["latest_handshake_ago"] = _parse_latest_handshake(line)
    info["success"] = True
    return info
