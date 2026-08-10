"""Orquestração do ciclo de recolha por fonte.

Cada fonte percorre: recolha bruta -> normalização -> filtragem -> pontuação
-> histórico (upsert) -> eventos -> notificações. Falhas numa fonte não
interrompem as restantes.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

import httpx

from monitor.collectors.base import BaseCollector, CollectorContext
from monitor.collectors.registry import get_registry
from monitor.database.migrations import initialize_database
from monitor.database.repository import Repository
from monitor.database.session import Database
from monitor.models.events import ApplicationEvent
from monitor.services.filtering import apply_filters
from monitor.services.history import HistoryService
from monitor.services.notifications import Notifier, build_notifier
from monitor.services.pipeline import normalize_listing
from monitor.services.scoring import score_property
from monitor.settings import Settings, apply_overrides

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
    ),
}


async def run_collection(
    settings: Settings,
    *,
    sources: list[str] | None = None,
    notifier: Notifier | None = None,
) -> dict[str, Any]:
    """Executa a recolha das fontes pedidas e devolve um resumo por fonte."""
    registry = get_registry()
    db = Database(settings)
    initialize_database(db.engine)
    notifier = notifier or build_notifier()
    summary: dict[str, Any] = {}

    # Overrides de configuração definidos no dashboard (aplicam-se nesta recolha).
    override_session = db.new_session()
    try:
        overrides = Repository(override_session).get_override("search")
    finally:
        override_session.close()
    if overrides:
        settings = apply_overrides(settings, overrides)
        logger.info("Overrides de configuração aplicados: %s", sorted(overrides))

    async with httpx.AsyncClient(
        headers=_HEADERS,
        timeout=httpx.Timeout(30.0),
        follow_redirects=True,
    ) as client:
        for source in _resolve_sources(settings, sources):
            if not registry.is_implemented(source):
                logger.info("Fonte %s não implementada; a ignorar.", source)
                continue
            summary[source] = await _collect_source(
                settings, db, registry, client, source, notifier
            )
    return summary


async def _collect_source(
    settings: Settings,
    db: Database,
    registry,
    client: httpx.AsyncClient,
    source: str,
    notifier: Notifier,
) -> dict[str, Any]:
    session = db.new_session()
    run = None
    try:
        repo = Repository(session)
        history = HistoryService(repo, settings.history)
        run = repo.start_source_run(source)
        session.commit()
        context = CollectorContext(
            source=source,
            settings=settings,
            client=client,
            logger=logger,
        )
        collector = registry.create(source, context)
        stats = await _run_collector(collector, settings, repo, history, notifier)
        repo.finish_source_run(run, status="COMPLETED", **stats)
        session.commit()
        return {"status": "COMPLETED", **stats}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Falha na recolha da fonte %s", source)
        try:
            session.rollback()
            repo = Repository(session)
            repo.record_error(
                source=source,
                url=None,
                error_type=type(exc).__name__,
                message=str(exc),
                traceback=traceback.format_exc(),
            )
            if run is not None:
                repo.finish_source_run(
                    run, status="FAILED", errors_count=1, error_message=str(exc)
                )
            session.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao registar o erro da fonte %s", source)
        return {"status": "FAILED", "error": str(exc)}
    finally:
        session.close()


async def _run_collector(
    collector: BaseCollector,
    settings: Settings,
    repo: Repository,
    history: HistoryService,
    notifier: Notifier,
) -> dict[str, Any]:
    listings = await collector.search()
    raw_listings = [await collector.fetch_detail(raw) for raw in listings]

    seen_urls: set[str] = set()
    events: list[ApplicationEvent] = []
    new = updated = accepted = rejected = 0

    for raw in raw_listings:
        normalized = normalize_listing(raw)
        seen_urls.add(normalized.normalized_url)

        result = apply_filters(normalized, settings.search)
        if not result.accepted:
            rejected += 1
            logger.debug(
                "Rejeitado (%s): %s — %s",
                collector.source_name,
                normalized.title,
                "; ".join(result.rejected_reasons),
            )
            continue
        accepted += 1

        score, classification, reasons = score_property(
            normalized, settings.scoring, settings.search
        )
        normalized.score = score
        normalized.classification = classification
        normalized.score_reasons_json = reasons

        upsert = history.upsert(normalized, raw)
        events.extend(upsert.events)
        if upsert.is_new:
            new += 1
        else:
            updated += 1

    removed_events = history.mark_missing_properties_removed(
        collector.source_name, seen_urls
    )
    events.extend(removed_events)

    for event in events:
        repo.record_event(event)
    notifier.notify(events)

    return {
        "pages_visited": collector.context.pages_visited,
        "items_found": len(raw_listings),
        "items_accepted": accepted,
        "items_rejected": rejected,
        "items_new": new,
        "items_updated": updated,
        "errors_count": 0,
    }


def _resolve_sources(settings: Settings, sources: list[str] | None) -> list[str]:
    if sources:
        return sources
    return settings.enabled_sources
