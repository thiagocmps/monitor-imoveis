"""Guardar e limpar screenshots e snapshots de HTML."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime

from monitor.settings import PROJECT_ROOT

SCREENSHOT_DIR = PROJECT_ROOT / "screenshots"
SNAPSHOT_DIR = PROJECT_ROOT / "snapshots"

logger = logging.getLogger(__name__)


def clean_old_artifacts(days: int = 30) -> None:
    """Remove screenshots e snapshots mais antigos que `days` dias."""
    cutoff = datetime.now().timestamp() - days * 86400
    for directory in (SCREENSHOT_DIR, SNAPSHOT_DIR):
        if not directory.exists():
            continue
        for item in directory.iterdir():
            if item.is_file() and item.stat().st_mtime < cutoff:
                item.unlink(missing_ok=True)
                logger.debug("Removido artefacto antigo: %s", item.name)


def clear_all() -> None:
    """Limpa todas as screenshots e snapshots."""
    for directory in (SCREENSHOT_DIR, SNAPSHOT_DIR):
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)
            directory.mkdir(parents=True, exist_ok=True)
    logger.info("Screenshots e snapshots limpos.")
