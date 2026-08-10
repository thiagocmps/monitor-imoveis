"""Modelos brutos — tal como são extraídos das fontes, sem normalização."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RawPropertyListing(BaseModel):
    """Anúncio bruto extraído de uma fonte.

    Todos os campos são opcionais: nunca inventamos informação. Valores em
    falta ficam a None até à normalização.
    """

    source: str
    url: str
    source_reference: str | None = None
    source_listing_id: str | None = None
    lot_number: str | None = None
    title: str | None = None
    description: str | None = None
    property_type: str | None = None
    typology: str | None = None
    price_text: str | None = None
    price_value: float | None = None
    base_value_text: str | None = None
    base_value: float | None = None
    minimum_value_text: str | None = None
    minimum_value: float | None = None
    tax_value_text: str | None = None
    tax_value: float | None = None
    currency: str | None = None
    usable_area_text: str | None = None
    usable_area_m2: float | None = None
    gross_private_area_text: str | None = None
    gross_private_area_m2: float | None = None
    gross_area_text: str | None = None
    gross_area_m2: float | None = None
    total_area_text: str | None = None
    total_area_m2: float | None = None
    land_area_text: str | None = None
    land_area_m2: float | None = None
    district: str | None = None
    municipality: str | None = None
    parish: str | None = None
    locality: str | None = None
    address: str | None = None
    postal_code: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    condition_text: str | None = None
    occupancy_text: str | None = None
    visit_text: str | None = None
    key_delivery_text: str | None = None
    sale_method_text: str | None = None
    auction_start_at: datetime | None = None
    auction_end_at: datetime | None = None
    auction_start_text: str | None = None
    auction_end_text: str | None = None
    court: str | None = None
    legal_process: str | None = None
    registration_number: str | None = None
    tax_article: str | None = None
    main_image_url: str | None = None
    energy_certificate: str | None = None
    bedrooms: int | None = None
    bathrooms: int | None = None
    floor: str | None = None
    has_elevator: bool | None = None
    has_garage: bool | None = None
    has_balcony: bool | None = None
    has_terrace: bool | None = None
    has_garden: bool | None = None
    has_yard: bool | None = None
    public_contacts: str | None = None
    listing_status_text: str | None = None
    raw_data: dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "allow"}
