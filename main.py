"""Monitor Imobiliário — interface de linha de comandos.

Comandos:
  init         Cria a base de dados e as tabelas.
  collect      Recolhe, normaliza, filtra, pontua e regista imóveis.
  export       Exporta os imóveis ativos para Excel ou CSV.
  backup       Cria um backup consistente da base.
  restore      Restaura a base a partir de um backup.
  status       Resumo da base de dados.
  sources      Estado das fontes (ativas, implementadas).
  health       Verifica a disponibilidade das fontes.
  dashboard    Lança o painel Streamlit.
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys
from pathlib import Path
from typing import Any

import typer
from monitor.collectors.registry import get_registry
from monitor.database.migrations import initialize_database
from monitor.database.models import Property
from monitor.database.repository import Repository
from monitor.database.session import Database
from monitor.exceptions import ExecutionLockedError
from monitor.logging_config import setup_logging
from monitor.orchestration.locking import ExecutionLock
from monitor.orchestration.pipeline import run_collection
from monitor.services.backup import create_backup, restore_backup
from monitor.services.export import export_dataframe, properties_to_dataframe
from monitor.settings import Settings, load_settings

app = typer.Typer(add_completion=False, no_args_is_help=True, help="Monitor Imobiliário.")

_CONFIG_PATH: Path | None = None


@app.callback()
def _set_config(
    config: Path | None = typer.Option(
        None, "--config", "-c", help="Caminho para config.yaml."
    ),
) -> None:
    global _CONFIG_PATH
    _CONFIG_PATH = config


def _settings() -> Settings:
    return load_settings(_CONFIG_PATH)


@app.command()
def init() -> None:
    """Cria a base de dados e as tabelas em falta."""
    settings = _settings()
    db = Database(settings)
    initialize_database(db.engine)
    db.dispose()
    typer.echo(f"Base de dados pronta: {settings.application.absolute_database_path}")


@app.command()
def collect(
    sources: list[str] | None = typer.Option(
        None,
        "--source",
        "-s",
        help="Fontes a recolher (repetível). Por defeito usa as fontes ativas.",
    ),
) -> None:
    """Recolhe, normaliza, filtra, pontua e regista imóveis."""
    settings = _settings()
    setup_logging(level=20)
    try:
        with ExecutionLock():
            summary = asyncio.run(run_collection(settings, sources=sources))
    except ExecutionLockedError as exc:
        typer.echo(f"ERRO: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    for source, stats in summary.items():
        status = stats.get("status", "?")
        if status == "COMPLETED":
            typer.echo(
                f"{source:<16} OK   encontrados={stats['items_found']} "
                f"aceites={stats['items_accepted']} rejeitados={stats['items_rejected']} "
                f"novos={stats['items_new']} atualizados={stats['items_updated']} "
                f"paginas={stats['pages_visited']}"
            )
        else:
            typer.echo(f"{source:<16} FALHOU  ({stats.get('error')})", err=True)


@app.command()
def export(
    format: str = typer.Option(
        "xlsx", "--format", "-f", help="Formato de exportação: xlsx ou csv."
    ),
    filename: str = typer.Option("imoveis", "--filename", "-n", help="Nome do ficheiro."),
) -> None:
    """Exporta os imóveis ativos para Excel ou CSV."""
    settings = _settings()
    db = Database(settings)
    initialize_database(db.engine)
    session = db.new_session()
    try:
        rows = _rows_from_properties(Repository(session).list_properties(status="ACTIVE"))
    finally:
        session.close()
    frame = properties_to_dataframe(rows)
    path = export_dataframe(frame, format=format, filename=filename)
    typer.echo(f"Exportado: {path}")


@app.command()
def backup(
    compress: bool = typer.Option(True, help="Comprimir o backup (gzip)."),
) -> None:
    """Cria um backup consistente da base SQLite."""
    settings = _settings()
    db = Database(settings)
    path = create_backup(db.engine, compress=compress)
    db.dispose()
    typer.echo(f"Backup criado: {path}")


@app.command()
def restore(
    path: Path = typer.Argument(..., exists=True, help="Caminho do backup."),
    confirm: bool = typer.Option(False, "--confirm", help="Confirma o restauro."),
) -> None:
    """Restaura a base a partir de um backup (requer --confirm)."""
    settings = _settings()
    db = Database(settings)
    if not confirm:
        db.dispose()
        typer.echo("Restauro requer --confirm para sobrepor a base ativa.", err=True)
        raise typer.Exit(code=1)
    target = restore_backup(path, db.engine, confirm=True)
    db.dispose()
    typer.echo(f"Base restaurada: {target}")


@app.command()
def status() -> None:
    """Mostra um resumo do estado da base de dados."""
    settings = _settings()
    db = Database(settings)
    initialize_database(db.engine)
    session = db.new_session()
    try:
        repo = Repository(session)
        rows = repo.list_properties(status="ACTIVE")
        active = len(rows)
        total = len(repo.list_properties())
        classifications = _count_classifications(rows)
        latest = repo.latest_run()
    finally:
        session.close()
    db.dispose()

    typer.echo(f"Imóveis ativos:      {active}")
    typer.echo(f"Imóveis no total:    {total}")
    for classification, count in classifications.items():
        typer.echo(f"  {classification:<14} {count}")
    if latest:
        typer.echo(
            f"Última execução:     {latest.source} em {latest.started_at:%Y-%m-%d %H:%M} "
            f"({latest.status})"
        )


@app.command()
def sources() -> None:
    """Mostra o estado das fontes (ativas e implementadas)."""
    settings = _settings()
    registry = get_registry()
    for name, cfg in settings.sources.items():
        state = registry.status(name)
        enabled = "ativada " if cfg.enabled else "desativada"
        typer.echo(f"{name:<18} {enabled} ({state})")


@app.command()
def health(
    sources: list[str] | None = typer.Option(
        None,
        "--source",
        "-s",
        help="Fontes a verificar (repetível). Por defeito usa as ativas.",
    ),
) -> None:
    """Verifica a disponibilidade das fontes."""
    import httpx
    from monitor.collectors.base import CollectorContext

    settings = _settings()
    registry = get_registry()
    targets = sources or settings.enabled_sources

    async def _check() -> None:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0)) as client:
            for source in targets:
                if not registry.is_implemented(source):
                    typer.echo(f"{source:<16} não implementada")
                    continue
                context = CollectorContext(
                    source=source,
                    settings=settings,
                    client=client,
                    logger=logging.getLogger(__name__),
                )
                try:
                    result = await registry.create(source, context).health_check()
                except Exception as exc:  # noqa: BLE001
                    typer.echo(f"{source:<16} ERRO  {exc}", err=True)
                    continue
                if result.reachable:
                    typer.echo(f"{source:<16} OK    (HTTP {result.http_status})")
                else:
                    typer.echo(f"{source:<16} INDISPONÍVEL  {result.message}", err=True)

    asyncio.run(_check())


@app.command()
def dashboard(
    port: int = typer.Option(8501, "--port", "-p", help="Porta do Streamlit."),
) -> None:
    """Lança o painel Streamlit (app.py)."""
    project_root = Path(__file__).resolve().parent
    typer.echo(f"A lançar o painel em http://localhost:{port}")
    import contextlib

    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(project_root / "app.py"),
        "--server.port",
        str(port),
    ]
    with contextlib.suppress(KeyboardInterrupt):
        subprocess.run(command, check=True)


def _rows_from_properties(properties: list[Property]) -> list[dict[str, Any]]:
    return [
        {
            "id": p.id,
            "score": p.score,
            "classification": p.classification,
            "title": p.title,
            "price": p.price,
            "currency": p.currency,
            "usable_area_m2": p.usable_area_m2,
            "price_per_m2": p.price_per_m2,
            "municipality": p.municipality,
            "parish": p.parish,
            "distance_from_povoa_km": p.distance_from_povoa_km,
            "source": p.source,
            "renovation_level": p.renovation_level,
            "occupancy_status": p.occupancy_status,
            "legal_ownership_type": p.legal_ownership_type,
            "sale_method": p.sale_method,
            "status": p.status,
            "auction_end_at": p.auction_end_at,
            "url": p.url,
            "first_seen_at": p.first_seen_at,
            "last_seen_at": p.last_seen_at,
        }
        for p in properties
    ]


def _count_classifications(properties: list[Property]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for prop in properties:
        counts[prop.classification] = counts.get(prop.classification, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))


if __name__ == "__main__":
    app()
