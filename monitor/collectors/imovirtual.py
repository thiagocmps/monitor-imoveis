"""Coletor Imovirtual.

Fonte: https://www.imovirtual.com
Portal de imobiliárias e particulares. A listagem é uma aplicação Next.js
com dados estruturados completos no blob ``__NEXT_DATA__`` (GraphQL
``AdvertListItem``). O scraping usa esse blob, sem depender de classes CSS
instáveis. Suporta filtro por imóveis em leilão.
"""

from __future__ import annotations

import json
import logging
import re

from monitor.browser.network import fetch_html
from monitor.collectors.base import BaseCollector, CollectorHealth
from monitor.models.raw import RawPropertyListing

logger = logging.getLogger(__name__)

BASE_URL = "https://www.imovirtual.com"
LIST_URL = (
    "https://www.imovirtual.com/pt/resultados/comprar/"
    "apartamento,moradia,leilao/todo-o-pais?page={page}"
)

_NEXT_DATA_RE = re.compile(
    r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL
)

_ROOMS_MAP = {
    "ONE": 1,
    "TWO": 2,
    "THREE": 3,
    "FOUR": 4,
    "FIVE": 5,
    "SIX": 6,
    "SEVEN": 7,
    "EIGHT": 8,
}

_ESTATE_TYPE_MAP = {
    "FLAT": "APARTMENT",
    "HOUSE": "HOUSE",
    "PLOT": "LAND",
    "GARAGE": "COMMERCIAL",
    "PREMISES": "COMMERCIAL",
    "ROOM": "OTHER",
}


class ImovirtualCollector(BaseCollector):
    source_name = "imovirtual"

    async def search(self) -> list[RawPropertyListing]:
        settings = self.context.source_settings
        results: list[RawPropertyListing] = []
        for page in range(1, settings.maximum_pages + 1):
            url = LIST_URL.format(page=page)
            try:
                html, _status = await fetch_html(self.context.client, url)
            except Exception as exc:
                self.log("Falha ao obter página %d: %s", page, exc, level=logging.ERROR)
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
            self.log(
                "Bloco __NEXT_DATA__ não encontrado (página %d)",
                page,
                level=logging.WARNING,
            )
            return []
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            self.log("JSON __NEXT_DATA__ inválido: %s", exc, level=logging.WARNING)
            return []

        page_data = (
            data.get("props", {})
            .get("pageProps", {})
            .get("data", {})
        )
        search_ads = page_data.get("searchAds") or {}
        items = search_ads.get("items") or []
        listings: list[RawPropertyListing] = []
        for node in items:
            listing = self._from_node(node)
            if listing:
                listings.append(listing)
        return listings

    def _from_node(self, node: dict) -> RawPropertyListing | None:
        ad_id = node.get("id")
        slug = node.get("slug")
        if not ad_id or not slug:
            return None

        url = f"{BASE_URL}/pt/anuncio/{slug}"

        price_obj = node.get("totalPrice") or {}
        price_value = price_obj.get("value")
        currency = price_obj.get("currency") or "€"
        if currency == "EUR":
            currency = "€"

        area = node.get("areaInSquareMeters")
        terrain = node.get("terrainAreaInSquareMeters")

        estate_type = node.get("estate")
        property_type = _ESTATE_TYPE_MAP.get(str(estate_type)) if estate_type else None

        rooms_str = node.get("roomsNumber")
        bedrooms = _ROOMS_MAP.get(str(rooms_str)) if rooms_str else None

        floor_str = node.get("floorNumber")

        location = node.get("location") or {}
        address = location.get("address") or {}
        city_obj = address.get("city") or {}
        province_obj = address.get("province") or {}
        street_obj = address.get("street") or {}

        municipality = province_obj.get("name") or city_obj.get("name")
        district = province_obj.get("name")
        street = street_obj.get("name")

        images = node.get("images") or []
        main_image = None
        if images:
            first = images[0]
            main_image = first.get("medium") or first.get("large")

        tags = node.get("tags") or []
        tag_values = {t.get("value") for t in tags if isinstance(t, dict)}

        listing = RawPropertyListing(
            source=self.source_name,
            url=url,
            source_reference=str(ad_id),
            source_listing_id=str(ad_id),
            title=node.get("title"),
            description=node.get("shortDescription"),
            property_type=property_type,
            price_value=price_value,
            currency=currency,
            usable_area_m2=area,
            total_area_m2=terrain or area,
            district=district,
            municipality=municipality,
            address=street,
            bedrooms=bedrooms,
            floor=floor_str,
            main_image_url=main_image,
            listing_status_text=node.get("transaction"),
            has_garage="PARKING_SPOT" in tag_values or "GARAGE" in tag_values,
            has_balcony="BALCONY" in tag_values,
            has_terrace="TERRACE" in tag_values,
            has_garden="GARDEN" in tag_values,
        )
        return listing

    async def fetch_detail(self, listing: RawPropertyListing) -> RawPropertyListing:
        return listing

    async def _delay(self) -> None:
        import asyncio

        await asyncio.sleep(self.context.source_settings.delay_seconds)

    async def health_check(self) -> CollectorHealth:
        try:
            html, status = await fetch_html(self.context.client, BASE_URL)
        except Exception as exc:
            return CollectorHealth(self.source_name, False, message=str(exc))
        reachable = status == 200 and "imovirtual" in html.lower()
        return CollectorHealth(self.source_name, reachable, http_status=status)
