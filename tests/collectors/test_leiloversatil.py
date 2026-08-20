"""Testes do coletor Leiloversatil (helpers sem browser)."""

from __future__ import annotations

from bs4 import BeautifulSoup
from monitor.collectors.leiloversatil import (
    LeiloversatilCollector,
    _extract_end_timestamp,
    _parse_euro,
    _parse_lot_ids,
)


def test_parse_lot_ids_valid() -> None:
    lot_id, venda_id, tipo = _parse_lot_ids(
        "https://www.leiloversatil.pt/?page=leilao&leilao=10503&venda=1704&tipo=7"
    )
    assert lot_id == "10503"
    assert venda_id == "1704"
    assert tipo == "7"


def test_parse_lot_ids_relative() -> None:
    lot_id, venda_id, tipo = _parse_lot_ids("./?page=leilao&leilao=9923&venda=1643&tipo=2")
    assert lot_id == "9923"
    assert venda_id == "1643"
    assert tipo == "2"


def test_parse_lot_ids_none_for_invalid() -> None:
    lot_id, venda_id, tipo = _parse_lot_ids("https://example.com/nope")
    assert lot_id is None
    assert venda_id is None
    assert tipo is None


def test_parse_euro_valid() -> None:
    assert _parse_euro("460.000,00") == 460000.0
    assert _parse_euro("199.000,00") == 199000.0
    assert _parse_euro("0,00") == 0.0


def test_parse_euro_invalid() -> None:
    assert _parse_euro(None) is None
    assert _parse_euro("") is None


def test_extract_end_timestamp_found() -> None:
    html = """
    <div>
        <script>
        var terminovenda = new Date(1787871540000);
        </script>
    </div>
    """
    soup = BeautifulSoup(html, "lxml")
    dt = _extract_end_timestamp(soup.find("div"))
    assert dt is not None
    assert dt.year == 2026


def test_extract_end_timestamp_missing() -> None:
    html = "<div><p>No script here</p></div>"
    soup = BeautifulSoup(html, "lxml")
    assert _extract_end_timestamp(soup.find("div")) is None


def test_parse_card_extracts_fields() -> None:
    html = """
    <div class="home_block_advert">
        <section class="section">
            <div class="row-fluid">
                <div class="span3">
                    <a href="./?page=leilao&leilao=9923&venda=1643&tipo=2">
                        <img src="images/90/1/test.jpg" alt="Lote 1" />
                    </a>
                </div>
                <div class="span9">
                    <div class="span3 tipo_leilao_pesq">
                        <p class="tipo_leilao">LEILÃO ELECTRÓNICO</p>
                    </div>
                </div>
                <div class="span9 pesquisa_titulo">
                    <a href="./?page=leilao&leilao=9923&venda=1643&tipo=2">
                        <h1>Lote 1</h1>
                    </a>
                    <p class="texto_lote">Apartamento T4 no centro da cidade.</p>
                </div>
                <div class="infobox_valores infobox_valores_pesq">
                    <div class="infobox_valorbase infoxbox_33percent">
                        <small>Valor Minimo</small>
                        <p>460.000,00 €</p>
                    </div>
                </div>
            </div>
        </section>
    </div>
    """
    soup = BeautifulSoup(html, "lxml")
    collector = _make_collector()
    listing = collector._parse_card(soup.find("div", class_="home_block_advert"))
    assert listing is not None
    assert listing.title == "Lote 1"
    assert listing.minimum_value == 460000.0
    assert listing.sale_method_text == "LEILÃO ELECTRÓNICO"
    assert listing.description is not None
    assert listing.raw_data["venda_id"] == "1643"
    assert listing.raw_data["tipo"] == "2"


def test_parse_card_returns_none_for_empty() -> None:
    html = (
        "<div class='home_block_advert'><section>"
        "<div class='row-fluid'>"
        "<div class='span9 pesquisa_titulo'></div>"
        "</div></section></div>"
    )
    soup = BeautifulSoup(html, "lxml")
    collector = _make_collector()
    assert collector._parse_card(soup.find("div", class_="home_block_advert")) is None


def _make_collector() -> LeiloversatilCollector:
    from unittest.mock import MagicMock

    context = MagicMock()
    context.source_settings = MagicMock()
    context.source_settings.delay_seconds = 0
    context.source_settings.maximum_pages = 1
    return LeiloversatilCollector(context)
