"""Notificações (reservado para versões futuras).

A primeira versão não envia notificações. Este módulo fornece uma
fachada para futuras integrações (e-mail, Ntfy, etc.) sem afetar o
comportamento atual.
"""

from __future__ import annotations

import logging
from typing import Protocol

from monitor.models.events import ApplicationEvent

logger = logging.getLogger(__name__)


class Notifier(Protocol):
    def notify(self, events: list[ApplicationEvent]) -> None: ...


class NoopNotifier:
    """Notificador vazio: descarta eventos sem efeito."""

    def notify(self, events: list[ApplicationEvent]) -> None:
        count = len(events)
        del events
        logger.debug("Notificações desativadas; %s eventos ignorados.", count)


def build_notifier() -> Notifier:
    return NoopNotifier()
