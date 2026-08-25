from __future__ import annotations

import logging
import sqlite3

from core.config import Config
from core import database as db
from collectors.base import BaseCollector

logger = logging.getLogger(__name__)


def fetch_exchange_rates(conn: sqlite3.Connection, config: Config) -> dict[str, float]:
    """Fetch USD/JPY and EUR/JPY from open.er-api.com in a single request.

    EUR/JPY is derived as a cross rate from the USD response.
    """
    col = BaseCollector(config)
    result: dict[str, float] = {}
    try:
        data = col.fetch_json(config.exchange_api_url)  # .../latest/USD
        rates = data.get("rates", {})
        usd_jpy = rates.get("JPY")
        eur_per_usd = rates.get("EUR")
        if usd_jpy:
            db.upsert_exchange_rate(conn, "USDJPY", float(usd_jpy))
            result["USDJPY"] = float(usd_jpy)
            logger.info("USDJPY = %s", usd_jpy)
        if usd_jpy and eur_per_usd:
            eur_jpy = float(usd_jpy) / float(eur_per_usd)
            db.upsert_exchange_rate(conn, "EURJPY", eur_jpy)
            result["EURJPY"] = eur_jpy
            logger.info("EURJPY = %s (cross)", round(eur_jpy, 4))
    except Exception as exc:  # noqa: BLE001
        logger.warning("exchange rate fetch failed: %s", exc)

    for pair in ("USDJPY", "EURJPY"):
        if pair not in result:
            rate = db.get_exchange_rate(conn, pair)
            if rate:
                result[pair] = rate
    return result

