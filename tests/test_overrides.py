"""Testes de overrides de configuração (dashboard -> recolha)."""

from __future__ import annotations

from monitor.settings import Settings, apply_overrides


def _base() -> Settings:
    return Settings()


def test_apply_overrides_flat_search_fields() -> None:
    updated = apply_overrides(_base(), {"maximum_price_eur": 200_000})
    assert updated.search.maximum_price_eur == 200_000
    assert updated.search.accept_unknown_type is True


def test_apply_overrides_radius_nested() -> None:
    updated = apply_overrides(_base(), {"radius.enabled": False, "radius.maximum_km": 50})
    assert updated.search.radius.enabled is False
    assert updated.search.radius.maximum_km == 50
    assert updated.search.radius.center_name == "Póvoa de Varzim"


def test_apply_overrides_scoring() -> None:
    updated = apply_overrides(_base(), {"unknown_type_penalty": -20})
    assert updated.scoring.unknown_type_penalty == -20


def test_apply_overrides_none_returns_same() -> None:
    base = _base()
    assert apply_overrides(base, None) is base
    assert apply_overrides(base, {}) is base


def test_apply_overrides_unknown_keys_ignored() -> None:
    updated = apply_overrides(_base(), {"nao_existe": 1})
    assert updated is not _base()
    assert updated.search.maximum_price_eur == 140_000
