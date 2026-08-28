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
    startup (telegram_worker.py, bale_worker.py, services/web_app.py)."""
    from database import models  # noqa: F401  (registers models on Base)
    Base.metadata.create_all(bind=engine)
