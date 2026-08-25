from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from app.ui_components import get_config, get_connection, link_column_config, render_ranking_table
from core import analysis, database as db
from core.models import AlertSettings, Category


def _load_alert_settings(conn, cfg) -> AlertSettings:
    raw = db.get_setting(conn, "alert_settings")
    if raw:
        try:
            data = json.loads(raw)
            return AlertSettings(
                min_profit_rate=float(data.get("min_profit_rate", cfg.analysis.min_profit_rate)),
                categories=[c for c in data.get("categories", []) if c in Category.values()],
            )
        except (ValueError, TypeError):
            pass
    return AlertSettings(
        min_profit_rate=cfg.analysis.min_profit_rate,
        categories=[c.value for c in Category],
    )


def _save_alert_settings(conn, settings: AlertSettings) -> None:
    db.set_setting(
        conn,
        "alert_settings",
        json.dumps(
            {
                "min_profit_rate": settings.min_profit_rate,
                "categories": settings.categories,
            }
        ),
    )


def render() -> None:
    cfg = get_config()
    conn = get_connection()

    st.title("アラート")
    st.caption("閾値を超えた利益率のカードを一覧表示します")

    settings = _load_alert_settings(conn, cfg)

    with st.form("alert_form"):
        col1, col2 = st.columns(2)
        with col1:
            threshold = st.number_input(
                "利益率の閾値 (%)",
                min_value=0.0,
                max_value=500.0,
                value=float(settings.min_profit_rate),
                step=1.0,
            )
        with col2:
            cat_labels = {Category.label(c): c for c in Category}
            selected = st.multiselect(
                "対象カテゴリ",
                list(cat_labels.keys()),
                default=[Category.label(c) for c in settings.categories],
            )
        submitted = st.form_submit_button("設定を保存", type="primary")

    if submitted:
        cats = [cat_labels[x] for x in selected] if selected else []
        settings = AlertSettings(min_profit_rate=threshold, categories=cats)
        _save_alert_settings(conn, settings)
        st.success("アラート設定を保存しました")

    st.divider()

    matched = analysis.alert_matches(conn, cfg, settings)
    st.subheader(f"条件に合致するカード（利益率 {settings.min_profit_rate:g}% 以上）")
    st.markdown(f"該当: **{len(matched)}枚**　カテゴリ: {', '.join(Category.label(c) for c in settings.categories) or 'すべて'}")

    if matched.empty:
        st.info("条件に合致するカードがありません")
        return

    st.dataframe(
        render_ranking_table(matched, cfg),
        width="stretch",
        height=480,
        column_config=link_column_config(),
        hide_index=True,
    )
