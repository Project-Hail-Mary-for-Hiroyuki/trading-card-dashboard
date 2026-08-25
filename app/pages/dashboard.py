from __future__ import annotations

import streamlit as st

from app.ui_components import (
    get_config,
    get_connection,
    kpi_card,
    plot_rate_distribution,
    render_ranking_table,
)
from core import analysis


def render() -> None:
    cfg = get_config()
    conn = get_connection()

    st.title("TCG 海外転売リサーチダッシュボード")
    st.caption("日本国内の仕入れ価格と海外（米国・欧州）の販売価格から利益スプレッドを分析します")

    df = analysis.compute_spreads(conn, cfg)
    summary = analysis.summarize(df, cfg)

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        kpi_card("対象カード数", f"{summary['card_count']:,}枚")
    with col2:
        kpi_card("平均利益率", f"{summary['average_rate']:+.1f}%")
    with col3:
        kpi_card("有望カード (20%以上)", f"{summary['promising_count']:,}枚")
    with col4:
        kpi_card("注目カード (50%以上)", f"{summary['hot_count']:,}枚")

    fx = analysis.resolve_fx(conn)
    if fx:
        st.caption(
            f"為替: USD/JPY = {fx.get('USDJPY', '-'):,.2f} / EUR/JPY = {fx.get('EURJPY', '-'):,.2f}　"
            f"手数料: {cfg.fees.tcgplayer*100:.1f}% (TCGPlayer), {cfg.fees.ebay*100:.1f}% (eBay), "
            f"{cfg.fees.cardmarket*100:.1f}% (Cardmarket)　送料: ¥{cfg.fees.shipping_cost_jpy:,.0f}"
        )

    st.divider()

    if df.empty:
        st.info(
            "まだ価格データがありません。左のサイドバーまたは `python -m scripts.collect all` で"
            "データ収集を実行してください。"
        )
        return

    st.subheader("利益率ランキング（上位20）")
    top = df.nlargest(20, "profit_rate_pct")
    st.dataframe(render_ranking_table(top, cfg), width="stretch", height=460)

    st.divider()
    st.subheader("利益率の分布")
    plot_rate_distribution(df)

    st.divider()
    st.subheader("カテゴリ別サマリー")
    st.dataframe(summary["category_summary"], width='stretch')

    st.divider()
    st.markdown(
        "**免責事項**: 本ツールの利益計算は参考値です。実際の取引結果を保証するものではなく、"
        "取引は自己責任で行ってください。"
    )
