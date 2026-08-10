"""Testes do coletor Citius (helpers sem browser)."""

from __future__ import annotations

from monitor.collectors.citius import FORM_URL, _detail_url, municipality_for_tribunal


def test_municipality_for_tribunal_known() -> None:
    assert municipality_for_tribunal("Vila do Conde") == "Vila do Conde"
    assert municipality_for_tribunal("Póvoa de Varzim") == "Póvoa de Varzim"
    assert municipality_for_tribunal("Paços de Ferreira") == "Paços de Ferreira"


def test_municipality_for_tribunal_unknown() -> None:
    assert municipality_for_tribunal("Tribunal Judicial da Comarca de Lisboa") is None
    assert municipality_for_tribunal("") is None
    assert municipality_for_tribunal(None) is None


def test_detail_url_is_unique_per_listing() -> None:
    first = _detail_url(12345, "1234/23.4T8PRT")
    second = _detail_url(67890, "5678/23.4T8PRT")
    assert first != second
    assert "nprocesso=12345" in first
    assert "nprocesso=67890" in second


def test_detail_url_fallbacks() -> None:
    assert _detail_url(None, "1234/23.4T8PRT").endswith("#1234/23.4T8PRT")
    assert _detail_url(None, None) == FORM_URL
