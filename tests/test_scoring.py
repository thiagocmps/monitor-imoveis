"""Testes da pontuação transparente de oportunidades."""

from __future__ import annotations

import json

from monitor.models.enums import Classification, LegalStatus, OccupancyStatus, PropertyType
from monitor.models.normalized import NormalizedProperty
from monitor.services.scoring import score_property
from monitor.settings import ScoringSettings, SearchSettings


def _prop(**kwargs) -> NormalizedProperty:
    base: dict = {
        "source": "citius",
        "url": "https://exemplo.pt/x",
        "normalized_url": "https://exemplo.pt/x",
        "property_type": PropertyType.APARTMENT,
        "title": "Apartamento T2",
        "price": 80_000,
        "municipality": "Póvoa de Varzim",
    }
    base.update(kwargs)
    return NormalizedProperty(**base)


def test_automatically_rejected_gets_zero() -> None:
    score, classification, reasons = score_property(
        _prop(legal_status=LegalStatus.AUTOMATICALLY_REJECTED),
        ScoringSettings(),
        SearchSettings(),
    )
    assert score == 0.0
    assert classification is Classification.EXCLUDE
    assert json.loads(reasons) == []


def test_good_property_high_score() -> None:
    from monitor.models.enums import LegalOwnershipType

    prop = _prop(
        price=60_000,
        legal_ownership_type=LegalOwnershipType.FULL_OWNERSHIP,
        occupancy_status=OccupancyStatus.VACANT,
        distance_from_povoa_km=3.0,
    )
    score, classification, reasons = score_property(
        prop, ScoringSettings(), SearchSettings()
    )
    assert score > 50
    assert classification is not Classification.EXCLUDE
    parsed = json.loads(reasons)
    assert parsed


def test_occupied_penalized() -> None:
    scoring = ScoringSettings()
    vacant, _, _ = score_property(
        _prop(occupancy_status=OccupancyStatus.VACANT), scoring, SearchSettings()
    )
    occupied, _, _ = score_property(
        _prop(occupancy_status=OccupancyStatus.OCCUPIED_BY_OWNER), scoring, SearchSettings()
    )
    assert occupied < vacant


def test_score_is_clamped_to_bounds() -> None:
    prop = _prop(
        price=60_000,
        occupancy_status=OccupancyStatus.VACANT,
        distance_from_povoa_km=1.0,
    )
    score, _, _ = score_property(prop, ScoringSettings(), SearchSettings())
    assert 0.0 <= score <= 100.0


def test_recent_price_drop_adds_points() -> None:
    scoring = ScoringSettings()
    base_score, _, _ = score_property(_prop(), scoring, SearchSettings())
    dropped_score, _, _ = score_property(
        _prop(), scoring, SearchSettings(), price_dropped_recently=True
    )
    assert dropped_score == base_score + scoring.recent_price_drop
