from __future__ import annotations

import logging
from typing import Callable

from core.config import Config
from core.models import Card

logger = logging.getLogger(__name__)


def fetch_catalog(
    config: Config,
    category: str | None = None,
    limit: int = 500,
    progress: Callable[[int, str], None] | None = None,
) -> list[Card]:
    """Fetch card catalog. Falls back gracefully per-source so one failing
    API never breaks the whole run."""
    cards: list[Card] = []
    category = (category or "").lower()
    steps = []

    if category in ("", "pokemon"):
        steps.append(("pokemon", _fetch_tcgdex, config))
    if category in ("", "yugioh"):
        steps.append(("yugioh", _fetch_ygoprodeck, config))
    if category in ("", "onepiece"):
        steps.append(("onepiece", _fetch_onepiece, config))

    for cat, func, cfg in steps:
        try:
            batch = func(cfg, limit=limit)
            cards.extend(batch)
            if progress:
                progress(len(batch), cat)
            logger.info("catalog[%s]: %d cards", cat, len(batch))
        except Exception as exc:  # noqa: BLE001 - keep other sources alive
            logger.warning("catalog[%s] failed: %s", cat, exc)
            if progress:
                progress(0, cat)
    return cards


def _fetch_tcgdex(config: Config, limit: int) -> list[Card]:
    from collectors.base import BaseCollector

    col = BaseCollector(config)
    base = config.catalog["tcgdex_base_url"].rstrip("/")
    locale = config.catalog.get("tcgdex_locale", "en")
    cards: list[Card] = []
    page = 1
    per_page = 100
    while len(cards) < limit:
        data = col.fetch_json(
            f"{base}/{locale}/cards",
            params={"pagination:page": page, "pagination:itemsPerPage": per_page},
        )
        if not data:
            break
        for c in data:
            cards.append(
                Card(
                    card_key=c["id"],
                    name=c["name"],
                    category="pokemon",
                    set_name=c.get("set", {}).get("name", ""),
                    language=locale,
                    rarity=c.get("rarity", ""),
                    image_url=c.get("image", "") or "",
                )
            )
        page += 1
    return cards[:limit]


def _fetch_ygoprodeck(config: Config, limit: int) -> list[Card]:
    from collectors.base import BaseCollector

    col = BaseCollector(config)
    url = config.catalog["ygoprodeck_url"]
    data = col.fetch_json(url, params={"num": min(limit, 1000), "offset": 0})
    cards: list[Card] = []
    for c in (data or {}).get("data", []):
        cards.append(
            Card(
                card_key=str(c.get("id", "")),
                name=c.get("name", ""),
                category="yugioh",
                set_name=", ".join(s.get("set_name", "") for s in c.get("card_sets", [])[:2]),
                language="en",
                rarity=", ".join(s.get("set_rarity", "") for s in c.get("card_sets", [])[:2]),
                image_url=(c.get("card_images") or [{}])[0].get("image_url", ""),
            )
        )
    return cards[:limit]


def _fetch_onepiece(config: Config, limit: int) -> list[Card]:
    from collectors.base import BaseCollector

    col = BaseCollector(config)
    url = config.catalog["onepiece_url"]
    data = col.fetch_json(url, params={"page": 1, "pageSize": limit})
    items = data if isinstance(data, list) else (data or {}).get("items", data or {}).get("cards", [])
    cards: list[Card] = []
    for c in items:
        cards.append(
            Card(
                card_key=str(c.get("id", "")),
                name=c.get("name", ""),
                category="onepiece",
                set_name=c.get("set", {}).get("name", "") if isinstance(c.get("set"), dict) else c.get("set_name", ""),
                language="en",
                rarity=c.get("rarity", ""),
                image_url=c.get("image_url", c.get("image", "")) or "",
            )
        )
    return cards[:limit]
