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
    assert "nprocesso=1234%2F23.4T8PRT" in first or "nprocesso=1234/23.4T8PRT" in first
    assert "nprocesso=5678%2F23.4T8PRT" in second or "nprocesso=5678/23.4T8PRT" in second


def test_detail_url_prefers_legal_process_over_html_id() -> None:
    url = _detail_url(12345, "1234/23.4T8PRT")
    assert "nprocesso=" in url
    assert "html_id=" not in url


def test_detail_url_fallbacks() -> None:
    url_with_process = _detail_url(None, "1234/23.4T8PRT")
    assert "nprocesso=" in url_with_process
    assert url_with_process.startswith(FORM_URL)

    url_with_html_id = _detail_url(42, None)
    assert "html_id=42" in url_with_html_id
    assert url_with_html_id.startswith(FORM_URL)

    assert _detail_url(None, None) == FORM_URL
