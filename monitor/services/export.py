"""Exportação de dados para Excel e CSV."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from monitor.exceptions import ExportError
from monitor.settings import PROJECT_ROOT

EXPORT_DIR = PROJECT_ROOT / "exports"


def properties_to_dataframe(rows: list[dict]) -> pd.DataFrame:
    """Converte registos de imóveis num DataFrame para exportação."""
    columns = [
        "id",
        "score",
        "classification",
        "property_type",
        "title",
        "price",
        "currency",
        "usable_area_m2",
        "price_per_m2",
        "municipality",
        "parish",
        "distance_from_povoa_km",
        "source",
        "renovation_level",
        "occupancy_status",
        "legal_ownership_type",
        "sale_method",
        "status",
        "auction_end_at",
        "url",
        "first_seen_at",
        "last_seen_at",
    ]
    frame = pd.DataFrame(rows)
    for col in columns:
        if col not in frame.columns:
            frame[col] = None
    return frame[columns]


def _safe_name(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "_-").strip() or "export"


def export_dataframe(
    frame: pd.DataFrame,
    *,
    format: str,
    filename: str = "imoveis",
    directory: Path | None = None,
) -> Path:
    """Exporta um DataFrame para xlsx ou csv e devolve o caminho."""
    directory = directory or EXPORT_DIR
    directory.mkdir(parents=True, exist_ok=True)
    safe = _safe_name(filename)
    if format == "xlsx":
        path = directory / f"{safe}.xlsx"
        try:
            frame.to_excel(path, index=False)
        except Exception as exc:  # pragma: no cover
            raise ExportError(f"Falha ao exportar Excel: {exc}") from exc
    elif format == "csv":
        path = directory / f"{safe}.csv"
        try:
            frame.to_csv(path, index=False, encoding="utf-8-sig")
        except Exception as exc:  # pragma: no cover
            raise ExportError(f"Falha ao exportar CSV: {exc}") from exc
    else:
        raise ExportError(f"Formato desconhecido: {format!r}")
    return path
