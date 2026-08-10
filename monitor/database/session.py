"""Gestão de sessão e engine SQLite (modo WAL, transações curtas)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from monitor.settings import Settings


def create_engine_for(database_path: Path) -> Engine:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{database_path}",
        connect_args={"timeout": 30},
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


class Database:
    """Fachada sobre engine + sessionmaker."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.engine = create_engine_for(settings.application.absolute_database_path)
        self._session_factory: sessionmaker[Session] = sessionmaker(
            bind=self.engine, expire_on_commit=False, future=True
        )

    def new_session(self) -> Session:
        return self._session_factory()

    def dispose(self) -> None:
        self.engine.dispose()
