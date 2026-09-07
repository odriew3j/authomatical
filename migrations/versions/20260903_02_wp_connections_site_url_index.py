"""Index wp_connections.site_url for the plugin status lookup

Revision ID: 20260903_02
Revises: 20260903_01
Create Date: 2026-09-03

The new /api/connect/status endpoint looks up wp_connections by site_url to
tell the plugin whether this exact site is already paired (see
find_wp_connection_status in database/repository.py). This migration only
adds a supporting index; no data or existing columns change.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260903_02"
down_revision: Union[str, Sequence[str], None] = "20260903_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_wp_connections_site_url", "wp_connections", ["site_url"])


def downgrade() -> None:
    op.drop_index("ix_wp_connections_site_url", table_name="wp_connections")
