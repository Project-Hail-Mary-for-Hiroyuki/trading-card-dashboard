from __future__ import annotations

import pandas as pd
import streamlit as st

from app.ui_components import (
    get_config,
    get_connection,
    format_jpy,
    format_pct,
    plot_price_trend,
)
from core import analysis, database as db
from core.models import Category


def render() -> None:
    cfg = get_config()
    conn = get_connection()

    st.title("カード検索")
    st.caption("カードを絞り込んで、価格の推移とスプレッドの詳細を確認します")

    categories = [c.value for c in Category]
    cat_options = {Category.label(c): c for c in categories}
    col1, col2 = st.columns([2, 1])
    with col1:
        q = st.text_input("カード名で検索", placeholder="例: Pikachu, Charizard, Luffy")
    with col2:
        selected_cat = st.selectbox("カテゴリ", ["すべて"] + list(cat_options.keys()))

    cat_value = cat_options.get(selected_cat) if selected_cat != "すべて" else None
    name_q = q.strip()

    # SQL側でフィルタし、全カードの読み込みを避ける
    matches = conn.execute(
        """
        SELECT id, card_key, name, category, set_name, rarity, image_url FROM cards
        WHERE (:name_q = '' OR lower(name) LIKE '%' || lower(:name_q) || '%')
          AND (:cat IS NULL OR category = :cat)
        ORDER BY name
        LIMIT 200
        """,
        {"name_q": name_q, "cat": cat_value},
    ).fetchall()

    st.markdown(f"**{len(matches)}件** のカードが該当")

    if not matches:
        st.info("条件に一致するカードがありません")
        return

    card_id = int(matches[0]["id"])
    if len(matches) > 1:
        label_by_id = {
            r["id"]: f"[{Category.label(r['category'])}] {r['name']}  ({r['set_name'] or '未設定'})"
            for r in matches
        }
        choice = st.selectbox("カードを選択", list(label_by_id.values()))
        card_id = next(k for k, v in label_by_id.items() if v == choice)

    sel = next(r for r in matches if r["id"] == card_id)
    col1, col2 = st.columns([1, 2])

    with col1:
        if sel["image_url"]:
            try:
                st.image(sel["image_url"], width=220)
            except Exception:
                st.caption("画像を取得できませんでした")
        st.markdown(
            f"**{sel['name']}**\n\n"
            f"- カテゴリ: {Category.label(sel['category'])}\n"
            f"- セット: {sel['set_name'] or '-'}\n"
            f"- レアリティ: {sel['rarity'] or '-'}"
        )

    with col2:
        latest = {}
        for source in cfg.all_sources:
            row = db.latest_price(conn, card_id, source.name)
            if row:
                latest[source.name] = row

        st.subheader("最新価格（ソース別）")
        if latest:
            rows = []
            for source in cfg.all_sources:
                row = latest.get(source.name)
                if not row:
                    continue
                price = float(row["price"])
                side = "仕入れ" if source.side == "buy" else "販売"
                rows.append(
                    {
                        "区分": side,
                        "ソース": source.label,
                        "通貨": source.currency,
                        "価格": format_jpy(price) if source.currency == "JPY" else f"{price:,.2f} {source.currency}",
                        "取得日時": row["fetched_at"],
                    }
                )
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        else:
            st.caption("価格データがありません")

    st.divider()

    st.subheader("価格推移")
    history = db.price_history(conn, card_id)
    if history:
        sources_with_data = sorted({h["source"] for h in history})
        source_choice = st.multiselect("表示するソース", sources_with_data, default=sources_with_data)
        series = [
            h for h in history if h["source"] in source_choice
        ]
        if series:
            dates = [h["fetched_at"] for h in series]
            labels = [
                f"{h['price']:,.0f} {h['currency']} ({cfg.source(h['source']).label if cfg.source(h['source']) else h['source']})"
                for h in series
            ]
            plot_price_trend(dates, [float(h["price"]) for h in series], "価格")
            st.caption("・".join(sorted(set(labels))))
        else:
            st.caption("表示する価格データがありません")
    else:
        st.caption("価格履歴がありません")

    st.divider()

    st.subheader("スプレッド履歴")
    spreads = db.spread_history(conn, card_id)
    if spreads:
        sdf = pd.DataFrame(
            [
                {
                    "計算日時": s["calculated_at"],
                    "仕入価格(JPY)": format_jpy(s["buy_price_jpy"]),
                    "売却価格(JPY)": format_jpy(s["sell_price_jpy"]),
                    "純利益(JPY)": format_jpy(s["net_profit_jpy"]),
                    "利益率": format_pct(s["profit_rate_pct"]),
                }
                for s in spreads
            ]
        )
        st.dataframe(sdf, width="stretch", hide_index=True)
        plot_price_trend(
            [s["calculated_at"] for s in spreads],
            [s["profit_rate_pct"] for s in spreads],
            "利益率 (%)",
        )
    else:
        st.caption("スプレッド計算履歴がありません")
