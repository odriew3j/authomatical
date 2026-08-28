import datetime

from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship

from database.db import Base


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
        cascade="all, delete-orphan"
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
