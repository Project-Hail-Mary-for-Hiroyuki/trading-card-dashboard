from __future__ import annotations

import logging
import random

from core.config import Config, PriceSource
from core.models import Card
from core import database as db

logger = logging.getLogger(__name__)

DEMO_CARDS = [
    # (key, name, category, set, rarity)
    ("sv3-51", "Pikachu", "pokemon", "Obsidian Flames", "Rare"),
    ("sv2-199", "Mew ex", "pokemon", "Paldea Evolved", "Double Rare"),
    ("sv3-192", "Charizard ex", "pokemon", "Obsidian Flames", "Ultra Rare"),
    ("sv4-99", "Iron Valiant ex", "pokemon", "Paradox Rift", "Ultra Rare"),
    ("sv1-83", "Miraidon ex", "pokemon", "Scarlet & Violet", "Ultra Rare"),
    ("sv5-137", "Gholdengo ex", "pokemon", "Temporal Forces", "Ultra Rare"),
    ("sv6-159", "Greninja ex", "pokemon", "Twilight Masquerade", "Ultra Rare"),
    ("swsh9-107", "Umbreon V", "pokemon", "Brilliant Stars", "Double Rare"),
    ("swsh10-157", "Lugia V", "pokemon", "Silver Tempest", "Double Rare"),
    ("swsh12-171", "Giratina VSTAR", "pokemon", "Crown Zenith", "Ultra Rare"),
    ("yug-11145", "Blue-Eyes White Dragon", "yugioh", "Legend of Blue Eyes", "Ultra Rare"),
    ("yug-46986414", "Dark Magician", "yugioh", "Legend of Blue Eyes", "Ultra Rare"),
    ("yug-61257749", "Exodia the Forbidden One", "yugioh", "Legend of Blue Eyes", "Ultra Rare"),
    ("yug-38033121", "Raigeki", "yugioh", "Starter Deck", "Ultra Rare"),
    ("yug-58921041", "Monster Reborn", "yugioh", "Legend of Blue Eyes", "Super Rare"),
    ("yug-89832901", "Pot of Greed", "yugioh", "Starter Deck", "Super Rare"),
    ("yug-40319297", "Tri-Brigade Shuraig", "yugioh", "Rise of the Duelist", "Secret Rare"),
    ("opc-01001", "Monkey D. Luffy", "onepiece", "Romance Dawn", "Secret Rare"),
    ("opc-01015", "Roronoa Zoro", "onepiece", "Romance Dawn", "Super Rare"),
    ("opc-01007", "Nami", "onepiece", "Romance Dawn", "Super Rare"),
    ("opc-04024", "Sabo", "onepiece", "Paramilitary Force", "Super Rare"),
    ("opc-04011", "Portgas D. Ace", "onepiece", "The Best", "Rare"),
    ("opc-03013", "Trafalgar Law", "onepiece", "Pillars of Strength", "Rare"),
    ("opc-02002", "Eustass Kid", "onepiece", "Paramount War", "Super Rare"),
    ("other-1", "Dragon Ball Fusion World Goku", "other", "Fusion World", "Secret Rare"),
    ("other-2", "Digimon Omnimon", "other", "BT-01", "Secret Rare"),
]


def seed(cfg: Config) -> None:
    conn = db.connect(cfg.db_path)
    db.init_db(conn)

    if db.count_cards(conn) == 0:
        for key, name, cat, set_name, rarity in DEMO_CARDS:
            db.get_or_create_card(
                conn,
                Card(
                    card_key=key,
                    name=name,
                    category=cat,
                    set_name=set_name,
                    language="jp",
                    rarity=rarity,
                ),
            )
        conn.commit()
        logger.info("seeded %d demo cards", db.count_cards(conn))
    else:
        logger.info("cards already present (%d), skipping card seed", db.count_cards(conn))

    if db.count_prices(conn) == 0:
        from collectors.price_scraper import MockPriceScraper

        cards = [
            Card(card_key=r["card_key"], name=r["name"], category=r["category"], rarity=r["rarity"])
            for r in conn.execute("SELECT * FROM cards").fetchall()
        ]
        buy_sources = cfg.buy_sources or [
            PriceSource("mercari", "メルカリ", "buy", "JPY"),
            PriceSource("amazon", "Amazon", "buy", "JPY"),
        ]
        sell_sources = cfg.sell_sources or [
            PriceSource("tcgplayer", "TCGPlayer", "sell", "USD"),
            PriceSource("ebay", "eBay", "sell", "USD"),
        ]
        id_map = {r["card_key"]: int(r["id"]) for r in conn.execute("SELECT id, card_key FROM cards")}
        fx = {p: db.get_exchange_rate(conn, p) for p in ("USDJPY", "EURJPY")}
        fx = {k: v for k, v in fx.items() if v is not None}
        for source in buy_sources + sell_sources:
            scraper = MockPriceScraper(cfg, source, fx=fx)
            for card in cards:
                rec = scraper.fetch_price(card)
                if rec is None or card.card_key not in id_map:
                    continue
                rec.card_id = id_map[card.card_key]
                db.insert_price(conn, rec)
            conn.commit()
        logger.info("seeded %d price records", db.count_prices(conn))


    if db.get_exchange_rate(conn, "USDJPY") is None:
        db.upsert_exchange_rate(conn, "USDJPY", 150.0)
        db.upsert_exchange_rate(conn, "EURJPY", 163.0)
        logger.info("seeded fallback exchange rates")

    from core import analysis

    df = analysis.compute_spreads(conn, cfg)
    analysis.persist_spreads(conn, df)
    logger.info("computed %d demo spreads", len(df))
    conn.close()


def run(cfg: Config) -> None:
    seed(cfg)


if __name__ == "__main__":
    import logging as _logging

    from core.config import load_config

    _logging.basicConfig(level=_logging.INFO)
    seed(load_config())
