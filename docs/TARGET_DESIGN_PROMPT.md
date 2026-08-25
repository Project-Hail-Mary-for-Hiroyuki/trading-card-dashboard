# 構造化プロンプト: 改善後の目標設計（Target State）

## 0. このドキュメントの位置づけ
> `IMPROVEMENT_PROMPT.md` の改善タスクを**すべて適用し終えた完成形**を定義する。あなたはこの仕様どおりにコードを実装・リファクタリングせよ。既存の公開インターフェース（関数名・Streamlitページ構成・CLIコマンド）は原則維持し、内部実装を以下の目標構造へ置き換える。

---

## 1. 改善後のディレクトリ構成

```
trading-card-dashboard/
├── app/
│   ├── main.py                  # 変更なし（4ページ構成）
│   ├── ui_components.py         # [改] config引数化、get_config呼び出しはrender冒頭1回
│   └── pages/
│       ├── dashboard.py         # SQL一括取得版スプレッドを利用
│       ├── search.py            # [改] SQL側フィルタ + LIMIT
│       ├── alerts.py
│       └── settings.py          # [改] 正確な新規件数カウント
├── core/
│   ├── config.py                # [改] db_path解決をプロジェクトルート基準に固定
│   ├── database.py              # [改] get_latest_prices(全一括), prices UNIQUE制約+UPSERT,
│   │                            #     spreads.run_id カラム追加（マイグレーション付き）
│   ├── models.py                # [改] Spread.verdict 削除（classify()に統一）
│   ├── analysis.py              # [改] N+1解消, fx_markup適用
│   └── scheduler.py             # [改] init_db() 呼び出し追加
├── collectors/
│   ├── base.py                  # 変更なし
│   ├── catalog_api.py           # 変更なし
│   ├── price_scraper.py         # [改] card_key→id マップ参照
│   └── exchange_rate.py         # [改] 1リクエストで USDJPY/EURJPY 取得
├── scripts/
│   ├── collect.py               # [改] main() + __main__ガード
│   └── seed_demo.py             # [改] run_id 対応
├── tests/                       # [新規]
│   ├── conftest.py              # in-memory SQLite フィクスチャ
│   ├── test_analysis.py
│   ├── test_config.py
│   ├── test_price_scraper.py
│   └── test_collect_cli.py      # import時副作用がないことの検証
└── requirements.txt             # pytest 追加（dev セクション）
```

---

## 2. コア実装イメージ（目標コード）

### 2.1 `core/database.py` — 一括最新価格取得（N+1解消の中核）

```python
def get_latest_prices(conn) -> dict[tuple[int, str], sqlite3.Row]:
    """{(card_id, source): 最新価格レコード} を1クエリで返す。"""
    rows = conn.execute(
        """
        SELECT card_id, source, currency, price, fetched_at FROM (
            SELECT p.*, ROW_NUMBER() OVER (
                PARTITION BY p.card_id, p.source
                ORDER BY p.fetched_at DESC, p.id DESC
            ) AS rn
            FROM prices p
        ) WHERE rn = 1
        """
    ).fetchall()
    return {(r["card_id"], r["source"]): r for r in rows}
```

### 2.2 `core/analysis.py` — compute_spreads の書き換え

```python
def _fx_to_jpy(currency: str, fx: dict[str, float]) -> float | None:
    if currency == "JPY":
        return 1.0
    pair = f"{currency}JPY"
    return fx.get(pair)

def compute_spreads(conn, cfg, fx=None) -> pd.DataFrame:
    fx = fx or resolve_fx(conn)
    latest = db.get_latest_prices(conn)          # ← 1クエリ
    cards = {r["id"]: r for r in conn.execute(
        "SELECT id, name, category, set_name, image_url FROM cards")}

    records = []
    for cid, card in cards.items():
        buy_jpy = min_filtered(
            to_jpy(latest.get((cid, s.name)), fx)
            for s in cfg.buy_sources)
        sell_hit = max_by(
            (to_jpy(latest.get((cid, s.name)), fx), s.name)
            for s in cfg.sell_sources)
        ...
        markup = 1.0 + cfg.fees.fx_markup        # ← B1: fx_markup を仕入れコストに反映
        net = sell_price_jpy * (1 - fee_rate) - shipping - buy_price_jpy * markup
        rate_pct = net / buy_price_jpy * 100.0
        verdict = classify(rate_pct, cfg)        # ← B2: 判定は classify() に統一
        records.append({...})
    return pd.DataFrame(records)
```

- 計算クエリ数: **カード数×ソース数+2 → 常に3クエリ固定**

### 2.3 `core/database.py` — スキーマ進化と重複排除

```python
CREATE UNIQUE INDEX IF NOT EXISTS uq_prices_daily
    ON prices(card_id, source, date(fetched_at));

def insert_price(conn, rec: PriceRecord) -> int:
    conn.execute("""
        INSERT INTO prices (card_id, source, currency, price)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(card_id, source, date(fetched_at))
        DO UPDATE SET price = excluded.price, fetched_at = datetime('now')
    """, ...)
```

- `spreads` テーブルへ `run_id TEXT` カラムを**冪等マイグレーション**で追加（`PRAGMA table_info` で存在確認→ALTER）。`insert_spread()` / `latest_spreads()` は `run_id`（uuid4短縮）基準に切替 → D2 解消。


### 2.4 `scripts/collect.py` — CLI の正常化

```python
def main() -> None:
    parser = argparse.ArgumentParser(...)
    ...
    args = parser.parse_args()
    cfg = load_config(args.config)
    COMMANDS[args.command](cfg, args)

if __name__ == "__main__":
    main()
```

- 各 `cmd_*` は共通の `contextmanager` で接続管理を統一。
- テストから `import scripts.collect` しても副作用ゼロ。

### 2.5 `collectors/exchange_rate.py` — API 1回化

```python
data = col.fetch_json(config.exchange_api_url)   # .../latest/USD
jpy = data["rates"]["JPY"]                       # USDJPY
eur = jpy / data["rates"]["EUR"]                 # EURJPY をクロスレートで導出
```

### 2.6 UI層の規約

```python
def render_ranking_table(df: pd.DataFrame, cfg: Config, with_set=True):
    rates = df["profit_rate_pct"]
    df = df.assign(判定=rates.map(lambda r: classify(r, cfg)))  # 行ごとのget_config廃止
```

- 各ページの `render()` 冒頭で `cfg = get_config(); conn = get_connection()` を1回だけ実行し、下位関数には引数で渡す。
- 検索ページ:

```python
matches = conn.execute(
    """SELECT id, name, category, set_name, rarity, image_url FROM cards
       WHERE (? = '' OR lower(name) LIKE '%' || lower(?) || '%')
         AND (? IS NULL OR category = ?)
       LIMIT 200""",
    (name_q, name_q, cat_value, cat_value),
).fetchall()
```

### 2.7 テスト（tests/conftest.py イメージ）

```python
@pytest.fixture
def conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    database.init_db(conn)
    yield conn

@pytest.fixture
def cfg(tmp_path):
    return load_config(DEFAULTS_PATH)  # mock有効のテスト用config
```

| テスト | 検証内容 |
|---|---|
| `test_compute_spreads_basic` | 仕入最安・売却最高、手数料・送料・fx_markup込みの純利益 |
| `test_classify_boundaries` | 19.9→慎重 / 20.0→有望 / 49.9→有望 / 50.0→注目 |
| `test_insert_price_upsert` | 同日同ソース再取得で行が増えず価格更新される |
| `test_latest_spreads_run_isolation` | 異なるrun_idの結果が混ざらない |
| `test_collect_import_no_side_effect` | `import scripts.collect` でSystemExitが出ない |

---

## 3. 改善前後の比較サマリ

| 項目 | 現状 | 目標 |
|---|---|---|
| スプレッド計算のSQL発行数 | O(カード×ソース)+2 | **3（固定）** |
| fx_markup | 未使用（デッド設定） | 仕入コストに反映 |
| 利益判定 | 2箇所で二重定義 | `analysis.classify()` に一本化 |
| prices 重複 | 無条件INSERTで蓄積 | 日次UNIQUE制約+UPSERT |
| spreads 最新取得 | 秒精度タイムスタンプ比較 | run_id による正確なrun分離 |
| CLI import | 副作用で即argparse実行 | main()+ガード、テスト可能 |
| 為替API呼び出し | 2リクエスト | 1リクエスト（クロスレート） |
| テスト | なし | pytest 5ファイル以上 |
| 検索フィルタ | 全件読込+Pythonループ | SQL WHERE + LIMIT 200 |

## 4. 完了条件（DoD）
- [ ] 上記ディレクトリ構成・規約どおりに実装されている
- [ ] `pytest` 全グリーン
- [ ] `python3 -m scripts.collect all`（mock有効）が正常完了
- [ ] Streamlit 4ページすべて動作、500カードのダッシュボード描画が体感高速化
- [ ] 既存 `config.yaml` 互換（キー追加のみ、削除なし）
- [ ] README にマイグレーション手順（spreads.run_id 自動ALTER）を追記
