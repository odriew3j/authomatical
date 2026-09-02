import datetime
from enum import Enum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    UniqueConstraint,
    CheckConstraint,
    Index,
)
from sqlalchemy.orm import relationship

from database.db import Base


class ArticleJobStatus(str, Enum):
    """Durable lifecycle states for an article request.

    The values are stored as ordinary strings instead of a database-native
    enum.  That keeps the same migration portable between PostgreSQL (the
    production source of truth) and SQLite (the local/test database).
    """

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class Tenant(Base):
    """One row per end-user of the bot, identified by which platform they
    talked to us on (telegram/bale) plus their chat id on that platform.
    A telegram chat_id=111 and a bale chat_id=111 are two different
    tenants — the platform is part of the identity, never assumed."""

    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True)
    platform = Column(String(20), nullable=False)            # 'telegram' | 'bale'
    platform_chat_id = Column(String(64), nullable=False)
    display_name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    wp_connection = relationship(
        "WPConnection", back_populates="tenant", uselist=False,
        cascade="all, delete-orphan",
    )
    article_jobs = relationship(
        "ArticleJob", back_populates="tenant", cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("platform", "platform_chat_id", name="uq_tenant_platform_chat"),
    )


class WPConnection(Base):
    """The WordPress/WooCommerce site a tenant has connected, via the
    ODview Sync companion plugin. `secret_encrypted` is the plugin's
    per-site secret (X-ODVIEW-SECRET header), encrypted at rest with
    Config.SECRET_KEY — never stored or logged in plaintext."""

    __tablename__ = "wp_connections"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, unique=True)
    site_url = Column(String(500), nullable=False)
    secret_encrypted = Column(String(2000), nullable=False)
    verified = Column(Boolean, default=False)
    connected_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    tenant = relationship("Tenant", back_populates="wp_connection")


class ArticleJob(Base):
    """The durable source of truth for one requested article.

    Redis only carries this row's ``id`` to the worker.  Request details,
    tenant ownership, lifecycle state and WordPress publishing outcome live
    here so a Redis stream ID can never become the business identifier.
    """

    __tablename__ = "article_jobs"

    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=False, index=True)

    # These are a durable notification/audit snapshot derived from the owning
    # Tenant when the job is created.  They are never accepted from Redis as
    # authority for WordPress site selection.
    platform = Column(String(20), nullable=False)
    platform_chat_id = Column(String(64), nullable=False)
    source = Column(String(32), nullable=False, default="bot")

    # Durable request input.
    keywords = Column(Text, nullable=False)
    article_type = Column(String(255), nullable=False, default="")
    notes = Column(Text, nullable=False, default="")
    chapters = Column(Integer, nullable=False, default=5)
    max_words = Column(Integer, nullable=False, default=500)
    tone = Column(String(100), nullable=False, default="informative")
    audience = Column(String(255), nullable=False, default="general")

    # Optional featured image: a URL already uploaded to the tenant's own
    # WordPress media library (via SiteConnectorClient.upload_media before
    # this job is created — see workers/common_handlers.py). Never an
    # arbitrary external URL; the plugin resolves it with
    # attachment_url_to_postid, which only matches local attachments.
    featured_image_url = Column(Text, nullable=True)

    status = Column(String(20), nullable=False, default=ArticleJobStatus.PENDING.value, index=True)
    retry_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)

    # Redis is transport only, but retaining the queue message ID is useful
    # for diagnosis without ever using it as the job's primary identity.
    queue_message_id = Column(String(100), nullable=True)
    requested_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    queued_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    wordpress_post_id = Column(Integer, nullable=True)
    wordpress_post_url = Column(Text, nullable=True)

    tenant = relationship("Tenant", back_populates="article_jobs")
    attempts = relationship(
        "ArticleAttempt",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="ArticleAttempt.attempt_number",
    )
    results = relationship(
        "ArticleResult",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="ArticleResult.id",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'PROCESSING', 'SUCCESS', 'FAILED')",
            name="ck_article_jobs_status",
        ),
        Index("ix_article_jobs_tenant_status", "tenant_id", "status"),
        Index("ix_article_jobs_requested_at", "requested_at"),
    )


class ArticleAttempt(Base):
    """One execution attempt for an ArticleJob.

    Keeping attempt rows separate from the job makes terminal errors and any
    future deliberate retry/recovery workflow auditable without overwriting
    the history of prior worker runs.
    """

    __tablename__ = "article_attempts"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("article_jobs.id"), nullable=False, index=True)
    attempt_number = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default=ArticleJobStatus.PROCESSING.value)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    job = relationship("ArticleJob", back_populates="attempts")
    result = relationship(
        "ArticleResult", back_populates="attempt", uselist=False,
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('PROCESSING', 'SUCCESS', 'FAILED')",
            name="ck_article_attempts_status",
        ),
        UniqueConstraint("job_id", "attempt_number", name="uq_article_attempt_job_number"),
    )


class ArticleResult(Base):
    """Structured AI output for one worker attempt, saved before publishing.

    A job can retain outputs from more than one explicitly initiated attempt;
    ``attempt_id`` is unique so each execution contributes at most one result.
    ``chapters_json`` intentionally uses portable Text JSON so the exact same
    model works on PostgreSQL and the project's SQLite development setup.
    """

    __tablename__ = "article_results"

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("article_jobs.id"), nullable=False, index=True)
    attempt_id = Column(Integer, ForeignKey("article_attempts.id"), nullable=False)

    title = Column(String(500), nullable=False)
    slug = Column(String(500), nullable=True)
    subtitle = Column(Text, nullable=True)
    introduction = Column(Text, nullable=True)
    chapters_json = Column(Text, nullable=False, default="[]")
    conclusions = Column(Text, nullable=True)
    image_prompt = Column(Text, nullable=True)
    content_html = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    job = relationship("ArticleJob", back_populates="results")
    attempt = relationship("ArticleAttempt", back_populates="result")

    __table_args__ = (
        UniqueConstraint("attempt_id", name="uq_article_result_attempt"),
    )
