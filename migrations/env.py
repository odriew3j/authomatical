"""Alembic environment wired to Authomatical's SQLAlchemy models."""
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from config import Config
from database.db import Base
from database import models  # noqa: F401 -- register all ORM models on Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# A deployed container normally has DATABASE_URL in its environment.  For
# local `.env` users Config loads that same setting.  Keep an explicitly set
# Alembic URL intact so tests and one-off operators can target a temporary DB.
_configured_url = config.get_main_option("sqlalchemy.url")
_environment_url = os.getenv("DATABASE_URL")
if _environment_url:
    config.set_main_option("sqlalchemy.url", _environment_url)
elif not _configured_url or _configured_url == "sqlite:///authomatical.db":
    config.set_main_option("sqlalchemy.url", Config.DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL without opening a database connection."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Apply migrations using the configured SQLite/PostgreSQL URL."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
