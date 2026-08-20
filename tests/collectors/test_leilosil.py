"""Testes do coletor Leilosil (helpers sem browser)."""

from __future__ import annotations

from bs4 import BeautifulSoup
from monitor.collectors.leilosil import (
    LeilosilCollector,
    _lot_id_from_url,
    _parse_datetime,
    _safe_float,
)


def test_lot_id_from_url_with_slug_and_id() -> None:
    url = "https://www.leilosil.pt/pt/leiloes/apartamento-t1-1-na-cidade-da-maia/apartamento-t1-1-na-cidade-da-maia-12345"
    assert _lot_id_from_url(url) == "12345"


def test_lot_id_from_url_with_lot_pattern() -> None:
    url = "https://www.leilosil.pt/pt/lot/9999"
    assert _lot_id_from_url(url) == "9999"


def test_lot_id_from_url_returns_none_for_unknown() -> None:
    assert _lot_id_from_url("https://example.com/other") is None


def test_parse_datetime_valid() -> None:
    dt = _parse_datetime("18/09/2026", "10:00")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 9
    assert dt.day == 18
    assert dt.hour == 10
    assert dt.minute == 0


def test_parse_datetime_invalid() -> None:
    assert _parse_datetime("invalid", "time") is None


def test_safe_float_valid() -> None:
    assert _safe_float(1234.5) == 1234.5
    assert _safe_float("67890") == 67890.0
    assert _safe_float(0) == 0.0


def test_safe_float_none() -> None:
    assert _safe_float(None) is None


def test_safe_float_invalid() -> None:
    assert _safe_float("not-a-number") is None


def test_parse_card_extracts_title_and_url() -> None:
    base = "https://www.leilosil.pt"
    path = "/pt/leiloes/apartamento-t1/apartamento-t1"
    html = f"""
    <li>
        <div class="image">
            <a class="img" href="{base}{path}">
                <img src="{base}/media/img.jpg" alt="Apartamento T1" />
            </a>
        </div>
        <div class="content">
            <div class="count-lots"><p>1 Lote</p></div>
            <div class="title">
                <h2><a href="{base}{path}">Apartamento T1 | Porto</a></h2>
            </div>
            <div class="date-count">
                <p>Termina a 01/12/2026 01:01</p>
            </div>
            <div class="actions">
                <a href="{base}{path}" class="button1">Ver Lotes</a>
            </div>
        </div>
    </li>
    """
    soup = BeautifulSoup(html, "lxml")
    card = soup.find("li")
    collector = _make_collector()
    listing = collector._parse_card(card)
    assert listing is not None
    assert listing.title == "Apartamento T1 | Porto"
    assert "leilosil.pt" in listing.url
    assert listing.auction_end_at is not None
    assert listing.auction_end_at.year == 2026


def test_parse_card_returns_none_for_empty() -> None:
    html = "<li><div class='content'></div></li>"
    soup = BeautifulSoup(html, "lxml")
    collector = _make_collector()
    assert collector._parse_card(soup.find("li")) is None


def test_parse_listing_page_finds_multiple() -> None:
    html = """
    <ul class="auction-grid grid">
        <li>
            <div class="title"><h2><a href="/pt/leiloes/a/a-1">A</a></h2></div>
        </li>
        <li>
            <div class="title"><h2><a href="/pt/leiloes/b/b-2">B</a></h2></div>
        </li>
    </ul>
    """
    soup = BeautifulSoup(html, "lxml")
    collector = _make_collector()
    items = collector._parse_listing_page(soup)
    assert len(items) == 2


def _make_collector() -> LeilosilCollector:
    from unittest.mock import MagicMock

    context = MagicMock()
    context.source_settings = MagicMock()
    context.source_settings.delay_seconds = 0
    context.source_settings.maximum_pages = 1
    return LeilosilCollector(context)
