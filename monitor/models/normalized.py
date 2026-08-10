"""Modelo normalizado de um imóvel, pronto a persistir e pontuar."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from monitor.models.enums import (
    Classification,
    GeolocationAccuracy,
    KeyDeliveryStatus,
    LegalOwnershipType,
    LegalStatus,
    ListingStatus,
    OccupancyStatus,
    PropertyType,
    RenovationLevel,
    SaleMethod,
    VisitStatus,
)


class NormalizedProperty(BaseModel):
    source: str
    source_reference: str | None = None
    source_listing_id: str | None = None
    url: str
    normalized_url: str
    title: str | None = None
    description: str | None = None
    property_type: PropertyType = PropertyType.UNKNOWN
    typology: str | None = None
    price: float | None = None
    base_value: float | None = None
    minimum_value: float | None = None
    tax_value: float | None = None
    currency: str = "EUR"
    usable_area_m2: float | None = None
    gross_private_area_m2: float | None = None
    gross_area_m2: float | None = None
    total_area_m2: float | None = None
    land_area_m2: float | None = None
    price_per_m2: float | None = None
    district: str | None = None
    municipality: str | None = None
    parish: str | None = None
    locality: str | None = None
    address: str | None = None
    postal_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    geolocation_accuracy: GeolocationAccuracy = GeolocationAccuracy.UNKNOWN
    distance_from_povoa_km: float | None = None
    renovation_level: RenovationLevel = RenovationLevel.NOT_IDENTIFIED
    condition_text: str | None = None
    legal_ownership_type: LegalOwnershipType = LegalOwnershipType.UNKNOWN
    legal_status: LegalStatus = LegalStatus.ACCEPTED
    occupancy_status: OccupancyStatus = OccupancyStatus.UNKNOWN
    visit_status: VisitStatus = VisitStatus.UNKNOWN
    key_delivery_status: KeyDeliveryStatus = KeyDeliveryStatus.UNKNOWN
    sale_method: SaleMethod = SaleMethod.UNKNOWN
    auction_start_at: datetime | None = None
    auction_end_at: datetime | None = None
    court: str | None = None
    legal_process: str | None = None
    registration_number: str | None = None
    tax_article: str | None = None
    main_image_url: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    floor: str | None = None
    has_elevator: bool | None = None
    has_garage: bool | None = None
    has_balcony: bool | None = None
    has_terrace: bool | None = None
    has_garden: bool | None = None
    has_yard: bool | None = None
    energy_certificate: str | None = None
    status: ListingStatus = ListingStatus.ACTIVE
    score: float = 0.0
    classification: Classification = Classification.EXCLUDE
    score_reasons_json: str = Field(default_factory=lambda: "[]")
    legal_alerts: list[str] = Field(default_factory=list)
    technical_alerts: list[str] = Field(default_factory=list)
    canonical_fingerprint: str = ""

    model_config = {"extra": "forbid"}
