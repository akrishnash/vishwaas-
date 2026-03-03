"""
Pydantic schemas for API request/response.
Separate from domain and persistence for clean API contract.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.domain.enums import (
    NodeStatus,
    ConnectionStatus,
    JoinRequestStatus,
    ConnectionRequestStatus,
    NotificationType,
    LogEventType,
)


# ----- Join flow -----


class RequestJoinBody(BaseModel):
    """POST /request-join body. public_key optional: if omitted, controller will issue keys on approve."""

    node_name: str = Field(..., min_length=1, max_length=255)
    agent_url: str = Field(..., min_length=1, max_length=512)
    public_key: Optional[str] = Field(default="", max_length=512)


class JoinRequestSchema(BaseModel):
    id: int
    node_name: str
    public_key: Optional[str] = ""
    agent_url: str
    status: JoinRequestStatus
    requested_at: datetime

    class Config:
        from_attributes = True


# ----- Connection flow -----


class RequestConnectionBody(BaseModel):
    """POST /request-connection body."""

    requester_id: int = Field(..., gt=0)
    target_id: int = Field(..., gt=0)


class ConnectionRequestSchema(BaseModel):
    id: int
    requester_id: int
    target_id: int
    status: ConnectionRequestStatus
    requested_at: datetime

    class Config:
        from_attributes = True


class ConnectionRequestWithNodesSchema(ConnectionRequestSchema):
    """With requester/target names for dashboard."""

    requester_name: Optional[str] = None
    target_name: Optional[str] = None


# ----- Nodes -----


class NodeSchema(BaseModel):
    id: int
    name: str
    public_key: str
    agent_url: str
    vpn_ip: str
    status: NodeStatus
    last_seen: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class NodeUpdateBody(BaseModel):
    """PATCH /nodes/{id}: update agent_url and/or name."""
    agent_url: Optional[str] = Field(default=None, min_length=1, max_length=512)
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)


# ----- Connections -----


class ConnectionSchema(BaseModel):
    id: int
    node_a_id: int
    node_b_id: int
    status: ConnectionStatus
    created_at: datetime

    class Config:
        from_attributes = True


class ConnectionWithNodesSchema(ConnectionSchema):
    node_a_name: Optional[str] = None
    node_b_name: Optional[str] = None


# ----- Notifications -----


class NotificationSchema(BaseModel):
    id: int
    type: NotificationType
    message: str
    is_read: bool
    created_at: datetime

    @field_validator("is_read", mode="before")
    @classmethod
    def coerce_is_read(cls, v):  # SQLite stores 0/1
        return bool(v)

    class Config:
        from_attributes = True


# ----- Logs -----


class LogSchema(BaseModel):
    id: int
    event_type: LogEventType
    description: str
    created_at: datetime

    class Config:
        from_attributes = True


# ----- Stats -----


class StatsSchema(BaseModel):
    """GET /stats response."""

    total_nodes: int
    active_nodes: int
    pending_join_requests: int
    pending_connection_requests: int
    active_connections: int
    unread_notifications: int


# ----- Stats detailed (bandwidth, connectivity from agents) -----


class PeerStatsSchema(BaseModel):
    public_key: str
    allowed_ips: str = ""
    transfer_rx: int = 0
    transfer_tx: int = 0
    latest_handshake_ago: Optional[int] = None  # seconds ago, None = never


class NodeStatsSchema(BaseModel):
    node_id: int
    node_name: str
    vpn_ip: str
    agent_url: str
    reachable: bool
    total_rx: int = 0
    total_tx: int = 0
    peers: list[PeerStatsSchema] = []


class StatsDetailedSchema(BaseModel):
    nodes: list[NodeStatsSchema] = []
    total_rx: int = 0
    total_tx: int = 0


# ----- Topology (nodes + connections graph) -----


class TopologyNodeSchema(BaseModel):
    id: int
    name: str
    vpn_ip: str
    status: NodeStatus


class TopologyEdgeSchema(BaseModel):
    id: int
    source_id: int
    target_id: int
    status: ConnectionStatus


class TopologySchema(BaseModel):
    nodes: list[TopologyNodeSchema]
    edges: list[TopologyEdgeSchema]
