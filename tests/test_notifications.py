"""Testes do serviço de notificações."""

from __future__ import annotations

from monitor.models.enums import EventType
from monitor.models.events import ApplicationEvent
from monitor.services.notifications import NoopNotifier


def test_noop_notifier_accepts_events() -> None:
    notifier = NoopNotifier()
    events = [
        ApplicationEvent(event_type=EventType.NEW_LISTING, message="Novo anúncio"),
        ApplicationEvent(event_type=EventType.PRICE_DECREASE, message="Preço baixou"),
    ]
    notifier.notify(events)


def test_noop_notifier_accepts_empty_list() -> None:
    NoopNotifier().notify([])
