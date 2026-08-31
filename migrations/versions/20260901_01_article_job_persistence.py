"""add durable article jobs, attempts, and results

Revision ID: 20260901_01
Revises: 20260830_01
Create Date: 2026-09-01

Redis streams are deliberately not used as the durable Article identity.
This migration adds PostgreSQL/SQLite-backed request, execution and output
history; a stream entry now carries only article_jobs.id to the worker.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260901_01"
down_revision: Union[str, Sequence[str], None] = "20260830_01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "article_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("platform_chat_id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False, server_default=sa.text("'bot'")),
        sa.Column("keywords", sa.Text(), nullable=False),
        sa.Column("article_type", sa.String(length=255), nullable=False, server_default=sa.text("''")),
        sa.Column("notes", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("chapters", sa.Integer(), nullable=False, server_default=sa.text("5")),
        sa.Column("max_words", sa.Integer(), nullable=False, server_default=sa.text("500")),
        sa.Column("tone", sa.String(length=100), nullable=False, server_default=sa.text("'informative'")),
        sa.Column("audience", sa.String(length=255), nullable=False, server_default=sa.text("'general'")),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("queue_message_id", sa.String(length=100), nullable=True),
        sa.Column("requested_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("queued_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("wordpress_post_id", sa.Integer(), nullable=True),
        sa.Column("wordpress_post_url", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'SUCCESS', 'FAILED')",
            name="ck_article_jobs_status",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_article_jobs_tenant_id", "article_jobs", ["tenant_id"], unique=False)
    op.create_index("ix_article_jobs_status", "article_jobs", ["status"], unique=False)
    op.create_index("ix_article_jobs_tenant_status", "article_jobs", ["tenant_id", "status"], unique=False)
    op.create_index("ix_article_jobs_requested_at", "article_jobs", ["requested_at"], unique=False)

    op.create_table(
        "article_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default=sa.text("'PROCESSING'")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "status IN ('PROCESSING', 'SUCCESS', 'FAILED')",
            name="ck_article_attempts_status",
        ),
        sa.ForeignKeyConstraint(["job_id"], ["article_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "attempt_number", name="uq_article_attempt_job_number"),
    )
    op.create_index("ix_article_attempts_job_id", "article_attempts", ["job_id"], unique=False)

    op.create_table(
        "article_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("attempt_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("slug", sa.String(length=500), nullable=True),
        sa.Column("subtitle", sa.Text(), nullable=True),
        sa.Column("introduction", sa.Text(), nullable=True),
        sa.Column("chapters_json", sa.Text(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("conclusions", sa.Text(), nullable=True),
        sa.Column("image_prompt", sa.Text(), nullable=True),
        sa.Column("content_html", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["attempt_id"], ["article_attempts.id"]),
        sa.ForeignKeyConstraint(["job_id"], ["article_jobs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id", name="uq_article_result_attempt"),
    )
    op.create_index("ix_article_results_job_id", "article_results", ["job_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_article_results_job_id", table_name="article_results")
    op.drop_table("article_results")

    op.drop_index("ix_article_attempts_job_id", table_name="article_attempts")
    op.drop_table("article_attempts")

    op.drop_index("ix_article_jobs_requested_at", table_name="article_jobs")
    op.drop_index("ix_article_jobs_tenant_status", table_name="article_jobs")
    op.drop_index("ix_article_jobs_status", table_name="article_jobs")
    op.drop_index("ix_article_jobs_tenant_id", table_name="article_jobs")
    op.drop_table("article_jobs")
