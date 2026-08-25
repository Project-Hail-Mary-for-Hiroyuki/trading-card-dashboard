# 海外トレーディングカード利益リサーチダッシュボード — 開発プラン

## 0. プロジェクト概要

海外（米国・欧州）市場で**短期フリップ（仕入れ→転売）**で利益が出せるトレーディングカードをリサーチし、可視化する Streamlit ダッシュボードアプリを開発する。

- **戦略**: 仕入れ値（日本国内・低価格帯）と販売値（海外・高価格帯）の**価格スプレッド**を検出し、利益率の高いカードをランキング表示
- **対象カード**:
  - ポケモンカード（日本語版・英語版）
  - 遊戯王
  - ワンピースカード（OPCG）
  - その他日本発 TCG
- **データソース**: API + スクレイピングのハイブリッド

---

## 1. 構造化プロンプト（開発指示書）

以下を各フェーズの実装時にプロンプトとして使用する。

### 1.1 役割定義
> あなたはトレーディングカードの海外転売リサーチツールを開発するシニアデータエンジニア兼フルスタック開発者です。Streamlit を用いて、収集・分析・可視化を行うプロトタイプを段階的に構築します。

### 1.2 技術スタック
- Python 3.10+
- Streamlit（UI）
- pandas / numpy（分析）
- requests / httpx（データ取得）
- BeautifulSoup4 / lxml（スクレイピング）
- APScheduler（定期収集）
- SQLite（永続化）→ 必要に応じて PostgreSQL へ移行可能

### 1.3 データモデル（SQLite テーブル）
- `cards`: id, name, set_name, category(enum: pokemon/yugioh/onepiece/other), language, rarity, image_url, created_at
- `prices`: id, card_id, source(enum: buy_mercari/buy_amazon/buy_suruga/sell_tcgplayer/sell_ebay/sell_cardmarket), price_jpy, price_usd, price_eur, currency, fetched_at
- `spreads`: id, card_id, buy_price_jpy, sell_price_jpy, gross_profit_jpy, fee_rate, net_profit_jpy, profit_rate_pct, exchange_rate, calculated_at
- `exchange_rates`: currency_pair, rate, fetched_at

### 1.4 分析ロジック
- **スプレッド計算**:
  - `net_profit = sell_price × (1 - fee_rate) × exchange_rate - buy_price - shipping_cost`
  - `profit_rate_pct = net_profit / buy_price × 100`
- **手数料（参考値、設定画面で可変）**: eBay ~13%、TCGPlayer ~10%、Cardmarket ~5%＋送金手数料
- **為替**: USD/JPY, EUR/JPY を外部API（無料: exchangerate-api 等）で取得しキャッシュ
- **利益基準**: profit_rate_pct >= 20% を「有望」、>= 50% を「注目」として判定

### 1.5 データ収集設計（ハイブリッド）
| 用途 | ソース | 方式 | 頻度 |
|---|---|---|---|
| カードカタログ | Pokémon TCG API / TCGdex / その他無料API | API | 週次 |
| 海外販売価格 | TCGPlayer, eBay, Cardmarket | スクレイピング | 日次 |
| 国内仕入れ価格 | メルカリ / Amazon / 駿河屋 | スクレイピング | 日次 |
| 為替レート | 無料為替API | API | 日次 |

- スクレイピングは**利用規約・robots.txt を遵守**し、リクエスト間隔（3秒以上）・ユーザーエージェント・レート制限を必ず実装する
- API があるソースは優先して API を使用
- 失敗時はリトライ（上限3回）+ 指数バックオフ

### 1.6 UI 設計（Streamlit マルチページ）
- **ページ1: ダッシュボード**
  - KPI: 有望カード数、平均利益率、市場売上合計、為替レート
  - 利益率ランキングテーブル（ソート・フィルタ）
  - カテゴリ別・セット別集計
- **ページ2: カード検索**
  - カード名・カテゴリ・セット・レアリティで検索
  - 個別カードの価格推移チャート（plotly）
  - スプレッド推移・売買タイミングの可視化
- **ページ3: アラート設定**
  - 利益率閾値、対象カテゴリを設定
  - 条件に合致したカードの一覧表示（通知は後日）
- **ページ4: 設定**
  - 手数料率・送料・為替レート上乗せ率・利益率閾値を可変設定

### 1.7 品質要件
- モジュール分割（収集/分析/UI を分離）、単一責任を守る
- スクレイピング例外・API エラーは全て捕捉し、UI でエラーを明示
- 外部依存は最小化し、要件にないライブラリは追加しない
- コードに説明コメントを過剰に書かない（必要な箇所のみ）

---

## 2. 開発フェーズ計画

### フェーズ1: 基盤構築
- プロジェクト構成・venv・requirements.txt 作成
- SQLite スキーマ定義 + DB 初期化モジュール
- 設定管理（config.yaml または .env + dataclass）

### フェーズ2: データ収集モジュール
- カードカタログ API クライアント（ポケモン → 遊戯王 → ワンピースの順）
- 価格スクレイパー（海外販売価格）
- 価格スクレイパー（国内仕入れ価格）
- 為替レート取得
- 収集実行スクリプト（CLI: `python -m collector run`）

### フェーズ3: 分析エンジン
- スプレッド計算・利益率算出ロジック
- ランキング・フィルタ・集計関数
- 価格推移・トレンド指標

### フェーズ4: Streamlit UI
- マルチページ構成 + サイドバーナビゲーション
- ダッシュボード / 検索 / アラート / 設定の各ページ実装
- plotly によるチャート描画

### フェーズ5: 定期実行と運用
- APScheduler による定期収集（日次）
- 設定の永続化（SQLite に保存）
- ログ出力（logging）
- 起動スクリプト `start.sh`（Streamlit + スケジューラを一括起動）

### フェーズ6: 検証・ドキュメント
- スモークテスト（モックデータで UI・分析の動作確認）
- README 作成（セットアップ手順・使い方・免責事項）
- デプロイプレビュー（/deploy-website）

---

## 3. ディレクトリ構成（予定）

```
trading-card-dashboard/
├── app/
│   ├── main.py                 # Streamlit エントリポイント
│   ├── pages/
│   │   ├── 1_dashboard.py
│   │   ├── 2_search.py
│   │   ├── 3_alerts.py
│   │   └── 4_settings.py
│   └── ui_components.py
├── core/
│   ├── config.py               # 設定管理
│   ├── database.py             # SQLite 接続・スキーマ
│   ├── models.py               # データクラス
│   ├── analysis.py             # スプレッド・利益率計算
│   └── scheduler.py            # 定期収集
├── collectors/
│   ├── base.py                 # 共通ベース（リトライ・間隔制御）
│   ├── catalog_api.py          # カードカタログ
│   ├── price_scraper.py        # 価格スクレイパー
│   └── exchange_rate.py        # 為替
├── requirements.txt
├── config.example.yaml
└── README.md
```

---

## 4. リスクと対策

| リスク | 対策 |
|---|---|
| スクレイピングがサイト改変で壊れる | セレクタを設定ファイル化し、失敗時は明示エラー |
| スクレイピングの規約・法律違反 | 利用規約確認、robots.txt 尊重、間隔制御、API 優先 |
| 手数料・為替の誤差で利益計算がずれる | 設定画面で可変にし、参考値である旨をUIに明記 |
| データ鮮度の低下 | 日次スケジューラ + fetched_at の表示 |
| API レート制限 | キャッシュとバックオフリトライ |

---

## 5. 免責事項

- 本ツールの利益計算は参考値であり、実際の取引結果を保証しない
- 取引は利用者の自己責任で行うこと
- スクレイピング対象サイトの利用規約を必ず遵守すること
