from __future__ import annotations

import json

import streamlit as st
import pandas as pd
import plotly.express as px

from core.config import Config, load_config, apply_overrides
from core import database as db
from core.models import Category

CATEGORY_COLORS = {
    "pokemon": "#ef5350",
    "yugioh": "#42a5f5",
    "onepiece": "#ffca28",
    "other": "#66bb6a",
}

VERDICT_COLORS = {
    "注目": "background-color: #fef3c7; color: #92400e",
    "有望": "background-color: #d1fae5; color: #065f46",
    "慎重": "background-color: #e0e7ff; color: #3730a3",
    "不可": "background-color: #fee2e2; color: #991b1b",
}


@st.cache_resource
def get_connection():
    cfg = load_config()
    conn = db.connect(cfg.db_path)
    db.init_db(conn)
    return conn


def get_config() -> Config:
    cfg = load_config()
    conn = get_connection()
    raw = db.get_setting(conn, "config_overrides")
    if raw:
        try:
            cfg = apply_overrides(cfg, json.loads(raw))
        except (ValueError, TypeError):
            pass
    return cfg


def save_config_overrides(conn, overrides: dict) -> None:
    db.set_setting(conn, "config_overrides", json.dumps(overrides))


def init_demo_if_empty(conn, cfg: Config) -> None:
    if db.count_cards(conn) == 0:
        from scripts.seed_demo import seed

        seed(cfg)


def format_jpy(value: float) -> str:
    if value is None:
        return "-"
    return f"¥{value:,.0f}"


def format_pct(value: float) -> str:
    if value is None:
        return "-"
    return f"{value:+.1f}%"


def category_label(value: str) -> str:
    return Category.label(value)


def kpi_card(label: str, value: str, help: str | None = None) -> None:
    st.markdown(
        f"""
        <div style="background:#0e1117;border:1px solid #31333f;border-radius:10px;
             padding:16px 18px;margin-bottom:8px;">
            <div style="color:#8b93a7;font-size:0.85rem;">{label}</div>
            <div style="color:#fafafa;font-size:1.6rem;font-weight:700;margin-top:2px;">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _source_link_url(source_name: str, card_name: str, cfg: Config) -> str | None:
    src = cfg.source(source_name)
    if not src:
        return None
    return src.search_url(card_name)


# st.dataframe 用のリンク列設定（セルのURLを「開く」表示でクリック可能にする）
def link_column_config() -> dict:
    return {
        "仕入れリンク": st.column_config.LinkColumn(
            "仕入れ ⧉", display_text="🔍 開く"
        ),
        "売却リンク": st.column_config.LinkColumn(
            "売却 ⧉", display_text="🔍 開く"
        ),
    }


def render_ranking_table(df: pd.DataFrame, cfg: Config, with_set: bool = True):
    if df.empty:
        return pd.DataFrame()

    def verdict_col(rate: float) -> str:
        return (
            "注目"
            if rate >= cfg.analysis.hot_profit_rate
            else "有望"
            if rate >= cfg.analysis.min_profit_rate
            else "慎重"
            if rate >= 0
            else "不可"
        )

    out = df.copy()
    out["カテゴリ"] = out["category"].map(category_label)
    out["カード名"] = out["card_name"]
    if with_set:
        out["セット"] = out["set_name"]
    out["仕入価格"] = out["buy_price_jpy"].map(format_jpy)
    out["売却価格"] = out["sell_price_jpy"].map(format_jpy)
    out["手数料率"] = (out["fee_rate"] * 100).map(lambda v: f"{v:.1f}%")
    out["純利益"] = out["net_profit_jpy"].map(format_jpy)
    out["利益率"] = out["profit_rate_pct"]
    out["判定"] = out["profit_rate_pct"].map(verdict_col)
    out["売却先"] = out["source_sell"].map(lambda s: _source_label(s, cfg))

    # 仕入れ先・売却先への検索リンク（LinkColumn用に生URLを入れる）
    out["仕入れリンク"] = [
        _source_link_url(b, n, cfg)
        for b, n in zip(out["source_buy"], out["card_name"])
    ]
    out["売却リンク"] = [
        _source_link_url(s, n, cfg)
        for s, n in zip(out["source_sell"], out["card_name"])
    ]



    keep = ["カテゴリ", "カード名"]
    if with_set:
        keep.append("セット")
    keep += ["仕入価格", "売却価格", "手数料率", "純利益", "利益率", "判定", "売却先",
             "仕入れリンク", "売却リンク"]

    styled = (
        out[keep]
        .style.format({"利益率": "{:+.1f}%"})
        .map(_style_verdict, subset=["判定"])
        .map(_style_rate, subset=["利益率"])
    )
    return styled


def _source_label(source: str, cfg: Config | None = None) -> str:
    cfg = cfg or get_config()
    s = cfg.source(source)
    return s.label if s else source



def _style_verdict(v: str) -> str:
    return VERDICT_COLORS.get(v, "")


def _style_rate(v: float) -> str:
    if v >= 50:
        return "color: #10b981; font-weight: 700;"
    if v >= 20:
        return "color: #34d399;"
    if v >= 0:
        return "color: #93c5fd;"
    return "color: #f87171;"


def plot_rate_distribution(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("表示できるデータがありません")
        return
    fig = px.histogram(
        df,
        x="profit_rate_pct",
        color="category",
        color_discrete_map=CATEGORY_COLORS,
        nbins=30,
        labels={
            "profit_rate_pct": "利益率 (%)",
            "count": "カード数",
            "category": "カテゴリ",
        },
    )
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig, width='stretch')


def plot_price_trend(dates, values, label: str) -> None:
    fig = px.line(
        x=dates,
        y=values,
        labels={"x": "取得日時", "y": label},
    )
    fig.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10))
    st.plotly_chart(fig, width='stretch')
