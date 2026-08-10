"""Deteção de estado de anúncio a partir de texto bruto."""

from __future__ import annotations

from monitor.models.enums import ListingStatus
from monitor.services.normalization import normalize_text

_SOLD = ["vendido", "adjudicado", "alienado", "venda efetuada", "venda efectuada"]
_REMOVED = ["anúncio removido", "anuncio removido", "anúncio terminado", "anuncio terminado", "removido"]
_SUSPENDED = ["suspenso", "processo suspenso", "leilão suspenso", "leilao suspenso", "adiado"]
_ENDED = ["terminado", "leilão terminado", "leilao terminado", "fim do prazo", "encerrado"]


def detect_listing_status(text: str | None, *, ended_without_proposal: bool = False) -> ListingStatus:
    """Classifica o estado do anúncio com base no texto disponível."""
    if not text:
        return ListingStatus.ACTIVE
    haystack = normalize_text(text)
    if any(p in haystack for p in _SOLD):
        return ListingStatus.SOLD
    if any(p in haystack for p in _SUSPENDED):
        return ListingStatus.SUSPENDED
    if ended_without_proposal:
        return ListingStatus.ENDED
    if any(p in haystack for p in _ENDED):
        return ListingStatus.ENDED
    if any(p in haystack for p in _REMOVED):
        return ListingStatus.REMOVED
    return ListingStatus.ACTIVE


def ended_without_proposal(text: str | None) -> bool:
    """True quando o anúncio terminou sem possibilidade de proposta."""
    if not text:
        return False
    haystack = normalize_text(text)
    return "terminado sem possibilidade de proposta" in haystack or (
        "sem possibilidade de proposta" in haystack
    )
