"""
VISHWAAS Agent - TPM NV storage for WireGuard private key.

When use_tpm_wg_key is enabled, the agent stores and reads the WG private key
from a TPM NV index so the key is bound to hardware. Requires tpm2-tools.
"""

import subprocess
import tempfile
from pathlib import Path
from typing import Callable

# WireGuard private key is 44 bytes base64; use 45 for NV size to match tpm_scripts
WG_KEY_NV_SIZE = 45


def read_wg_key_from_tpm(nv_index: int = 1) -> str | None:
    """
    Read WireGuard private key from TPM NV index.
    Runs tpm2_startup -c and tpm2_nvread. Returns key string or None if TPM unavailable.
    """
    try:
        subprocess.run(
            ["tpm2_startup", "-c"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None

    try:
        r = subprocess.run(
            ["tpm2_nvread", "-C", "o", "-s", str(WG_KEY_NV_SIZE), str(nv_index)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode != 0 or not r.stdout:
            return None
        key = r.stdout.strip()
        return key if key else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def write_wg_key_to_tpm(private_key: str, nv_index: int = 1) -> bool:
    """
    Write WireGuard private key to TPM NV index.
    Defines the index if needed (ownerread|policywrite|ownerwrite). Returns True on success.
    """
    key = (private_key or "").strip()
    if not key or len(key) > WG_KEY_NV_SIZE:
        return False

    try:
        subprocess.run(
            ["tpm2_startup", "-c"],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False

    # Define NV index (idempotent: may already exist)
    try:
        subprocess.run(
            [
                "tpm2_nvdefine", "-C", "o",
                "-s", str(WG_KEY_NV_SIZE),
                "-a", "ownerread|policywrite|ownerwrite",
                str(nv_index),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Ignore return code: index may already be defined
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".key", delete=False) as f:
            f.write(key)
            tmp = f.name
        try:
            r = subprocess.run(
                ["tpm2_nvwrite", "-C", "o", "-i", tmp, str(nv_index)],
                capture_output=True,
                text=True,
                timeout=10,
            )
            return r.returncode == 0
        finally:
            Path(tmp).unlink(missing_ok=True)
    except OSError:
        return False


def get_private_key_path_for_wg() -> tuple[Path, Callable[[], None]]:
    """
    Return (path, cleanup) for use with 'wg set ... private-key <path>'.
    If TPM is enabled and key is in TPM, reads from TPM into a temp file and returns
    that path; cleanup() removes the temp file. Otherwise returns keys_dir/privatekey
    and a no-op cleanup.
    """
    from app.config import get_keys_dir, get_use_tpm_wg_key, get_tpm_nv_index_wg

    keys_dir = get_keys_dir()
    file_path = keys_dir / "privatekey"

    if not get_use_tpm_wg_key():
        return file_path, lambda: None

    key = read_wg_key_from_tpm(get_tpm_nv_index_wg())
    if not key:
        return file_path, lambda: None

    fd, tmp_path = tempfile.mkstemp(suffix=".wgkey", prefix="vishwaas_")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            f.write(key)
        return Path(tmp_path), lambda: Path(tmp_path).unlink(missing_ok=True)
    except OSError:
        Path(tmp_path).unlink(missing_ok=True)
        return file_path, lambda: None
