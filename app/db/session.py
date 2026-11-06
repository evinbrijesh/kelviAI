import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base

logger = logging.getLogger(__name__)


def normalize_database_url(url: str) -> str:
    """Point plain postgresql:// URLs at psycopg 3, the driver this project installs."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


class Database:
    def __init__(self, url: str, *, echo: bool = False, connect_timeout: int = 3) -> None:
        self.url = normalize_database_url(url)
        connect_args: dict[str, Any] = {}
        if self.url.startswith("postgresql"):
            # Without this a health check can block for minutes behind a dead proxy port.
            connect_args["connect_timeout"] = connect_timeout
        engine_kwargs: dict[str, Any] = {
            "pool_pre_ping": True,
            "echo": echo,
            "connect_args": connect_args,
        }
        if not self.url.startswith("sqlite"):
            engine_kwargs["pool_timeout"] = connect_timeout

        self.engine: Engine = create_engine(self.url, **engine_kwargs)
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)

    def create_schema(self) -> None:
        # Import registers every model on Base.metadata before create_all runs.
        from app.db import models  # noqa: F401

        Base.metadata.create_all(self.engine)
        logger.info("Database schema ready")

    def check(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception:
            logger.warning("Database health check failed", exc_info=True)
            return False
        return True

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        self.engine.dispose()
