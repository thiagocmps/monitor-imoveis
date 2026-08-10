"""Conversão de um anúncio bruto num imóvel normalizado.

Ponto único que combina os classificadores de `services/normalization`,
`services/status_detection`, `services/geocoding` e `services/deduplication`
para transformar um `RawPropertyListing` num `NormalizedProperty` pronto a
filtrar, pontuar e persistir. Nunca inventamos informação: o que não for
reconhecido fica como UNKNOWN/None.
"""

from __future__ import annotations

from monitor.models.enums import GeolocationAccuracy
from monitor.models.normalized import NormalizedProperty
from monitor.models.raw import RawPropertyListing
from monitor.services import deduplication
from monitor.services.geocoding import CENTER_LAT, CENTER_LON, geocode, haversine_km
from monitor.services.normalization import (
    classify_key_delivery,
    classify_legal_ownership,
    classify_occupancy,
    classify_renovation_level,
    classify_sale_method,
    classify_visit,
    clean_display_text,
    compute_price_per_m2,
    detect_property_type,
    identify_typology,
    normalize_url,
    parse_area,
    parse_price,
)
from monitor.services.status_detection import detect_listing_status


def normalize_listing(raw: RawPropertyListing) -> NormalizedProperty:
    """Converte um anúncio bruto num imóvel normalizado."""
    title = clean_display_text(raw.title)
    description = clean_display_text(raw.description)
    typology = raw.typology or identify_typology(f"{title} {description}")

    property_type = detect_property_type(title, description, typology)
    price = raw.price_value if raw.price_value is not None else parse_price(raw.price_text)
    base_value = raw.base_value if raw.base_value is not None else parse_price(raw.base_value_text)
    minimum_value = (
        raw.minimum_value if raw.minimum_value is not None else parse_price(raw.minimum_value_text)
    )
    tax_value = raw.tax_value if raw.tax_value is not None else parse_price(raw.tax_value_text)
    if price is None and base_value is not None:
        price = base_value

    usable_area_m2 = (
        raw.usable_area_m2 if raw.usable_area_m2 is not None else parse_area(raw.usable_area_text)
    )
    gross_private_area_m2 = (
        raw.gross_private_area_m2
        if raw.gross_private_area_m2 is not None
        else parse_area(raw.gross_private_area_text)
    )
    gross_area_m2 = (
        raw.gross_area_m2 if raw.gross_area_m2 is not None else parse_area(raw.gross_area_text)
    )
    total_area_m2 = (
        raw.total_area_m2 if raw.total_area_m2 is not None else parse_area(raw.total_area_text)
    )
    land_area_m2 = (
        raw.land_area_m2 if raw.land_area_m2 is not None else parse_area(raw.land_area_text)
    )

    renovation_level, _ = classify_renovation_level(description, raw.condition_text)
    legal_ownership_type, legal_status, legal_alerts = classify_legal_ownership(title, description)
    occupancy_status, _ = classify_occupancy(raw.occupancy_text or description)
    visit_status, _ = classify_visit(raw.visit_text or description)
    key_delivery_status, _ = classify_key_delivery(raw.key_delivery_text)
    sale_method = classify_sale_method(raw.sale_method_text or description)

    geo = geocode(
        municipality=raw.municipality,
        parish=raw.parish,
        locality=raw.locality,
        postal_code=raw.postal_code,
        address=raw.address,
        latitude=raw.latitude,
        longitude=raw.longitude,
    )
    distance = None
    if geo.latitude is not None and geo.longitude is not None:
        distance = round(
            haversine_km(CENTER_LAT, CENTER_LON, geo.latitude, geo.longitude), 2
        )

    normalized = NormalizedProperty(
        source=raw.source,
        source_reference=raw.source_reference,
        source_listing_id=raw.source_listing_id,
        url=raw.url,
        normalized_url=normalize_url(raw.url),
        title=title,
        description=description,
        property_type=property_type,
        typology=typology,
        price=price,
        base_value=base_value,
        minimum_value=minimum_value,
        tax_value=tax_value,
        currency=raw.currency or "EUR",
        usable_area_m2=usable_area_m2,
        gross_private_area_m2=gross_private_area_m2,
        gross_area_m2=gross_area_m2,
        total_area_m2=total_area_m2,
        land_area_m2=land_area_m2,
        price_per_m2=compute_price_per_m2(price, usable_area_m2),
        district=raw.district,
        municipality=raw.municipality,
        parish=raw.parish,
        locality=raw.locality,
        address=clean_display_text(raw.address),
        postal_code=raw.postal_code,
        latitude=geo.latitude,
        longitude=geo.longitude,
        geolocation_accuracy=GeolocationAccuracy(geo.accuracy),
        distance_from_povoa_km=distance,
        renovation_level=renovation_level,
        condition_text=clean_display_text(raw.condition_text),
        legal_ownership_type=legal_ownership_type,
        legal_status=legal_status,
        occupancy_status=occupancy_status,
        visit_status=visit_status,
        key_delivery_status=key_delivery_status,
        sale_method=sale_method,
        auction_start_at=raw.auction_start_at,
        auction_end_at=raw.auction_end_at,
        court=raw.court,
        legal_process=raw.legal_process,
        registration_number=raw.registration_number,
        tax_article=raw.tax_article,
        main_image_url=raw.main_image_url,
        bedrooms=raw.bedrooms,
        bathrooms=raw.bathrooms,
        floor=raw.floor,
        has_elevator=raw.has_elevator,
        has_garage=raw.has_garage,
        has_balcony=raw.has_balcony,
        has_terrace=raw.has_terrace,
        has_garden=raw.has_garden,
        has_yard=raw.has_yard,
        energy_certificate=raw.energy_certificate,
        status=detect_listing_status(raw.listing_status_text),
        legal_alerts=legal_alerts,
    )
    normalized.canonical_fingerprint = deduplication.canonical_fingerprint(normalized)
    return normalized
