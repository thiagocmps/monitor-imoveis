"""Modelos ORM (SQLAlchemy 2.x) para SQLite.

Sem campos relacionados com vista de mar, proximidade da costa ou
distância ao mar, conforme os requisitos do projeto.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from monitor.database.base import Base


def _utcnow() -> datetime:
    return datetime.utcnow()


class Property(Base):
    __tablename__ = "properties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_fingerprint: Mapped[str] = mapped_column(String(64), index=True, default="")
    source: Mapped[str] = mapped_column(String(64), index=True)
    source_reference: Mapped[str | None] = mapped_column(String(128), index=True)
    source_listing_id: Mapped[str | None] = mapped_column(String(128), index=True)
    url: Mapped[str] = mapped_column(Text)
    normalized_url: Mapped[str] = mapped_column(Text, index=True)
    title: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    property_type: Mapped[str] = mapped_column(String(32), default="UNKNOWN", index=True)
    typology: Mapped[str | None] = mapped_column(String(16), index=True)
    price: Mapped[float | None] = mapped_column(Float, index=True)
    base_value: Mapped[float | None] = mapped_column(Float)
    minimum_value: Mapped[float | None] = mapped_column(Float)
    tax_value: Mapped[float | None] = mapped_column(Float)
    currency: Mapped[str] = mapped_column(String(8), default="EUR")
    usable_area_m2: Mapped[float | None] = mapped_column(Float)
    gross_private_area_m2: Mapped[float | None] = mapped_column(Float)
    gross_area_m2: Mapped[float | None] = mapped_column(Float)
    total_area_m2: Mapped[float | None] = mapped_column(Float)
    land_area_m2: Mapped[float | None] = mapped_column(Float)
    price_per_m2: Mapped[float | None] = mapped_column(Float)
    district: Mapped[str | None] = mapped_column(String(64), index=True)
    municipality: Mapped[str | None] = mapped_column(String(64), index=True)
    parish: Mapped[str | None] = mapped_column(String(64), index=True)
    locality: Mapped[str | None] = mapped_column(String(128))
    address: Mapped[str | None] = mapped_column(Text)
    postal_code: Mapped[str | None] = mapped_column(String(16), index=True)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    geolocation_accuracy: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    distance_from_povoa_km: Mapped[float | None] = mapped_column(Float, index=True)
    renovation_level: Mapped[str] = mapped_column(
        String(40), default="NOT_IDENTIFIED", index=True
    )
    condition_text: Mapped[str | None] = mapped_column(Text)
    legal_ownership_type: Mapped[str] = mapped_column(String(32), default="UNKNOWN", index=True)
    legal_status: Mapped[str] = mapped_column(String(32), default="ACCEPTED", index=True)
    occupancy_status: Mapped[str] = mapped_column(String(32), default="UNKNOWN", index=True)
    visit_status: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    key_delivery_status: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    sale_method: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    auction_start_at: Mapped[datetime | None] = mapped_column(DateTime)
    auction_end_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    court: Mapped[str | None] = mapped_column(String(128))
    legal_process: Mapped[str | None] = mapped_column(String(128), index=True)
    registration_number: Mapped[str | None] = mapped_column(String(128))
    tax_article: Mapped[str | None] = mapped_column(String(128))
    main_image_url: Mapped[str | None] = mapped_column(Text)
    bedrooms: Mapped[int | None] = mapped_column(Integer)
    bathrooms: Mapped[int | None] = mapped_column(Integer)
    floor: Mapped[str | None] = mapped_column(String(16))
    has_elevator: Mapped[bool | None] = mapped_column(Boolean)
    has_garage: Mapped[bool | None] = mapped_column(Boolean)
    has_balcony: Mapped[bool | None] = mapped_column(Boolean)
    has_terrace: Mapped[bool | None] = mapped_column(Boolean)
    has_garden: Mapped[bool | None] = mapped_column(Boolean)
    has_yard: Mapped[bool | None] = mapped_column(Boolean)
    energy_certificate: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), default="ACTIVE", index=True)
    score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    classification: Mapped[str] = mapped_column(String(24), default="EXCLUDE", index=True)
    score_reasons_json: Mapped[str] = mapped_column(Text, default="[]")
    legal_alerts_json: Mapped[str] = mapped_column(Text, default="[]")
    technical_alerts_json: Mapped[str] = mapped_column(Text, default="[]")
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)
    raw_data_json: Mapped[str] = mapped_column(Text, default="{}")

    observations: Mapped[list[PropertyObservation]] = relationship(
        back_populates="property_", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("source", "normalized_url", name="uq_property_source_url"),
    )


class PropertyObservation(Base):
    __tablename__ = "property_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(64))
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    price: Mapped[float | None] = mapped_column(Float)
    base_value: Mapped[float | None] = mapped_column(Float)
    minimum_value: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str | None] = mapped_column(String(24))
    auction_end_at: Mapped[datetime | None] = mapped_column(DateTime)
    content_hash: Mapped[str] = mapped_column(String(64), index=True, default="")
    raw_data_json: Mapped[str] = mapped_column(Text, default="{}")

    property_: Mapped[Property] = relationship(back_populates="observations")


class SourceRun(Base):
    __tablename__ = "source_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(24), default="RUNNING", index=True)
    pages_visited: Mapped[int] = mapped_column(Integer, default=0)
    items_found: Mapped[int] = mapped_column(Integer, default=0)
    items_accepted: Mapped[int] = mapped_column(Integer, default=0)
    items_rejected: Mapped[int] = mapped_column(Integer, default=0)
    items_new: Mapped[int] = mapped_column(Integer, default=0)
    items_updated: Mapped[int] = mapped_column(Integer, default=0)
    errors_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)


class PropertyMatch(Base):
    __tablename__ = "property_matches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id_a: Mapped[int] = mapped_column(Integer, index=True)
    property_id_b: Mapped[int] = mapped_column(Integer, index=True)
    similarity_score: Mapped[float] = mapped_column(Float, default=0.0)
    match_reason: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="POSSIBLE_DUPLICATE", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    __table_args__ = (
        UniqueConstraint("property_id_a", "property_id_b", name="uq_match_pair"),
    )


class UserDecision(Base):
    __tablename__ = "user_decisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    property_id: Mapped[int] = mapped_column(
        ForeignKey("properties.id", ondelete="CASCADE"), index=True
    )
    decision: Mapped[str] = mapped_column(String(32), index=True)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)


class ErrorRecord(Base):
    __tablename__ = "errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    url: Mapped[str | None] = mapped_column(Text)
    error_type: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
    traceback: Mapped[str | None] = mapped_column(Text)
    screenshot_path: Mapped[str | None] = mapped_column(Text)
    html_snapshot_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class ApplicationEventRecord(Base):
    __tablename__ = "application_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(32), index=True)
    property_id: Mapped[int | None] = mapped_column(Integer, index=True)
    source: Mapped[str | None] = mapped_column(String(64), index=True)
    message: Mapped[str] = mapped_column(Text, default="")
    previous_value: Mapped[object | None] = mapped_column(JSON)
    new_value: Mapped[object | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class SettingsOverride(Base):
    __tablename__ = "settings_overrides"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[object] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )
