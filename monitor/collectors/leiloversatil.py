"""Coletor Leiloversatil.

Fonte: https://www.leiloversatil.pt
Leilões de imóveis com listagem HTML server-rendered. Cada cartão contém
título, descrição, tipo de venda, valor mínimo e timestamp de fim. Os
preços atuais (lances) são obtidos via endpoint JSON dedicado.
A listagem não tem paginação — todos os imóveis aparecem numa só página.
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

BASE_URL = "https://www.leiloversatil.pt"
LIST_URL = "https://www.leiloversatil.pt/"
AJAX_LOTE_URL = "https://www.leiloversatil.pt/service/index.php"

_LOT_RE = re.compile(r"leilao=(\d+)&venda=(\d+)&tipo=(\d+)")
_PRICE_RE = re.compile(r"([\d.]+,\d{2})\s*€")
_TIMESTAMP_RE = re.compile(r"var lasttime = (\d+);")
_END_TIMESTAMP_RE = re.compile(r"var terminovenda = new Date\((\d+)\)")
_CONCELHO_RE = re.compile(r"concelho de\s+(.+?)[,.]")


class LeiloversatilCollector(BaseCollector):
    source_name = "leiloversatil"

    async def search(self) -> list[RawPropertyListing]:
        settings = self.context.source_settings
        results: list[RawPropertyListing] = []

        for page in range(1, settings.maximum_pages + 1):
            params = {
                "chkimoveis": "I",
                "q": "",
                "price_from": "0",
                "price_to": str(int(settings.maximum_pages * 500000)),
                "order_by": "ending_soonest",
            }
            if page > 1:
                params["offset"] = str((page - 1) * 20)
            url = f"{LIST_URL}?{urlencode(params)}"
            try:
                html, _status = await fetch_html(self.context.client, url)
            except Exception as exc:
                self.log("Falha ao obter página %d: %s", page, exc, level=logging.ERROR)
                raise
            self.context.record_page()
            soup = BeautifulSoup(html, "lxml")
            items = self._parse_page(soup)
            results.extend(items)
            self.log("Página %d: %d lotes", page, len(items))
            if not items:
                break
            await self._delay()

        await self._fetch_current_prices(results)
        return results

    def _parse_page(self, soup: BeautifulSoup) -> list[RawPropertyListing]:
        listings: list[RawPropertyListing] = []
        for card in soup.select("div.home_block_advert"):
            listing = self._parse_card(card)
            if listing:
                listings.append(listing)
        return listings

    def _parse_card(self, card: Tag) -> RawPropertyListing | None:
        title_tag = card.select_one("h1")
        if title_tag is None:
            return None
        title = title_tag.get_text(" ", strip=True) or None

        link_tag = card.select_one("a[href*='page=leilao']")
        if link_tag is None:
            link_tag = card.select_one(".span3 a")
        if link_tag is None:
            return None
        href = link_tag.get("href") or ""
        url = href if href.startswith("http") else f"{BASE_URL}/{href.lstrip('./')}"

        lot_id, venda_id, tipo = _parse_lot_ids(url)
        if not lot_id or not venda_id:
            return None

        description_tag = card.select_one("p.texto_lote")
        description = description_tag.get_text(" ", strip=True) if description_tag else None

        sale_type_tag = card.select_one("p.tipo_leilao")
        sale_method = sale_type_tag.get_text(strip=True) if sale_type_tag else None

        image_tag = card.select_one(".span3 img")
        image_url = image_tag.get("src") if image_tag else None
        if image_url and not image_url.startswith("http"):
            image_url = f"{BASE_URL}/{image_url.lstrip('/')}"

        min_value = None
        min_value_text = None
        price_tag = card.select_one(".infobox_valorbase p")
        if price_tag:
            min_value_text = price_tag.get_text(strip=True)
            pm = _PRICE_RE.search(min_value_text)
            if pm:
                min_value = _parse_euro(pm.group(1))

        listing = RawPropertyListing(
            source=self.source_name,
            url=url,
            title=title,
            source_listing_id=str(lot_id),
            description=description,
            sale_method_text=sale_method,
            minimum_value=min_value,
            minimum_value_text=min_value_text,
            main_image_url=image_url,
            raw_data={"venda_id": venda_id, "tipo": tipo},
        )

        if description:
            cm = _CONCELHO_RE.search(description)
            if cm:
                listing.municipality = cm.group(1).strip()

        end_dt = _extract_end_timestamp(card)
        if end_dt:
            listing.auction_end_at = end_dt

        return listing

    async def _fetch_current_prices(self, listings: list[RawPropertyListing]) -> None:
        for listing in listings:
            venda_id = listing.raw_data.get("venda_id")
            lot_id = listing.source_listing_id
            if not venda_id or not lot_id:
                continue
            try:
                params = {
                    "d": "servico",
                    "c": "lotes",
                    "m": "getlote",
                    "venda": str(venda_id),
                    "lote": str(lot_id),
                }
                resp = await self.context.client.get(
                    AJAX_LOTE_URL,
                    params=params,
                    headers=build_headers({"X-Requested-With": "XMLHttpRequest"}),
                )
                resp.raise_for_status()
                data = resp.json()
                self.context.record_page()
                detalhes = data.get("detalhes") or data
                valor = detalhes.get("valoractual") or detalhes.get("valorActual")
                if valor and str(valor) != "0.00":
                    listing.price_text = str(valor)
                    listing.price_value = _safe_float(valor)
                liquidacao = detalhes.get("liquidacao")
                if liquidacao and str(liquidacao) != "0.00":
                    listing.minimum_value = _safe_float(liquidacao)
                    listing.minimum_value_text = f"{liquidacao} €"
                listing.currency = "€"
                loc = detalhes.get("localizacao")
                if loc and not listing.municipality:
                    listing.address = str(loc).strip()
                concelho = detalhes.get("concelhoconservatoria")
                if concelho and not listing.municipality:
                    listing.municipality = str(concelho).strip()
                desc = detalhes.get("DescLote")
                if desc and not listing.description:
                    listing.description = str(desc).strip()[:20_000]
            except Exception as exc:
                self.log(
                    "AJAX preço falhou para lote %s: %s", lot_id, exc, level=logging.WARNING
                )
            await self._delay()

    async def _delay(self) -> None:
        import asyncio

        await asyncio.sleep(self.context.source_settings.delay_seconds)

    async def health_check(self) -> CollectorHealth:
        try:
            html, status = await fetch_html(self.context.client, BASE_URL)
        except Exception as exc:
            return CollectorHealth(self.source_name, False, message=str(exc))
        reachable = status == 200 and "leiloversatil" in html.lower()
        return CollectorHealth(self.source_name, reachable, http_status=status)


def _parse_lot_ids(url: str) -> tuple[str | None, str | None, str | None]:
    m = _LOT_RE.search(url)
    if m:
        return m.group(1), m.group(2), m.group(3)
    return None, None, None


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_euro(value: str) -> float | None:
    try:
        return float(value.replace(".", "").replace(",", "."))
    except (ValueError, AttributeError):
        return None


def _extract_end_timestamp(card: Tag) -> datetime | None:
    for script in card.find_all("script"):
        text = script.string or ""
        m = _END_TIMESTAMP_RE.search(text)
        if m:
            ts_ms = int(m.group(1))
            return datetime.fromtimestamp(ts_ms / 1000, tz=UTC)
    return None
