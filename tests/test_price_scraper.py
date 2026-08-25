from __future__ import annotations

from collectors.price_scraper import GenericPriceScraper, MockPriceScraper, _resolve_json_path
from core.config import PriceSource
from core.models import Card, PriceRecord


def test_resolve_json_path_nested():
    payload = {"data": {"items": [{"price": 123.4}]}}
    assert _resolve_json_path(payload, "data.items.0.price") == 123.4


def test_resolve_json_path_missing():
    assert _resolve_json_path({"a": 1}, "a.b.c") is None


def test_to_number_via_parse_json():
    src = PriceSource("api", "API", "sell", "USD",
                      url_template="https://x/{query}", extra={"json_path": "price"})
    scraper = GenericPriceScraper.__new__(GenericPriceScraper)  # HTTPを使わずパーサのみ検証
    scraper.source = src
    rec = scraper._parse_json({"price": "$45.99"}, Card("k", "Card X", "other"))
    assert rec is not None and rec.price == 45.99


def test_mock_scraper_deterministic():
    src = PriceSource("mercari", "メルカリ", "buy", "JPY")
    card = Card("sv3-51", "Pikachu", "pokemon")
    a = MockPriceScraper(None, src).fetch_price(card).price
    b = MockPriceScraper(None, src).fetch_price(card).price
    assert a == b  # seed固定で決定論的
