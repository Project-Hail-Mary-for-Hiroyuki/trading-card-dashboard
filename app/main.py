from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st  # noqa: E402

from app.pages import alerts, dashboard, search, settings  # noqa: E402
from app.ui_components import get_config, get_connection, init_demo_if_empty  # noqa: E402

st.set_page_config(
    page_title="TCG 海外転売リサーチダッシュボード",
    layout="wide",
    initial_sidebar_state="expanded",
)

cfg = get_config()
conn = get_connection()
init_demo_if_empty(conn, cfg)

pg = st.navigation(
    [
        st.Page(dashboard.render, title="ダッシュボード", url_path="dashboard", default=True),
        st.Page(search.render, title="カード検索", url_path="search"),
        st.Page(alerts.render, title="アラート", url_path="alerts"),
        st.Page(settings.render, title="設定", url_path="settings"),
    ]
)
pg.run()
