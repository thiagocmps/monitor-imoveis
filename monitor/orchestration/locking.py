"""Mecanismo de bloqueio para impedir execuções paralelas do coletor."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path

from monitor.exceptions import ExecutionLockedError
from monitor.settings import PROJECT_ROOT

LOCK_DIR = PROJECT_ROOT / "data"
DEFAULT_LOCK = LOCK_DIR / "collector.lock"


class ExecutionLock:
    """Lock baseado em flock(2), fiável entre processos e contentores.

    Use como context manager: `with ExecutionLock(): ...`
    """

    def __init__(self, path: Path | None = None, *, non_blocking: bool = True) -> None:
        self.path = path or Path(os.getenv("MONITOR_LOCK_FILE", DEFAULT_LOCK))
        self.non_blocking = non_blocking
        self._fd: int | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if self.non_blocking:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    os.close(fd)
                    raise ExecutionLockedError(
                        "Já existe uma execução do coletor em curso."
                    ) from exc
            else:
                fcntl.flock(fd, fcntl.LOCK_EX)
        except ExecutionLockedError:
            raise
        self._fd = fd

    def release(self) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> ExecutionLock:
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.release()
