"""initial tenants and WordPress connections schema

Revision ID: 20260830_01
Revises:
Create Date: 2026-08-30

"""
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260830_01"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _existing_tables() -> set[str]:
    # Offline SQL generation has no inspectable connection. Emit the normal
    # CREATE statements there; the adoption guard is only needed online.
    if context.is_offline_mode():
        return set()
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    # The project historically used Base.metadata.create_all() for local
    # SQLite development.  Make this one initial migration safe to adopt on
    # such an already-initialized database: create only tables that are not
    # present, then Alembic records the revision normally.  Later migrations
    # should be conventional explicit schema changes.
    existing_tables = _existing_tables()

    if "tenants" not in existing_tables:
        op.create_table(
            "tenants",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("platform", sa.String(length=20), nullable=False),
            sa.Column("platform_chat_id", sa.String(length=64), nullable=False),
            sa.Column("display_name", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("platform", "platform_chat_id", name="uq_tenant_platform_chat"),
        )
    if "wp_connections" not in existing_tables:
        op.create_table(
            "wp_connections",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("tenant_id", sa.Integer(), nullable=False),
            sa.Column("site_url", sa.String(length=500), nullable=False),
            sa.Column("secret_encrypted", sa.String(length=2000), nullable=False),
            sa.Column("verified", sa.Boolean(), nullable=True),
            sa.Column("connected_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("tenant_id"),
        )


def downgrade() -> None:
    existing_tables = _existing_tables()
    if "wp_connections" in existing_tables:
        op.drop_table("wp_connections")
    if "tenants" in existing_tables:
        op.drop_table("tenants")
