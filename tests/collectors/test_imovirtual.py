"""Testes do coletor Imovirtual (helpers sem browser)."""

from __future__ import annotations

import json

from monitor.collectors.imovirtual import _ESTATE_TYPE_MAP, _ROOMS_MAP, ImovirtualCollector


def test_from_node_basic() -> None:
    node = {
        "id": 123456,
        "slug": "apartamento-t2-porto-ID1abc",
        "title": "Apartamento T2 no Porto",
        "shortDescription": "Excelente apartamento.",
        "estate": "FLAT",
        "transaction": "SELL",
        "totalPrice": {"value": 150000, "currency": "EUR"},
        "areaInSquareMeters": 80,
        "roomsNumber": "TWO",
        "floorNumber": "SECOND",
        "location": {
            "address": {
                "city": {"name": "Porto"},
                "province": {"name": "Porto"},
                "street": {"name": "Rua da Liberdade"},
            }
        },
        "images": [{"medium": "https://img.example.com/1.jpg"}],
        "tags": [{"value": "BALCONY"}, {"value": "POOL"}],
    }
    collector = _make_collector()
    listing = collector._from_node(node)
    assert listing is not None
    assert listing.source_reference == "123456"
    assert listing.title == "Apartamento T2 no Porto"
    assert listing.price_value == 150000
    assert listing.currency == "€"
    assert listing.usable_area_m2 == 80
    assert listing.bedrooms == 2
    assert listing.floor == "SECOND"
    assert listing.municipality == "Porto"
    assert listing.district == "Porto"
    assert listing.address == "Rua da Liberdade"
    assert listing.main_image_url == "https://img.example.com/1.jpg"
    assert listing.has_balcony is True
    assert listing.property_type == "APARTMENT"


def test_from_node_missing_required() -> None:
    collector = _make_collector()
    assert collector._from_node({}) is None
    assert collector._from_node({"id": 1}) is None


def test_from_node_minimal() -> None:
    node = {"id": 1, "slug": "test-ID1"}
    collector = _make_collector()
    listing = collector._from_node(node)
    assert listing is not None
    assert listing.source_reference == "1"
    assert listing.price_value is None
    assert listing.bedrooms is None


def test_rooms_map_coverage() -> None:
    assert _ROOMS_MAP["ONE"] == 1
    assert _ROOMS_MAP["FIVE"] == 5
    assert "SIX" in _ROOMS_MAP


def test_estate_type_map() -> None:
    assert _ESTATE_TYPE_MAP["FLAT"] == "APARTMENT"
    assert _ESTATE_TYPE_MAP["HOUSE"] == "HOUSE"
    assert _ESTATE_TYPE_MAP["PLOT"] == "LAND"


def test_parse_page_with_next_data() -> None:
    next_data = {
        "props": {
            "pageProps": {
                "data": {
                    "searchAds": {
                        "items": [
                            {
                                "id": 100,
                                "slug": "moradia-t3-IDxyz",
                                "title": "Moradia T3",
                                "totalPrice": {"value": 200000, "currency": "EUR"},
                            }
                        ]
                    }
                }
            }
        }
    }
    payload = json.dumps(next_data)
    html = (
        '<html><head>'
        '<script id="__NEXT_DATA__" type="application/json">'
        f"{payload}"
        "</script></head></html>"
    )
    collector = _make_collector()
    items = collector._parse_page(html, 1)
    assert len(items) == 1
    assert items[0].title == "Moradia T3"


def test_parse_page_without_next_data() -> None:
    html = "<html><head></head><body></body></html>"
    collector = _make_collector()
    items = collector._parse_page(html, 1)
    assert items == []


def test_parse_page_invalid_json() -> None:
    html = '<html><head><script id="__NEXT_DATA__">{invalid json</script></head></html>'
    collector = _make_collector()
    items = collector._parse_page(html, 1)
    assert items == []


def _make_collector() -> ImovirtualCollector:
    from unittest.mock import MagicMock

    context = MagicMock()
    context.source_settings = MagicMock()
    context.source_settings.delay_seconds = 0
    context.source_settings.maximum_pages = 1
    return ImovirtualCollector(context)
