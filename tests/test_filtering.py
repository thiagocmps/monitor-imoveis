"""Testes da filtragem de imóveis segundo os critérios de pesquisa."""

from __future__ import annotations

from monitor.models.enums import LegalStatus, PropertyType
from monitor.models.normalized import NormalizedProperty
from monitor.services.filtering import apply_filters
from monitor.settings import SearchSettings


def _prop(**kwargs) -> NormalizedProperty:
    base: dict = {
        "source": "citius",
        "url": "https://exemplo.pt/x",
        "normalized_url": "https://exemplo.pt/x",
        "property_type": PropertyType.APARTMENT,
        "price": 100_000,
    }
    base.update(kwargs)
    return NormalizedProperty(**base)


def test_accepted_in_explicit_municipality_without_coords() -> None:
    result = apply_filters(_prop(municipality="Vila do Conde"), SearchSettings())
    assert result.accepted
    assert not result.rejected_reasons


def test_accepted_within_radius() -> None:
    # ~10 km da Póvoa de Varzim.
    result = apply_filters(
        _prop(municipality="Póvoa de Varzim", latitude=41.45, longitude=-8.70),
        SearchSettings(),
    )
    assert result.accepted


def test_rejected_outside_radius_and_municipality() -> None:
    result = apply_filters(
        _prop(municipality="Lisboa", latitude=38.72, longitude=-9.14),
        SearchSettings(),
    )
    assert not result.accepted
    assert any("raio" in r for r in result.rejected_reasons)


def test_rejected_above_max_price() -> None:
    settings = SearchSettings(maximum_price_eur=140_000)
    result = apply_filters(_prop(municipality="Porto", price=200_000), settings)
    assert not result.accepted
    assert any("Preço" in r for r in result.rejected_reasons)


def test_rejected_unknown_price() -> None:
    result = apply_filters(_prop(municipality="Porto", price=None), SearchSettings())
    assert not result.accepted
    assert "Preço desconhecido" in result.rejected_reasons


def test_rejected_non_residential_type() -> None:
    result = apply_filters(
        _prop(municipality="Porto", property_type=PropertyType.LAND), SearchSettings()
    )
    assert not result.accepted
    assert any("Tipo de imóvel" in r for r in result.rejected_reasons)


def test_rejected_automatic_legal_status() -> None:
    result = apply_filters(
        _prop(municipality="Porto", legal_status=LegalStatus.AUTOMATICALLY_REJECTED),
        SearchSettings(),
    )
    assert not result.accepted
    assert any("direito parcial" in r for r in result.rejected_reasons)


def test_rejected_occupied_when_excluded() -> None:
    from monitor.models.enums import OccupancyStatus

    settings = SearchSettings(include_occupied_properties=False)
    result = apply_filters(
        _prop(
            municipality="Porto",
            occupancy_status=OccupancyStatus.OCCUPIED_BY_OWNER,
        ),
        settings,
    )
    assert not result.accepted
    assert any("ocupado" in r for r in result.rejected_reasons)


def test_radius_disabled_accepts_unknown_location() -> None:
    settings = SearchSettings()
    settings.radius.enabled = False
    result = apply_filters(
        _prop(municipality="Braga", price=80_000),
        settings,
    )
    assert result.accepted
