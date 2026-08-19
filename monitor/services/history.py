"""Serviço de histórico: persistência incremental e deteção de alterações.

A cada execução:
  1. identifica anúncios novos;
  2. atualiza a última verificação;
  3. cria observação;
  4. compara preço, estado e prazo;
  5. regista eventos (redução, aumento, vendido, removido, reativado).

Não marca um anúncio como removido após apenas uma falha: usa
`missing_checks_before_removed` do histórico de verificações.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from monitor.database.models import (
    Property,
    PropertyObservation,
)
from monitor.database.repository import Repository, property_from_normalized
from monitor.models.enums import EventType, ListingStatus
from monitor.models.events import ApplicationEvent
from monitor.models.normalized import NormalizedProperty
from monitor.models.raw import RawPropertyListing
from monitor.settings import HistorySettings

logger = logging.getLogger(__name__)


def _content_hash(raw: RawPropertyListing) -> str:
    payload = json.dumps(raw.raw_data, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class UpsertResult:
    property: Property
    is_new: bool = False
    events: list[ApplicationEvent] = field(default_factory=list)
    price_dropped: bool = False


class HistoryService:
    def __init__(
        self,
        repository: Repository,
        settings: HistorySettings | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings or HistorySettings()

    def upsert(
        self,
        normalized: NormalizedProperty,
        raw: RawPropertyListing,
        *,
        observed_at: datetime | None = None,
    ) -> UpsertResult:
        observed_at = observed_at or datetime.now(UTC).replace(tzinfo=None)
        existing = self._find_existing(normalized)

        if existing is None:
            record = property_from_normalized(normalized, raw)
            record.last_seen_at = observed_at
            record.last_active_at = observed_at
            self.repository.add(record)
            self.repository.session.flush()
            observation = PropertyObservation(
                property_id=record.id,
                source=normalized.source,
                checked_at=observed_at,
                price=normalized.price,
                base_value=normalized.base_value,
                minimum_value=normalized.minimum_value,
                status=normalized.status.value,
                auction_end_at=normalized.auction_end_at,
                content_hash=_content_hash(raw),
                raw_data_json=json.dumps(raw.raw_data, ensure_ascii=False, default=str),
            )
            self.repository.add_observation(observation)
            events = [
                ApplicationEvent(
                    event_type=EventType.NEW_LISTING,
                    property_id=record.id,
                    source=normalized.source,
                    message=f"Novo anúncio: {normalized.title or normalized.normalized_url}",
                )
            ]
            return UpsertResult(property=record, is_new=True, events=events)

        return self._update(existing, normalized, raw, observed_at)

    def _find_existing(self, normalized: NormalizedProperty) -> Property | None:
        if normalized.source_reference:
            found = self.repository.find_by_source_reference(
                normalized.source, normalized.source_reference
            )
            if found:
                return found
        if normalized.source_listing_id:
            found = self.repository.find_by_source_listing_id(
                normalized.source, normalized.source_listing_id
            )
            if found:
                return found
        return self.repository.find_by_normalized_url(normalized.source, normalized.normalized_url)

    def _update(
        self,
        record: Property,
        normalized: NormalizedProperty,
        raw: RawPropertyListing,
        observed_at: datetime,
    ) -> UpsertResult:
        events: list[ApplicationEvent] = []
        price_dropped = False

        # Reativação
        if record.status in {ListingStatus.REMOVED.value, ListingStatus.SOLD.value}:
            if normalized.status is ListingStatus.ACTIVE:
                record.status = ListingStatus.ACTIVE.value
                record.removed_at = None
                events.append(
                    ApplicationEvent(
                        event_type=EventType.REACTIVATED,
                        property_id=record.id,
                        source=normalized.source,
                        message="Anúncio reativado",
                        previous_value=record.status,
                        new_value=normalized.status.value,
                    )
                )

        # Preço
        if _different(record.price, normalized.price):
            previous = record.price
            if previous is not None and normalized.price is not None:
                if normalized.price < previous:
                    price_dropped = True
                event_type = (
                    EventType.PRICE_DECREASE if price_dropped else EventType.PRICE_INCREASE
                )
                events.append(
                    ApplicationEvent(
                        event_type=event_type,
                        property_id=record.id,
                        source=normalized.source,
                        message=f"Preço alterado: {previous} -> {normalized.price}",
                        previous_value=previous,
                        new_value=normalized.price,
                    )
                )
            record.price = normalized.price

        # Prazo de leilão
        if _different(_as_iso(record.auction_end_at), _as_iso(normalized.auction_end_at)):
            events.append(
                ApplicationEvent(
                    event_type=EventType.AUCTION_END_CHANGED,
                    property_id=record.id,
                    source=normalized.source,
                    message="Prazo de leilão alterado",
                    previous_value=_as_iso(record.auction_end_at),
                    new_value=_as_iso(normalized.auction_end_at),
                )
            )
            record.auction_end_at = normalized.auction_end_at

        # Estado
        if record.status != normalized.status.value:
            if normalized.status is ListingStatus.SOLD:
                event_type = EventType.SOLD
                record.removed_at = observed_at
            elif normalized.status is ListingStatus.REMOVED:
                event_type = EventType.REMOVED
                record.removed_at = observed_at
            else:
                event_type = EventType.STATUS_CHANGED
            events.append(
                ApplicationEvent(
                    event_type=event_type,
                    property_id=record.id,
                    source=normalized.source,
                    message=f"Estado alterado: {record.status} -> {normalized.status.value}",
                    previous_value=record.status,
                    new_value=normalized.status.value,
                )
            )
            record.status = normalized.status.value

        # Ocupação
        if record.occupancy_status != normalized.occupancy_status.value:
            events.append(
                ApplicationEvent(
                    event_type=EventType.OCCUPANCY_CHANGED,
                    property_id=record.id,
                    source=normalized.source,
                    message="Situação de ocupação alterada",
                    previous_value=record.occupancy_status,
                    new_value=normalized.occupancy_status.value,
                )
            )
            record.occupancy_status = normalized.occupancy_status.value

        # Atualização de campos relevantes
        record.last_seen_at = observed_at
        record.last_active_at = observed_at
        record.title = normalized.title
        record.description = normalized.description
        record.base_value = normalized.base_value
        record.minimum_value = normalized.minimum_value
        record.condition_text = normalized.condition_text
        record.renovation_level = normalized.renovation_level.value
        record.visit_status = normalized.visit_status.value
        record.score = normalized.score
        record.classification = normalized.classification.value
        record.score_reasons_json = normalized.score_reasons_json
        record.canonical_fingerprint = normalized.canonical_fingerprint

        observation = PropertyObservation(
            property_id=record.id,
            source=normalized.source,
            checked_at=observed_at,
            price=normalized.price,
            base_value=normalized.base_value,
            minimum_value=normalized.minimum_value,
            status=normalized.status.value,
            auction_end_at=normalized.auction_end_at,
            content_hash=_content_hash(raw),
            raw_data_json=json.dumps(raw.raw_data, ensure_ascii=False, default=str),
        )
        self.repository.add_observation(observation)

        return UpsertResult(property=record, is_new=False, events=events, price_dropped=price_dropped)

    def mark_missing_properties_removed(self, source: str, seen_urls: set[str]) -> list[ApplicationEvent]:
        """Marca como removidos anúncios ativos da fonte ausentes em N verificações."""
        events: list[ApplicationEvent] = []
        missing = self.repository.list_properties(source=source, status=ListingStatus.ACTIVE.value)
        for prop in missing:
            if prop.normalized_url in seen_urls:
                continue
            recent = self.repository.observations_for(prop.id)
            if recent and len(recent) >= self.settings.missing_checks_before_removed:
                prop.status = ListingStatus.REMOVED.value
                prop.removed_at = datetime.now(UTC).replace(tzinfo=None)
                events.append(
                    ApplicationEvent(
                        event_type=EventType.REMOVED,
                        property_id=prop.id,
                        source=source,
                        message="Anúncio não confirmado em várias verificações",
                    )
                )
        return events


def _different(a, b) -> bool:
    if a is None and b is None:
        return False
    return a != b


def _as_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
