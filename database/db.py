from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from config import Config

DATABASE_URL = Config.DATABASE_URL or "sqlite:///authomatical.db"

# check_same_thread is only relevant for sqlite (PTB workers use asyncio +
# threads under the hood); for Postgres/MySQL this arg is simply omitted.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=connect_args, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def init_db():
    """Create tables that don't exist yet. Safe to call on every worker
    startup (telegram_worker.py, bale_worker.py, services/web_app.py) —
    this is a dev/local-quickstart convenience (create_all only adds
    missing tables, never alters existing ones, and never touches
    alembic_version). In production, prefer running `alembic upgrade
    head` as an explicit deploy step (see migrations/) so schema changes
    are tracked and reversible instead of relying on this."""
    from database import models  # noqa: F401  (registers models on Base)
    Base.metadata.create_all(bind=engine)


def reset_for_tests(database_url: str):
    """Test-only: repoint the engine/session at a fresh database file
    without re-registering the ORM model classes. Reloading
    database.models with importlib would re-run `class Tenant(Base):`
    against a stale SQLAlchemy declarative registry and raise
    'Table already defined for this MetaData instance' — the schema
    itself never changes between tests, only which file it lives in, so
    we just rebuild engine + SessionLocal and re-run create_all against
    the *existing* Base/metadata."""
    global engine, SessionLocal

    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    engine = create_engine(database_url, connect_args=connect_args, future=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

    # database/repository.py and database/licensing.py each did
    # `from database.db import SessionLocal`, which bound their own
    # module-level name to the *old* factory — patch both in place so their
    # functions pick up the new one too.
    import database.repository as repo
    repo.SessionLocal = SessionLocal
    import database.licensing as licensing
    licensing.SessionLocal = SessionLocal

    init_db()