"""Coletor Leilosoc.

Fonte: https://www.leilosoc.com
A listagem de imóveis é uma aplicação Next.js que inclui um blob
`__NEXT_DATA__` com dados estruturados completos por lote (título,
preços, coordenadas, datas, estado, descrição). A recolha usa esse blob,
sem depender de classes CSS instáveis. A página de detalhe não é
necessária porque a listagem já contém os dados.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime

from monitor.browser.network import fetch_html
from monitor.collectors.base import BaseCollector, CollectorHealth
from monitor.models.raw import RawPropertyListing

logger = logging.getLogger(__name__)

BASE_URL = "https://leilosoc.com"
CATEGORY_URL = "https://leilosoc.com/pt-PT/category/5-imoveis/?page={page}"

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)


class LeilosocCollector(BaseCollector):
    source_name = "leilosoc"

    async def search(self) -> list[RawPropertyListing]:
        settings = self.context.source_settings
        results: list[RawPropertyListing] = []
        for page in range(1, settings.maximum_pages + 1):
            url = CATEGORY_URL.format(page=page)
            try:
                html, _status = await fetch_html(self.context.client, url)
            except Exception as exc:
                self.log(f"Falha ao obter página {page}: {exc}", logging.ERROR)
                raise
            self.context.record_page()
            items = self._parse_page(html, page)
            results.extend(items)
            self.log("Página %d: %d imóveis", page, len(items))
            if not items:
                break
            await self._delay()
        return results

    def _parse_page(self, html: str, page: int) -> list[RawPropertyListing]:
        match = _NEXT_DATA_RE.search(html)
        if not match:
            self.log("Bloco __NEXT_DATA__ não encontrado (página %d)", page, level=logging.WARNING)
            return []
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            self.log("JSON __NEXT_DATA__ inválido: %s", exc, level=logging.WARNING)
            return []
        lots = data.get("props", {}).get("pageProps", {}).get("lots", {})
        items = lots.get("items") or []
        listings: list[RawPropertyListing] = []
        for item in items:
            listing = self._from_json_item(item)
            if listing:
                listings.append(listing)
        return listings

    def _from_json_item(self, item: dict) -> RawPropertyListing | None:
        auction_id = item.get("auctionId")
        batch_id = item.get("batchId")
        if not auction_id or not batch_id:
            return None
        url = f"{BASE_URL}/pt-PT/lot/{auction_id}/{batch_id}"
        if item.get("title"):
            slug = _slug(item["title"])
            url = f"{url}-{slug}/"

        coords = item.get("coordinates") or {}
        listing = RawPropertyListing(
            source=self.source_name,
            url=url,
            source_reference=str(item.get("reference")) if item.get("reference") else None,
            source_listing_id=str(batch_id),
            lot_number=str(item.get("number")) if item.get("number") else None,
            title=item.get("title"),
            description=_strip_html(item.get("description")),
            price_value=item.get("valueMinimum") or item.get("valueBase") or item.get("valueOpen"),
            price_text=item.get("valueMinimum") is not None
            and _format_price(item.get("valueMinimum"))
            or None,
            base_value=item.get("valueBase"),
            minimum_value=item.get("valueMinimum"),
            tax_value=item.get("realStateTaxFree"),
            currency=item.get("currencySymbol") or "€",
            district=item.get("addressLocation"),
            municipality=item.get("addressLocation"),
            address=item.get("address"),
            postal_code=item.get("addressZipCode"),
            latitude=coords.get("latitude"),
            longitude=coords.get("longitude"),
            auction_start_at=_parse_iso(item.get("auctionStartDate")),
            auction_end_at=_parse_iso(item.get("auctionEndDate")),
            legal_process=str(item.get("processNumber")) if item.get("processNumber") else None,
            main_image_url=item.get("pictureDefault"),
            listing_status_text=item.get("batchStatus"),
            raw_data=item,
        )
        return listing

    async def fetch_detail(self, listing: RawPropertyListing) -> RawPropertyListing:
        # A listagem __NEXT_DATA__ já contém todos os dados essenciais.
        return listing

    async def _delay(self) -> None:
        import asyncio

        await asyncio.sleep(self.context.source_settings.delay_seconds)

    async def health_check(self) -> CollectorHealth:
        try:
            html, status = await fetch_html(self.context.client, BASE_URL)
        except Exception as exc:
            return CollectorHealth(self.source_name, False, message=str(exc))
        reachable = status == 200 and "leilosoc" in html.lower()
        return CollectorHealth(self.source_name, reachable, http_status=status)


def _strip_html(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", text).strip() or None


def _format_price(value) -> str | None:
    if value is None:
        return None
    try:
        return f"{float(value):,.2f} €"
    except (TypeError, ValueError):
        return str(value)


def _parse_iso(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def _slug(title: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\s-]", "", title).strip().lower()
    slug = re.sub(r"\s+", "-", slug)
    return slug[:80]
