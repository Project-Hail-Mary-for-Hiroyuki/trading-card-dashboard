from __future__ import annotations

import argparse
import logging
import sqlite3
from contextlib import contextmanager

from core.config import Config, load_config
from core import database as db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("collect")


@contextmanager
def session(cfg: Config):
    conn = db.connect(cfg.db_path)
    try:
        db.init_db(conn)
        yield conn
    finally:
        conn.close()


def cmd_catalog(cfg, limit: int = 500) -> None:
    from collectors import catalog_api

    with session(cfg) as conn:
        cards = catalog_api.fetch_catalog(
            cfg, limit=limit, progress=lambda n, c: logger.info("  %s: %d", c, n)
        )
        for card in cards:
            db.get_or_create_card(conn, card)
        conn.commit()
        logger.info("total cards in DB: %d", db.count_cards(conn))


def cmd_fx(cfg) -> None:
    from collectors import exchange_rate

    with session(cfg) as conn:
        rates = exchange_rate.fetch_exchange_rates(conn, cfg)
        logger.info("exchange rates: %s", rates)


def cmd_prices(cfg) -> None:
    from collectors import price_scraper

    with session(cfg) as conn:
        inserted = price_scraper.collect_prices(conn, cfg)
        logger.info("inserted %d price records", inserted)


def cmd_spreads(cfg) -> None:
    from core import analysis

    with session(cfg) as conn:
        df = analysis.compute_spreads(conn, cfg)
        run_id = analysis.persist_spreads(conn, df)
        logger.info("computed %d spreads (run_id=%s)", len(df), run_id)


def cmd_all(cfg, limit: int = 500) -> None:
    from core import analysis

    with session(cfg) as conn:
        from collectors import catalog_api, exchange_rate, price_scraper

        cards = catalog_api.fetch_catalog(cfg, limit=limit)
        for card in cards:
            db.get_or_create_card(conn, card)
        conn.commit()
        logger.info("catalog: %d cards", db.count_cards(conn))

        exchange_rate.fetch_exchange_rates(conn, cfg)
        price_scraper.collect_prices(conn, cfg)
        df = analysis.compute_spreads(conn, cfg)
        run_id = analysis.persist_spreads(conn, df)
        logger.info("spreads: %d (run_id=%s)", len(df), run_id)


def cmd_schedule(cfg) -> None:
    from core import scheduler
    from time import sleep

    sched = scheduler.create_scheduler(cfg)
    sched.start()
    logger.info("scheduler started (daily at 06:00 Asia/Tokyo). Press Ctrl+C to stop.")
    try:
        while True:
            sleep(60)
    except KeyboardInterrupt:
        sched.shutdown(wait=False)


COMMANDS = {
    "catalog": lambda c, a: cmd_catalog(c, a.limit),
    "fx": lambda c, a: cmd_fx(c),
    "prices": lambda c, a: cmd_prices(c),
    "spreads": lambda c, a: cmd_spreads(c),
    "all": lambda c, a: cmd_all(c, a.limit),
    "schedule": lambda c, a: cmd_schedule(c),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Trading card data collection CLI")
    parser.add_argument(
        "command",
        choices=["catalog", "fx", "prices", "spreads", "all", "schedule"],
    )
    parser.add_argument("--config", default=None, help="path to config yaml")
    parser.add_argument("--limit", type=int, default=500, help="max catalog cards per source")
    args = parser.parse_args()

    cfg = load_config(args.config)
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    COMMANDS[args.command](cfg, args)


if __name__ == "__main__":
    main()

