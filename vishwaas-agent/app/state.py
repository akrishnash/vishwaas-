"""
VISHWAAS Agent - Runtime state machine.

States: WAITING -> APPROVED -> ACTIVE. ERROR can occur from any state.
Transitions are driven only by MASTER commands (e.g. /wg/start moves to ACTIVE).
"""

from enum import Enum
from threading import Lock

# Singleton state guarded by lock
_lock = Lock()
_state: "AgentState" = None  # type: ignore[assignment]


class AgentState(str, Enum):
    """Node lifecycle; MASTER is the single authority for transitions."""
    WAITING = "WAITING"      # Joined, awaiting approval/commands
    APPROVED = "APPROVED"    # Approved by MASTER
    ACTIVE = "ACTIVE"        # WireGuard running and peers applied
    ERROR = "ERROR"          # Error state; may retry or require manual intervention


def get_state() -> AgentState:
    """Return current agent state. Thread-safe."""
    global _state
    with _lock:
        if _state is None:
            _state = AgentState.WAITING
        return _state


def set_state(new: AgentState) -> None:
    """Set state. Only MASTER-triggered logic should call this."""
    global _state
    with _lock:
        _state = new


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
