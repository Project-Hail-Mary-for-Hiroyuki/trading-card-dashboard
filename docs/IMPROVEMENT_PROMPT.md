# 構造化プロンプト: trading-card-dashboard コード改善

## 1. 役割定義
> あなたはPython/Streamlitアプリケーションのシニアレビュアー兼リファクタリングエンジニアです。TCG海外転売リサーチダッシュボード（Streamlit + SQLite + pandas + plotly）のコードベースを、**動作を壊さない範囲で**段階的に改善します。外部依存の追加は最小限にとどめ、既存の設計方針（収集/分析/UIの分離、config駆動スクレイピング）は維持してください。

## 2. 制約条件
- Python 3.10+ / 既存 requirements.txt のライブラリのみ使用（テスト用に pytest の追加は可）
- 各フェーズ終了後に `streamlit run app/main.py` および `python3 -m scripts.collect all`（mock有効）でスモーク確認すること
- 破壊的変更（DBスキーマ変更・設定キー削除）を行う場合はマイグレーション手順を README に追記すること
- スクレイピング関連（間隔制御・robots.txt配慮）の仕様は緩めてはならない

## 3. 発見済みの問題点と改善タスク

### フェーズ1: パフォーマンス（最優先）
- **[P1] `core/analysis.py` `compute_spreads()` のN+1クエリ**
  - カード毎・ソース毎に `db.latest_price()` を個別実行しており O(カード数×ソース数) 回のクエリが発生する。カード数百件で顕著に遅い。
  - 改善: 1つのウィンドウ関数クエリ（`ROW_NUMBER() OVER (PARTITION BY card_id, source ORDER BY fetched_at DESC)`）または集約SQLで全最新価格を一括取得する。
- **[P1] `app/ui_components.py` `render_ranking_table()` 内 `verdict_col` が行ごとに `get_config()` を呼ぶ**
  - 判定閾値は引数またはクロージャで渡し、`get_config()` は1回だけ呼ぶ。
- **[P2] `app/pages/search.py` が全カードをPython側でフィルタ**
  - `SELECT ... FROM cards` を全部読み込んでループ比較している。SQLの `WHERE name LIKE ? COLLATE NOCASE` + `category = ?` に置換し、LIMITをかける。

### フェーズ2: 正確性バグ
- **[B1] `fees.fx_markup`（為替上乗せ率）がどこにも使用されていない**
  - `analysis.compute_spreads()` のJPY換算に `(1 + fx_markup)` を適用するか、UIから削除するか決めて実装する。
- **[B2] 判定ロジックの二重定義**
  - `core/models.py Spread.verdict` は閾値50/20がハードコード。`analysis.classify()` はconfig参照。`Spread.verdict` を廃止し `classify()` に統一する。
- **[B3] `scripts/collect.py` が `if __name__ == "__main__":` ガードなしでモジュール読み込み時に argparse 実行される**
  - import時に副作用があるため、ガードを付け `main()` 関数に集約する。
- **[B4] `app/pages/settings.py` の「新規追加 n件」カウントが不正**
  - `db.get_or_create_card()` は既存カードのidも返すため常に全件カウントになる。戻り値ではなく挿入前後の `count_cards()` 差分で計算する。
- **[B5] `core/config.py` `load_config()` のdb_path解決ロジック**
  - `path.name != "config.yaml"` の分岐が直感に反し、CWD依存でDB場所が変わる。プロジェクトルート基準に固定する。
- **[B6] `collectors/price_scraper.py` `collect_prices()` でカードごとにcard_key→id検索を実行**
  - 事前に `{card_key: id}` マップを作ってO(1)参照にする。
- **[B7] `core/scheduler.py` `run_collection()` が `init_db()` を呼ばない**
  - 新規DBでスケジューラ起動するとクラッシュする。`db.init_db(conn)` を追加。

### フェーズ3: データ整合性・運用性
- **[D1] prices テーブルに重複蓄積**
  - 同日同ソースの再取得でも無条件INSERTされる。UNIQUE(card_id, source, date(fetched_at)) 制約 + UPSERT、または取得前チェックを追加。
- **[D2] `spreads.latest_spreads()` の `MAX(calculated_at)` 全体比較**
  - 秒精度のタイスタンプのため同時刻の一部行のみ返る恐れ。最新runを識別する `run_id` を導入するか `MAX(id)` 基準に変更。
- **[D3] ログ設計**
  - Streamlit UI実行時はloggingが表示されない。`st.status`/`st.toast` への収集結果通知、またはファイルハンドラ追加。
- **[D4] `exchange_rate.py` がAPIを2回叩く**
  - USDレート応答の `rates` にはEUR/JPYも含まれる。1リクエストで両ペア取得する。

### フェーズ4: テスト整備
- pytest を導入し、以下のユニットテストを作成:
  - `_resolve_json_path` / `_to_number`（price_scraper）
  - `compute_spreads`（in-memory SQLite + フィクスチャデータ、fx_markup適用も検証）
  - `classify` の境界値（19.9/20.0/49.9/50.0）
  - `load_config` のマージ・db_path解決
- CI想定のコマンド例をREADMEに記載（`python3 -m pytest`）。

## 5. 成果物
1. リファクタリング済みコード（フェーズ順にコミット分割）
2. `tests/` ディレクトリとユニットテスト
3. 変更点まとめ（README の CHANGELOG セクション or PR説明文）

## 6. 完了条件
- [ ] `python3 -m scripts.collect all` がモックで正常完了する
- [ ] `streamlit run app/main.py --server.port 8501` で4ページすべて動作する
- [ ] `pytest` がグリーン
- [ ] compute_spreads が500カードで1秒以内（目安）
