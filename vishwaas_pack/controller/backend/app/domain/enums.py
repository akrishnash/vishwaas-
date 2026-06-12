"""
Domain enums: strict lifecycle states.
NO node becomes ACTIVE without approval.
NO connection is created without approval.
"""
from enum import Enum


class NodeStatus(str, Enum):
    """Node lifecycle states."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    OFFLINE = "OFFLINE"


class ConnectionStatus(str, Enum):
    """Connection lifecycle states."""

    REQUESTED = "REQUESTED"
    APPROVED = "APPROVED"
    ACTIVE = "ACTIVE"
    REJECTED = "REJECTED"
    TERMINATED = "TERMINATED"


class JoinRequestStatus(str, Enum):
    """Join request states (mirrors approval flow)."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ConnectionRequestStatus(str, Enum):
    """Connection request states."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class NotificationType(str, Enum):
    """Notification categories for dashboard."""

    JOIN_APPROVED = "JOIN_APPROVED"
    JOIN_REJECTED = "JOIN_REJECTED"
    CONNECTION_APPROVED = "CONNECTION_APPROVED"
    CONNECTION_REJECTED = "CONNECTION_REJECTED"
    CONNECTION_TERMINATED = "CONNECTION_TERMINATED"
    NODE_OFFLINE = "NODE_OFFLINE"
    SYSTEM = "SYSTEM"


class LogEventType(str, Enum):
    """Audit log event types."""

    JOIN_REQUESTED = "JOIN_REQUESTED"
    JOIN_APPROVED = "JOIN_APPROVED"
    JOIN_REJECTED = "JOIN_REJECTED"
    CONNECTION_REQUESTED = "CONNECTION_REQUESTED"
    CONNECTION_APPROVED = "CONNECTION_APPROVED"
    CONNECTION_REJECTED = "CONNECTION_REJECTED"
    CONNECTION_TERMINATED = "CONNECTION_TERMINATED"
    NODE_REMOVED = "NODE_REMOVED"
    NODE_OFFLINE = "NODE_OFFLINE"
