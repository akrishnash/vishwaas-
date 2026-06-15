"""Initial schema baseline — captures all tables as they exist at project start.

Revision ID: 0001
Revises:
Create Date: 2026-04-07

Run `alembic stamp head` on an existing database (created by create_all) to mark
it as already at this revision without re-running the DDL.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "nodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("public_key", sa.String(512), nullable=False),
        sa.Column("agent_url", sa.String(512), nullable=False),
        sa.Column("vpn_ip", sa.String(45), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "APPROVED", "ACTIVE", "REJECTED", "OFFLINE", name="nodestatus"),
            nullable=False,
        ),
        sa.Column("is_gateway", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_key"),
        sa.UniqueConstraint("vpn_ip"),
    )
    op.create_index("ix_nodes_id", "nodes", ["id"])
    op.create_index("ix_nodes_name", "nodes", ["name"])

    op.create_table(
        "join_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("node_name", sa.String(255), nullable=False),
        sa.Column("public_key", sa.String(512), nullable=False),
        sa.Column("agent_url", sa.String(512), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "APPROVED", "REJECTED", name="joinrequeststatus"),
            nullable=False,
        ),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_join_requests_id", "join_requests", ["id"])

    op.create_table(
        "connection_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("requester_id", sa.Integer(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("PENDING", "APPROVED", "REJECTED", name="connectionrequeststatus"),
            nullable=False,
        ),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["requester_id"], ["nodes.id"]),
        sa.ForeignKeyConstraint(["target_id"], ["nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_connection_requests_id", "connection_requests", ["id"])

    op.create_table(
        "connections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("node_a_id", sa.Integer(), nullable=False),
        sa.Column("node_b_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum("ACTIVE", "REJECTED", "TERMINATED", name="connectionstatus"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["node_a_id"], ["nodes.id"]),
        sa.ForeignKeyConstraint(["node_b_id"], ["nodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_connections_id", "connections", ["id"])

    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "type",
            sa.Enum(
                "JOIN_APPROVED", "JOIN_REJECTED",
                "CONNECTION_APPROVED", "CONNECTION_REJECTED", "CONNECTION_TERMINATED",
                name="notificationtype",
            ),
            nullable=False,
        ),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_id", "notifications", ["id"])

    op.create_table(
        "logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum(
                "JOIN_REQUESTED", "JOIN_APPROVED", "JOIN_REJECTED",
                "CONNECTION_REQUESTED", "CONNECTION_APPROVED",
                "CONNECTION_REJECTED", "CONNECTION_TERMINATED",
                "NODE_REMOVED", "NODE_OFFLINE",
                name="logeventtype",
            ),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_logs_id", "logs", ["id"])

    op.create_table(
        "revoked_tokens",
        sa.Column("jti", sa.String(64), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("jti"),
    )


def downgrade() -> None:
    op.drop_table("revoked_tokens")
    op.drop_index("ix_logs_id", table_name="logs")
    op.drop_table("logs")
    op.drop_index("ix_notifications_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_connections_id", table_name="connections")
    op.drop_table("connections")
    op.drop_index("ix_connection_requests_id", table_name="connection_requests")
    op.drop_table("connection_requests")
    op.drop_index("ix_join_requests_id", table_name="join_requests")
    op.drop_table("join_requests")
    op.drop_index("ix_nodes_name", table_name="nodes")
    op.drop_index("ix_nodes_id", table_name="nodes")
    op.drop_table("nodes")
