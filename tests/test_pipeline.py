"""Testes do pipeline de normalização RawPropertyListing -> NormalizedProperty."""

from __future__ import annotations

from monitor.models.enums import (
    LegalOwnershipType,
    LegalStatus,
    PropertyType,
)
from monitor.models.raw import RawPropertyListing
from monitor.services.pipeline import normalize_listing


def test_normalize_citius_listing() -> None:
    raw = RawPropertyListing(
        source="citius",
        url="https://www.citius.mj.pt/portal/consultas/consultasvenda.aspx",
        source_reference="1234/23.5T8VCD",
        source_listing_id="42",
        title="Fração autónoma destinada a habitação T2",
        description="Fração autónoma destinada a habitação, T2, com 73,90 m2, desocupada.",
        base_value=71887.2,
        base_value_text="71 887,20 €",
        municipality="Póvoa de Varzim",
        court="Juízo de Execução de Póvoa de Varzim",
        legal_process="1234/23.5T8VCD",
        registration_number="1234",
        tax_article="5678",
        raw_data={"tribunal_name": "Póvoa de Varzim", "detail_fetched": True},
    )

    normalized = normalize_listing(raw)

    assert normalized.source == "citius"
    assert normalized.source_reference == "1234/23.5T8VCD"
    assert normalized.property_type is PropertyType.APARTMENT
    assert normalized.price == 71887.2
    assert normalized.base_value == 71887.2
    assert normalized.typology == "T2"
    assert normalized.legal_ownership_type is LegalOwnershipType.AUTONOMOUS_UNIT
    assert normalized.legal_status is LegalStatus.ACCEPTED
    assert normalized.municipality == "Póvoa de Varzim"
    assert normalized.distance_from_povoa_km is not None
    assert normalized.canonical_fingerprint
    assert "utm_source" not in normalized.normalized_url


def test_normalize_rejected_legal_status() -> None:
    raw = RawPropertyListing(
        source="leilosoc",
        url="https://leilosoc.com/pt-PT/lot/1/2",
        title="Quota indivisa de prédio",
        description="Venda de quota indivisa de prédio urbano.",
        price_value=50_000,
        municipality="Vila do Conde",
    )

    normalized = normalize_listing(raw)

    assert normalized.legal_status is LegalStatus.AUTOMATICALLY_REJECTED
    assert normalized.legal_ownership_type is LegalOwnershipType.UNDIVIDED_SHARE
    assert normalized.legal_alerts


def test_normalize_price_and_area_from_text() -> None:
    raw = RawPropertyListing(
        source="leilon",
        url="https://www.leilon.pt/pt/auction/lot/1",
        title="Moradia T3",
        description="Moradia T3 com 140 000,00 € de valor base.",
        base_value_text="140 000,00 €",
        usable_area_text="150,00 m2",
        municipality="Porto",
    )

    normalized = normalize_listing(raw)

    assert normalized.base_value == 140000.0
    assert normalized.price is None or normalized.price == 140000.0
    assert normalized.usable_area_m2 == 150.0
    assert normalized.property_type is PropertyType.HOUSE


def test_normalize_unknown_type_and_missing_price() -> None:
    raw = RawPropertyListing(
        source="leilon",
        url="https://www.leilon.pt/pt/auction/lot/9",
        title="Lote em leilão",
        description="Sem mais detalhes.",
    )

    normalized = normalize_listing(raw)

    assert normalized.property_type is PropertyType.LAND
    assert normalized.price is None
    assert normalized.distance_from_povoa_km is None
