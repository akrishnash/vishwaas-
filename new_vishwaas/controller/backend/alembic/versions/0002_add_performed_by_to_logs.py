"""Add performed_by column and indexes to logs table.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("logs", sa.Column("performed_by", sa.String(255), nullable=True))
    op.create_index("ix_logs_event_type", "logs", ["event_type"])
    op.create_index("ix_logs_created_at", "logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_logs_created_at", table_name="logs")
    op.drop_index("ix_logs_event_type", table_name="logs")
    op.drop_column("logs", "performed_by")
