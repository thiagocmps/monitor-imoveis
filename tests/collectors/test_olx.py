"""Testes do coletor OLX (helpers sem browser)."""

from __future__ import annotations

from unittest.mock import MagicMock

from bs4 import BeautifulSoup
from monitor.collectors.olx import (
    OlxCollector,
    _enrich_from_description,
    _extract_ad_id,
    _parse_price_text,
)

HTML_CARD = """
<div data-cy="l-card">
  <a href="/d/imoveis/apartamento-t1-99999.html">
    <img src="https://img.example.com/photo.jpg"/>
  </a>
  <h4>Apartamento T1 em Leilão</h4>
  <p data-cy="ad-price">75 000 €</p>
  <p data-cy="card-location">Porto, Porto</p>
</div>
"""

HTML_CARD_MINIMAL = """
<div data-cy="l-card">
  <a href="/d/imoveis/casa-1.html">
    <img/>
  </a>
  <h4>Test</h4>
</div>
"""


def test_parse_card_basic() -> None:
    soup = BeautifulSoup(HTML_CARD, "lxml")
    card = soup.select_one("[data-cy='l-card']")
    collector = _make_collector()
    listing = collector._parse_card(card)
    assert listing is not None
    assert listing.source_reference == "99999"
    assert listing.title == "Apartamento T1 em Leilão"
    assert listing.price_value == 75000.0
    assert listing.municipality == "Porto"
    assert listing.main_image_url == "https://img.example.com/photo.jpg"


def test_parse_card_minimal() -> None:
    soup = BeautifulSoup(HTML_CARD_MINIMAL, "lxml")
    card = soup.select_one("[data-cy='l-card']")
    collector = _make_collector()
    listing = collector._parse_card(card)
    assert listing is not None
    assert listing.source_reference == "1"
    assert listing.price_value is None


def test_extract_ad_id() -> None:
    assert _extract_ad_id("https://www.olx.pt/d/imoveis/casa-123.html") == "123"
    assert _extract_ad_id("https://www.olx.pt/d/imoveis/casa/456") == "456"
    assert _extract_ad_id("https://www.olx.pt/imoveis/q-leilao/") is None


def test_parse_price_text() -> None:
    assert _parse_price_text("75 000 €") == 75000.0
    assert _parse_price_text("1 250,50 €") == 1250.5
    assert _parse_price_text("Sob consulta") is None
    assert _parse_price_text(None) is None


def test_enrich_from_description_area() -> None:
    listing = MagicMock()
    listing.usable_area_m2 = None
    listing.bedrooms = None
    _enrich_from_description(listing, "Imóvel com 85,5 m² de área útil.")
    assert listing.usable_area_m2 == 85.5
    assert listing.usable_area_text == "85,5 m²"


def test_enrich_from_description_rooms_t() -> None:
    listing = MagicMock()
    listing.usable_area_m2 = None
    listing.bedrooms = None
    _enrich_from_description(listing, "Apartamento T3 com 3 quartos.")
    assert listing.bedrooms == 3


def test_enrich_from_description_rooms_number() -> None:
    listing = MagicMock()
    listing.usable_area_m2 = None
    listing.bedrooms = None
    _enrich_from_description(listing, "Moradia com 4 quartos.")
    assert listing.bedrooms == 4


def _make_collector() -> OlxCollector:
    context = MagicMock()
    context.source_settings = MagicMock()
    context.source_settings.delay_seconds = 0
    context.source_settings.maximum_pages = 1
    return OlxCollector(context)
