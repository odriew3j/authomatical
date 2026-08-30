import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine

from database import models  # noqa: F401 -- register model metadata
from database.db import Base


ROOT = Path(__file__).resolve().parents[1]


def _alembic_config(database_url: str) -> AlembicConfig:
    config = AlembicConfig(str(ROOT / "alembic.ini"))
    # Keep the target explicit: migrations/env.py deliberately honors this
    # non-default URL for test/one-off use when DATABASE_URL is not exported.
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_initial_migration_upgrades_and_downgrades_cleanly(tmp_path, monkeypatch):
    db_path = tmp_path / "migrated.sqlite3"
    url = f"sqlite:///{db_path}"
    monkeypatch.delenv("DATABASE_URL", raising=False)
    config = _alembic_config(url)

    command.upgrade(config, "head")

    connection = sqlite3.connect(db_path)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    finally:
        connection.close()

    assert {"alembic_version", "tenants", "wp_connections"}.issubset(tables)
    assert revision == "20260830_01"

    command.downgrade(config, "base")
    connection = sqlite3.connect(db_path)
    try:
        tables_after_downgrade = {
            row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        connection.close()

    assert "tenants" not in tables_after_downgrade
    assert "wp_connections" not in tables_after_downgrade


def test_initial_migration_adopts_an_existing_create_all_schema(tmp_path, monkeypatch):
    """Users upgrading from the pre-Alembic local SQLite setup do not need
    to delete their existing tenant connections before starting the new code."""
    db_path = tmp_path / "existing.sqlite3"
    url = f"sqlite:///{db_path}"
    monkeypatch.delenv("DATABASE_URL", raising=False)

    engine = create_engine(url)
    try:
        Base.metadata.create_all(engine)
    finally:
        engine.dispose()

    command.upgrade(_alembic_config(url), "head")
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "20260830_01"
