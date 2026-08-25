#!/bin/bash
# Trading Card Dashboard 起動スクリプト
# 使い方: ./start.sh [port]
#   port: Streamlit の待ち受けポート（デフォルト 8501）

set -e

PORT="${1:-8501}"

# 依存関係の確認
if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 が見つかりません"
    exit 1
fi

# 設定ファイルが無ければ example からコピー
if [ ! -f config.yaml ]; then
    cp config.example.yaml config.yaml
    echo "config.yaml を作成しました"
fi

# 依存関係のインストール（未インストール時のみ）
python3 -c "import streamlit, pandas, plotly" 2>/dev/null || pip3 install --break-system-packages -r requirements.txt

# DB初期化とデモデータ投入（初回のみ）
python3 -m scripts.seed_demo 2>/dev/null || true

echo "Streamlit をポート ${PORT} で起動します..."
exec streamlit run app/main.py --server.port "${PORT}" --server.address 0.0.0.0 --server.headless true
