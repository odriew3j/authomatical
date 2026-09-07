"""Add licenses and ai_usage tables for feature entitlements and AI quota

Revision ID: 20260903_01
Revises: 20260902_02
Create Date: 2026-09-03

Introduces the licensing/quota data model as a concern separate from
article history: `licenses` holds per-tenant feature flags and AI limit
ceilings (never plan-name branching — see the License model docstring),
`ai_usage` records each consumed AI credit for quota enforcement and
reporting. Neither table touches tenants, wp_connections, pending_connections
or article_jobs; no existing data is modified.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260903_01"
down_revision: Union[str, Sequence[str], None] = "20260902_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "licenses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("plan_key", sa.String(length=50), nullable=False, server_default=sa.text("'trial'")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("features_json", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("ai_daily_limit", sa.Integer(), nullable=True),
        sa.Column("ai_monthly_limit", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('active', 'suspended', 'expired')", name="ck_licenses_status"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_licenses_tenant_id"),
    )

    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(length=50), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_usage_tenant_id", "ai_usage", ["tenant_id"])
    op.create_index("ix_ai_usage_occurred_at", "ai_usage", ["occurred_at"])
    op.create_index("ix_ai_usage_tenant_occurred", "ai_usage", ["tenant_id", "occurred_at"])


def downgrade() -> None:
    op.drop_index("ix_ai_usage_tenant_occurred", table_name="ai_usage")
    op.drop_index("ix_ai_usage_occurred_at", table_name="ai_usage")
    op.drop_index("ix_ai_usage_tenant_id", table_name="ai_usage")
    op.drop_table("ai_usage")
    op.drop_table("licenses")
