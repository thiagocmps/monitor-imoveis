"""Base para coletores e contexto de recolha."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import httpx

from monitor.models.raw import RawPropertyListing

if TYPE_CHECKING:
    from monitor.browser.manager import BrowserManager


@dataclass
class CollectorHealth:
    source: str
    reachable: bool
    message: str = ""
    http_status: int | None = None


@dataclass
class CollectorContext:
    """Contexto partilhado por um coletor durante uma execução."""

    source: str
    settings: object
    client: httpx.AsyncClient
    browser: BrowserManager | None = None
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("collector"))
    pages_visited: int = 0

    def record_page(self) -> None:
        self.pages_visited += 1

    @property
    def source_settings(self):
        return self.settings.source_settings(self.source)


class BaseCollector(ABC):
    """Contrato comum a todos os coletores."""

    source_name: str = ""
    uses_javascript: bool = False

    def __init__(self, context: CollectorContext) -> None:
        if not self.source_name:
            raise ValueError("source_name deve ser definido no coletor")
        self.context = context

    @abstractmethod
    async def search(self) -> list[RawPropertyListing]:
        """Pesquisa e devolve os anúncios encontrados (dados brutos)."""

    async def fetch_detail(self, listing: RawPropertyListing) -> RawPropertyListing:
        """Preenche detalhes adicionais quando necessário."""
        return listing

    async def health_check(self) -> CollectorHealth:
        """Verificação ligeira da disponibilidade da fonte."""
        return CollectorHealth(source=self.source_name, reachable=True)

    def log(self, message: str, *args: object, level: int = logging.INFO) -> None:
        if args:
            message = message % args
        self.context.logger.log(level, "[%s] %s", self.source_name, message)
