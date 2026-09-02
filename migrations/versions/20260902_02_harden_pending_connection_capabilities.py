"""Harden one-click pairing capabilities

Revision ID: 20260902_02
Revises: 20260902_01
Create Date: 2026-09-02

The first pending_connections revision briefly stored raw, cross-platform
bearer tokens.  Pending handshakes intentionally live only a few minutes, so
this migration fail-safely revokes any still-open legacy handshakes and
rebuilds the table with a token digest and an explicit target platform.  No
WordPress connection or durable Article history is touched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260902_02"
down_revision: Union[str, Sequence[str], None] = "20260902_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_hardened_table() -> None:
    op.create_table(
        "pending_connections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("site_url", sa.String(length=500), nullable=False),
        sa.Column("secret_encrypted", sa.String(length=2000), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "platform IN ('telegram', 'bale')",
            name="ck_pending_connections_platform",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_digest", name="uq_pending_connections_token_digest"),
    )
    op.create_index(
        "ix_pending_connections_token_digest",
        "pending_connections",
        ["token_digest"],
        unique=True,
    )


def _create_legacy_table() -> None:
    """Schema from 20260902_01, used only for a reversible downgrade."""

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
        "ix_pending_connections_token",
        "pending_connections",
        ["token"],
        unique=True,
    )


def upgrade() -> None:
    # Existing rows are unconsumed bearer credentials that cannot safely be
    # assigned a platform after the fact.  Revoking them is safer than guessing
    # and costs at most the configured short token TTL; users can immediately
    # generate a replacement link in wp-admin.
    op.drop_table("pending_connections")
    _create_hardened_table()


def downgrade() -> None:
    # The raw tokens cannot be reconstructed from their SHA-256 digests.  As in
    # upgrade, fail closed rather than recreating usable unbound capabilities.
    op.drop_table("pending_connections")
    _create_legacy_table()
