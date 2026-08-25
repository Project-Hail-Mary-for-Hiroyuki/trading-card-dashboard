# TCG 海外転売リサーチダッシュボード

海外（米国・欧州）市場で**短期フリップ**により利益が見込めるトレーディングカードを、国内の仕入れ価格と海外の販売価格の**価格スプレッド**から分析して可視化する Streamlit アプリです。

## 機能

- **ダッシュボード**: 利益率ランキング、利益率分布、カテゴリ別サマリー
- **カード検索**: カード名・カテゴリで絞り込み、価格推移とスプレッド履歴を表示
- **アラート**: 利益率の閾値とカテゴリを設定し、該当カードを一覧表示
- **設定**: 手数料率・送料・分析閾値の変更、データ収集の実行

## 技術スタック

- Python 3.10+ / Streamlit / pandas / plotly
- SQLite（データ永続化）
- APScheduler（日次定期収集）
- データ収集: TCGdex / YGOPRODeck / open.er-api.com（API）+ 設定駆動スクレイパー

## クイックスタート

```bash
# 依存関係のインストール
pip3 install --break-system-packages -r requirements.txt

# 設定ファイル作成
cp config.example.yaml config.yaml

# 初回データ投入（デモデータ）
python3 -m scripts.seed_demo

# 起動
streamlit run app/main.py --server.port 8501
```

または起動スクリプトを使用:

```bash
./start.sh
```

## データ収集 CLI

```bash
# カードカタログを外部APIから取得（ポケモン/遊戯王）
python3 -m scripts.collect catalog --limit 500

# 為替レート取得
python3 -m scripts.collect fx

# 価格収集（有効化されたソース or モック）
python3 -m scripts.collect prices

# スプレッド再計算
python3 -m scripts.collect spreads

# 全実行
python3 -m scripts.collect all

# 日次定期収集スケジューラ起動（06:00 Asia/Tokyo）
python3 -m scripts.collect schedule
```

## 設定

`config.yaml` を編集します（雛形は `config.example.yaml`）。

| 項目 | 説明 |
|---|---|
| `fees.*` | eBay / TCGPlayer / Cardmarket の手数料率、送料、為替上乗せ率 |
| `analysis.min_profit_rate` / `hot_profit_rate` | 有望 / 注目 判定の利益率閾値 |
| `catalog.*` | カタログAPIのエンドポイント |
| `mock.enabled` | `true` で外部API不要の疑似価格を生成（初期デモ用） |
| `price_sources.*` | 実価格スクレイピングのソース定義 |

### 実価格スクレイピングの有効化

`config.yaml` の `price_sources` で `url_template` を設定し `enabled: true` にします。

- プレースホルダ: `{query}`（カード名）、`{card_key}`
- `extra.parser`: `json`（デフォルト）または `html`
- `extra.json_path`: JSONレスポンス内の価格へのドットパス
- `extra.css` / `extra.css_attr`: HTMLパーサ用のセレクタ

**注意**: スクレイピング対象サイトの利用規約と robots.txt を必ず確認し、`http.request_interval` を 3 秒以上に保ってください。

## ディレクトリ構成

```
app/                  Streamlit アプリ（メイン + 4ページ）
core/                 設定・DB・分析・スケジューラ
collectors/           データ収集（カタログAPI・価格・為替）
scripts/              収集CLI・デモデータシード
data/                 実行時に生成されるSQLite DB（git管理外）
config.example.yaml   設定雛形
start.sh              起動スクリプト
```

## 免責事項

- 本ツールの利益計算は参考値であり、実際の取引結果を保証するものではありません。
- 取引は自己責任で行ってください。
- スクレイピングを利用する際は、対象サイトの利用規約に従ってください。

## 変更履歴（2026-08 リファクタリング）

- **パフォーマンス**: スプレッド計算のN+1クエリを解消（`ROW_NUMBER()` による一括最新価格取得、クエリ数固定3）。検索ページをSQLフィルタ+LIMIT化。ランキングテーブルの行毎 `get_config()` 呼び出しを廃止。
- **正確性**: `fx_markup`（為替上乗せ率）を仕入コスト計算に反映。利益判定を `analysis.classify()` に一本化。CLI（`scripts/collect.py`)を `main()` 関数+ガード化。設定ページの新規カード件数カウント修正。スケジューラ実行時のDB初期化追加。
- **データ整合性**: prices テーブルに日次UNIQUE制約+UPSERT（同日再取得は更新のみ）。spreads に `run_id` を追加し最新run取得を正確化。
- **その他**: 為替API呼び出しを1リクエスト化（EURJPYはクロスレート導出）。
- **テスト**: pytest 導入（`tests/`）。`.venv/bin/python -m pytest tests` で実行。

### マイグレーション

既存DBをお使いの場合も `db.init_db()` 実行時に `spreads.run_id` カラムが自動追加されます（冪等）。手動作業は不要です。

