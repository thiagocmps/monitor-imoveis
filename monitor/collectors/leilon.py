"""Coletor LeilOn.

Fonte: https://www.leilon.pt
Leilões eletrónicos de imóveis. As páginas de listagem são renderizadas
no servidor; as de detalhe dos lotes também, embora possam apresentar
erros temporários (a tratar como falha isolada).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime

from bs4 import BeautifulSoup, Tag

from monitor.browser.network import fetch_html, tag_text
from monitor.collectors.base import BaseCollector, CollectorHealth
from monitor.models.raw import RawPropertyListing

logger = logging.getLogger(__name__)

BASE_URL = "https://www.leilon.pt"
LIST_URL = "https://www.leilon.pt/pt/auction/list/type/1?page={page}"

_DATE_RE = re.compile(
    r"DATA IN[ÍI]CIO\s*([\d/]+)\s*\(?\s*([\d:]+)?H?\s*\)?\s*\|\s*DATA FIM\s*"
    r"([\d/]+)\s*\(?\s*([\d:]+)?H?",
    re.IGNORECASE,
)


class LeilonCollector(BaseCollector):
    source_name = "leilon"

    async def search(self) -> list[RawPropertyListing]:
        settings = self.context.source_settings
        results: list[RawPropertyListing] = []
        for page in range(1, settings.maximum_pages + 1):
            url = LIST_URL.format(page=page)
            try:
                html, _status = await fetch_html(self.context.client, url)
            except Exception as exc:
                self.log(f"Falha ao obter página {page}: {exc}", logging.ERROR)
                raise
            self.context.record_page()
            soup = BeautifulSoup(html, "lxml")
            items = self._parse_listing_page(soup)
            results.extend(items)
            self.log("Página %d: %d lotes", page, len(items))
            if not items:
                break
            await self._delay()
        return results

    def _parse_listing_page(self, soup: BeautifulSoup) -> list[RawPropertyListing]:
        listings: list[RawPropertyListing] = []
        for card in soup.select("li.lot-list.lot"):
            listing = self._parse_lot_card(card)
            if listing:
                listings.append(listing)
        return listings

    def _parse_lot_card(self, card: Tag) -> RawPropertyListing | None:
        link = card.select_one(".title h2 a")
        if link is None:
            return None
        href = link.get("href") or ""
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        title = link.get_text(" ", strip=True) or None

        listing = RawPropertyListing(
            source=self.source_name,
            url=url,
            title=title,
            raw_data={"detail_fetch": True},
        )

        listing.source_listing_id = _lot_id_from_url(url)

        description_text = card.get_text(" ", strip=True)
        listing.auction_start_text, listing.auction_end_text, start_dt, end_dt = _parse_dates(
            description_text
        )
        listing.auction_start_at = start_dt
        listing.auction_end_at = end_dt

        location = tag_text(card, "p.district")
        listing.locality = location
        if location:
            listing.municipality = _guess_municipality(location)

        sale_type = tag_text(card, "p.type")
        if sale_type:
            listing.sale_method_text = sale_type

        value_text = tag_text(card, ".opening-value.info-content")
        if value_text:
            listing.base_value_text = value_text
            listing.minimum_value_text = value_text

        status_text = tag_text(card, ".lot-status .value")
        listing.listing_status_text = status_text
        return listing

    async def fetch_detail(self, listing: RawPropertyListing) -> RawPropertyListing:
        try:
            html, _status = await fetch_html(self.context.client, listing.url)
        except Exception as exc:
            self.log(f"Detalhe falhou para {listing.url}: {exc}", logging.WARNING)
            return listing
        self.context.record_page()
        if _is_error_page(html):
            self.log(
                "Página de detalhe com erro temporário: %s",
                listing.url,
                level=logging.WARNING,
            )
            listing.raw_data["detail_error"] = True
            return listing
        soup = BeautifulSoup(html, "lxml")
        listing.description = _extract_detail_description(soup) or listing.description
        listing.raw_data["detail_fetched"] = True
        return listing

    async def _delay(self) -> None:
        import asyncio

        await asyncio.sleep(self.context.source_settings.delay_seconds)

    async def health_check(self) -> CollectorHealth:
        try:
            html, status = await fetch_html(self.context.client, "https://www.leilon.pt")
        except Exception as exc:
            return CollectorHealth(self.source_name, False, message=str(exc))
        reachable = status == 200 and "leilon" in html.lower()
        return CollectorHealth(self.source_name, reachable, http_status=status)


def _lot_id_from_url(url: str) -> str | None:
    match = re.search(r"/(?:lot|view)/id/(\d+)", url)
    return match.group(1) if match else None


def _parse_dates(text: str) -> tuple[str | None, str | None, datetime | None, datetime | None]:
    match = _DATE_RE.search(text)
    if not match:
        return None, None, None, None
    start_text = match.group(1)
    end_text = match.group(3)
    start_dt = _parse_date(start_text)
    end_dt = _parse_date(end_text)
    return start_text, end_text, start_dt, end_dt


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value.strip(), "%d/%m/%Y")
    except ValueError:
        return None


def _guess_municipality(location: str) -> str | None:
    return location.strip()[:60] or None


def _is_error_page(html: str) -> bool:
    return "Fatal error" in html or "PDOException" in html or len(html) < 5000


def _extract_detail_description(soup: BeautifulSoup) -> str | None:
    selectors = [
        ".tab-content .description",
        "#descricao",
        ".block-info .description",
        ".description",
    ]
    for selector in selectors:
        tag = soup.select_one(selector)
        if tag:
            text = tag.get_text(" ", strip=True)
            if len(text) > 40:
                return text[:20_000]
    return None
