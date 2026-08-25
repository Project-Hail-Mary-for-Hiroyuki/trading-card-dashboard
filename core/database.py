from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from core.models import Card, PriceRecord

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_key TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    set_name TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT '',
    rarity TEXT NOT NULL DEFAULT '',
    image_url TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS prices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL REFERENCES cards(id),
    source TEXT NOT NULL,
    currency TEXT NOT NULL,
    price REAL NOT NULL,
    extra TEXT NOT NULL DEFAULT '{}',
    fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_prices_card ON prices(card_id, source, fetched_at);

CREATE TABLE IF NOT EXISTS spreads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id INTEGER NOT NULL REFERENCES cards(id),
    buy_price_jpy REAL NOT NULL,
    sell_price_jpy REAL NOT NULL,
    gross_profit_jpy REAL NOT NULL,
    fee_rate REAL NOT NULL DEFAULT 0,
    net_profit_jpy REAL NOT NULL,
    profit_rate_pct REAL NOT NULL,
    source_sell TEXT NOT NULL DEFAULT '',
    exchange_rate REAL NOT NULL DEFAULT 1,
    calculated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_spreads_card ON spreads(card_id, calculated_at);
CREATE UNIQUE INDEX IF NOT EXISTS uq_prices_daily
    ON prices(card_id, source, date(fetched_at));


CREATE TABLE IF NOT EXISTS exchange_rates (
    currency_pair TEXT PRIMARY KEY,
    rate REAL NOT NULL,
    fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    # Streamlit は rerun ごとに別スレッドでスクリプトを実行するため、
    # キャッシュした接続を別スレッドから使えるように check_same_thread=False にする。
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


MIGRATIONS = [
    # (description, sql) — applied when needed
    (
        "spreads.run_id",
        "ALTER TABLE spreads ADD COLUMN run_id TEXT NOT NULL DEFAULT ''",
    ),
]


def migrate(conn: sqlite3.Connection) -> None:
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(spreads)")}
    for desc, sql in MIGRATIONS:
        table, col = desc.split(".")
        if col not in columns:
            conn.execute(sql)
            logger.info("applied migration: add %s", desc)
    conn.commit()


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    migrate(conn)


# ---- cards ----
def get_or_create_card(conn: sqlite3.Connection, card: Card) -> int:
    row = conn.execute(
        "SELECT id FROM cards WHERE card_key = ?", (card.card_key,)
    ).fetchone()
    if row:
        return int(row["id"])
    cur = conn.execute(
        """
        INSERT INTO cards (card_key, name, category, set_name, language, rarity, image_url)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            card.card_key,
            card.name,
            card.category,
            card.set_name,
            card.language,
            card.rarity,
            card.image_url,
        ),
    )
    return int(cur.lastrowid)


def count_cards(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) AS c FROM cards").fetchone()["c"])


# ---- prices ----
def insert_price(conn: sqlite3.Connection, rec: PriceRecord) -> int:
    """Insert a price record. Re-fetching the same card/source on the same
    day updates the existing row instead of duplicating it."""
    cur = conn.execute(
        """
        INSERT INTO prices (card_id, source, currency, price, extra)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(card_id, source, date(fetched_at)) DO UPDATE SET
            currency = excluded.currency,
            price = excluded.price,
            extra = excluded.extra,
            fetched_at = datetime('now')
        """,
        (rec.card_id, rec.source, rec.currency, rec.price, json.dumps(rec.extra)),
    )
    return int(cur.lastrowid)


def get_latest_prices(conn: sqlite3.Connection) -> dict[tuple[int, str], sqlite3.Row]:
    """Return {(card_id, source): latest price row} in a single query."""
    rows = conn.execute(
        """
        SELECT card_id, source, currency, price, fetched_at FROM (
            SELECT p.*, ROW_NUMBER() OVER (
                PARTITION BY p.card_id, p.source
                ORDER BY p.fetched_at DESC, p.id DESC
            ) AS rn
            FROM prices p
        ) WHERE rn = 1
        """
    ).fetchall()
    return {(r["card_id"], r["source"]): r for r in rows}


def count_prices(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) AS c FROM prices").fetchone()["c"])


def latest_price(conn: sqlite3.Connection, card_id: int, source: str) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT * FROM prices
        WHERE card_id = ? AND source = ?
        ORDER BY fetched_at DESC, id DESC
        LIMIT 1
        """,
        (card_id, source),
    ).fetchone()


def price_history(conn: sqlite3.Connection, card_id: int, source: str | None = None) -> list[sqlite3.Row]:
    if source:
        return conn.execute(
            """
            SELECT * FROM prices
            WHERE card_id = ? AND source = ?
            ORDER BY fetched_at ASC, id ASC
            """,
            (card_id, source),
        ).fetchall()
    return conn.execute(
        """
        SELECT * FROM prices
        WHERE card_id = ?
        ORDER BY fetched_at ASC, id ASC
        """,
        (card_id,),
    ).fetchall()


# ---- spreads ----
def insert_spread(conn: sqlite3.Connection, spread: dict) -> int:
    cur = conn.execute(
        """
        INSERT INTO spreads
            (card_id, buy_price_jpy, sell_price_jpy, gross_profit_jpy, fee_rate,
             net_profit_jpy, profit_rate_pct, source_sell, exchange_rate, run_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            spread["card_id"],
            spread["buy_price_jpy"],
            spread["sell_price_jpy"],
            spread["gross_profit_jpy"],
            spread["fee_rate"],
            spread["net_profit_jpy"],
            spread["profit_rate_pct"],
            spread["source_sell"],
            spread["exchange_rate"],
            spread.get("run_id", ""),
        ),
    )
    return int(cur.lastrowid)


def latest_run_id(conn: sqlite3.Connection) -> str | None:
    row = conn.execute(
        "SELECT run_id FROM spreads ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return row["run_id"] if row and row["run_id"] else None


def latest_spreads(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return all rows from the most recent calculation run."""
    run_id = latest_run_id(conn)
    if run_id is None:
        # legacy rows without run_id: fall back to the max calculated_at
        return conn.execute(
            """
            SELECT s.*, c.name AS card_name, c.category, c.set_name, c.image_url
            FROM spreads s
            JOIN cards c ON c.id = s.card_id
            WHERE s.calculated_at = (SELECT MAX(calculated_at) FROM spreads)
            ORDER BY s.profit_rate_pct DESC
            """
        ).fetchall()
    return conn.execute(
        """
        SELECT s.*, c.name AS card_name, c.category, c.set_name, c.image_url
        FROM spreads s
        JOIN cards c ON c.id = s.card_id
        WHERE s.run_id = ?
        ORDER BY s.profit_rate_pct DESC
        """,
        (run_id,),
    ).fetchall()



def spread_history(conn: sqlite3.Connection, card_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT * FROM spreads WHERE card_id = ? ORDER BY calculated_at ASC, id ASC
        """,
        (card_id,),
    ).fetchall()


# ---- exchange rates ----
def upsert_exchange_rate(conn: sqlite3.Connection, pair: str, rate: float) -> None:
    conn.execute(
        """
        INSERT INTO exchange_rates (currency_pair, rate, fetched_at)
        VALUES (?, ?, datetime('now'))
        ON CONFLICT(currency_pair) DO UPDATE SET
            rate = excluded.rate,
            fetched_at = datetime('now')
        """,
        (pair, rate),
    )
    conn.commit()


def get_exchange_rate(conn: sqlite3.Connection, pair: str) -> float | None:
    row = conn.execute(
        "SELECT rate FROM exchange_rates WHERE currency_pair = ?", (pair,)
    ).fetchone()
    return float(row["rate"]) if row else None


# ---- settings ----
def get_setting(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    conn.commit()
