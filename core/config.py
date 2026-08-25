from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULTS: dict = {
    "database": {
        "path": "data/trading_cards.db",
    },
    "http": {
        "request_interval": 3.0,
        "request_timeout": 20,
        "max_retries": 3,
        "user_agent": "trading-card-dashboard/0.1 (+research dashboard)",
    },
    "fees": {
        "ebay": 0.1325,
        "tcgplayer": 0.10,
        "cardmarket": 0.05,
        "shipping_cost_jpy": 500,
        "fx_markup": 0.03,
    },
    "analysis": {
        "min_profit_rate": 20.0,
        "hot_profit_rate": 50.0,
    },
    "exchange": {
        "api_url": "https://open.er-api.com/v6/latest/USD",
    },
    "catalog": {
        "tcgdex_base_url": "https://api.tcgdex.net/v2",
        "tcgdex_locale": "en",
        "ygoprodeck_url": "https://db.ygoprodeck.com/api/v7/cardinfo.php",
        "onepiece_url": "https://api.onepiece-cardgame.dev/api/cards",
    },
    "mock": {
        "enabled": True,
    },
    "price_sources": {
        "buy": [
            {
                "name": "mercari",
                "label": "メルカリ",
                "currency": "JPY",
                "url_template": "",
                "link_template": "https://jp.mercari.com/search?keyword={query}",
                "enabled": False,
            },
            {
                "name": "amazon",
                "label": "Amazon",
                "currency": "JPY",
                "url_template": "",
                "link_template": "https://www.amazon.co.jp/s?k={query}",
                "enabled": False,
            },
            {
                "name": "suruga",
                "label": "駿河屋",
                "currency": "JPY",
                "url_template": "",
                "link_template": "https://www.suruga-ya.jp/search?category=&search_word={query}",
                "enabled": False,
            },
        ],
        "sell": [
            {
                "name": "tcgplayer",
                "label": "TCGPlayer",
                "currency": "USD",
                "url_template": "",
                "link_template": "https://www.tcgplayer.com/search/all/product?q={query}",
                "enabled": False,
            },
            {
                "name": "ebay",
                "label": "eBay",
                "currency": "USD",
                "url_template": "",
                "link_template": "https://www.ebay.com/sch/i.html?_nkw={query}",
                "enabled": False,
            },
            {
                "name": "cardmarket",
                "label": "Cardmarket",
                "currency": "EUR",
                "url_template": "",
                "link_template": "https://www.cardmarket.com/en/AllProducts?searchString={query}",
                "enabled": False,
            },
        ],
    },
}


@dataclass
class FeeConfig:
    ebay: float = 0.1325
    tcgplayer: float = 0.10
    cardmarket: float = 0.05
    shipping_cost_jpy: float = 500
    fx_markup: float = 0.03

    def fee_for(self, source: str) -> float:
        key = source.lower()
        if key in ("tcgplayer", "tcg_player"):
            return self.tcgplayer
        if key == "ebay":
            return self.ebay
        if key == "cardmarket":
            return self.cardmarket
        return 0.0


@dataclass
class AnalysisConfig:
    min_profit_rate: float = 20.0
    hot_profit_rate: float = 50.0


@dataclass
class HttpConfig:
    request_interval: float = 3.0
    request_timeout: int = 20
    max_retries: int = 3
    user_agent: str = "trading-card-dashboard/0.1"


@dataclass
class PriceSource:
    name: str
    label: str
    side: str
    currency: str
    url_template: str = ""
    enabled: bool = False
    extra: dict = field(default_factory=dict)
    link_template: str = ""

    def search_url(self, card_name: str) -> str | None:
        """Return a human-clickable search URL for the card, if configured."""
        import re
        import urllib.parse

        if not self.link_template:
            return None
        query = re.sub(r"[^0-9A-Za-z ]", "", card_name).strip()
        return self.link_template.format(query=urllib.parse.quote(query))



@dataclass
class Config:
    db_path: Path
    http: HttpConfig
    fees: FeeConfig
    analysis: AnalysisConfig
    exchange_api_url: str
    catalog: dict = field(default_factory=dict)
    buy_sources: list = field(default_factory=list)
    sell_sources: list = field(default_factory=list)
    raw: dict = field(default_factory=dict)

    @property
    def all_sources(self) -> list[PriceSource]:
        return self.buy_sources + self.sell_sources

    def source(self, name: str) -> PriceSource | None:
        for s in self.all_sources:
            if s.name == name:
                return s
        return None


def _merge(base: dict, override: dict) -> dict:
    merged = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = _merge(merged[k], v)
        else:
            merged[k] = v
    return merged


def load_config(path: str | Path | None = None) -> Config:
    if path is None:
        path = Path(__file__).resolve().parent.parent / "config.yaml"
    path = Path(path)
    raw: dict = copy.deepcopy(DEFAULTS)
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            raw = _merge(raw, yaml.safe_load(f) or {})

    db_path = Path(raw["database"]["path"])
    if not db_path.is_absolute():
        # プロジェクトルート（core/ の親）基準で固定し、CWDに依存しない
        project_root = Path(__file__).resolve().parent.parent
        db_path = project_root / db_path

    sources = []
    for side in ("buy", "sell"):
        for s in raw["price_sources"][side]:
            sources.append(
                PriceSource(
                    name=s.get("name", ""),
                    label=s.get("label", s.get("name", "")),
                    side=side,
                    currency=s.get("currency", "JPY"),
                    url_template=s.get("url_template", ""),
                    enabled=bool(s.get("enabled", False)),
                    extra=s.get("extra", {}),
                    link_template=s.get(
                        "link_template",
                        next(
                            (d["link_template"] for d in DEFAULTS["price_sources"][side] if d["name"] == s.get("name")),
                            "",
                        ),
                    ),
                )
            )

    cfg = Config(
        db_path=db_path,
        http=HttpConfig(**raw["http"]),
        fees=FeeConfig(**raw["fees"]),
        analysis=AnalysisConfig(**raw["analysis"]),
        exchange_api_url=raw["exchange"]["api_url"],
        catalog=raw["catalog"],
        raw=raw,
    )
    cfg.buy_sources = [s for s in sources if s.side == "buy"]
    cfg.sell_sources = [s for s in sources if s.side == "sell"]
    return cfg


def find_config_file() -> Path | None:
    candidates = [
        Path(os.getcwd()) / "config.yaml",
        Path(__file__).resolve().parent.parent / "config.yaml",
    ]
    for c in candidates:
        if c.exists():
            return c
    return None


def apply_overrides(cfg: Config, overrides: dict) -> Config:
    fees = overrides.get("fees", {}) or {}
    analysis_ov = overrides.get("analysis", {}) or {}

    for key in ("ebay", "tcgplayer", "cardmarket"):
        if key in fees:
            setattr(cfg.fees, key, float(fees[key]))
    for key in ("shipping_cost_jpy", "fx_markup"):
        if key in fees:
            setattr(cfg.fees, key, float(fees[key]))
    for key in ("min_profit_rate", "hot_profit_rate"):
        if key in analysis_ov:
            setattr(cfg.analysis, key, float(analysis_ov[key]))
    return cfg
