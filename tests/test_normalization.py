"""Testes das funções de normalização de texto, preço, área e classificadores."""

from __future__ import annotations

import pytest
from monitor.models.enums import (
    LegalOwnershipType,
    LegalStatus,
    OccupancyStatus,
    PropertyType,
    RenovationLevel,
    SaleMethod,
)
from monitor.services.normalization import (
    classify_legal_ownership,
    classify_occupancy,
    classify_renovation_level,
    classify_sale_method,
    compute_price_per_m2,
    detect_property_type,
    identify_typology,
    normalize_municipality,
    normalize_url,
    parse_area,
    parse_price,
)
from monitor.services.status_detection import detect_listing_status


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("140 000,00 €", 140000.0),
        ("140.000 €", 140000.0),
        ("€140.000", 140000.0),
        ("140000 EUR", 140000.0),
        ("57 090,00 €", 57090.0),
        ("71 887,20 €", 71887.2),
        ("1.250,50 €", 1250.5),
        ("1,000.50 €", 1000.5),
        ("140000", 140000.0),
        ("1.000.000 €", 1000000.0),
        ("140,5 €", 140.5),
    ],
)
def test_parse_price_valid(text: str, expected: float) -> None:
    assert parse_price(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", [None, "", "valor", "140-000 €", "-500 €", "abc"])
def test_parse_price_invalid(text: str | None) -> None:
    assert parse_price(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("73,90 m2", 73.9),
        ("100.5 m²", 100.5),
        ("74 metros quadrados", 74.0),
        ("1.000 m2", 1000.0),
        ("1.000,50 m²", 1000.5),
        ("45,0 m²", 45.0),
    ],
)
def test_parse_area(text: str, expected: float) -> None:
    assert parse_area(text) == pytest.approx(expected)


@pytest.mark.parametrize("text", [None, "", "sem área", "abc"])
def test_parse_area_invalid(text: str | None) -> None:
    assert parse_area(text) is None


def test_identify_typology() -> None:
    assert identify_typology("Apartamento T2 em Póvoa de Varzim") == "T2"
    assert identify_typology("Moradia T3+1") == "T3+1"
    assert identify_typology("sem tipologia") is None


def test_normalize_url_strips_tracking_params() -> None:
    url = "https://exemplo.pt/imovel/123?utm_source=x&ref=y&preco=1"
    assert normalize_url(url) == "https://exemplo.pt/imovel/123?preco=1"


def test_normalize_municipality() -> None:
    assert normalize_municipality("  PÓVOA de Varzim  ") == "povoa de varzim"
    assert normalize_municipality("") is None


def test_compute_price_per_m2() -> None:
    assert compute_price_per_m2(100_000, 50) == 2000.0
    assert compute_price_per_m2(100_000, None) is None
    assert compute_price_per_m2(None, 50) is None


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Apartamento T2", PropertyType.APARTMENT),
        ("Fração autónoma destinada a habitação", PropertyType.APARTMENT),
        ("Fração autónoma destinada a escritório", PropertyType.COMMERCIAL),
        ("FRAÇÃO AUTÓNOMA NO PORTO DESTINADA A ESCRITÓRIO", PropertyType.COMMERCIAL),
        ("Fração autónoma tipo loja", PropertyType.COMMERCIAL),
        ("Moradia em bom estado", PropertyType.HOUSE),
        ("Vivenda T3", PropertyType.HOUSE),
        ("Terreno urbano", PropertyType.LAND),
        ("Loja comercial", PropertyType.COMMERCIAL),
        ("Lote X", PropertyType.LAND),
        ("Descrição genérica", PropertyType.UNKNOWN),
    ],
)
def test_detect_property_type(title: str, expected: PropertyType) -> None:
    assert detect_property_type(title=title) is expected


def test_classify_legal_ownership_autonomous_unit_accepted() -> None:
    ownership, status, alerts = classify_legal_ownership(
        "Fração autónoma destinada a habitação", None
    )
    assert ownership is LegalOwnershipType.AUTONOMOUS_UNIT
    assert status is LegalStatus.ACCEPTED
    assert alerts == []


def test_classify_legal_ownership_indivisa_rejected() -> None:
    ownership, status, alerts = classify_legal_ownership("Fração indivisa de imóvel", None)
    assert ownership is LegalOwnershipType.UNDIVIDED_SHARE
    assert status is LegalStatus.AUTOMATICALLY_REJECTED
    assert alerts


def test_classify_legal_ownership_partial_rights_rejected() -> None:
    ownership, status, _ = classify_legal_ownership("Direito à meação sobre prédio", None)
    assert ownership is LegalOwnershipType.MARITAL_SHARE
    assert status is LegalStatus.AUTOMATICALLY_REJECTED


def test_classify_legal_ownership_plain_fraction_review() -> None:
    _, status, _ = classify_legal_ownership("Fração de prédio urbano", None)
    assert status is LegalStatus.REQUIRES_REVIEW


def test_classify_legal_ownership_full_ownership() -> None:
    ownership, status, _ = classify_legal_ownership("Imóvel para venda", "Prédio urbano")
    assert ownership is LegalOwnershipType.FULL_OWNERSHIP
    assert status is LegalStatus.ACCEPTED


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Imóvel em ruína", RenovationLevel.RUIN_OR_RECONSTRUCTION),
        ("Pode exigir obras estruturais", RenovationLevel.POSSIBLE_STRUCTURAL_WORKS),
        ("Necessita de remodelação total", RenovationLevel.FULL_RENOVATION),
        ("Requer obras de conservação", RenovationLevel.MEDIUM_WORKS),
        ("Precisa de obras leves", RenovationLevel.LIGHT_WORKS),
        ("Em bom estado", RenovationLevel.NOT_IDENTIFIED),
    ],
)
def test_classify_renovation_level(text: str, expected: RenovationLevel) -> None:
    level, _ = classify_renovation_level(text)
    assert level is expected


def test_classify_occupancy() -> None:
    assert classify_occupancy("Imóvel desocupado")[0] is OccupancyStatus.VACANT
    assert classify_occupancy("Ocupado pelo executado")[0] is OccupancyStatus.OCCUPIED_BY_OWNER
    assert classify_occupancy(None)[0] is OccupancyStatus.UNKNOWN


def test_classify_sale_method() -> None:
    assert classify_sale_method("Leilão eletrónico") is SaleMethod.ELECTRONIC_AUCTION
    assert classify_sale_method("Negociação particular") is SaleMethod.PRIVATE_NEGOTIATION
    assert classify_sale_method(None) is SaleMethod.UNKNOWN


def test_detect_listing_status() -> None:
    from monitor.models.enums import ListingStatus

    assert detect_listing_status("Vendido em leilão") is ListingStatus.SOLD
    assert detect_listing_status("Leilão suspenso") is ListingStatus.SUSPENDED
    assert detect_listing_status("Anúncio removido") is ListingStatus.REMOVED
    assert detect_listing_status("Em venda") is ListingStatus.ACTIVE
    assert detect_listing_status(None) is ListingStatus.ACTIVE
