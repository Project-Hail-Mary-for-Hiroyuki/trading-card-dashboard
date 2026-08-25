from __future__ import annotations

import enum
from dataclasses import dataclass, field


class Category(str, enum.Enum):
    POKEMON = "pokemon"
    YUGIOH = "yugioh"
    ONEPIECE = "onepiece"
    OTHER = "other"

    @classmethod
    def label(cls, value: str) -> str:
        return {
            cls.POKEMON.value: "ポケモン",
            cls.YUGIOH.value: "遊戯王",
            cls.ONEPIECE.value: "ワンピース",
            cls.OTHER.value: "その他",
        }.get(value, value)

    @classmethod
    def values(cls) -> list[str]:
        return [c.value for c in cls]


BUY_SIDES = ("buy",)
SELL_SIDES = ("sell",)


@dataclass
class Card:
    card_key: str
    name: str
    category: str
    set_name: str = ""
    language: str = ""
    rarity: str = ""
    image_url: str = ""

    @property
    def display_name(self) -> str:
        prefix = Category.label(self.category)
        return f"[{prefix}] {self.name}"


@dataclass
class PriceRecord:
    card_id: int
    source: str
    currency: str
    price: float
    extra: dict = field(default_factory=dict)


@dataclass
class Spread:
    card_id: int
    card_name: str
    category: str
    buy_price_jpy: float
    sell_price_jpy: float
    gross_profit_jpy: float
    fee_rate: float
    net_profit_jpy: float
    profit_rate_pct: float
    source_sell: str
    exchange_rate: float

    # 判定は core.analysis.classify(rate, cfg) に一本化（config閾値を参照）


@dataclass
class AlertSettings:
    min_profit_rate: float = 20.0
    categories: list = field(default_factory=lambda: [c.value for c in Category])
