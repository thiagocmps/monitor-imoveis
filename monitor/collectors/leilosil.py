"""Coletor Leilosil.

Fonte: https://www.leilosil.pt
Leilões eletrónicos de imóveis. A listagem é HTML server-rendered com
cartões em ``ul.auction-grid.grid``. Os IDs numéricos dos lotes só estão
disponíveis nas páginas de detalhe (atributo ``data-lot-id``). Os preços
são obtidos via AJAX (``POST /pt/auction/get-list-info``) usando esses IDs.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from urllib.parse import urlencode

from bs4 import BeautifulSoup, Tag

from monitor.browser.network import build_headers, fetch_html
from monitor.collectors.base import BaseCollector, CollectorHealth
from monitor.models.raw import RawPropertyListing

logger = logging.getLogger(__name__)

BASE_URL = "https://www.leilosil.pt"
CATEGORY_URL = "https://www.leilosil.pt/pt/auction/category/id/5"
GET_LIST_INFO_URL = "https://www.leilosil.pt/pt/auction/get-list-info"

_DATE_RE = re.compile(r"Termina a (\d{2}/\d{2}/\d{4})\s+(\d{2}:\d{2})")
_LOT_ID_RE = re.compile(r'data-lot-id="(\d+)"')
_AREA_RE = re.compile(r"Área Total:\s*([\d.,]+)\s*m2?", re.IGNORECASE)
_CONCELHO_RE = re.compile(r"Concelho:\s*(.+)", re.IGNORECASE)


class LeilosilCollector(BaseCollector):
    source_name = "leilosil"

    async def search(self) -> list[RawPropertyListing]:
        settings = self.context.source_settings
        results: list[RawPropertyListing] = []

        for page in range(1, settings.maximum_pages + 1):
            url = f"{CATEGORY_URL}?page={page}&v=c"
            try:
                html, _status = await fetch_html(self.context.client, url)
            except Exception as exc:
                self.log("Falha ao obter página %d: %s", page, exc, level=logging.ERROR)
                break
            self.context.record_page()
            soup = BeautifulSoup(html, "lxml")
            items = self._parse_listing_page(soup)
            results.extend(items)
            self.log("Página %d: %d lotes", page, len(items))
            if not items:
                break
            await self._delay()

        for listing in results:
            await self.fetch_detail(listing)
            await self._delay()

        numeric_ids = [
            listing.source_listing_id
            for listing in results
            if listing.source_listing_id and listing.source_listing_id.isdigit()
        ]
        if numeric_ids:
            await self._fetch_prices(numeric_ids, results)

        return results

    def _parse_listing_page(self, soup: BeautifulSoup) -> list[RawPropertyListing]:
        listings: list[RawPropertyListing] = []
        for li in soup.select("ul.auction-grid.grid > li"):
            listing = self._parse_card(li)
            if listing:
                listings.append(listing)
        return listings

    def _parse_card(self, card: Tag) -> RawPropertyListing | None:
        title_link = card.select_one(".title h2 a")
        if title_link is None:
            return None
        href = title_link.get("href") or ""
        url = href if href.startswith("http") else f"{BASE_URL}{href}"
        title = title_link.get_text(" ", strip=True) or None

        image_tag = card.select_one(".image img")
        image_url = image_tag.get("src") if image_tag else None
        if image_url and not image_url.startswith("http"):
            image_url = f"{BASE_URL}/{image_url.lstrip('/')}"

        end_text = None
        end_dt = None
        date_p = card.select_one(".date-count p")
        if date_p:
            end_text = date_p.get_text(strip=True)
            m = _DATE_RE.search(end_text)
            if m:
                end_dt = _parse_datetime(m.group(1), m.group(2))

        return RawPropertyListing(
            source=self.source_name,
            url=url,
            title=title,
            auction_end_text=end_text,
            auction_end_at=end_dt,
            main_image_url=image_url,
        )

    async def fetch_detail(self, listing: RawPropertyListing) -> RawPropertyListing:
        try:
            html, _status = await fetch_html(self.context.client, listing.url)
        except Exception as exc:
            self.log("Detalhe falhou para %s: %s", listing.url, exc, level=logging.WARNING)
            return listing
        self.context.record_page()

        m = _LOT_ID_RE.search(html)
        if m:
            listing.source_listing_id = m.group(1)

        soup = BeautifulSoup(html, "lxml")
        desc_tag = soup.select_one(".tab-content.description .description")
        if desc_tag:
            text = desc_tag.get_text(" ", strip=True)
            if len(text) > 40:
                listing.description = text[:20_000]

        details_tag = soup.select_one(".tab-content.lot-details .detais")
        if details_tag:
            for p in details_tag.find_all("p"):
                ptext = p.get_text(strip=True)
                am = _AREA_RE.search(ptext)
                if am:
                    listing.usable_area_text = am.group(0)
                    listing.usable_area_m2 = _safe_float(am.group(1).replace(",", "."))
                cm = _CONCELHO_RE.search(ptext)
                if cm:
                    listing.municipality = cm.group(1).strip()

        return listing

    async def _fetch_prices(
        self,
        lot_ids: list[str],
        listings: list[RawPropertyListing],
    ) -> None:
        listing_map = {
            lst.source_listing_id: lst
            for lst in listings
            if lst.source_listing_id and lst.source_listing_id.isdigit()
        }
        try:
            form_data = [("lot_ids[]", lid) for lid in lot_ids]
            resp = await self.context.client.post(
                GET_LIST_INFO_URL,
                content=urlencode(form_data),
                headers=build_headers({
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-Requested-With": "XMLHttpRequest",
                    "Referer": CATEGORY_URL,
                }),
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            self.log("Falha ao obter preços via AJAX: %s", exc, level=logging.WARNING)
            return
        self.context.record_page()

        lots = data.get("lots", {})
        if isinstance(lots, list):
            lot_items = lots
        elif isinstance(lots, dict):
            lot_items = list(lots.values())
        else:
            lot_items = []
        for lot_info in lot_items:
            lid = str(lot_info.get("id", ""))
            listing = listing_map.get(lid)
            if listing is None:
                continue
            currency = lot_info.get("currency_symbol") or "€"
            listing.currency = currency

            base = _safe_float(lot_info.get("base_amount"))
            if base is not None:
                listing.base_value = base
                listing.base_value_text = lot_info.get("base_amount_formated")

            reserve = _safe_float(lot_info.get("reserve_amount"))
            if reserve is not None:
                listing.minimum_value = reserve
                listing.minimum_value_text = lot_info.get("reserve_amount_formated")

            current = _safe_float(lot_info.get("complete_amount"))
            if current is not None:
                listing.price_value = current
                listing.price_text = lot_info.get("complete_amount_formated")

            status = lot_info.get("status")
            listing.listing_status_text = lot_info.get("status_label") or status

            secs_end = lot_info.get("seconds_to_end")
            if secs_end is not None and secs_end > 0:
                now_ts = datetime.now(UTC).timestamp()
                listing.auction_end_at = datetime.fromtimestamp(
                    now_ts + secs_end, tz=UTC
                )

    async def _delay(self) -> None:
        import asyncio

        await asyncio.sleep(self.context.source_settings.delay_seconds)

    async def health_check(self) -> CollectorHealth:
        try:
            html, status = await fetch_html(self.context.client, BASE_URL)
        except Exception as exc:
            return CollectorHealth(self.source_name, False, message=str(exc))
        reachable = status == 200 and "leilosil" in html.lower()
        return CollectorHealth(self.source_name, reachable, http_status=status)


def _lot_id_from_url(url: str) -> str | None:
    match = re.search(r"/leiloes/[^/]+/([^/]+?)(?:-(\d+))?(?:/|$)", url)
    if match:
        return match.group(2) or match.group(1)
    match = re.search(r"/lot/(\d+)", url)
    return match.group(1) if match else None


def _parse_datetime(date_str: str, time_str: str) -> datetime | None:
    try:
        return datetime.strptime(f"{date_str} {time_str}", "%d/%m/%Y %H:%M")
    except ValueError:
        return None


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
