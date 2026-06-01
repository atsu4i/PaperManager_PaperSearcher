# CLAUDE.md - 論文管理システム開発記録

## プロジェクト概要

医学論文のPDFファイルを自動解析し、Notionデータベースに登録するPythonベースの自動化システムです。

### 開発背景
- 手動でのPDFアップロード→Claude解析→Notion投稿の工程を完全自動化
- GASベースのSlack Botの知見を活用しつつ、スタンドアロンアプリケーションとして再設計
- Gemini 2.5 ProとGoogle Cloud Vision APIを活用した高精度な論文解析

## システム構成

### 主要技術スタック
- **言語**: Python 3.8+
- **PDF処理**: PyMuPDF + Google Cloud Vision API
- **AI解析**: Gemini 2.5 Pro
- **PubMed連携**: Biopython
- **Notion連携**: Notion Python SDK
- **Obsidian連携**: Markdown生成 + YAMLフロントマター
- **ファイル監視**: Watchdog

### アーキテクチャ
```
論文管理システム
├── PDF監視サービス (watchdog)
├── PDF処理サービス (Vision API)
├── 論文解析サービス (Gemini)
├── PubMed検索サービス (Biopython)
├── OpenAlex検索サービス (OpenAlex API)
├── Notion投稿サービス (Notion SDK)
├── Obsidian連携サービス (Markdown生成)
└── ファイル管理サービス (自動移動・整理)
```

## 実装された機能

### 1. 自動PDF処理
- フォルダ監視による新規PDFファイル検出
- PyMuPDF → Google Cloud Vision API のフォールバック処理
- 50MB制限、並行処理対応（最大3ファイル同時）

### 2. AI解析エンジン
- Gemini 2.5 Proによる論文メタデータ抽出
  - タイトル、著者、雑誌名、DOI等
- 2000-3000文字の構造化された日本語要約自動生成
- 医学論文特化のプロンプト設計

### 3. PubMed統合 & OpenAlexメタデータ補完
- 複数検索戦略による高精度PMID検索
  - タイトル+著者名
  - タイトル+雑誌名
  - DOI検索
  - タイトル単独検索
- 自動PubMedリンク生成
- **OpenAlexメタデータ補完**: PubMed未収録論文のメタデータを自動補完
  - タイトル、著者、雑誌名、DOI、出版年を取得
  - 被引用数の自動取得（全論文対象）
  - メタデータ優先順位: PubMed > OpenAlex > Gemini

### 4. Notion連携
- 既存テンプレート形式での自動投稿
- 重複チェック機能
- エラーハンドリングとデータ修正

### 5. ファイル管理システム
- 処理済みPDFの自動移動・整理
- 成功/失敗別アーカイブ
- 月別サブフォルダ管理
- 処理状態がわかるファイル命名規則

### 6. 包括的管理機能
- 処理済みファイルデータベース
- システム状態監視
- 古いファイルの自動クリーンアップ
- 詳細ログ機能

### 7. Obsidian連携機能（v1.6.0追加）
- **Markdown自動生成**: YAMLフロントマター + 構造化本文
- **統一タグ付けシステム**: tagging_guidelines.mdに基づく自動正規化
  - 複数形優先（`large-language-models`）
  - 略語自動併記（`natural-language-processing` + `nlp`）
  - 冗長表現の除去（`artificial-intelligence-ai` → `artificial-intelligence`）
- **重複チェック機能**: Notion IDベースの検索・スキップ
- **ファイル名衝突回避**: 異なる論文への自動連番追加
- **年別フォルダ整理**: `papers/2024/`, `papers/2025/` 自動分類
- **PDF添付対応**: `attachments/pdfs/` へのコピー（オプション）
- **Notionリンク**: 双方向参照を実現

### 8. NotionからObsidianへの移行機能
- **一括移行スクリプト**: `migrate_notion_to_obsidian.py`
- **柔軟なフィルタリング**: 年別・件数制限対応
- **PDFダウンロード**: Notion添付ファイルの自動取得
- **再解析**: Gemini AIによるキーワード抽出強化
- **PubMed補完**: PMID検索と著者情報更新
- **進捗管理**: 統計情報とエラーハンドリング

### 9. NotionとObsidianの同期機能（v1.7.0追加）
- **双方向同期**: NotionデータベースとObsidian Vaultを同期
  - Notionで修正したアイテムの内容をObsidianに反映
  - 新しいプロパティの自動追加
  - 常にNotionを優先して上書き
- **同期スクリプト**: `sync_notion_to_obsidian.py`
  - 最近更新されたページのみを同期（`--since 2024-01-01`）
  - 処理件数制限対応（`--limit 10`）
  - ドライランモード（`--dry-run`）
- **CLI統合**: `python cli.py sync`コマンドで実行
- **GUI統合**: ヘッダーに「🔄 Notion同期」ボタンを追加
  - ワンクリックで同期実行
  - 同期ログをリアルタイム表示
- **自動更新機能**:
  - Notion IDベースのファイル検索
  - 既存ファイルの上書き更新
  - 新規ファイルの自動作成

### 10. セマンティック検索システム（v1.8.0追加）
- **Paper Searcher**: 独立した検索専用Webアプリ
  - Googleライクなシンプルな検索UI
  - 自然言語での論文検索（質問形式も可）
  - ポート8503で起動（既存GUIと独立）
- **ベクトルデータベース**: ChromaDB統合
  - Gemini Embedding APIによる高精度ベクトル化（`gemini-embedding-001`）
  - タイトル + 要約の結合テキストをベクトル化
  - コサイン類似度による関連論文検索
  - バッチ処理対応（100件/バッチ、約25倍高速化）
- **Deep Search（HyDE + Reranking）**: 高精度検索モード
  - **Step 1 - HyDE（Query Expansion）**: LLMが架空の論文要約を生成してクエリ拡張
  - **Step 2 - Broad Retrieval**: ベクトル検索でTop 30を取得（高再現率）
  - **Step 3 - Reranking**: LLMが元の質問に基づいて精査・並べ替え（高適合率）
  - 使用モデル: **gemini-3.5-flash** (Google Cloud API経由)
  - UIステータス表示: 3段階の処理状況を可視化
- **Fast Search**: 通常ベクトル検索モード
  - HyDE・Rerankingなしの高速検索
  - 速度優先の場合に使用
- **検索モード切り替え**: UIで選択可能
  - Deep Search: 精度重視、医学的文脈を理解
  - Fast Search: 速度重視、シンプルなベクトル検索
- **自動ベクトル登録**: 論文登録時に自動実行
  - Notion投稿成功後に自動ベクトル化
  - メタデータ保存（タイトル、著者、雑誌、年、DOI、PMID、キーワード、要約全文、Notion URL、Obsidianパス）
- **一括移行ツール**: `migrate_to_chromadb.py`
  - 既存Notionデータベースの全論文を一括ベクトル化
  - Notionブロック取得による要約の自動取得
  - バッチ処理（100件/バッチ）で高速実行
  - 重複スキップ機能
  - ドライランモード対応
- **検索結果表示**:
  - 類似度スコア表示（カラーコーディング）
  - メタデータ詳細表示（著者、雑誌、年）
  - 要約の全文展開表示（documentフィールドから取得）
  - Notion/Obsidianへのリンク
  - キーワードバッジ表示
  - Deep Search統計情報（候補取得数、選出率、HyDEクエリ）
- **セマンティックマップ（v1.9.0追加）**:
  - **UMAP次元削減**: 768次元のembeddingを2次元に圧縮
  - **Plotlyインタラクティブ可視化**: ホバーで論文詳細表示
  - **カラーコーディング**: 年度・雑誌による色分け
  - **意味的配置**: 近い位置の論文は内容が類似
  - **タブUI**: 検索タブ/セマンティックマップタブの切り替え
  - **論文数制限**: 50/100/200/500件/全件から選択可能

## 設定・環境変数

### 必須設定
```env
GEMINI_API_KEY=your_gemini_api_key
NOTION_TOKEN=your_notion_token
NOTION_DATABASE_ID=your_notion_database_id_here
GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account.json
```

### オプション設定
```env
PUBMED_EMAIL=your_email@example.com
WATCH_FOLDER=./pdfs
PROCESSED_FOLDER=./processed_pdfs
LOG_LEVEL=INFO

# Obsidian連携設定（v1.6.0）
OBSIDIAN_ENABLED=false
OBSIDIAN_VAULT_PATH=./obsidian_vault
OBSIDIAN_ORGANIZE_BY_YEAR=true
OBSIDIAN_INCLUDE_PDF=false
OBSIDIAN_TAG_KEYWORDS=true
OBSIDIAN_LINK_TO_NOTION=true
```

## 使用方法

### 基本コマンド
```bash
# 初期セットアップ
python cli.py setup

# 設定確認
python cli.py config

# システム開始（デーモンモード）
python cli.py start

# 単一ファイル処理
python cli.py process paper.pdf

# システム状態確認
python cli.py status

# ファイルクリーンアップ
python cli.py cleanup --days 30

# NotionとObsidianの同期（v1.7.0）
python cli.py sync                      # 全ページを同期
python cli.py sync --since 2024-01-01  # 2024年1月1日以降の更新のみ
python cli.py sync --limit 10           # 最大10ページまで
python cli.py sync --dry-run            # 実行前の確認のみ

# ChromaDBへの一括移行（v1.8.0）
python migrate_to_chromadb.py           # 全論文をベクトル化
python migrate_to_chromadb.py --limit 10  # 最大10件まで
python migrate_to_chromadb.py --dry-run   # 実行前の確認のみ

# 検索アプリ起動（v1.8.0）
# Windows: start_searcher.bat
# Mac/Linux: ./start_searcher.sh
# または直接: python start_searcher.py
```

### 起動スクリプト
```batch
# インストール（初回のみ）
quick_install.bat      # Windows（ダブルクリック可）
./quick_install.sh     # Mac/Linux（コマンドライン）
quick_install.command  # macOS（ダブルクリック可）

# Paper Manager（論文登録GUI）
start_manager.bat      # Windows（ダブルクリック可）
./start_manager.sh     # Mac/Linux（コマンドライン）
start_manager.command  # macOS（ダブルクリック可）

# Paper Searcher（検索アプリ）
start_searcher.bat      # Windows（ダブルクリック可）
./start_searcher.sh     # Mac/Linux（コマンドライン）
start_searcher.command  # macOS（ダブルクリック可）

# CLI モード
start_cli.bat       # Windows
python cli.py       # Mac/Linux
```

**macOS向け補足:**
- `.command` ファイルはダブルクリックでターミナルが自動起動します
- `.sh` ファイルはコマンドラインから実行します（`./start_manager.sh`）
- すべてのスクリプトは自動的にスクリプトのディレクトリに移動してから実行されます

## フォルダ構造

```
PaperManager/
├── app/                    # メインアプリケーション
│   ├── models/            # データモデル
│   │   └── paper.py       # 論文データモデル
│   ├── services/          # 各種サービス
│   │   ├── pdf_processor.py      # PDF処理
│   │   ├── gemini_service.py     # Gemini連携
│   │   ├── gemma_service.py      # Deep Search LLM（HyDE/Rerank）（v1.8.0）
│   │   ├── pubmed_service.py     # PubMed検索
│   │   ├── openalex_service.py   # OpenAlex連携
│   │   ├── notion_service.py     # Notion連携
│   │   ├── obsidian_service.py   # Obsidian連携（v1.6.0）
│   │   ├── chromadb_service.py   # ChromaDB連携（v1.8.0）
│   │   └── file_watcher.py       # ファイル監視
│   ├── utils/             # ユーティリティ
│   │   ├── logger.py      # ログ設定
│   │   └── file_manager.py # ファイル管理
│   ├── config.py          # 設定管理
│   └── main.py            # メインアプリケーション
├── config/                # 設定ファイル
│   ├── config.yaml        # システム設定
│   └── article_template.json # Notionテンプレート
├── data/                  # データストレージ（v1.8.0）
│   └── chroma_db/        # ChromaDBベクトルストア
├── search_app/            # 検索アプリ（v1.8.0）
│   ├── app.py            # Paper Searcher メイン
│   └── requirements.txt  # 検索アプリ用依存関係
├── pdfs/                  # PDF監視フォルダ
├── processed_pdfs/        # 処理済みPDF保存先
│   ├── success/          # 成功ファイル
│   ├── failed/           # 失敗ファイル
│   └── backup/           # バックアップ
├── obsidian_vault/        # Obsidian Vault（v1.6.0）
│   ├── papers/           # 論文Markdownファイル
│   │   ├── 2024/        # 年別フォルダ
│   │   └── 2025/
│   ├── attachments/      # PDFファイル
│   │   └── pdfs/
│   └── templates/        # テンプレート
├── logs/                  # ログファイル
├── cli.py                 # CLIインターフェース
├── migrate_notion_to_obsidian.py  # Notion→Obsidian移行スクリプト（v1.6.0）
├── sync_notion_to_obsidian.py     # Notion⇄Obsidian同期スクリプト（v1.7.0）
├── migrate_to_chromadb.py         # ChromaDB一括移行スクリプト（v1.8.0）
├── test_summary_retrieval.py      # 要約取得テストスクリプト（v1.8.0）
│
├── quick_install.bat/.sh/.command      # インストールスクリプト
├── start_manager.bat/.sh/.command/.py  # Paper Manager起動スクリプト
├── start_searcher.bat/.sh/.command/.py # Paper Searcher起動スクリプト（v1.8.0）
├── start_cli.bat                       # CLIモード起動スクリプト
├── tagging_guidelines.md               # タグ付けガイドライン（v1.6.0）
│
├── requirements.txt      # 依存関係
├── README.md             # 使用方法
└── CLAUDE.md             # このファイル
```

## 処理フロー

1. **ファイル検出**: `pdfs/`フォルダ内の新規PDFを自動検出
2. **テキスト抽出**: PyMuPDF → Vision API のフォールバック処理
3. **論文解析**: Gemini 2.5 Proで包括的なメタデータ抽出と要約生成
4. **PMID検索**: 複数戦略でPubMed検索実行
5. **OpenAlexメタデータ取得**:
   - 被引用数の取得（全論文対象）
   - PubMed未収録の場合、メタデータを補完（タイトル、著者、雑誌、年、DOI）
   - 優先順位: PubMed > OpenAlex > Gemini
6. **重複チェック**: Notion内既存記事の確認
7. **データ投稿**: Notionデータベースへの構造化投稿
8. **Obsidian連携**: Markdown形式でVaultにエクスポート（有効時）
   - Notion ID重複チェック（既存ファイルをスキップ）
   - タグ正規化（統一ルールに基づく）
   - ファイル名衝突回避（連番自動追加）
9. **ChromaDBベクトル登録**（v1.8.0）:
   - タイトル + 要約をGemini Embedding APIでベクトル化
   - メタデータとともにChromaDBに保存
   - 検索用インデックス自動更新
10. **ファイル整理**: 処理済みPDFの自動移動・アーカイブ

## エラーハンドリング

### 堅牢性設計
- 各APIのリトライ機能（指数バックオフ）
- データサイズ制限対応（Notion API制限等）
- ファイルロック状態の検出と待機
- 包括的例外処理とログ記録

### フォールバック機能
- PDF処理: PyMuPDF → Vision API
- PubMed検索: 複数検索戦略の段階的実行
- メタデータ取得: PubMed → OpenAlex → Gemini
- Notion投稿: データ修正とリトライ

## パフォーマンス

### 最適化要素
- 並行処理（最大3ファイル同時）
- 非同期処理（asyncio）
- 適切なAPI制限遵守
- メモリ効率的なPDF処理

### 制限事項
- PDFファイルサイズ: 50MB上限
- 同時処理数: 3ファイル（設定可能）
- Gemini 2.5 Proトークン制限: 8192トークン
- Vision API制限: Google Cloud課金設定依存

## 開発時の技術的判断

### フレームワーク選択理由
**Python選択理由:**
1. PDF処理ライブラリの豊富さ（PyMuPDF、pdfplumber等）
2. Google AI Python SDKでのシームレスなGemini連携
3. Notion公式Pythonクライアントの安定性
4. 非同期処理とファイル監視の実装容易性

### アーキテクチャ設計
**モジュラー設計:**
- 各サービスの独立性確保
- 設定ファイルによる柔軟な調整
- シングルトンパターンでリソース管理

**エラーハンドリング戦略:**
- 段階的フォールバック処理
- 詳細ログによるデバッグ支援
- 処理失敗時のファイル保護

## Obsidian連携の技術的実装詳細

### タグ正規化システム
`app/services/obsidian_service.py:20-64`

**正規化マッピング**:
- 単数形→複数形統一
- 冗長表現の除去（`artificial-intelligence-ai` → `artificial-intelligence`）
- 表記統一（米国英語優先）
- 略語の自動展開と併記

**必須略語併記**:
- `large-language-models` → 自動的に `llm` も追加
- `natural-language-processing` → 自動的に `nlp` も追加

### 重複チェックアルゴリズム
`app/services/obsidian_service.py:407-440`

1. **Notion IDベースの検索**: YAMLフロントマターを全ファイル検索
2. **ハイフン有無両対応**: `abc-123` と `abc123` を同一視
3. **同じ論文の場合**: スキップして既存ファイルを保護
4. **異なる論文の場合**: ファイル名に連番追加（`_2`, `_3`...）

### Markdownファイル構造
```yaml
---
title: "Large Language Models in Clinical NLP"
authors: ["Smith, J.", "Doe, A."]
journal: "JMIR Medical Informatics"
year: 2024
doi: "10.xxxx/xxx"
pmid: "12345678"
tags: ["large-language-models", "llm", "nlp", "year-2024"]
notion_id: "abc123-def456"
created: 2025-01-24T10:30:00
---

# Large Language Models in Clinical NLP

## 📖 基本情報
[著者、雑誌、DOI、PMID...]

## 🔬 要約
[2000-3000文字の日本語要約]

## 🏷️ キーワード
#large-language-models #llm #nlp #clinical-decision-support

## 📎 関連ファイル
- [[attachments/pdfs/Smith_2024_Large_Language_Models.pdf|原文PDF]]

## 🔗 関連情報
- [Notion記事](https://www.notion.so/...)
```

## 将来の拡張可能性

### 機能拡張案
- ~~Obsidian連携~~ ✅ 実装済み（v1.6.0）
- ~~統一タグ付けシステム~~ ✅ 実装済み（v1.6.0）
- 他の文書形式対応（Word、PowerPoint等）
- 複数Notionデータベース対応
- Web UI実装
- Docker化
- クラウドデプロイ対応

### 技術的改善案
- ベクトル検索による類似論文検出
- ~~論文分類・タグ付け自動化~~ ✅ 部分実装済み（v1.6.0）
- 引用関係の自動解析
- 多言語対応
- Obsidianグラフビュー最適化（バックリンク活用）

## 運用上の考慮事項

### セキュリティ
- API キーの環境変数管理
- ファイルパスの検証
- 一時ファイルの自動削除

### 保守性
- 包括的ログ機能
- 設定ファイルでの動作調整
- CLIツールによる管理機能

### 可用性
- 処理失敗時の自動復旧
- システム状態監視
- ファイル整合性チェック

## 開発履歴

### 初期開発
- **開始日**: 2024年12月1日
- **v1.0.0リリース**: 2024年12月17日
  - 基本的なPDF処理、Gemini解析、Notion投稿機能

### Obsidian連携追加
- **v1.6.0リリース**: 2025年1月24日
  - Obsidian Markdown生成機能
  - 統一タグ付けシステム
  - NotionからObsidianへの移行ツール
  - 重複チェック・ファイル名衝突回避機能

### Notion⇄Obsidian同期機能追加
- **v1.7.0リリース**: 2025年1月頃
  - NotionとObsidianの双方向同期
  - 最近更新されたページのみを効率的に同期
  - GUI統合（ワンクリック同期）

### セマンティック検索システム追加
- **v1.8.0リリース**: 2025年1月29日
  - ChromaDBベクトルデータベース統合
  - Gemini Embedding API（`gemini-embedding-001`）によるベクトル化
  - Paper Searcher独立アプリケーション（ポート8503）
  - Deep Search（HyDE + Reranking）高精度検索
    - gemini-3.5-flash モデル使用（Google Cloud API経由）
  - Fast Search（通常ベクトル検索）高速検索
  - Deep Search LLMサービス（HyDE/Rerank機能）
  - バッチ処理による高速一括移行（100件/バッチ）
  - Notionブロック取得による要約全文保存
  - UIステータス表示（3段階処理可視化）
  - Deep Search統計情報表示

### セマンティックマップ可視化機能追加
- **v1.9.0リリース**: 2025年1月30日
  - UMAP次元削減アルゴリズム統合（768次元→2次元）
  - Plotlyインタラクティブ散布図による可視化
  - 論文コレクション全体の意味的構造を視覚化
  - カラーコーディング機能（年度・雑誌別）
  - ホバーで論文詳細表示
  - タブUI実装（検索タブ/セマンティックマップタブ）
  - 論文数フィルタリング（50/100/200/500件/全件）
  - マップ統計情報表示

### OpenAlex統合と関連論文探索機能追加
- **v1.10.0リリース**: 2025年12月31日
  - **OpenAlex API統合**: 被引用数の自動取得・保存
    - `app/services/openalex_service.py` 新規作成
    - 論文登録時にDOI/タイトルベースで被引用数を自動取得
    - Notion「Citations」プロパティとChromaDBメタデータに保存
  - **被引用数一括更新スクリプト**: `update_citations.py`
    - 既存論文の被引用数を一括更新
    - ドライランモード、件数制限、強制更新オプション対応
  - **セマンティックマップ拡張機能**:
    - 被引用数の対数スケール可視化（0-1000+件を視覚的に区別）
    - ノードクリックで論文詳細ダイアログ表示
    - 選択状態トラッキングで無限ループ防止
  - **関連論文自動表示機能**: `chromadb_service.get_similar_papers()`
    - ベクトル空間での類似検索
    - セマンティックマップ: 10件の類似論文をトグル形式で表示
    - 検索結果画面: 5件の類似論文をトグル形式で表示
    - 各関連論文に著者・雑誌・年・被引用数・要約・リンクを表示
  - **芋づる式探索**: 関連論文から更に関連論文を探索可能

### OpenAlexメタデータ補完機能追加
- **v1.10.1リリース**: 2025年1月5日
  - **PubMed未収録論文のメタデータ補完**: OpenAlexを第二のメタデータソースとして活用
    - `openalex_service.get_paper_metadata()` の拡張
      - タイトル、著者リスト（最大20名）、雑誌名、DOI、出版年を抽出
      - authorship配列からの著者情報取得
      - primary_locationからの雑誌情報取得
    - `app/main.py` の処理フロー改善
      - `pubmed_found` フラグによるPubMed検索成否の追跡
      - 条件分岐によるOpenAlexメタデータ取得
      - 被引用数は常に取得、メタデータはPubMed未収録時のみ補完
      - 新規 `_merge_metadata_from_openalex()` 関数
  - **メタデータ取得の3段階優先順位システム**:
    1. PubMed（最優先・最も信頼性が高い）
    2. OpenAlex（PubMed未収録時の補完）
    3. Gemini（ベースライン抽出）
  - **論文データベースのカバレッジ向上**: プレプリント、arXiv論文、学会発表などPubMed未収録の論文にも対応

---

このシステムにより、医学論文の管理が手動プロセスから完全自動化され、NotionとObsidianの両方で効率的な論文管理を実現します。さらに、高精度なセマンティック検索により、膨大な論文データベースから必要な情報を瞬時に見つけ出すことができます。セマンティックマップ機能により、論文コレクション全体の構造を直感的に把握し、関連論文の発見が容易になりました。OpenAlex統合により被引用数が可視化され、インパクトのある論文を素早く特定できます。関連論文表示機能により、興味のある論文から芋づる式に関連研究を探索し、研究の全体像を効率的に把握できるようになりました。
