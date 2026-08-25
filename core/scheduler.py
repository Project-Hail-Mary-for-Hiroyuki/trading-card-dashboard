from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from core.config import Config
from core import database as db

logger = logging.getLogger(__name__)


def run_collection(config: Config) -> None:
    from collectors import catalog_api, exchange_rate, price_scraper
    from core import analysis

    conn = db.connect(config.db_path)
    try:
        db.init_db(conn)
        exchange_rate.fetch_exchange_rates(conn, config)
        price_scraper.collect_prices(conn, config)
        df = analysis.compute_spreads(conn, config)
        analysis.persist_spreads(conn, df)
        logger.info("collection done: %d spreads computed", len(df))
    finally:
        conn.close()


def create_scheduler(config: Config, hour: int = 6, minute: int = 0) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="Asia/Tokyo")
    scheduler.add_job(
        run_collection,
        CronTrigger(hour=hour, minute=minute),
        args=[config],
        id="daily_collection",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    return scheduler
