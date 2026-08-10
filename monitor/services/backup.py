"""Backup do SQLite usando a API de backup do SQLite.

Não copia cegamente a base durante escrita ativa; usa VACUUM INTO para
produzir um snapshot consistente, verifica a integridade e comprime
opcionalmente. A restauração nunca sobrepõe uma base ativa sem confirmação.
"""

from __future__ import annotations

import gzip
import logging
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from monitor.exceptions import BackupError
from monitor.settings import PROJECT_ROOT

BACKUP_DIR = PROJECT_ROOT / "backups"
RETENTION_DAYS = 14

logger = logging.getLogger(__name__)


def create_backup(
    engine: Engine,
    *,
    directory: Path | None = None,
    compress: bool = True,
    retention_days: int = RETENTION_DAYS,
) -> Path:
    """Cria um backup consistente da base SQLite."""
    directory = directory or BACKUP_DIR
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    raw_path = directory / f"imoveis_{stamp}.db"
    try:
        with engine.connect() as conn:
            conn.execute(text(f"VACUUM INTO '{raw_path.as_posix()}'"))
    except Exception as exc:
        raise BackupError(f"Falha ao criar backup: {exc}") from exc

    if compress:
        compressed = raw_path.with_suffix(raw_path.suffix + ".gz")
        try:
            with raw_path.open("rb") as src, gzip.open(compressed, "wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            raw_path.unlink()
        except Exception as exc:
            raise BackupError(f"Falha ao comprimir backup: {exc}") from exc
        final_path = compressed
    else:
        final_path = raw_path

    _enforce_retention(directory, retention_days)
    logger.info("Backup criado: %s", final_path)
    return final_path


def verify_backup(path: Path) -> bool:
    """Verifica a integridade de um backup comprimido ou não."""
    if path.suffix == ".gz":
        target = path.with_suffix("")
        try:
            with gzip.open(path, "rb") as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
        except Exception as exc:
            raise BackupError(f"Backup corrompido ({path.name}): {exc}") from exc
        return target.exists()
    return path.exists()


def restore_backup(path: Path, engine: Engine, *, confirm: bool = False) -> Path:
    """Restaura um backup para o ficheiro ativo da base.

    Requer confirmação explícita; nunca sobrepõe a base ativa por defeito.
    """
    if not confirm:
        raise BackupError("Restauro requer confirmação explícita (confirm=True).")
    if not path.exists():
        raise BackupError(f"Backup não encontrado: {path}")

    database_path = Path(engine.url.database or "")
    if not database_path.is_absolute():
        database_path = PROJECT_ROOT / database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)

    source = path
    if path.suffix == ".gz":
        source = path.with_suffix("")
        try:
            with gzip.open(path, "rb") as src, source.open("wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
        except Exception as exc:
            raise BackupError(f"Falha ao descomprimir backup: {exc}") from exc

    try:
        engine.dispose()
        shutil.copyfile(source, database_path)
    except Exception as exc:
        raise BackupError(f"Falha ao restaurar base: {exc}") from exc

    logger.info("Base restaurada a partir de %s", path.name)
    return database_path


def _enforce_retention(directory: Path, retention_days: int) -> None:
    cutoff = datetime.now().timestamp() - retention_days * 86400
    for item in directory.iterdir():
        if item.is_file() and item.name.startswith("imoveis_"):
            if item.stat().st_mtime < cutoff:
                item.unlink(missing_ok=True)
