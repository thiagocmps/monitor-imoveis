"""Deduplicação de anúncios em dois níveis.

Nível 1 (mesma fonte): ID, referência ou URL normalizada.
Nível 2 (fontes diferentes): comparação ponderada de morada, código
postal, concelho, freguesia, tipologia, área, preço, título e descrição.

Não fundimos automaticamente com confiança baixa: registamos como
possível duplicado para revisão.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from monitor.models.normalized import NormalizedProperty
from monitor.services.normalization import normalize_text, strip_accents

_ARTICLE_RE = re.compile(r"\b(um|uma|uns|umas|o|a|os|as|de|da|do|das|dos|em|no|na|para)\b", re.IGNORECASE)


@dataclass
class MatchResult:
    property_id_a: int
    property_id_b: int
    similarity_score: float
    match_reason: str
    status: str = "POSSIBLE_DUPLICATE"

    reasons: list[str] = field(default_factory=list)


def _tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    cleaned = _ARTICLE_RE.sub(" ", normalize_text(text))
    return {w for w in cleaned.split() if len(w) > 2}


def _similarity(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def canonical_fingerprint(prop: NormalizedProperty) -> str:
    """Fingerprint para deteção de duplicados entre fontes.

    Combina concelho + freguesia + tipologia + área (arredondada) +
    preço (arredondado às centenas).
    """
    parts = [
        strip_accents(prop.municipality or "").lower(),
        strip_accents(prop.parish or "").lower(),
        strip_accents(prop.locality or "").lower(),
        prop.typology or "",
        str(round(prop.usable_area_m2, -1)) if prop.usable_area_m2 else "",
        str(round(prop.price or 0, -2)),
    ]
    raw = "|".join(parts).strip("|")
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def same_source_matches(prop: NormalizedProperty) -> list[str]:
    """Identificadores estáveis da mesma fonte, para procurar na base."""
    keys: list[str] = []
    if prop.source_reference:
        keys.append(f"{prop.source}|ref|{strip_accents(prop.source_reference).lower()}")
    if prop.source_listing_id:
        keys.append(f"{prop.source}|id|{strip_accents(prop.source_listing_id).lower()}")
    if prop.normalized_url:
        keys.append(f"{prop.source}|url|{prop.normalized_url}")
    return keys


def cross_source_similarity(a: NormalizedProperty, b: NormalizedProperty) -> tuple[float, list[str]]:
    """Calcula uma pontuação de semelhança entre dois anúncios (0-100)."""
    score = 0.0
    reasons: list[str] = []

    # Morada igual -> muito alto
    if a.address and b.address and _tokens(a.address) & _tokens(b.address) and _similarity(
        _tokens(a.address), _tokens(b.address)
    ) >= 0.7:
        score += 30
        reasons.append("Morada igual")

    # Código postal igual -> alto
    if a.postal_code and b.postal_code and _normalize_postal(a.postal_code) == _normalize_postal(b.postal_code):
        score += 20
        reasons.append("Código postal igual")

    # Coordenadas próximas -> alto
    if a.latitude is not None and a.longitude is not None and b.latitude is not None and b.longitude is not None:
        distance = abs(a.latitude - b.latitude) + abs(a.longitude - b.longitude)
        if distance < 0.005:
            score += 20
            reasons.append("Coordenadas próximas")

    # Concelho + freguesia iguais -> médio
    if a.municipality and b.municipality and normalize_text(a.municipality) == normalize_text(b.municipality):
        score += 10
        reasons.append("Concelho igual")
        if a.parish and b.parish and normalize_text(a.parish) == normalize_text(b.parish):
            score += 5
            reasons.append("Freguesia igual")

    # Tipologia igual -> médio
    if a.typology and b.typology and a.typology == b.typology:
        score += 10
        reasons.append("Tipologia igual")

    # Área com diferença < 5% -> alto
    if a.usable_area_m2 and b.usable_area_m2:
        diff = abs(a.usable_area_m2 - b.usable_area_m2) / max(a.usable_area_m2, b.usable_area_m2)
        if diff < 0.05:
            score += 15
            reasons.append("Área com diferença menor que 5%")

    # Preço com diferença < 10% -> médio
    if a.price and b.price:
        diff = abs(a.price - b.price) / max(a.price, b.price)
        if diff < 0.10:
            score += 10
            reasons.append("Preço com diferença menor que 10%")

    # Título / descrição semelhantes -> médio
    title_sim = _similarity(_tokens(a.title), _tokens(b.title))
    if title_sim >= 0.5:
        score += 8
        reasons.append("Título semelhante")
    desc_sim = _similarity(_tokens(a.description), _tokens(b.description))
    if desc_sim >= 0.5:
        score += 7
        reasons.append("Descrição semelhante")

    return min(score, 100.0), reasons


def _normalize_postal(code: str) -> str:
    return re.sub(r"\s+", "", code).upper()


def suggest_duplicate_status(score: float) -> str:
    if score >= 75:
        return "CONFIRMED_DUPLICATE"
    if score >= 50:
        return "POSSIBLE_DUPLICATE"
    return "NOT_DUPLICATE"
