# GitHub 連携手順（Cursor で編集するための準備）

このプロジェクトはローカルの git リポジトリとして初期化済みで、すべての開発成果がコミットされています。Cursor での編集・修正のためには、これを GitHub に公開リポジトリとしてアップロードしてください。

## 前提

- お使いの PC に `git` がインストールされていること
- GitHub アカウントがあること

## 手順

### 1. GitHub でリポジトリを作成

GitHub にログインし、右上の **[+]** → **[New repository]** を選択。

- Repository name: `trading-card-dashboard`（任意）
- Visibility: Public または Private（任意）
- **Initialize this repository with: は何も選択しない**（空で作成）

**[Create repository]** をクリック。

### 2. このプロジェクトをダウンロード

現在の作業環境からローカルに取得します。GitHub にプッシュする前に、このプロジェクトのファイル一式をローカルに用意してください。

- この環境のファイル一式を zip でダウンロードして展開する
- またはこの環境から `git push` ではなく、ファイルをコピーする

> 注意: `data/` ディレクトリ（SQLite DB）と `config.yaml` は Git 管理外です。アップロード不要です。

### 3. ローカルで git リポジトリを初期化

```bash
cd trading-card-dashboard
git init
git add .
git commit -m "Initial commit"
```

### 4. リモートを追加してプッシュ

```bash
git remote add origin https://github.com/<あなたのユーザー名>/trading-card-dashboard.git
git branch -M main
git push -u origin main
```

### 5. Cursor で開く

1. Cursor を起動
2. **File > Open Folder** でクローン（またはコピー）した `trading-card-dashboard` フォルダを開く
3. 以後、Cursor の AI チャットで修正・改善ができます

## 環境構築（ローカル実行）

```bash
pip3 install -r requirements.txt
cp config.example.yaml config.yaml
./start.sh
```

ブラウザで http://localhost:8501 にアクセスしてください。

## 本環境での再実行が必要な場合

このチャットを再開した場合、以下でサーバを再起動できます。

```bash
cd /workspace
streamlit run app/main.py --server.port 8501
```

## 補足

- `.gitignore` に `data/`（DB）と `config.yaml` が含まれており、機密情報や収集データが誤って公開されないようになっています。
- 変更を加えたら `git add . && git commit -m "..."` でコミットし、`git push` で GitHub に反映してください。
