"""add article job featured image

Revision ID: 20260901_02
Revises: 20260901_01
Create Date: 2026-09-01

Featured image URLs are uploaded to the tenant's own WordPress media
library before the durable job is created (see
workers/common_handlers.py) and are never taken from an arbitrary
external URL — the plugin resolves them with attachment_url_to_postid,
which only matches local attachments.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20260901_02'
down_revision: Union[str, Sequence[str], None] = '20260901_01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('article_jobs', sa.Column('featured_image_url', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('article_jobs', 'featured_image_url')
