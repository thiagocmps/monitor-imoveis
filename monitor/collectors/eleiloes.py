"""Coletor e-leilões (adiado)."""

from __future__ import annotations

import logging

from monitor.collectors.base import BaseCollector
from monitor.exceptions import CollectorNotImplementedError
from monitor.models.raw import RawPropertyListing

logger = logging.getLogger(__name__)


class EleiloesCollector(BaseCollector):
    source_name = "eleiloes"
    uses_javascript = True

    async def search(self) -> list[RawPropertyListing]:
        raise CollectorNotImplementedError(self.source_name)
