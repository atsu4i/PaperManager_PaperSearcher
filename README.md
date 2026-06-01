# 論文管理・検索システム (Paper Manager & Searcher)

医学論文のPDFを自動解析してNotionに登録し、高精度なセマンティック検索で必要な論文を瞬時に見つけ出す、2つの統合システムです。

## 📦 3つのシステム

### 🤖 Paper Manager（論文登録システム）
PDFファイルをフォルダに保存するだけで、論文情報を**完全自動で**Notionデータベースに登録します。

**主な機能:**
- 📄 PDF自動読み取り（Google Cloud Vision API）
- 🤖 論文情報の自動抽出（Gemini AI）
- 🔬 PubMed自動検索・リンク生成
- 📚 Notion自動投稿
- 📝 Obsidian連携（オプション）

### 🔌 Claude Code MCP サーバー（v1.11.0）
Claude Code から直接、論文登録・検索・エクスポートを自然言語で操作できます。

**主な機能:**
- 📄 PDFパスを渡すだけで論文を全自動登録（Webアプリと同等の処理）
- 🔍 セマンティック検索（Fast / Deep モード）
- 📤 プロジェクト別論文エクスポート（JSON）
- 🔗 類似論文の芋づる式探索
- 📊 データベース統計確認

### 🔍 Paper Searcher（検索システム）
蓄積された論文を、医学的文脈を理解した高精度なセマンティック検索で素早く見つけ出します。

**主な機能:**
- 🎯 Deep Search（HyDE + Reranking）
  - gemini-3.5-flash による医学的文脈理解
  - 質問形式での自然言語検索
  - 3段階の高精度検索（クエリ拡張→広範囲検索→AIフィルタリング）
- ⚡ Fast Search（高速ベクトル検索）
- 🗺️ セマンティックマップ（論文の視覚的探索）
  - UMAP次元削減による2次元可視化
  - クリックで論文詳細ダイアログ表示
  - 被引用数の対数スケール可視化
- 🔗 関連論文の自動表示（ベクトル空間での類似検索）
- 📱 モバイル・タブレット対応UI
- 🔗 Notion/DOI/PubMedへの直接リンク

---

## 🚀 クイックスタート

### インストール（初回のみ）

#### Windows:
```bash
# 1. Pythonをインストール（https://www.python.org/downloads/）
#    ※「Add Python to PATH」に必ずチェック

# 2. フォルダに移動
cd PaperManager

# 3. 自動インストール
quick_install.bat          # ダブルクリックでも起動可能
```

#### Mac/Linux:
```bash
# 1. フォルダに移動
cd PaperManager

# 2. 自動インストール
./quick_install.sh         # コマンドラインから起動
```

**macOS限定: ダブルクリックでインストール**
```
quick_install.command をダブルクリック
```

### 📖 Paper Manager（論文登録）の起動

#### Windows:
```bash
start_manager.bat        # ダブルクリックでも起動可能
```

#### Mac/Linux:
```bash
./start_manager.sh       # コマンドラインから起動
```

**macOS限定: ダブルクリックで起動**
```
start_manager.command をダブルクリック
```

**初回起動時の流れ:**
1. 設定チェック実行
2. 未設定の場合 → 設定ツール起動（http://localhost:8502）
3. 設定完了後 → メインGUI起動（http://localhost:8501）

### 🔍 Paper Searcher（検索）の起動

#### Windows:
```bash
start_searcher.bat       # ダブルクリックでも起動可能
```

#### Mac/Linux:
```bash
./start_searcher.sh      # コマンドラインから起動
```

**macOS限定: ダブルクリックで起動**
```
start_searcher.command をダブルクリック
```

ブラウザで http://localhost:8503 が自動的に開きます。

---

## ⚙️ 初期設定

### 必要なアカウント（すべて無料で始められます）

1. **Google Cloud** - PDF読み取りとAI解析
   - [Google Cloud Console](https://console.cloud.google.com/)
   - [Google AI Studio](https://aistudio.google.com/)

2. **Notion** - 論文データベース
   - [Notion](https://www.notion.so/)

### API設定（GUIで簡単設定）

Paper Manager起動後、「⚙️ 設定」タブで以下を設定:

#### 1. Google Cloud設定

**Gemini API キー:**
1. [Google AI Studio](https://aistudio.google.com/) → 「Get API key」
2. APIキーをコピー → GUI設定画面に貼り付け

**モデル選択（コスト最適化）:**
- メタデータ抽出: `gemini-3.1-flash-lite`（低コスト・高速）
- 要約作成: `gemini-3.5-flash`（安定版・高品質）
- Gemma 4選択肢: `gemma-4-31b-it`, `gemma-4-26b-a4b-it`
- 年間100論文で約¥50、**98%のコスト削減**

**Vision APIサービスアカウント:**
1. [Google Cloud Console](https://console.cloud.google.com/) → 「IAMと管理」→「サービスアカウント」
2. サービスアカウント作成
3. ロール付与: `Cloud Vision API ユーザー`
4. キー作成（JSON） → ダウンロード
5. GUI設定画面にJSONファイルパスを入力

#### 2. Notion設定

**Integration作成:**
1. [Notion Developers](https://www.notion.so/my-integrations) → 「New integration」
2. Integration Token をコピー → GUI設定画面に貼り付け

**データベース作成:**
必要なプロパティ:
- Title（タイトル）
- Authors（マルチセレクト）
- Journal（セレクト）
- Year（セレクト）※ v1.10.1から自動文字列変換対応
- DOI（URL）
- PMID（数値）
- PubMed（URL）
- Citations（数値）※ OpenAlex被引用数
- Key Words（マルチセレクト）
- Summary（テキスト）
- pdf（ファイル）

データベースURLから32文字のIDを抽出 → GUI設定画面に入力

#### 3. ChromaDB自動セットアップ

Paper Searcherは初回起動時に自動的にベクトルデータベースをセットアップします。
既存のNotion論文を検索可能にするには、以下を実行:

```bash
# 仮想環境を有効化
# Windows:
paper_manager_env\Scripts\activate
# Mac/Linux:
source paper_manager_env/bin/activate

# 全論文をベクトル化
python migrate_to_chromadb.py

# または件数制限付き（テスト用）
python migrate_to_chromadb.py --limit 10

# 実行前に確認
python migrate_to_chromadb.py --dry-run
```

---

## 📖 Paper Manager の使い方

### 基本的な使い方

1. **システム開始**
   - GUIで「🚀 システム開始」ボタンをクリック

2. **PDFファイルの処理**
   - **方法1**: `pdfs/` フォルダにPDFを保存（自動処理）
   - **方法2**: GUIの「📄 ファイル処理」タブでドラッグ&ドロップ

3. **結果確認**
   - Notionデータベースに自動登録
   - GUIダッシュボードで統計確認
   - `processed_pdfs/` フォルダに整理保存

### PubMed非収録論文の自動対応（v1.10.1+）

ACM、IEEE等の学会論文やarXiv論文など、PubMed非収録の論文も自動的に処理されます：
- PubMed検索で妥当性スコアが85点未満 → 自動却下
- OpenAlex APIから正確なメタデータを取得
- タイトル、著者、雑誌、年、DOI、被引用数を自動補完
- Notionに正しく登録

### 処理済みファイルの保存場所

```
processed_pdfs/
├── backup/          # オリジナルファイル名で保持
├── success/         # 処理成功（月別フォルダ）
│   └── 2025-01/
└── failed/          # 処理失敗
    └── 2025-01/
```

### Obsidian連携（オプション）

論文をMarkdown形式でローカル保存:

```env
# .env ファイルまたはGUI設定で
OBSIDIAN_ENABLED=true
OBSIDIAN_VAULT_PATH=/path/to/your/vault
OBSIDIAN_ORGANIZE_BY_YEAR=true
```

---

## 🔍 Paper Searcher の使い方

### 検索モード

#### Deep Search（精度重視）
- HyDE（クエリ拡張） + Reranking（AIフィルタリング）
- 医学的文脈を理解した高精度検索
- 質問形式でも検索可能

**例:**
```
小児ALLの維持療法
糖尿病治療におけるGLP-1受容体作動薬の効果
CRISPR遺伝子編集の最新動向
```

#### Fast Search（速度重視）
- シンプルなベクトル検索
- 高速レスポンス

### 検索結果

- タイトル・著者・雑誌・年・被引用数
- 類似度スコア（カラーコーディング）
- 要約全文（展開表示）
- **関連論文の自動表示**（5件、トグル形式）
- Notion/DOI/PubMedへのリンク

### セマンティックマップ（v1.10.0拡張）

論文コレクション全体を2次元空間で可視化:
- **UMAP次元削減**: 768次元→2次元に圧縮
- **インタラクティブ操作**:
  - ホバーで論文詳細確認
  - クリックで論文詳細ダイアログ表示
- **被引用数可視化**: 対数スケールで色分け（0-1000+件）
- **カラーコーディング**: 被引用数・年度・雑誌で色分け
- **意味的配置**: 近い位置の論文は内容が似ている
- **関連論文表示**: ダイアログ内で10件の類似論文を表示

**使い方:**
1. 「📊 セマンティックマップ」タブを開く
2. 表示する論文数と色分け基準を選択
3. 「🗺️ マップ生成」をクリック
4. ノードをクリックして論文詳細を表示
5. 関連論文を展開して芋づる式に探索

### モバイル対応

スマホ・タブレットから快適にアクセス可能:
- レスポンシブUI
- タッチ操作最適化
- 読みやすいフォントサイズ

---

## 🔌 Claude Code MCP サーバー（v1.11.0）

Claude Code から自然言語で論文管理システムを操作できます。どのリポジトリで作業中でも利用可能です。

### セットアップ

#### 1. 依存パッケージのインストール

```bash
paper_manager_env/bin/pip install "mcp[cli]>=1.2.0"
# または
pip install -r requirements_mcp.txt
```

#### 2. Claude Code への登録

`~/.claude.json` の `mcpServers` に以下を追加します（`claude mcp add` コマンド相当）:

```bash
python3 -c "
import json
path = '/Users/YOUR_NAME/.claude.json'
with open(path) as f:
    data = json.load(f)
if 'mcpServers' not in data:
    data['mcpServers'] = {}
data['mcpServers']['paper-manager'] = {
    'command': '/path/to/PaperManager/paper_manager_env/bin/python',
    'args': ['/path/to/PaperManager/mcp_server.py'],
    'cwd': '/path/to/PaperManager'
}
with open(path, 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
print('Done')
"
```

#### 3. Claude Code を再起動

再起動後、`paper-manager` サーバーが自動的に認識されます。

### 利用可能なツール（7つ）

| ツール | 機能 | 主なパラメータ |
|---|---|---|
| `register_paper` | PDF を全パイプラインで登録 | `file_path` |
| `search_papers` | セマンティック検索 | `query`, `n_results=5`, `mode="fast"\|"deep"` |
| `get_project_papers` | プロジェクト別論文一覧 | `project_name`, `limit=20` |
| `list_projects` | プロジェクト一覧取得 | なし |
| `export_project_papers` | 論文を JSON ファイルに保存 | `project_name`, `output_path=""` |
| `get_similar_papers` | 類似論文の芋づる式探索 | `notion_page_id`, `n_results=5` |
| `get_database_stats` | ChromaDB 統計情報 | なし |

### 使用例

Claude Code 上でそのまま自然言語で操作できます:

```
「/path/to/paper.pdf を論文データベースに登録して」
→ register_paper が呼ばれ、Notion + ChromaDB に自動登録。
  処理済みPDFは processed_pdfs/ に自動移動（Webアプリと同じ動作）。

「心不全に関する論文を検索して」
→ search_papers(query="心不全", mode="fast") が呼ばれる。

「心不全プロジェクトの論文を全部エクスポートして」
→ export_project_papers("心不全") が呼ばれ、JSON ファイルを生成。

「この論文（Notion ID: abc123）に似た論文を探して」
→ get_similar_papers("abc123") でベクトル類似検索。
```

### 注意事項

- `register_paper` の処理時間は 1 論文あたり 30 秒〜5 分
- 使用するモデルは `config/config.yaml` の設定に従う（GUI 設定と共通）
- OCR エンジン・モデルの変更は GUI 設定タブまたは `config/config.yaml` から行い、MCP サーバー再起動で反映

---

## 🔧 上級者向けコマンド

### CLI使用（Paper Manager）

```bash
# 仮想環境有効化
# Windows:
paper_manager_env\Scripts\activate
# Mac/Linux:
source paper_manager_env/bin/activate

# システム開始（常駐モード）
python cli.py start

# 単一ファイル処理
python cli.py process paper.pdf

# 設定確認
python cli.py config

# システム状態確認
python cli.py status
```

### NotionからObsidianへの移行

```bash
# 全論文を移行
python migrate_notion_to_obsidian.py

# 2024年の論文のみ
python migrate_notion_to_obsidian.py --year 2024

# テスト移行（10件）
python migrate_notion_to_obsidian.py --limit 10

# 実行前確認
python migrate_notion_to_obsidian.py --dry-run
```

### NotionとObsidianの同期

```bash
# 全ページを同期
python cli.py sync

# 最近更新されたページのみ
python cli.py sync --since 2024-01-01

# 件数制限付き
python cli.py sync --limit 10
```

### ChromaDBへの一括登録

```bash
# 全論文を登録
python migrate_to_chromadb.py

# 件数制限
python migrate_to_chromadb.py --limit 50

# 実行前確認
python migrate_to_chromadb.py --dry-run

# 要約取得テスト
python test_summary_retrieval.py
```

### 被引用数の一括更新（OpenAlex API）

```bash
# 全論文の被引用数を更新
python update_citations.py

# 件数制限
python update_citations.py --limit 10

# 実行前確認
python update_citations.py --dry-run

# 既存の被引用数も強制更新
python update_citations.py --force
```

---

## 📂 プロジェクト構成

```
PaperManager/
├── app/                        # メインアプリケーション
│   ├── services/              # 各種サービス
│   │   ├── pdf_processor.py  # PDF処理
│   │   ├── gemini_service.py # Gemini AI連携
│   │   ├── gemma_service.py  # Deep Search LLM（HyDE/Rerank）
│   │   ├── notion_service.py # Notion連携
│   │   ├── chromadb_service.py # ChromaDB連携
│   │   ├── obsidian_service.py # Obsidian連携
│   │   └── openalex_service.py # OpenAlex API連携
│   └── ...
├── search_app/                 # Paper Searcher
│   ├── app.py                 # Streamlit検索UI
│   └── requirements.txt       # 検索アプリ依存関係
├── data/
│   └── chroma_db/            # ベクトルデータベース
├── pdfs/                      # PDF監視フォルダ
├── processed_pdfs/            # 処理済みPDF
├── obsidian_vault/            # Obsidian Vault（オプション）
│
├── start_manager.bat/.sh      # Paper Manager起動
├── start_searcher.bat/.sh     # Paper Searcher起動
├── quick_install.bat/.sh      # インストールスクリプト
│
├── migrate_to_chromadb.py     # ChromaDB一括移行
├── migrate_notion_to_obsidian.py # Notion→Obsidian移行
├── sync_notion_to_obsidian.py # Notion⇄Obsidian同期
├── update_citations.py        # OpenAlex被引用数一括更新
├── test_summary_retrieval.py  # 要約取得テスト
├── mcp_server.py              # Claude Code MCP サーバー（v1.11.0）
│
├── requirements.txt           # Python依存関係
├── requirements_mcp.txt       # MCP サーバー追加依存関係
├── .env.example              # 環境変数テンプレート
├── README.md                 # このファイル
└── CLAUDE.md                 # 開発記録
```

---

## 🛠️ トラブルシューティング

### よくある問題

#### Paper Manager が起動しない
```bash
# 診断スクリプト実行
python debug_startup.py

# 強制設定モード
# Windows: setup_config.bat
# Mac: python setup_config.py
```

#### Paper Searcher で検索できない
```bash
# ChromaDBデータ確認
python -c "from app.services.chromadb_service import chromadb_service; print(f'登録数: {chromadb_service.get_count()}件')"

# データが0件の場合
python migrate_to_chromadb.py
```

#### モデルが見つからない
- Gemini API（Google AI Studio）で利用可能なモデルか確認
- APIキーが正しく設定されているか確認
- `gemini-3.1-flash-lite` または `gemini-3.5-flash` に一時的に変更してテスト

#### 文字化けエラー（Windows）
```bash
pip install -r requirements-simple.txt
```

#### Vision API エラー
- サービスアカウントに `Cloud Vision API ユーザー` ロールが付与されているか確認
- JSONキーファイルのパスが正しいか確認

#### 処理済みファイルを再処理したい
Paper Manager GUIから処理済みDBを管理できます：
1. 「⚙️ システム設定」タブを開く
2. 「🗄️ データベース管理」タブを選択
3. 以下のいずれかを実行：
   - **失敗したファイルのみ削除**: 処理失敗したファイルを再処理対象に
   - **データベース全体をリセット**: すべてのファイルを再処理対象に（警告表示あり）
4. アプリを再起動して変更を反映

### ログ確認

**Windows:**
```bash
type logs\paper_manager.log
```

**Mac/Linux:**
```bash
cat logs/paper_manager.log
# リアルタイム監視
tail -f logs/paper_manager.log
```

---

## 📈 システム仕様

### 対応ファイル
- 形式: PDF
- 最大サイズ: 50MB
- 言語: 英語・日本語

### 処理能力
- 処理時間: 1論文あたり30-60秒
- 同時処理: 1ファイルずつ順次処理

### 検索性能
- Deep Search: 約5-10秒（高精度）
- Fast Search: 約1-2秒（高速）
- 登録可能論文数: 制限なし

---

## 🆕 更新履歴

### v1.11.0 (2026-02-18)
- ✅ **Claude Code MCP サーバー追加** - `mcp_server.py` 新規追加
  - `register_paper`: PDF 全パイプライン登録（処理済みファイル自動移動対応）
  - `search_papers`: セマンティック検索（Fast / Deep モード）
  - `get_project_papers`: プロジェクト別論文一覧
  - `list_projects`: Notion プロジェクト一覧取得
  - `export_project_papers`: プロジェクト別論文 JSON エクスポート
  - `get_similar_papers`: 類似論文の芋づる式探索
  - `get_database_stats`: ChromaDB 統計情報
- ✅ **全プロジェクト横断利用可能** - `~/.claude.json` ユーザースコープ登録

### v1.10.1 (2026-01-09)
- ✅ **PubMed検索精度向上** - 妥当性検証システム実装（誤マッチ防止）
  - 検索戦略を6つ→3つに厳格化（DOI、タイトル+著者、タイトル+雑誌のみ）
  - スコアリングシステム導入（タイトル類似度60点、著者30点、年10点）
  - 85点未満は却下、OpenAlexへ自動フォールバック
- ✅ **OpenAlex連携強化** - PubMed非収録論文の正確なメタデータ取得
- ✅ **Notion投稿修正** - Year selectフィールドの型変換エラー修正
- ✅ **Paper Searcher UI改善** - 引用数0件の論文も「引用数: 0件」と明確に表示
- ✅ **セマンティックマップ改善** - 件数制限時、最新論文から優先表示（新しい順）
- ✅ **処理済みDB管理機能** - GUI設定タブからDB削除・リセット可能に

### v1.10.0 (2025-12-31)
- ✅ **OpenAlex被引用数統合** - 論文登録時に自動取得・Notion/ChromaDB保存
- ✅ **被引用数一括更新スクリプト** - 既存論文の被引用数を一括更新（update_citations.py）
- ✅ **セマンティックマップ拡張** - 被引用数の対数スケール可視化（0-1000+件）
- ✅ **クリック機能追加** - マップノードをクリックで論文詳細ダイアログ表示
- ✅ **関連論文表示** - セマンティックマップ（10件）と検索結果（5件）で類似論文を自動表示
- ✅ **芋づる式探索** - 関連論文をトグル形式で展開・要約確認・さらに探索可能

### v1.9.0 (2025-01-30)
- ✅ **セマンティックマップ機能** - 論文コレクションの2次元可視化
- ✅ **UMAP次元削減** - 768次元→2次元に圧縮
- ✅ **インタラクティブ可視化** - Plotlyによるホバー・カラーコーディング
- ✅ **タブUI追加** - 検索タブとマップタブの切り替え

### v1.8.0 (2025-01-29)
- ✅ **Paper Searcher 新規追加** - セマンティック検索システム
- ✅ **Deep Search（HyDE + Reranking）** - gemini-3.5-flash による高精度検索
- ✅ **ChromaDB統合** - Gemini Embedding API（gemini-embedding-001）
- ✅ **モバイル対応UI** - スマホ・タブレット最適化
- ✅ **バッチ処理** - 100件/バッチで高速登録

### v1.7.0 (2025-01)
- ✅ **Notion⇄Obsidian同期** - 双方向同期機能
- ✅ **GUI統合** - ワンクリック同期

### v1.6.2 (2024-12-17)
- ✅ **コスト最適化** - モデル選択機能（年間¥50〜）
- ✅ **DOI早期チェック** - APIコール削減

### v1.6.0 (2025-01-24)
- ✅ **Obsidian連携** - Markdown自動生成
- ✅ **統一タグシステム** - 自動タグ正規化

---

## 🤝 サポート

### 問題が解決しない場合
1. ログ確認: `logs/paper_manager.log`
2. 設定見直し: GUIの設定タブ
3. 再インストール: `quick_install.bat` 再実行

### フィードバック
- GitHubのIssueで問題報告・機能要望を歓迎

---

## 📄 ライセンス

MIT License

---

**🎉 Paper Manager & Searcherで論文管理を完全自動化し、研究に集中しましょう！**

🤖 Developed with [Claude Code](https://claude.ai/code)
