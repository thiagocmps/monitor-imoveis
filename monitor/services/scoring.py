"""Pontuação transparente de 0 a 100 para cada oportunidade.

As razões (positivas e penalizações) são registadas com o peso usado,
para auditar o resultado. Exclusões recebem pontuação zero.

Classificações:
  80-100: PRIORITY_HIGH
  65-79 : ANALYZE
  50-64 : WATCH
  1-49  : LOW_PRIORITY
  0     : EXCLUDE
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from monitor.models.enums import (
    Classification,
    GeolocationAccuracy,
    LegalOwnershipType,
    OccupancyStatus,
    RenovationLevel,
    VisitStatus,
)
from monitor.models.normalized import NormalizedProperty
from monitor.settings import ScoringSettings, SearchSettings


@dataclass
class ScoreBreakdown:
    total: float = 0.0
    reasons: list[str] = field(default_factory=list)
    penalties: list[str] = field(default_factory=list)


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, round(value, 2)))


def _classification_for(score: float) -> Classification:
    if score <= 0:
        return Classification.EXCLUDE
    if score >= 80:
        return Classification.PRIORITY_HIGH
    if score >= 65:
        return Classification.ANALYZE
    if score >= 50:
        return Classification.WATCH
    return Classification.LOW_PRIORITY


def score_property(
    prop: NormalizedProperty,
    scoring: ScoringSettings,
    search: SearchSettings,
    *,
    is_possible_duplicate: bool = False,
    price_dropped_recently: bool = False,
) -> tuple[float, Classification, str]:
    """Calcula a pontuação e devolve (score, classificacao, score_reasons_json)."""
    if prop.legal_status.value == "AUTOMATICALLY_REJECTED":
        return 0.0, Classification.EXCLUDE, json.dumps([], ensure_ascii=False)

    breakdown = ScoreBreakdown()

    def add(label: str, points: float) -> None:
        breakdown.total += points
        breakdown.reasons.append(f"{label}: {points:+.0f}")

    # Preço
    if prop.price is not None:
        if prop.price <= 70_000:
            add(f"Preço até 70 000 € ({prop.price:.0f} €)", scoring.price_up_to_70000)
        elif prop.price <= 100_000:
            add(f"Preço até 100 000 € ({prop.price:.0f} €)", scoring.price_up_to_100000)
        elif prop.price <= 120_000:
            add(f"Preço até 120 000 € ({prop.price:.0f} €)", scoring.price_up_to_120000)
        elif prop.price <= 140_000:
            add(f"Preço até 140 000 € ({prop.price:.0f} €)", scoring.price_up_to_140000)

    # Propriedade
    if prop.legal_ownership_type is LegalOwnershipType.FULL_OWNERSHIP:
        add("Propriedade plena", scoring.full_ownership)
    elif prop.legal_ownership_type is LegalOwnershipType.AUTONOMOUS_UNIT:
        add("Fração autónoma integral", scoring.autonomous_unit)
    elif prop.legal_ownership_type is LegalOwnershipType.UNKNOWN:
        add("Propriedade desconhecida", scoring.unknown_ownership_penalty)

    # Ocupação
    if prop.occupancy_status is OccupancyStatus.VACANT:
        add("Desocupado", scoring.vacant)
    elif prop.occupancy_status.value.startswith("OCCUPIED"):
        add("Ocupado", scoring.occupied_penalty)
    elif prop.occupancy_status is OccupancyStatus.UNKNOWN:
        add("Ocupação desconhecida", scoring.unknown_occupancy_penalty)

    # Visita
    if prop.visit_status is VisitStatus.AVAILABLE:
        add("Visita disponível", scoring.visit_available)
    elif prop.visit_status is VisitStatus.NOT_AVAILABLE:
        add("Visita indisponível", scoring.visit_unavailable_penalty)

    # Obras
    if prop.renovation_level is RenovationLevel.LIGHT_WORKS:
        add("Obras leves", scoring.light_works)
    elif prop.renovation_level is RenovationLevel.MEDIUM_WORKS:
        add("Obras médias", scoring.medium_works)
    elif prop.renovation_level is RenovationLevel.FULL_RENOVATION:
        add("Remodelação total", scoring.full_renovation)
    elif prop.renovation_level is RenovationLevel.POSSIBLE_STRUCTURAL_WORKS:
        add("Possíveis obras estruturais", scoring.structural_work_penalty)
    elif prop.renovation_level is RenovationLevel.RUIN_OR_RECONSTRUCTION:
        add("Ruína / reconstrução", scoring.ruin_penalty)

    # Localização prioritária (raio próximo)
    if _is_priority_location(prop, search):
        add("Localização prioritária", scoring.priority_location)
    elif prop.geolocation_accuracy in {
        GeolocationAccuracy.UNKNOWN,
        GeolocationAccuracy.MUNICIPALITY,
    } and prop.distance_from_povoa_km is None:
        add("Localização imprecisa", scoring.imprecise_location_penalty)

    # Modalidade
    if prop.sale_method.value == "PRIVATE_NEGOTIATION":
        add("Negociação particular", scoring.private_negotiation)

    # Redução recente
    if price_dropped_recently:
        add("Redução recente de preço", scoring.recent_price_drop)

    # Duplicado possível
    if is_possible_duplicate:
        add("Possível duplicado", scoring.possible_duplicate_penalty)

    # Prazo curto
    if prop.auction_end_at is not None:
        days_left = (prop.auction_end_at - _now()).days
        if days_left < 3:
            add("Prazo inferior a três dias", scoring.short_deadline_penalty)

    # Dados essenciais incompletos
    if prop.price is None or prop.title is None:
        add("Dados essenciais incompletos", scoring.incomplete_data_penalty)

    total = _clamp(breakdown.total)
    classification = _classification_for(total)
    reasons_json = json.dumps(breakdown.reasons, ensure_ascii=False)
    return total, classification, reasons_json


def _now():
    from datetime import datetime

    return datetime.utcnow()


def _is_priority_location(prop: NormalizedProperty, search: SearchSettings) -> bool:
    if not prop.municipality:
        return False
    for name in search.explicit_municipalities:
        if name and prop.municipality.strip().lower() == name.strip().lower():
            return True
    return False
