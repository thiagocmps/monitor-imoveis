"""Geocodificação com dicionário estático de concelhos portugueses.

Não depende de serviços externos por padrão. A distância é calculada pela
fórmula de Haversine em linha reta. Não calculamos distância ao mar ou à
costa — apenas distância ao centro configurado (Póvoa de Varzim).
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from typing import Any

from monitor.settings import PROJECT_ROOT

GEO_DATA_PATH = PROJECT_ROOT / "data" / "geo_pt.json"
CENTER_NAME = "Póvoa de Varzim"
CENTER_LAT = 41.3804
CENTER_LON = -8.7609

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distância em linha reta (km) entre dois pontos, pela fórmula de Haversine."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


@lru_cache(maxsize=1)
def load_municipalities() -> dict[str, tuple[float, float]]:
    """Carrega centróides dos concelhos (nome normalizado -> lat, lon)."""
    if not GEO_DATA_PATH.exists():
        return {}
    data: dict[str, Any] = json.loads(GEO_DATA_PATH.read_text(encoding="utf-8"))
    result: dict[str, tuple[float, float]] = {}
    for municipality, coords in data.items():
        if isinstance(coords, list) and len(coords) == 2:
            result[municipality.strip().lower()] = (float(coords[0]), float(coords[1]))
    return result


def _lookup(municipality: str | None) -> tuple[float, float] | None:
    if not municipality:
        return None
    table = load_municipalities()
    key = municipality.strip().lower()
    if key in table:
        return table[key]
    return None


class GeoResult:
    def __init__(
        self,
        latitude: float | None,
        longitude: float | None,
        accuracy: str,
        source: str,
    ) -> None:
        self.latitude = latitude
        self.longitude = longitude
        self.accuracy = accuracy
        self.source = source

    def __repr__(self) -> str:  # pragma: no cover
        return f"GeoResult(lat={self.latitude}, lon={self.longitude}, acc={self.accuracy})"


def geocode(
    *,
    municipality: str | None = None,
    parish: str | None = None,
    locality: str | None = None,
    postal_code: str | None = None,
    address: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
) -> GeoResult:
    """Determina as coordenadas e a precisão de forma honesta.

    Ordem de confiança: coordenadas fornecidas > morada > concelho.
    Nunca afirma precisão maior do que a informação disponível.
    """
    if latitude is not None and longitude is not None:
        if address or postal_code:
            return GeoResult(latitude, longitude, "ADDRESS", "source")
        return GeoResult(latitude, longitude, "APPROXIMATE", "source")

    coords = _lookup(municipality)
    if coords:
        return GeoResult(coords[0], coords[1], "MUNICIPALITY", "static")
    return GeoResult(None, None, "UNKNOWN", "none")
