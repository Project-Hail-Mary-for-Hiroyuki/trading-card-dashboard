from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from core import database as db  # noqa: E402
from core.config import Config, FeeConfig, AnalysisConfig, HttpConfig, PriceSource, load_config  # noqa: E402


@pytest.fixture
def conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    yield conn
    conn.close()


def make_cfg(**overrides) -> Config:
    cfg = load_config(PROJECT_ROOT / "config.example.yaml")
    cfg.db_path = ":memory:"
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


@pytest.fixture
def cfg() -> Config:
    c = make_cfg()
    c.fees = FeeConfig(ebay=0.10, tcgplayer=0.10, cardmarket=0.05,
                       shipping_cost_jpy=500, fx_markup=0.03)
    c.analysis = AnalysisConfig(min_profit_rate=20.0, hot_profit_rate=50.0)
    c.buy_sources = [PriceSource("mercari", "メルカリ", "buy", "JPY")]
    c.sell_sources = [
        PriceSource("tcgplayer", "TCGPlayer", "sell", "USD"),
        PriceSource("ebay", "eBay", "sell", "USD"),
    ]
    return c


def add_card(conn, key="sv3-51", name="Pikachu", category="pokemon") -> int:
    return db.get_or_create_card(
        conn,
        __import__("core.models", fromlist=["Card"]).Card(card_key=key, name=name, category=category),
    )


def add_price(conn, card_id, source, currency, price):
    db.insert_price(conn, __import__("core.models", fromlist=["PriceRecord"]).PriceRecord(
        card_id=card_id, source=source, currency=currency, price=price))
