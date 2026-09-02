"""add pending_connections table for one-click site connect

Revision ID: 20260902_01
Revises: 20260901_02
Create Date: 2026-09-02

Backs the "اتصال با یک کلیک" flow: the ODview Sync plugin registers a
short-lived (token, site_url, secret) handshake here via the new public
/api/connect/register endpoint, and the bot consumes it exactly once
when the person opens the /start connect_<token> deep link.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260902_01'
down_revision: Union[str, Sequence[str], None] = '20260901_02'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pending_connections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=128), nullable=False),
        sa.Column("site_url", sa.String(length=500), nullable=False),
        sa.Column("secret_encrypted", sa.String(length=2000), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_pending_connections_token"),
    )
    op.create_index(
        "ix_pending_connections_token", "pending_connections", ["token"], unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_pending_connections_token", table_name="pending_connections")
    op.drop_table("pending_connections")