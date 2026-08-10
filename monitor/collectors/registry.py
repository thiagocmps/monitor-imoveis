"""Registo central de coletores.

Fontes desativadas ou adiadas ficam registadas com um estado claro e não
causam falha global.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from monitor.exceptions import SourceNotFoundError

if TYPE_CHECKING:
    from monitor.collectors.base import BaseCollector, CollectorContext

logger = logging.getLogger(__name__)

_ALL_SOURCES = [
    "eleiloes",
    "citius",
    "financas",
    "leilosoc",
    "leilosil",
    "leilon",
    "leiloversatil",
    "caixa_imobiliario",
    "imovirtual",
    "idealista",
    "olx",
]


class CollectorRegistry:
    """Mapeia nomes de fonte para fábricas de coletores."""

    def __init__(self) -> None:
        self._factories: dict[str, Any] = {}
        self._implemented: set[str] = set()
        self._unavailable: set[str] = set()

    def register(self, source: str, factory: Any, *, implemented: bool = True) -> None:
        self._factories[source] = factory
        if implemented:
            self._implemented.add(source)
        else:
            self._unavailable.add(source)

    def create(self, source: str, context: CollectorContext) -> BaseCollector:
        if source not in self._factories:
            raise SourceNotFoundError(f"Fonte desconhecida: {source!r}")
        factory = self._factories[source]
        return factory(context)

    def is_implemented(self, source: str) -> bool:
        return source in self._implemented

    def status(self, source: str) -> str:
        if source in self._unavailable:
            return "UNAVAILABLE"
        if source in self._implemented:
            return "IMPLEMENTED"
        return "UNKNOWN"


_registry: CollectorRegistry | None = None


def get_registry() -> CollectorRegistry:
    """Devolve o registo global, construindo-o à primeira utilização."""
    global _registry
    if _registry is None:
        _registry = CollectorRegistry()
        _build_registry(_registry)
    return _registry


def _build_registry(registry: CollectorRegistry) -> None:
    from monitor.collectors.caixa_imobiliario import CaixaImobiliarioCollector
    from monitor.collectors.citius import CitiusCollector
    from monitor.collectors.eleiloes import EleiloesCollector
    from monitor.collectors.financas import FinancasCollector
    from monitor.collectors.idealista import IdealistaCollector
    from monitor.collectors.imovirtual import ImovirtualCollector
    from monitor.collectors.leilon import LeilonCollector
    from monitor.collectors.leilosil import LeilosilCollector
    from monitor.collectors.leilosoc import LeilosocCollector
    from monitor.collectors.leiloversatil import LeiloversatilCollector
    from monitor.collectors.olx import OlxCollector

    # Fontes implementadas
    registry.register("citius", CitiusCollector, implemented=True)
    registry.register("leilosoc", LeilosocCollector, implemented=True)
    registry.register("leilon", LeilonCollector, implemented=True)

    # Fontes adiadas / a validar (ficam desativadas por configuração)
    registry.register("eleiloes", EleiloesCollector, implemented=False)
    registry.register("financas", FinancasCollector, implemented=False)
    registry.register("leilosil", LeilosilCollector, implemented=False)
    registry.register("leiloversatil", LeiloversatilCollector, implemented=False)
    registry.register("caixa_imobiliario", CaixaImobiliarioCollector, implemented=False)
    registry.register("imovirtual", ImovirtualCollector, implemented=False)
    registry.register("idealista", IdealistaCollector, implemented=False)
    registry.register("olx", OlxCollector, implemented=False)
