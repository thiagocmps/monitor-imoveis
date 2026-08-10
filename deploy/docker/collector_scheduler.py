"""Agendador do coletor para Docker.

No arranque executa uma recolha imediata (COLLECTOR_RUN_ON_START=true) e de
seguida aguarda até à hora diária definida em config.yaml (schedule.daily_time),
repetindo o ciclo. Usa ExecutionLock para nunca sobrepor execuções.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from monitor.settings import PROJECT_ROOT, load_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("collector-scheduler")


def _next_run(now: datetime, daily_time: str) -> datetime:
    try:
        hour, minute = (int(part) for part in daily_time.split(":"))
    except ValueError as exc:
        raise ValueError(
            f"schedule.daily_time inválido: {daily_time!r} (esperado HH:MM)"
        ) from exc
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate


def _run_collection() -> int:
    logger.info("A iniciar recolha...")
    proc = subprocess.run([sys.executable, "main.py", "collect"], cwd=PROJECT_ROOT)
    if proc.returncode == 0:
        logger.info("Recolha concluída com sucesso.")
    else:
        logger.error("Recolha falhou (código %s).", proc.returncode)
    return proc.returncode


def main() -> None:
    settings = load_settings()
    timezone = ZoneInfo(settings.application.timezone)
    run_on_start = os.getenv("COLLECTOR_RUN_ON_START", "true").lower() == "true"

    if run_on_start:
        _run_collection()

    while True:
        now = datetime.now(timezone)
        next_run = _next_run(now, settings.schedule.daily_time)
        wait_seconds = (next_run - now).total_seconds()
        logger.info(
            "Próxima recolha às %s (daqui a %.1f h).",
            next_run.isoformat(),
            wait_seconds / 3600,
        )
        time.sleep(wait_seconds)
        _run_collection()


if __name__ == "__main__":
    main()
