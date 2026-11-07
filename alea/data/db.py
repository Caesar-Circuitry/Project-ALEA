"""Engine, session and Alembic helpers. Default database: `sqlite:///alea.db`."""

from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from alea.data.models import DEFAULT_DB_URL

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def default_url() -> str:
    """`ALEA_DB_URL` if set, else sqlite:///alea.db."""
    return os.environ.get("ALEA_DB_URL", DEFAULT_DB_URL)


def make_engine(url: str | None = None) -> Engine:
    return create_engine(url or default_url())


def make_session(engine: Engine) -> Session:
    return sessionmaker(engine, expire_on_commit=False)()


def alembic_config(url: str | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.set_main_option("sqlalchemy.url", (url or default_url()).replace("%", "%%"))
    return cfg


def upgrade(url: str | None = None, revision: str = "head") -> None:
    """Create or migrate the database at `url` to `revision`."""
    command.upgrade(alembic_config(url), revision)
