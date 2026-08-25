from __future__ import annotations

from core import database as db
from core.models import PriceRecord


def test_insert_price_upsert_same_day(conn):
    cid = db.get_or_create_card(conn, __import__("core.models", fromlist=["Card"]).Card(
        card_key="k1", name="Card", category="other"))
    db.insert_price(conn, PriceRecord(card_id=cid, source="mercari", currency="JPY", price=100))
    db.insert_price(conn, PriceRecord(card_id=cid, source="mercari", currency="JPY", price=200))
    rows = conn.execute("SELECT price FROM prices WHERE card_id=?", (cid,)).fetchall()
    assert len(rows) == 1  # 同日同ソースは重複しない
    assert rows[0]["price"] == 200


def test_insert_price_different_sources_kept(conn):
    cid = db.get_or_create_card(conn, __import__("core.models", fromlist=["Card"]).Card(
        card_key="k1", name="Card", category="other"))
    db.insert_price(conn, PriceRecord(card_id=cid, source="mercari", currency="JPY", price=100))
    db.insert_price(conn, PriceRecord(card_id=cid, source="amazon", currency="JPY", price=120))
    n = conn.execute("SELECT COUNT(*) c FROM prices WHERE card_id=?", (cid,)).fetchone()["c"]
    assert n == 2


def test_latest_spreads_legacy_rows(conn):
    # run_idなしのレガシー行でもクラッシュせずフォールバックする
    cid = db.get_or_create_card(conn, __import__("core.models", fromlist=["Card"]).Card(
        card_key="k2", name="Card2", category="other"))
    db.insert_spread(conn, {
        "card_id": cid, "buy_price_jpy": 100, "sell_price_jpy": 200,
        "gross_profit_jpy": 100, "fee_rate": 0, "net_profit_jpy": 90,
        "profit_rate_pct": 90.0, "source_sell": "ebay", "exchange_rate": 150,
    })
    rows = db.latest_spreads(conn)
    assert len(rows) == 1
