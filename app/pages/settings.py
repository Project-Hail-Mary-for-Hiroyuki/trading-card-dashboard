from __future__ import annotations

import json

import streamlit as st

from app.ui_components import (
    get_config,
    get_connection,
    save_config_overrides,
)
from core import analysis, database as db


def _load_overrides(conn) -> dict:
    raw = db.get_setting(conn, "config_overrides")
    if raw:
        try:
            return json.loads(raw)
        except (ValueError, TypeError):
            pass
    return {"fees": {}, "analysis": {}}


def render() -> None:
    cfg = get_config()
    conn = get_connection()

    st.title("設定")
    st.caption("手数料率・送料・閾値を変更し、データ収集を管理します")

    overrides = _load_overrides(conn)
    fees_ov = overrides.get("fees", {})
    analysis_ov = overrides.get("analysis", {})

    with st.form("fee_form"):
        st.subheader("手数料・コスト設定（%）")
        col1, col2, col3 = st.columns(3)
        with col1:
            ebay = st.number_input(
                "eBay 手数料 (%)",
                min_value=0.0,
                max_value=50.0,
                value=float(fees_ov.get("ebay", cfg.fees.ebay)) * 100,
                step=0.1,
            )
        with col2:
            tcg = st.number_input(
                "TCGPlayer 手数料 (%)",
                min_value=0.0,
                max_value=50.0,
                value=float(fees_ov.get("tcgplayer", cfg.fees.tcgplayer)) * 100,
                step=0.1,
            )
        with col3:
            cm = st.number_input(
                "Cardmarket 手数料 (%)",
                min_value=0.0,
                max_value=50.0,
                value=float(fees_ov.get("cardmarket", cfg.fees.cardmarket)) * 100,
                step=0.1,
            )
        col1, col2 = st.columns(2)
        with col1:
            shipping = st.number_input(
                "送料 (JPY)",
                min_value=0,
                value=int(fees_ov.get("shipping_cost_jpy", cfg.fees.shipping_cost_jpy)),
                step=100,
            )
        with col2:
            fx_markup = st.number_input(
                "為替レート上乗せ率 (%)",
                min_value=0.0,
                max_value=20.0,
                value=float(fees_ov.get("fx_markup", cfg.fees.fx_markup)) * 100,
                step=0.5,
            )
        st.subheader("分析閾値（%）")
        col1, col2 = st.columns(2)
        with col1:
            min_rate = st.number_input(
                "有望判定の利益率",
                min_value=0.0,
                max_value=200.0,
                value=float(analysis_ov.get("min_profit_rate", cfg.analysis.min_profit_rate)),
                step=1.0,
            )
        with col2:
            hot_rate = st.number_input(
                "注目判定の利益率",
                min_value=0.0,
                max_value=500.0,
                value=float(analysis_ov.get("hot_profit_rate", cfg.analysis.hot_profit_rate)),
                step=1.0,
            )
        submitted = st.form_submit_button("設定を保存", type="primary")

    if submitted:
        save_config_overrides(
            conn,
            {
                "fees": {
                    "ebay": round(ebay / 100, 4),
                    "tcgplayer": round(tcg / 100, 4),
                    "cardmarket": round(cm / 100, 4),
                    "shipping_cost_jpy": int(shipping),
                    "fx_markup": round(fx_markup / 100, 4),
                },
                "analysis": {
                    "min_profit_rate": float(min_rate),
                    "hot_profit_rate": float(hot_rate),
                },
            },
        )
        st.success("設定を保存しました。ダッシュボードに反映されます。")

    st.divider()

    st.subheader("データ収集")
    col1, col2, col3 = st.columns(3)
    run_fx = col1.button("為替レートを更新")
    run_prices = col2.button("価格を収集")
    run_spreads = col3.button("スプレッドを再計算")

    if run_fx or run_prices or run_spreads:
        with st.spinner("処理中..."):
            from core.scheduler import run_collection

            if run_fx:
                from collectors import exchange_rate

                rates = exchange_rate.fetch_exchange_rates(conn, cfg)
                st.success(f"為替を更新しました: {rates}")
            if run_prices:
                from collectors import price_scraper

                inserted = price_scraper.collect_prices(conn, cfg)
                st.success(f"価格レコードを {inserted} 件追加しました")
            if run_spreads:
                df = analysis.compute_spreads(conn, cfg)
                analysis.persist_spreads(conn, df)
                st.success(f"スプレッドを {len(df)} 件計算しました")

    st.divider()

    st.subheader("データ状態")
    card_count = db.count_cards(conn)
    price_count = db.count_prices(conn)
    fx_usd = db.get_exchange_rate(conn, "USDJPY")
    fx_eur = db.get_exchange_rate(conn, "EURJPY")
    last_spread = conn.execute("SELECT MAX(calculated_at) AS t FROM spreads").fetchone()["t"]

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("カード数", f"{card_count:,}")
    col2.metric("価格レコード", f"{price_count:,}")
    col3.metric("USD/JPY", f"{fx_usd:,.2f}" if fx_usd else "-")
    col4.metric("EUR/JPY", f"{fx_eur:,.2f}" if fx_eur else "-")
    st.caption(f"最終スプレッド計算: {last_spread or '未計算'}")

    st.divider()
    st.subheader("カタログ収集")
    if st.button("カードカタログを更新（外部API）"):
        with st.spinner("カタログを取得中..."):
            from collectors import catalog_api

            before = db.count_cards(conn)
            cards = catalog_api.fetch_catalog(cfg, limit=100)
            for card in cards:
                db.get_or_create_card(conn, card)
            conn.commit()
            after = db.count_cards(conn)
            st.success(f"カタログ取得: {len(cards)}件（新規追加 {after - before}件）")
