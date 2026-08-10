"""Criação de tabelas e migrações simples e idempotentes."""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from monitor.database.base import Base
from monitor.database.models import (  # noqa: F401  (import registo das tabelas)
    ApplicationEventRecord,
    ErrorRecord,
    Property,
    PropertyMatch,
    PropertyObservation,
    SourceRun,
    UserDecision,
)

logger = logging.getLogger(__name__)


def initialize_database(engine: Engine) -> None:
    """Cria as tabelas em falta e aplica pragmas de manutenção."""
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    Base.metadata.create_all(engine)
    created = sorted(set(Base.metadata.tables) - existing)
    if created:
        logger.info("Tabelas criadas: %s", ", ".join(created))

    with engine.begin() as conn:
        conn.execute(text("PRAGMA journal_mode=WAL"))
        conn.execute(text("PRAGMA wal_autocheckpoint=1000"))


def run_migrations(session: Session) -> None:
    """Ponto de extensão para migrações futuras.

    As migrações atuais são idempotentes via create_all. Quando forem
    necessárias migrações de esquema, implementá-las aqui com ALTER TABLE
    e um registo de versão na tabela application_events.
    """
    del session  # reservado
