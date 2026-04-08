"""
SQLAlchemy ORM models.
Schema matches specification: nodes, join_requests, connection_requests,
connections, notifications, logs, revoked_tokens.
"""
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Enum as SQLEnum,
)
from sqlalchemy.orm import relationship

from app.persistence.database import Base
from app.domain.enums import (
    NodeStatus,
    ConnectionStatus,
    JoinRequestStatus,
    ConnectionRequestStatus,
    NotificationType,
    LogEventType,
)


class Node(Base):
    """Approved/active VPN nodes. Status follows strict lifecycle."""

    __tablename__ = "nodes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, index=True)
    public_key = Column(String(512), nullable=False, unique=True)
    agent_url = Column(String(512), nullable=False)
    vpn_ip = Column(String(45), nullable=False, unique=True)  # IPv4 or IPv6
    status = Column(SQLEnum(NodeStatus), nullable=False, default=NodeStatus.APPROVED)
    is_gateway = Column(Integer, nullable=False, default=0)  # 1 = hub node, routes for all spokes
    last_seen = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships for connection requests and connections
    connection_requests_from = relationship(
        "ConnectionRequest", foreign_keys="ConnectionRequest.requester_id", back_populates="requester"
    )
    connection_requests_to = relationship(
        "ConnectionRequest", foreign_keys="ConnectionRequest.target_id", back_populates="target"
    )
    connections_a = relationship(
        "Connection", foreign_keys="Connection.node_a_id", back_populates="node_a"
    )
    connections_b = relationship(
        "Connection", foreign_keys="Connection.node_b_id", back_populates="node_b"
    )


class JoinRequest(Base):
    """Pending join requests; approval creates a node."""

    __tablename__ = "join_requests"

    id = Column(Integer, primary_key=True, index=True)
    node_name = Column(String(255), nullable=False)
    public_key = Column(String(512), nullable=False)
    agent_url = Column(String(512), nullable=False)
    status = Column(
        SQLEnum(JoinRequestStatus), nullable=False, default=JoinRequestStatus.PENDING
    )
    requested_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class ConnectionRequest(Base):
    """Connection requests between two nodes; approval creates connection."""

    __tablename__ = "connection_requests"

    id = Column(Integer, primary_key=True, index=True)
    requester_id = Column(Integer, ForeignKey("nodes.id"), nullable=False)
    target_id = Column(Integer, ForeignKey("nodes.id"), nullable=False)
    status = Column(
        SQLEnum(ConnectionRequestStatus),
        nullable=False,
        default=ConnectionRequestStatus.PENDING,
    )
    requested_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    requester = relationship("Node", foreign_keys=[requester_id], back_populates="connection_requests_from")
    target = relationship("Node", foreign_keys=[target_id], back_populates="connection_requests_to")


class Connection(Base):
    """Active or terminated peer connections between two nodes."""

    __tablename__ = "connections"

    id = Column(Integer, primary_key=True, index=True)
    node_a_id = Column(Integer, ForeignKey("nodes.id"), nullable=False)
    node_b_id = Column(Integer, ForeignKey("nodes.id"), nullable=False)
    status = Column(SQLEnum(ConnectionStatus), nullable=False, default=ConnectionStatus.ACTIVE)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    node_a = relationship("Node", foreign_keys=[node_a_id], back_populates="connections_a")
    node_b = relationship("Node", foreign_keys=[node_b_id], back_populates="connections_b")


class Notification(Base):
    """Dashboard notifications (join/connection events)."""

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    type = Column(SQLEnum(NotificationType), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Integer, nullable=False, default=0)  # SQLite no native bool
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class Log(Base):
    """Audit log: every action is logged."""

    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(SQLEnum(LogEventType), nullable=False)
    description = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


class RevokedToken(Base):
    """JWT token blacklist. Tokens are added on logout; pruned after expiry."""

    __tablename__ = "revoked_tokens"

    jti = Column(String(64), primary_key=True)
    revoked_at = Column(DateTime(timezone=True), default=datetime.utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)
