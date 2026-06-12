"""
VISHWAAS Agent - Runtime state machine.

States: WAITING -> APPROVED -> ACTIVE. ERROR can occur from any state.
Transitions are driven only by MASTER commands.

State is persisted to keys_dir/agent_state.json so it survives agent restarts
and the controller can reconcile mismatches via the heartbeat.
"""

import json
from enum import Enum
from pathlib import Path
from threading import Lock

# Singleton state guarded by lock
_lock = Lock()
_state: "AgentState | None" = None

_STATE_FILE = "agent_state.json"


class AgentState(str, Enum):
    """Node lifecycle; MASTER is the single authority for transitions."""
    WAITING = "WAITING"      # Joined, awaiting approval/commands
    APPROVED = "APPROVED"    # Approved by MASTER
    ACTIVE = "ACTIVE"        # WireGuard running and peers applied
    ERROR = "ERROR"          # Error state; may retry or require manual intervention


def _state_file_path() -> Path:
    try:
        from app.config import get_keys_dir
        return get_keys_dir() / _STATE_FILE
    except Exception:
        return Path(".") / _STATE_FILE


def _load_persisted() -> AgentState:
    try:
        data = json.loads(_state_file_path().read_text())
        return AgentState(data.get("state", AgentState.WAITING.value))
    except Exception:
        return AgentState.WAITING


def _persist(s: AgentState) -> None:
    try:
        p = _state_file_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"state": s.value}))
    except Exception:
        pass  # best-effort; in-memory wins


def get_state() -> AgentState:
    """Return current agent state. Thread-safe. Loads from disk on first call."""
    global _state
    with _lock:
        if _state is None:
            _state = _load_persisted()
        return _state


def set_state(new: AgentState) -> None:
    """Set state and persist to disk. Only MASTER-triggered logic should call this."""
    global _state
    with _lock:
        _state = new
        _persist(new)


def set_waiting() -> None:
    set_state(AgentState.WAITING)


def set_approved() -> None:
    set_state(AgentState.APPROVED)


def set_active() -> None:
    set_state(AgentState.ACTIVE)


def set_error() -> None:
    set_state(AgentState.ERROR)


def is_operational() -> bool:
    """True if node can execute WireGuard commands (ACTIVE or APPROVED)."""
    s = get_state()
    return s in (AgentState.ACTIVE, AgentState.APPROVED)
