"""Database engine and session management for pelis-feed."""

from __future__ import annotations

import logging

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import sessionmaker, Session

from src.common.models import Base

__all__ = ["get_engine", "get_session_factory", "init_db"]

logger = logging.getLogger(__name__)


def get_engine(config: dict) -> Engine:
    """Create a SQLAlchemy engine from the database configuration.

    Args:
        config: Full application config dict (expects config["database"]["url"]).

    Returns:
        A configured SQLAlchemy Engine instance.
    """
    db_url = config["database"]["url"]
    engine = create_engine(db_url, echo=False)
    logger.info("Database engine created for: %s", db_url.split("@")[-1] if "@" in db_url else db_url)
    return engine


def get_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to the given engine.

    Args:
        engine: A SQLAlchemy Engine instance.

    Returns:
        A sessionmaker configured for the engine.
    """
    return sessionmaker(bind=engine)


def init_db(engine: Engine) -> None:
    """Create all tables defined in the ORM models.

    Args:
        engine: A SQLAlchemy Engine instance.
    """
    Base.metadata.create_all(engine)
    logger.info("Database tables created/verified.")
