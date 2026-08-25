from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime

import pandas as pd

from core.config import Config
from core import database as db
from core.models import AlertSettings, Category

logger = logging.getLogger(__name__)


def _fx_to_jpy(cfg: Config, currency: str, fx: dict[str, float]) -> float | None:
    if currency == "JPY":
        return 1.0
    if currency == "USD":
        return fx.get("USDJPY")
    if currency == "EUR":
        return fx.get("EURJPY")
    return None


def resolve_fx(conn: sqlite3.Connection) -> dict[str, float]:
    usd = db.get_exchange_rate(conn, "USDJPY")
    eur = db.get_exchange_rate(conn, "EURJPY")
    out: dict[str, float] = {}
    if usd:
        out["USDJPY"] = usd
    if eur:
        out["EURJPY"] = eur
    return out


def compute_spreads(
    conn: sqlite3.Connection, cfg: Config, fx: dict[str, float] | None = None
) -> pd.DataFrame:
    fx = fx or resolve_fx(conn)
    latest = db.get_latest_prices(conn)  # 1クエリで全カード×ソースの最新価格を取得
    cards = conn.execute(
        "SELECT id, name AS card_name, category, set_name, image_url FROM cards"
    ).fetchall()

    markup = 1.0 + cfg.fees.fx_markup
    records = []
    for card in cards:
        cid = card["id"]

        buy_price_jpy = None
        for source in cfg.buy_sources:
            rec = latest.get((cid, source.name))
            if rec is None:
                continue
            rate = _fx_to_jpy(cfg, rec["currency"], fx)
            if rate is None:
                continue
            price_jpy = float(rec["price"]) * rate
            buy_price_jpy = (
                min(price_jpy, buy_price_jpy) if buy_price_jpy else price_jpy
            )

        sell_price_jpy = None
        sell_source = ""
        fee_rate = 0.0
        for source in cfg.sell_sources:
            rec = latest.get((cid, source.name))
            if rec is None:
                continue
            rate = _fx_to_jpy(cfg, rec["currency"], fx)
            if rate is None:
                continue
            price_jpy = float(rec["price"]) * rate
            if sell_price_jpy is None or price_jpy > sell_price_jpy:
                sell_price_jpy = price_jpy
                sell_source = source.name
                fee_rate = cfg.fees.fee_for(source.name)

        if buy_price_jpy is None or sell_price_jpy is None or buy_price_jpy <= 0:
            continue

        gross = sell_price_jpy - buy_price_jpy
        fees = sell_price_jpy * fee_rate
        shipping = cfg.fees.shipping_cost_jpy
        # 為替上乗せ率(fx_markup)は仕入れコスト側に反映する
        net = sell_price_jpy - fees - shipping - buy_price_jpy * markup
        rate_pct = net / buy_price_jpy * 100.0
        fx_rate = fx.get("USDJPY", 1.0)

        records.append(
            {
                "card_id": cid,
                "card_name": card["card_name"],
                "category": card["category"],
                "set_name": card["set_name"],
                "buy_price_jpy": round(buy_price_jpy),
                "sell_price_jpy": round(sell_price_jpy),
                "gross_profit_jpy": round(gross),
                "fee_rate": round(fee_rate, 4),
                "net_profit_jpy": round(net),
                "profit_rate_pct": round(rate_pct, 1),
                "source_sell": sell_source,
                "exchange_rate": round(fx_rate, 2),
                "image_url": card["image_url"] or "",
            }
        )

    return pd.DataFrame(records)


def persist_spreads(conn: sqlite3.Connection, df: pd.DataFrame) -> str | None:
    if df.empty:
        return None
    run_id = uuid.uuid4().hex[:12]
    for _, r in df.iterrows():
        db.insert_spread(
            conn,
            {
                "card_id": int(r["card_id"]),
                "buy_price_jpy": float(r["buy_price_jpy"]),
                "sell_price_jpy": float(r["sell_price_jpy"]),
                "gross_profit_jpy": float(r["gross_profit_jpy"]),
                "fee_rate": float(r["fee_rate"]),
                "net_profit_jpy": float(r["net_profit_jpy"]),
                "profit_rate_pct": float(r["profit_rate_pct"]),
                "source_sell": str(r["source_sell"]),
                "exchange_rate": float(r["exchange_rate"]),
                "run_id": run_id,
            },
        )
    conn.commit()
    return run_id


def classify(rate_pct: float, cfg: Config) -> str:
    if rate_pct >= cfg.analysis.hot_profit_rate:
        return "注目"
    if rate_pct >= cfg.analysis.min_profit_rate:
        return "有望"
    if rate_pct >= 0:
        return "慎重"
    return "不可"


def summarize(df: pd.DataFrame, cfg: Config) -> dict:
    if df.empty:
        return {
            "card_count": 0,
            "average_rate": 0.0,
            "min_rate": 0.0,
            "max_rate": 0.0,
            "median_rate": 0.0,
            "hot_count": 0,
            "promising_count": 0,
            "category_summary": pd.DataFrame(),
            "calculated_at": None,
        }
    rates = df["profit_rate_pct"]
    return {
        "card_count": int(len(df)),
        "average_rate": round(float(rates.mean()), 1),
        "min_rate": round(float(rates.min()), 1),
        "max_rate": round(float(rates.max()), 1),
        "median_rate": round(float(rates.median()), 1),
        "hot_count": int((rates >= cfg.analysis.hot_profit_rate).sum()),
        "promising_count": int((rates >= cfg.analysis.min_profit_rate).sum()),
        "category_summary": (
            df.groupby("category")["profit_rate_pct"]
            .agg(["count", "mean", "max"])
            .round(1)
            .reset_index()
        ),
        "calculated_at": datetime.now().isoformat(timespec="seconds"),
    }


def alert_matches(
    conn: sqlite3.Connection, cfg: Config, settings: AlertSettings | None = None
) -> pd.DataFrame:
    settings = settings or AlertSettings(
        min_profit_rate=cfg.analysis.min_profit_rate,
        categories=[c.value for c in Category],
    )
    df = compute_spreads(conn, cfg)
    if df.empty:
        return df
    df = df[df["profit_rate_pct"] >= settings.min_profit_rate]
    if settings.categories:
        df = df[df["category"].isin(settings.categories)]
    return df.sort_values("profit_rate_pct", ascending=False)


def category_label(value: str) -> str:
    from core.models import Category

    return Category.label(value)
