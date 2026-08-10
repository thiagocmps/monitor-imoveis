"""Testes da deduplicação de anúncios."""

from __future__ import annotations

from monitor.models.enums import PropertyType
from monitor.models.normalized import NormalizedProperty
from monitor.services.deduplication import (
    canonical_fingerprint,
    cross_source_similarity,
    same_source_matches,
)


def _prop(source: str = "citius", **kwargs) -> NormalizedProperty:
    base: dict = {
        "source": source,
        "url": f"https://exemplo.pt/{source}",
        "normalized_url": f"https://exemplo.pt/{source}",
        "property_type": PropertyType.APARTMENT,
        "title": "Apartamento T2 em Póvoa de Varzim",
        "price": 90_000,
        "municipality": "Póvoa de Varzim",
        "parish": "Centro",
        "address": "Rua de Santa Clara, 12",
        "postal_code": "4490-000",
        "typology": "T2",
        "usable_area_m2": 80.0,
    }
    base.update(kwargs)
    return NormalizedProperty(**base)


def test_canonical_fingerprint_is_stable_and_unique() -> None:
    a = _prop()
    b = _prop()
    assert canonical_fingerprint(a) == canonical_fingerprint(b)
    c = _prop(price=140_000)
    assert canonical_fingerprint(a) != canonical_fingerprint(c)


def test_canonical_fingerprint_empty_for_empty_property() -> None:
    assert canonical_fingerprint(_prop(municipality=None, title=None)) != ""


def test_same_source_matches_keys() -> None:
    prop = _prop(source="citius", source_reference="Proc 123", source_listing_id="42")
    keys = same_source_matches(prop)
    assert "citius|ref|proc 123" in keys
    assert "citius|id|42" in keys
    assert any(key.startswith("citius|url|") for key in keys)


def test_cross_source_similarity_identical() -> None:
    score, reasons = cross_source_similarity(_prop(source="citius"), _prop(source="leilosoc"))
    assert score >= 70
    assert reasons


def test_cross_source_similarity_different() -> None:
    a = _prop(source="citius")
    b = _prop(
        source="leilosoc",
        title="Terreno em Braga",
        price=20_000,
        municipality="Braga",
        parish="São Vítor",
        address="Quinta da Pedra",
        postal_code="4700-000",
        typology=None,
        usable_area_m2=500.0,
    )
    score, _ = cross_source_similarity(a, b)
    assert score < 40
