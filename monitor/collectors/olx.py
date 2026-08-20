"""Coletor OLX.

Fonte: https://www.olx.pt
Portal de anúncios classificados. O OLX implementa proteção anti-bot
agressiva que bloqueia pedidos HTTP diretos (403). Este coletor usa
Playwright (browser real) para aceder à página de resultados e extrair
os dados dos anúncios. Muitos resultados de imóveis em leilão redirecionam
para o Imovirtual (mesma empresa).
"""

from __future__ import annotations

import contextlib
import logging
import re

from bs4 import BeautifulSoup

from monitor.browser.manager import BrowserManager
from monitor.collectors.base import BaseCollector, CollectorHealth
from monitor.models.raw import RawPropertyListing

logger = logging.getLogger(__name__)

BASE_URL = "https://www.olx.pt"
SEARCH_URL = "https://www.olx.pt/imoveis/q-leilao/"

_AREA_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*m²")
_ROOMS_RE = re.compile(r"(\d+)\s*(?:quarto|T(\d))", re.IGNORECASE)


class OlxCollector(BaseCollector):
    source_name = "olx"
    uses_javascript = True

    async def search(self) -> list[RawPropertyListing]:
        settings = self.context.source_settings
        browser_settings = self.context.settings.browser
        results: list[RawPropertyListing] = []

        async with BrowserManager(browser_settings) as browser:
            page = browser.page
            for pg in range(1, settings.maximum_pages + 1):
                url = f"{SEARCH_URL}?page={pg}"
                try:
                    await page.goto(url, timeout=browser_settings.navigation_timeout_seconds * 1000)
                    await page.wait_for_selector("[data-cy='l-card'], .css-1sw7q4x", timeout=15000)
                except Exception as exc:
                    self.log(
                        "Falha ao carregar página %d: %s", pg, exc, level=logging.WARNING
                    )
                    break
                self.context.record_page()

                html = await page.content()
                items = self._parse_page(html)
                results.extend(items)
                self.log("Página %d: %d imóveis", pg, len(items))
                if not items:
                    break
                await self._delay()

        return results

    def _parse_page(self, html: str) -> list[RawPropertyListing]:
        soup = BeautifulSoup(html, "lxml")
        listings: list[RawPropertyListing] = []
        for card in soup.select("[data-cy='l-card']"):
            listing = self._parse_card(card)
            if listing:
                listings.append(listing)
        return listings

    def _parse_card(self, card) -> RawPropertyListing | None:
        link = card.select_one("a[href*='/d/']")
        if link is None:
            link = card.select_one("a")
        if link is None:
            return None
        href = link.get("href") or ""
        url = href if href.startswith("http") else f"{BASE_URL}{href}"

        title_tag = card.select_one("[data-cy='card-title'] h4, h6, h4")
        title = title_tag.get_text(strip=True) if title_tag else None
        if not title:
            return None

        ad_id = _extract_ad_id(url)

        price_tag = card.select_one("[data-cy='ad-price'], p[data-testid='ad-price']")
        price_text = price_tag.get_text(strip=True) if price_tag else None
        price_value = _parse_price_text(price_text)

        location_tag = card.select_one("[data-cy='card-location'], p[data-testid='location-date']")
        location_text = location_tag.get_text(strip=True) if location_tag else None

        img_tag = card.select_one("img[src]")
        image_url = img_tag.get("src") if img_tag else None

        desc_tag = card.select_one("[data-cy='l-card'] + div p, div.css-1mwdrlh p")
        description = desc_tag.get_text(strip=True) if desc_tag else None

        listing = RawPropertyListing(
            source=self.source_name,
            url=url,
            source_reference=ad_id,
            source_listing_id=ad_id,
            title=title,
            description=description,
            price_value=price_value,
            price_text=price_text,
            currency="€",
            main_image_url=image_url,
        )

        if location_text:
            parts = [p.strip() for p in location_text.split(",")]
            if len(parts) >= 2:
                listing.municipality = parts[-2] if len(parts) > 1 else parts[0]
                listing.district = parts[-1] if len(parts) > 2 else None
            elif parts:
                listing.municipality = parts[0]

        if description:
            _enrich_from_description(listing, description)

        return listing

    async def fetch_detail(self, listing: RawPropertyListing) -> RawPropertyListing:
        return listing

    async def _delay(self) -> None:
        import asyncio

        await asyncio.sleep(self.context.source_settings.delay_seconds)

    async def health_check(self) -> CollectorHealth:
        browser_settings = self.context.settings.browser
        try:
            async with BrowserManager(browser_settings) as browser:
                await browser.page.goto(BASE_URL, timeout=20000)
                html = await browser.page.content()
                reachable = "olx" in html.lower()
                return CollectorHealth(self.source_name, reachable)
        except Exception as exc:
            return CollectorHealth(self.source_name, False, message=str(exc))


def _extract_ad_id(url: str) -> str | None:
    m = re.search(r"[-/](\d+)(?:\.html|$)", url)
    return m.group(1) if m else None


def _parse_price_text(text: str | None) -> float | None:
    if not text:
        return None
    cleaned = text.replace("€", "").replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return None


def _enrich_from_description(listing: RawPropertyListing, description: str) -> None:
    if listing.usable_area_m2 is None:
        am = _AREA_RE.search(description)
        if am:
            listing.usable_area_text = am.group(0)
            with contextlib.suppress(ValueError, TypeError):
                listing.usable_area_m2 = float(am.group(1).replace(",", "."))

    if listing.bedrooms is None:
        rm = _ROOMS_RE.search(description)
        if rm:
            if rm.group(2):
                listing.bedrooms = int(rm.group(2))
            elif rm.group(1):
                listing.bedrooms = int(rm.group(1))
