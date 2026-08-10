"""Camada de acesso a dados (repository)."""

from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from monitor.database.models import (
    ApplicationEventRecord,
    ErrorRecord,
    Property,
    PropertyMatch,
    PropertyObservation,
    SourceRun,
    UserDecision,
)
from monitor.models.events import ApplicationEvent
from monitor.models.normalized import NormalizedProperty
from monitor.models.raw import RawPropertyListing

logger = logging.getLogger(__name__)


def property_from_normalized(normalized: NormalizedProperty, raw: RawPropertyListing | None = None) -> Property:
    """Constrói um registo Property (ORM) a partir do modelo normalizado."""
    now = datetime.utcnow()
    record = Property(
        canonical_fingerprint=normalized.canonical_fingerprint,
        source=normalized.source,
        source_reference=normalized.source_reference,
        source_listing_id=normalized.source_listing_id,
        url=normalized.url,
        normalized_url=normalized.normalized_url,
        title=normalized.title,
        description=normalized.description,
        property_type=normalized.property_type.value,
        typology=normalized.typology,
        price=normalized.price,
        base_value=normalized.base_value,
        minimum_value=normalized.minimum_value,
        tax_value=normalized.tax_value,
        currency=normalized.currency,
        usable_area_m2=normalized.usable_area_m2,
        gross_private_area_m2=normalized.gross_private_area_m2,
        gross_area_m2=normalized.gross_area_m2,
        total_area_m2=normalized.total_area_m2,
        land_area_m2=normalized.land_area_m2,
        price_per_m2=normalized.price_per_m2,
        district=normalized.district,
        municipality=normalized.municipality,
        parish=normalized.parish,
        locality=normalized.locality,
        address=normalized.address,
        postal_code=normalized.postal_code,
        latitude=normalized.latitude,
        longitude=normalized.longitude,
        geolocation_accuracy=normalized.geolocation_accuracy.value,
        distance_from_povoa_km=normalized.distance_from_povoa_km,
        renovation_level=normalized.renovation_level.value,
        condition_text=normalized.condition_text,
        legal_ownership_type=normalized.legal_ownership_type.value,
        legal_status=normalized.legal_status.value,
        occupancy_status=normalized.occupancy_status.value,
        visit_status=normalized.visit_status.value,
        key_delivery_status=normalized.key_delivery_status.value,
        sale_method=normalized.sale_method.value,
        auction_start_at=normalized.auction_start_at,
        auction_end_at=normalized.auction_end_at,
        court=normalized.court,
        legal_process=normalized.legal_process,
        registration_number=normalized.registration_number,
        tax_article=normalized.tax_article,
        main_image_url=normalized.main_image_url,
        bedrooms=normalized.bedrooms,
        bathrooms=normalized.bathrooms,
        floor=normalized.floor,
        has_elevator=normalized.has_elevator,
        has_garage=normalized.has_garage,
        has_balcony=normalized.has_balcony,
        has_terrace=normalized.has_terrace,
        has_garden=normalized.has_garden,
        has_yard=normalized.has_yard,
        energy_certificate=normalized.energy_certificate,
        status=normalized.status.value,
        score=normalized.score,
        classification=normalized.classification.value,
        score_reasons_json=normalized.score_reasons_json,
        legal_alerts_json=json.dumps(normalized.legal_alerts, ensure_ascii=False),
        technical_alerts_json=json.dumps(normalized.technical_alerts, ensure_ascii=False),
        first_seen_at=now,
        last_seen_at=now,
        last_active_at=now,
        raw_data_json=json.dumps(raw.raw_data if raw else {}, ensure_ascii=False, default=str),
    )
    return record


class Repository:
    """Operações de persistência usadas pelo coletor e pelo painel."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # ---- properties ----

    def find_by_normalized_url(self, source: str, normalized_url: str) -> Property | None:
        stmt = select(Property).where(
            Property.source == source, Property.normalized_url == normalized_url
        )
        return self.session.scalar(stmt)

    def find_by_source_reference(self, source: str, reference: str) -> Property | None:
        stmt = select(Property).where(
            Property.source == source, Property.source_reference == reference
        )
        return self.session.scalar(stmt)

    def find_by_source_listing_id(self, source: str, listing_id: str) -> Property | None:
        stmt = select(Property).where(
            Property.source == source, Property.source_listing_id == listing_id
        )
        return self.session.scalar(stmt)

    def find_by_fingerprint(self, fingerprint: str) -> Property | None:
        stmt = select(Property).where(Property.canonical_fingerprint == fingerprint)
        return self.session.scalar(stmt)

    def get(self, property_id: int) -> Property | None:
        return self.session.get(Property, property_id)

    def add(self, record: Property) -> Property:
        self.session.add(record)
        return record

    def count_active(self) -> int:
        stmt = select(func.count(Property.id)).where(Property.status == "ACTIVE")
        return int(self.session.scalar(stmt) or 0)

    def count_new_since(self, since: datetime) -> int:
        stmt = select(func.count(Property.id)).where(Property.first_seen_at >= since)
        return int(self.session.scalar(stmt) or 0)

    def list_properties(
        self,
        *,
        status: str | None = None,
        municipality: str | None = None,
        source: str | None = None,
        limit: int | None = None,
    ) -> list[Property]:
        stmt = select(Property)
        if status:
            stmt = stmt.where(Property.status == status)
        if municipality:
            stmt = stmt.where(Property.municipality == municipality)
        if source:
            stmt = stmt.where(Property.source == source)
        stmt = stmt.order_by(Property.score.desc())
        if limit:
            stmt = stmt.limit(limit)
        return list(self.session.scalars(stmt))

    # ---- observations ----

    def add_observation(self, observation: PropertyObservation) -> None:
        self.session.add(observation)

    def observations_for(self, property_id: int) -> list[PropertyObservation]:
        stmt = (
            select(PropertyObservation)
            .where(PropertyObservation.property_id == property_id)
            .order_by(PropertyObservation.checked_at.desc())
        )
        return list(self.session.scalars(stmt))

    # ---- source runs ----

    def start_source_run(self, source: str) -> SourceRun:
        run = SourceRun(source=source, status="RUNNING")
        self.session.add(run)
        return run

    def finish_source_run(
        self,
        run: SourceRun,
        *,
        status: str,
        pages_visited: int = 0,
        items_found: int = 0,
        items_accepted: int = 0,
        items_rejected: int = 0,
        items_new: int = 0,
        items_updated: int = 0,
        errors_count: int = 0,
        error_message: str | None = None,
    ) -> None:
        run.finished_at = datetime.utcnow()
        run.status = status
        run.pages_visited = pages_visited
        run.items_found = items_found
        run.items_accepted = items_accepted
        run.items_rejected = items_rejected
        run.items_new = items_new
        run.items_updated = items_updated
        run.errors_count = errors_count
        run.error_message = error_message

    def latest_run(self, source: str | None = None) -> SourceRun | None:
        stmt = select(SourceRun).order_by(SourceRun.started_at.desc())
        if source:
            stmt = stmt.where(SourceRun.source == source)
        return self.session.scalar(stmt)

    # ---- matches ----

    def add_match(self, match: PropertyMatch) -> None:
        self.session.add(match)

    def matches_for(self, property_id: int) -> list[PropertyMatch]:
        stmt = select(PropertyMatch).where(
            (PropertyMatch.property_id_a == property_id)
            | (PropertyMatch.property_id_b == property_id)
        )
        return list(self.session.scalars(stmt))

    # ---- decisions ----

    def set_decision(self, property_id: int, decision: str, notes: str | None = None) -> UserDecision:
        stmt = select(UserDecision).where(UserDecision.property_id == property_id)
        existing = self.session.scalar(stmt)
        if existing:
            existing.decision = decision
            existing.notes = notes
            existing.updated_at = datetime.utcnow()
            return existing
        record = UserDecision(property_id=property_id, decision=decision, notes=notes)
        self.session.add(record)
        return record

    def decision_for(self, property_id: int) -> UserDecision | None:
        stmt = select(UserDecision).where(UserDecision.property_id == property_id)
        return self.session.scalar(stmt)

    # ---- errors ----

    def record_error(
        self,
        *,
        source: str,
        url: str | None,
        error_type: str,
        message: str,
        traceback: str | None = None,
        screenshot_path: str | None = None,
        html_snapshot_path: str | None = None,
    ) -> None:
        record = ErrorRecord(
            source=source,
            url=url,
            error_type=error_type,
            message=message,
            traceback=traceback,
            screenshot_path=screenshot_path,
            html_snapshot_path=html_snapshot_path,
        )
        self.session.add(record)

    # ---- events ----

    def record_event(self, event: ApplicationEvent) -> None:
        record = ApplicationEventRecord(
            event_type=event.event_type.value,
            property_id=event.property_id,
            source=event.source,
            message=event.message,
            previous_value=event.previous_value,
            new_value=event.new_value,
            created_at=event.created_at,
        )
        self.session.add(record)

    def recent_events(self, limit: int = 200) -> list[ApplicationEventRecord]:
        stmt = select(ApplicationEventRecord).order_by(
            ApplicationEventRecord.created_at.desc()
        ).limit(limit)
        return list(self.session.scalars(stmt))

    def events_for_property(self, property_id: int, limit: int = 100) -> list[ApplicationEventRecord]:
        stmt = (
            select(ApplicationEventRecord)
            .where(ApplicationEventRecord.property_id == property_id)
            .order_by(ApplicationEventRecord.created_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))


