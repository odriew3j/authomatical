import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine

from database import models  # noqa: F401 -- register model metadata
from database.models import Tenant, WPConnection


ROOT = Path(__file__).resolve().parents[1]
HEAD_REVISION = "20260902_02"
ARTICLE_TABLES_REVISION = "20260901_01"  # first revision to create article_jobs/attempts/results
INITIAL_REVISION = "20260830_01"


def _alembic_config(database_url: str) -> AlembicConfig:
    config = AlembicConfig(str(ROOT / "alembic.ini"))
    # Keep the target explicit: migrations/env.py deliberately honors this
    # non-default URL for test/one-off use when DATABASE_URL is not exported.
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _tables(connection):
    return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_article_persistence_migration_upgrades_and_downgrades_cleanly(tmp_path, monkeypatch):
    db_path = tmp_path / "migrated.sqlite3"
    url = f"sqlite:///{db_path}"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = _alembic_config(url)

    command.upgrade(config, "head")

    connection = sqlite3.connect(db_path)
    try:
        tables = _tables(connection)
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        job_columns = {row[1] for row in connection.execute("PRAGMA table_info(article_jobs)")}
        attempt_columns = {row[1] for row in connection.execute("PRAGMA table_info(article_attempts)")}
        result_columns = {row[1] for row in connection.execute("PRAGMA table_info(article_results)")}
        pending_columns = {row[1] for row in connection.execute("PRAGMA table_info(pending_connections)")}
    finally:
        connection.close()

    assert {"alembic_version", "tenants", "wp_connections", "article_jobs", "article_attempts", "article_results", "pending_connections"}.issubset(tables)
    assert revision == HEAD_REVISION
    assert {"tenant_id", "keywords", "status", "retry_count", "queue_message_id", "wordpress_post_id", "featured_image_url"}.issubset(job_columns)
    assert {"job_id", "attempt_number", "status", "error_message"}.issubset(attempt_columns)
    assert {"job_id", "attempt_id", "title", "slug", "chapters_json", "image_prompt", "content_html"}.issubset(result_columns)
    assert {"token_digest", "platform", "site_url", "secret_encrypted", "expires_at", "consumed_at"}.issubset(pending_columns)
    assert "token" not in pending_columns

    # The article migration is independently reversible and leaves the
    # existing tenant/connection schema on its previous revision.
    command.downgrade(config, INITIAL_REVISION)
    connection = sqlite3.connect(db_path)
    try:
        after_article_downgrade = _tables(connection)
        revision_after_article_downgrade = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    finally:
        connection.close()

    assert {"tenants", "wp_connections"}.issubset(after_article_downgrade)
    assert not {"article_jobs", "article_attempts", "article_results"}.intersection(after_article_downgrade)
    assert revision_after_article_downgrade == INITIAL_REVISION

    command.downgrade(config, "base")
    connection = sqlite3.connect(db_path)
    try:
        tables_after_downgrade = _tables(connection)
    finally:
        connection.close()

    assert "tenants" not in tables_after_downgrade
    assert "wp_connections" not in tables_after_downgrade


def test_migration_adopts_existing_pre_article_tenant_schema(tmp_path, monkeypatch):
    """A legacy create_all database has tenant/WP tables but no Article
    history.  The initial migration adopts those tables, then the ordinary
    follow-up migration adds durable Article persistence without deletion."""

    db_path = tmp_path / "existing.sqlite3"
    url = f"sqlite:///{db_path}"
    monkeypatch.delenv("DATABASE_URL", raising=False)

    engine = create_engine(url)
    try:
        # Deliberately create only the schema that existed before this feature,
        # rather than current Base.metadata (which now includes article tables).
        Tenant.__table__.create(engine)
        WPConnection.__table__.create(engine)
        with engine.begin() as connection:
            connection.execute(Tenant.__table__.insert().values(
                id=7,
                platform="telegram",
                platform_chat_id="700",
                display_name="legacy tenant",
            ))
            connection.execute(WPConnection.__table__.insert().values(
                id=8,
                tenant_id=7,
                site_url="https://legacy.example",
                secret_encrypted="legacy-encrypted-value",
                verified=True,
            ))
    finally:
        engine.dispose()

    command.upgrade(_alembic_config(url), "head")
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == HEAD_REVISION
        assert {"tenants", "wp_connections", "article_jobs", "article_attempts", "article_results"}.issubset(_tables(connection))
        assert connection.execute("SELECT platform, platform_chat_id FROM tenants WHERE id=7").fetchone() == ("telegram", "700")
        assert connection.execute("SELECT site_url FROM wp_connections WHERE tenant_id=7").fetchone() == ("https://legacy.example",)


def test_pending_connection_hardening_revokes_unbound_legacy_capabilities(tmp_path, monkeypatch):
    """A pre-hardening token has no safe target platform, so upgrade must
    fail closed rather than accidentally allowing it in Telegram or Bale."""

    db_path = tmp_path / "legacy-pairing.sqlite3"
    url = f"sqlite:///{db_path}"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = _alembic_config(url)

    command.upgrade(config, "20260902_01")
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO pending_connections "
            "(token, site_url, secret_encrypted, expires_at) VALUES (?, ?, ?, ?)",
            ("old-token", "https://legacy.example", "encrypted", "2099-01-01 00:00:00"),
        )
        connection.commit()

    command.upgrade(config, "head")
    with sqlite3.connect(db_path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(pending_connections)")}
        assert "token_digest" in columns
        assert "token" not in columns
        assert connection.execute("SELECT COUNT(*) FROM pending_connections").fetchone() == (0,)
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == HEAD_REVISION
