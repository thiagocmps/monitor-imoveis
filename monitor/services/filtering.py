"""Filtragem de imóveis segundo os critérios de pesquisa.

Regras:
1. Aceite se estiver no concelho do Porto (explicitamente, mesmo fora do raio);
2. Aceite se estiver em Póvoa de Varzim, Vila do Conde ou Esposende;
3. Aceite se estiver num raio máximo de 30 km da Póvoa de Varzim.

Preço máximo configurável (140 000 € por padrão). Tipos aceites:
apartamento e moradia. Exclusões jurídicas e de tipo são aplicadas antes
da pontuação.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from monitor.models.enums import (
    GeolocationAccuracy,
    LegalStatus,
    PropertyType,
)
from monitor.models.normalized import NormalizedProperty
from monitor.services.geocoding import haversine_km
from monitor.services.normalization import (
    detect_non_residential_exclusion,
    municipalities_equal,
)
from monitor.settings import SearchSettings


@dataclass
class FilterResult:
    accepted: bool = False
    reasons: list[str] = field(default_factory=list)
    rejected_reasons: list[str] = field(default_factory=list)


def _in_explicit_municipality(prop: NormalizedProperty, settings: SearchSettings) -> bool:
    for name in settings.explicit_municipalities:
        if municipalities_equal(prop.municipality, name):
            return True
    return False


def _within_radius(prop: NormalizedProperty, settings: SearchSettings) -> bool:
    if not settings.radius.enabled:
        return True
    if prop.latitude is None or prop.longitude is None:
        return False
    distance = haversine_km(
        settings.radius.latitude, settings.radius.longitude, prop.latitude, prop.longitude
    )
    return distance <= settings.radius.maximum_km


def apply_filters(
    prop: NormalizedProperty,
    settings: SearchSettings,
    *,
    include_occupied: bool | None = None,
    include_ruins: bool | None = None,
) -> FilterResult:
    """Aplica os critérios de pesquisa e devolve o resultado detalhado."""
    if include_occupied is None:
        include_occupied = settings.include_occupied_properties
    if include_ruins is None:
        include_ruins = settings.include_ruins
    result = FilterResult()

    # Preço máximo
    if prop.price is not None and prop.price > settings.maximum_price_eur:
        result.rejected_reasons.append(
            f"Preço {prop.price:.2f} € acima do máximo {settings.maximum_price_eur:.2f} €"
        )

    # Tipo de imóvel
    if prop.property_type not in {PropertyType(t) for t in settings.accepted_property_types}:
        result.rejected_reasons.append(f"Tipo de imóvel não aceite: {prop.property_type.value}")

    # Menções não habitacionais no título/descrição (armazém, garagem,
    # escritório, arrecadação, etc.) mesmo que o tipo detetado seja apartamento.
    non_residential, reasons = detect_non_residential_exclusion(
        prop.title, prop.description, prop.property_type
    )
    if non_residential:
        result.rejected_reasons.extend(reasons)

    # Estado jurídico
    if prop.legal_status is LegalStatus.AUTOMATICALLY_REJECTED:
        result.rejected_reasons.append(
            "Imóvel com direito parcial ou limitado rejeitado automaticamente"
        )

    # Ocupação (opcional)
    if not include_occupied and prop.occupancy_status.value.startswith("OCCUPIED"):
        result.rejected_reasons.append("Imóvel ocupado excluído pelas definições")

    # Ruína (opcional)
    if not include_ruins and prop.renovation_level.value == "RUIN_OR_RECONSTRUCTION":
        result.rejected_reasons.append("Imóvel em ruína excluído pelas definições")

    # Localização
    if _in_explicit_municipality(prop, settings):
        result.reasons.append("Localização: concelho aceite explicitamente")
    elif _within_radius(prop, settings):
        result.reasons.append("Localização: dentro do raio da Póvoa de Varzim")
    else:
        if prop.latitude is None or prop.longitude is None:
            result.rejected_reasons.append(
                "Localização desconhecida (fora de concelho explícito e sem coordenadas)"
            )
        else:
            result.rejected_reasons.append(
                "Localização fora do raio e fora dos concelhos explícitos"
            )

    # Faltou preço -> rejeitar (não dá para pontuar)
    if prop.price is None:
        result.rejected_reasons.append("Preço desconhecido")

    result.accepted = not result.rejected_reasons
    return result


def location_notes(prop: NormalizedProperty) -> list[str]:
    """Notas de localização para o painel e para a pontuação."""
    notes: list[str] = []
    if prop.municipality:
        notes.append(f"Concelho: {prop.municipality}")
    if prop.distance_from_povoa_km is not None:
        notes.append(f"Distância à Póvoa de Varzim: {prop.distance_from_povoa_km:.1f} km")
    if prop.geolocation_accuracy is GeolocationAccuracy.UNKNOWN:
        notes.append("Geolocalização desconhecida")
    return notes
