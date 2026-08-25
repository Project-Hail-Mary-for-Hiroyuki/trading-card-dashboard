from __future__ import annotations

from core import analysis, database as db
from core.models import PriceRecord


def _setup(conn, cfg):
    cid = db.get_or_create_card(conn, __import__("core.models", fromlist=["Card"]).Card(
        card_key="sv3-51", name="Pikachu", category="pokemon"))
    # 仕入れ: メルカリ 1000 JPY（最安が選ばれる）
    db.insert_price(conn, PriceRecord(card_id=cid, source="mercari", currency="JPY", price=1000))
    # 販売: TCGPlayer $10 / eBay $12 → eBayが最高売却先
    db.insert_price(conn, PriceRecord(card_id=cid, source="tcgplayer", currency="USD", price=10))
    db.insert_price(conn, PriceRecord(card_id=cid, source="ebay", currency="USD", price=12))
    fx = {"USDJPY": 150.0}
    df = analysis.compute_spreads(conn, cfg, fx=fx)
    return cid, df


def test_compute_spreads_basic(conn, cfg):
    _, df = _setup(conn, cfg)
    assert len(df) == 1
    row = df.iloc[0]
    buy = 1000.0
    sell = 12 * 150.0  # eBay
    fee = sell * cfg.fees.fee_for("ebay")
    expected_net = sell - fee - cfg.fees.shipping_cost_jpy - buy * (1 + cfg.fees.fx_markup)
    assert row["source_sell"] == "ebay"
    assert row["buy_price_jpy"] == round(buy)
    assert row["sell_price_jpy"] == round(sell)
    assert row["net_profit_jpy"] == round(expected_net)


def test_latest_prices_single_query_map(conn, cfg):
    latest = db.get_latest_prices(conn)
    assert latest == {}
    _, df = _setup(conn, cfg)
    assert not df.empty


def test_classify_boundaries(cfg):
    assert analysis.classify(19.9, cfg) == "慎重"
    assert analysis.classify(20.0, cfg) == "有望"
    assert analysis.classify(49.9, cfg) == "有望"
    assert analysis.classify(50.0, cfg) == "注目"
    assert analysis.classify(-1, cfg) == "不可"


def test_run_id_isolation(conn, cfg):
    from core.models import Card

    cid = db.get_or_create_card(conn, Card(card_key="sv3-51", name="Pikachu", category="pokemon"))
    db.insert_price(conn, PriceRecord(card_id=cid, source="mercari", currency="JPY", price=1000))
    db.insert_price(conn, PriceRecord(card_id=cid, source="ebay", currency="USD", price=12))

    df1 = analysis.compute_spreads(conn, cfg, fx={"USDJPY": 150.0})
    r1 = analysis.persist_spreads(conn, df1)
    assert r1 and len(db.latest_spreads(conn)) == len(df1)

    # 新しいrunで価格を変更しても、latest_spreadsは最新runのみ返す
    df2 = analysis.compute_spreads(conn, cfg, fx={"USDJPY": 150.0})
    r2 = analysis.persist_spreads(conn, df2)
    assert r2 != r1
    rows = db.latest_spreads(conn)
    assert len(rows) == len(df2)
