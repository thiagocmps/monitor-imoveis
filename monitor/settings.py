"""Configuração da aplicação.

A configuração é lida de config.yaml (ou config.example.yaml como
fallback) e validada com modelos Pydantic.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class ApplicationSettings(BaseModel):
    name: str = "Monitor Imobiliário"
    timezone: str = "Europe/Lisbon"
    locale: str = "pt-PT"
    database_path: str = "data/imoveis.db"
    headless: bool = True

    @property
    def absolute_database_path(self) -> Path:
        path = Path(self.database_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path


class RadiusSettings(BaseModel):
    enabled: bool = True
    center_name: str = "Póvoa de Varzim"
    latitude: float = 41.3804
    longitude: float = -8.7609
    maximum_km: float = 30.0


class SearchSettings(BaseModel):
    maximum_price_eur: float = Field(default=140_000, gt=0)
    accepted_property_types: list[str] = ["APARTMENT", "HOUSE"]
    explicit_municipalities: list[str] = [
        "Porto",
        "Póvoa de Varzim",
        "Vila do Conde",
        "Esposende",
    ]
    radius: RadiusSettings = RadiusSettings()
    exclude_non_full_rights: bool = True
    include_occupied_properties: bool = True
    include_ruins: bool = True

    @field_validator("accepted_property_types")
    @classmethod
    def _validate_types(cls, value: list[str]) -> list[str]:
        allowed = {"APARTMENT", "HOUSE", "LAND", "COMMERCIAL", "OTHER"}
        unknown = {v for v in value if v not in allowed}
        if unknown:
            raise ValueError(f"Tipos de imóvel desconhecidos: {sorted(unknown)}")
        return value


class SourceSettings(BaseModel):
    enabled: bool = True
    delay_seconds: float = Field(default=5.0, ge=0)
    maximum_pages: int = Field(default=3, ge=1, le=20)
    # Específico do Citius: tribunais a consultar (IDs do formulário).
    # Vazio significa usar a lista regional predefinida; "all_tribunals"
    # consulta todos os tribunais disponíveis.
    tribunals: list[int] = Field(default_factory=list)
    all_tribunals: bool = False


class BrowserSettings(BaseModel):
    navigation_timeout_seconds: int = Field(default=45, gt=0)
    selector_timeout_seconds: int = Field(default=20, gt=0)
    channel: str = Field(default="auto", pattern=r"^(auto|chrome|chromium|msedge|firefox|bundled)$")
    block_images: bool = True
    block_fonts: bool = True
    block_media: bool = True
    save_screenshot_on_error: bool = True
    save_html_on_error: bool = True
    concurrency: int = Field(default=1, ge=1, le=2)


class ExecutionSettings(BaseModel):
    maximum_total_minutes: int = Field(default=45, gt=0)
    prevent_parallel_runs: bool = True
    process_priority: str = "low"


class HistorySettings(BaseModel):
    missing_checks_before_removed: int = Field(default=3, ge=1, le=10)


class ScheduleSettings(BaseModel):
    daily_time: str = "07:30"


class ScoringSettings(BaseModel):
    price_up_to_70000: float = 25
    price_up_to_100000: float = 20
    price_up_to_120000: float = 12
    price_up_to_140000: float = 5
    full_ownership: float = 15
    autonomous_unit: float = 12
    vacant: float = 12
    visit_available: float = 8
    light_works: float = 10
    medium_works: float = 8
    full_renovation: float = 4
    recent_price_drop: float = 5
    private_negotiation: float = 3
    priority_location: float = 5
    clear_legal_data: float = 5
    unknown_ownership_penalty: float = -10
    unknown_occupancy_penalty: float = -8
    occupied_penalty: float = -25
    visit_unavailable_penalty: float = -15
    structural_work_penalty: float = -15
    ruin_penalty: float = -20
    incomplete_data_penalty: float = -10
    possible_duplicate_penalty: float = -5
    above_local_reference_penalty: float = -10
    short_deadline_penalty: float = -5
    imprecise_location_penalty: float = -5


class Settings(BaseModel):
    application: ApplicationSettings = ApplicationSettings()
    search: SearchSettings = SearchSettings()
    sources: dict[str, SourceSettings] = {}
    browser: BrowserSettings = BrowserSettings()
    execution: ExecutionSettings = ExecutionSettings()
    history: HistorySettings = HistorySettings()
    schedule: ScheduleSettings = ScheduleSettings()
    scoring: ScoringSettings = ScoringSettings()

    @field_validator("sources")
    @classmethod
    def _default_sources(cls, value: dict[str, SourceSettings]) -> dict[str, SourceSettings]:
        known = {
            "eleiloes",
            "citius",
            "financas",
            "leilosoc",
            "leilosil",
            "leilon",
            "leiloversatil",
            "caixa_imobiliario",
            "imovirtual",
            "idealista",
            "olx",
        }
        for name in known:
            value.setdefault(name, SourceSettings())
        return value

    @property
    def enabled_sources(self) -> list[str]:
        return [name for name, cfg in self.sources.items() if cfg.enabled]

    def source_settings(self, name: str) -> SourceSettings:
        return self.sources.get(name, SourceSettings())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


def load_settings(path: str | Path | None = None) -> Settings:
    """Carrega e valida a configuração a partir de um ficheiro YAML.

    Usa config.yaml quando existir; caso contrário, config.example.yaml.
    """
    if path is None:
        candidates = [PROJECT_ROOT / "config.yaml", PROJECT_ROOT / "config.example.yaml"]
    else:
        candidates = [Path(path)]
    for candidate in candidates:
        if candidate.exists():
            raw: dict[str, Any] = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
            env_name = os.getenv("APP_ENV", "development")
            if env_name not in {"development", "production"}:
                raise ValueError(f"APP_ENV inválido: {env_name!r}")
            return Settings.model_validate(raw)
    raise FileNotFoundError(
        "Nenhum ficheiro de configuração encontrado. Crie config.yaml "
        "a partir de config.example.yaml."
    )
