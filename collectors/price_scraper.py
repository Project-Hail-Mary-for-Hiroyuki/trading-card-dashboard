from __future__ import annotations

import json
import logging
import random
import re
import sqlite3

from bs4 import BeautifulSoup

from core.config import Config, PriceSource
from core import database as db
from core.models import Card, PriceRecord
from collectors.base import BaseCollector, CollectorError

logger = logging.getLogger(__name__)


def _resolve_json_path(payload, path: str):
    node = payload
    for part in path.split("."):
        if isinstance(node, list):
            idx = int(part) if part.isdigit() else None
            node = node[idx] if idx is not None and idx < len(node) else None
        elif isinstance(node, dict):
            node = node.get(part)
        else:
            return None
        if node is None:
            return None
    return node


class GenericPriceScraper:
    """Config-driven scraper for one price source.

    A source's ``extra`` may define:
      - parser: "json" (default) or "html"
      - json_path: dot path to a numeric price in the JSON payload
      - css: CSS selector for the price element
      - css_attr: attribute to extract (default: text content)
    The URL template may use ``{query}`` (URL-encoded card name) and
    ``{card_key}`` placeholders.
    """

    def __init__(self, config: Config, source: PriceSource):
        self.cfg = config
        self.source = source
        self.col = BaseCollector(config)

    def fetch_price(self, card: Card) -> PriceRecord | None:
        if not self.source.url_template:
            return None
        query = re.sub(r"[^0-9A-Za-z ]", "", card.name).strip().replace(" ", "-")
        url = self.source.url_template.format(query=query, card_key=card.card_key)
        extra = self.source.extra or {}
        parser = extra.get("parser", "json")
        try:
            if parser == "html":
                resp = self.col.fetch(url)
                return self._parse_html(resp.text, card)
            return self._parse_json(self.col.fetch_json(url), card)
        except CollectorError as exc:
            logger.warning("price scrape failed for %s (%s): %s", card.name, self.source.name, exc)
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning("price scrape error for %s (%s): %s", card.name, self.source.name, exc)
            return None

    def _parse_html(self, html: str, card: Card) -> PriceRecord | None:
        extra = self.source.extra or {}
        soup = BeautifulSoup(html, "lxml")
        el = soup.select_one(extra["css"])
        if el is None:
            return None
        raw = el.get(extra.get("css_attr", "")) if extra.get("css_attr") else el.get_text(strip=True)
        price = self._to_number(raw)
        if price is None:
            return None
        return PriceRecord(card_id=0, source=self.source.name, currency=self.source.currency, price=price)

    def _parse_json(self, payload, card: Card) -> PriceRecord | None:
        extra = self.source.extra or {}
        path = extra.get("json_path", "")
        node = _resolve_json_path(payload, path) if path else payload
        price = self._to_number(node)
        if price is None:
            return None
        return PriceRecord(card_id=0, source=self.source.name, currency=self.source.currency, price=price)

    @staticmethod
    def _to_number(raw) -> float | None:
        if isinstance(raw, (int, float)):
            return float(raw)
        if isinstance(raw, str):
            m = re.search(r"[\d.,]+", raw.replace(",", ""))
            if m:
                try:
                    return float(m.group(0).replace(",", ""))
                except ValueError:
                    return None
        return None


class MockPriceScraper:
    """Deterministic demo prices so the dashboard is usable offline."""

    REFERENCE_FX = {"USDJPY": 150.0, "EURJPY": 163.0}

    def __init__(self, config: Config, source: PriceSource, fx: dict[str, float] | None = None):
        self.cfg = config
        self.source = source
        self.fx = fx or {}
        self.rng = random.Random(42)

    def fetch_price(self, card: Card) -> PriceRecord | None:
        base_jpy = _card_base_price(card)
        if self.source.side == "buy":
            price_jpy = base_jpy * self.rng.uniform(0.7, 1.1)
        else:
            price_jpy = base_jpy * self.rng.uniform(1.6, 3.4)
        price_jpy = max(price_jpy, 50)
        price = price_jpy
        if self.source.currency != "JPY":
            pair = f"{self.source.currency}JPY"
            rate = self.fx.get(pair) or self.REFERENCE_FX.get(pair, 1.0)
            price = price_jpy / rate
        return PriceRecord(
            card_id=0,
            source=self.source.name,
            currency=self.source.currency,
            price=round(price, 1),
        )


def _card_base_price(card: Card) -> float:
    key = card.card_key or ""
    m = re.search(r"-?(\d+)$", key)
    num = int(m.group(1)) if m else hash(card.name) % 100
    rng = random.Random(card.name)
    if "secret" in (card.rarity or "").lower() or "secret" in (card.set_name or "").lower():
        return 4000.0 + rng.uniform(0, 3000)
    if "ultra" in (card.rarity or "").lower() or "rare" == (card.rarity or "").lower():
        return 1500.0 + rng.uniform(0, 2500)
    if num % 3 == 0:
        return 800.0 + rng.uniform(0, 1200)
    return 120.0 + rng.uniform(0, 500)


def collect_prices(conn: sqlite3.Connection, cfg: Config) -> int:
    cards = [
        Card(
            card_key=r["card_key"],
            name=r["name"],
            category=r["category"],
            set_name=r["set_name"],
            rarity=r["rarity"],
        )
        for r in conn.execute("SELECT * FROM cards").fetchall()
    ]
    if not cards:
        logger.info("no cards in DB, nothing to price")
        return 0

    id_map = {r["card_key"]: int(r["id"]) for r in conn.execute("SELECT id, card_key FROM cards")}
    mock_enabled = bool(cfg.raw.get("mock", {}).get("enabled", False))
    fx = {pair: rate for pair, rate in ((p, db.get_exchange_rate(conn, p)) for p in ("USDJPY", "EURJPY")) if rate}
    inserted = 0
    for source in cfg.all_sources:
        if not source.enabled and not mock_enabled:
            continue
        scraper = MockPriceScraper(cfg, source, fx=fx) if mock_enabled else GenericPriceScraper(cfg, source)
        source_count = 0
        for card in cards:
            rec = scraper.fetch_price(card)
            if rec is None or card.card_key not in id_map:
                continue
            rec.card_id = id_map[card.card_key]
            db.insert_price(conn, rec)
            inserted += 1
            source_count += 1
        conn.commit()
        logger.info("price source %s: %d records", source.name, source_count)
    return inserted
