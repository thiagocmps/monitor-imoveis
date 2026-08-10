"""Testes da orquestração do ciclo de recolha com um coletor falso."""

from __future__ import annotations

import asyncio

from monitor.collectors.base import BaseCollector
from monitor.collectors.registry import get_registry
from monitor.database.models import (
    ApplicationEventRecord,
    ErrorRecord,
    PropertyObservation,
    SourceRun,
)
from monitor.database.repository import Repository
from monitor.database.session import Database
from monitor.models.raw import RawPropertyListing
from monitor.orchestration.pipeline import run_collection
from monitor.settings import ApplicationSettings, Settings, SourceSettings


class FakeCollector(BaseCollector):
    source_name = "fake"

    async def search(self) -> list[RawPropertyListing]:
        return [
            RawPropertyListing(
                source=self.source_name,
                url="https://exemplo.pt/a",
                title="Apartamento T2",
                description="Apartamento T2 desocupado.",
                price_value=90_000,
                base_value=90_000,
                municipality="Póvoa de Varzim",
            ),
            RawPropertyListing(
                source=self.source_name,
                url="https://exemplo.pt/b",
                title="Loja comercial",
                description="Loja comercial para arrendar.",
                price_value=80_000,
                base_value=80_000,
                municipality="Póvoa de Varzim",
            ),
        ]


class BrokenCollector(BaseCollector):
    source_name = "broken"

    async def search(self) -> list[RawPropertyListing]:
        raise RuntimeError("site em baixo")


def _settings(tmp_path) -> Settings:
    return Settings(
        application=ApplicationSettings(database_path=str(tmp_path / "test.db")),
        sources={
            "fake": SourceSettings(enabled=True, delay_seconds=0),
            "broken": SourceSettings(enabled=True, delay_seconds=0),
        },
    )


def _register_fakes() -> None:
    registry = get_registry()
    registry.register("fake", FakeCollector, implemented=True)
    registry.register("broken", BrokenCollector, implemented=True)


def test_run_collection_persists_and_filters(tmp_path) -> None:
    _register_fakes()
    settings = _settings(tmp_path)
    summary = asyncio.run(run_collection(settings, sources=["fake"]))

    assert summary["fake"]["status"] == "COMPLETED"
    assert summary["fake"]["items_found"] == 2
    assert summary["fake"]["items_accepted"] == 1
    assert summary["fake"]["items_rejected"] == 1
    assert summary["fake"]["items_new"] == 1

    session = Database(settings).new_session()
    try:
        repo = Repository(session)
        properties = repo.list_properties(status="ACTIVE")
        assert len(properties) == 1
        stored = properties[0]
        assert stored.source == "fake"
        assert stored.municipality == "Póvoa de Varzim"
        assert stored.price == 90_000

        assert len(session.query(PropertyObservation).all()) == 1

        events = session.query(ApplicationEventRecord).all()
        assert any(event.event_type == "NEW_LISTING" for event in events)

        run = repo.latest_run("fake")
        assert run is not None
        assert run.status == "COMPLETED"
        assert run.items_found == 2
        assert run.items_rejected == 1
    finally:
        session.close()


def test_run_collection_second_run_updates(tmp_path) -> None:
    _register_fakes()
    settings = _settings(tmp_path)
    asyncio.run(run_collection(settings, sources=["fake"]))
    second = asyncio.run(run_collection(settings, sources=["fake"]))

    assert second["fake"]["items_new"] == 0
    assert second["fake"]["items_updated"] == 1

    session = Database(settings).new_session()
    try:
        repo = Repository(session)
        properties = repo.list_properties(status="ACTIVE")
        assert len(properties) == 1
        run = repo.latest_run("fake")
        assert run.status == "COMPLETED"
        assert isinstance(run, SourceRun)
    finally:
        session.close()


def test_run_collection_failure_is_isolated(tmp_path) -> None:
    _register_fakes()
    settings = _settings(tmp_path)
    summary = asyncio.run(run_collection(settings, sources=["broken", "fake"]))

    assert summary["broken"]["status"] == "FAILED"
    assert summary["fake"]["status"] == "COMPLETED"

    session = Database(settings).new_session()
    try:
        repo = Repository(session)
        run = repo.latest_run("broken")
        assert run is not None
        assert run.status == "FAILED"
        errors = session.query(ErrorRecord).all()
        assert len(errors) == 1
        assert "site em baixo" in errors[0].message
    finally:
        session.close()
