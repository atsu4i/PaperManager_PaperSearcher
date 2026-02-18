#!/usr/bin/env python3
"""
PaperManager MCP Server

Claude CodeからPDFパスを渡すだけで論文登録・検索・類似論文探索が行えるMCPサーバー。
stdioトランスポートを使用するため print() は禁止。ログはstderrへ。
"""

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path

# スクリプトの場所を基準に作業ディレクトリを固定
# （別リポジトリから呼ばれても相対パスが正しく解決されるようにする）
PROJECT_ROOT = Path(__file__).parent.resolve()
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

# stdioトランスポートのため、すべてのログをstderrへ
logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")

# 設定とサービスをインポート（.envを自動ロード）
from app.config import config  # noqa: E402
from app.main import app as paper_manager  # noqa: E402
from app.services.chromadb_service import chromadb_service  # noqa: E402
from app.services.notion_service import notion_service  # noqa: E402
from app.services.file_watcher import ProcessedFileManager  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

# Webアプリと同じ処理済みファイルDBを共有
_processed_file_manager = ProcessedFileManager(config.processed_files_db)

mcp = FastMCP("paper-manager")


# ---------------------------------------------------------------------------
# ツール1: PDF論文を全パイプラインで登録
# ---------------------------------------------------------------------------

@mcp.tool()
async def register_paper(file_path: str) -> str:
    """
    PDFファイルを論文管理パイプラインで処理してNotionに登録します。

    OCR → Gemini解析 → PubMed/OpenAlex検索 → Notion投稿 → ChromaDB登録の
    全工程を自動実行します。処理には30秒〜5分程度かかります。

    Args:
        file_path: 登録するPDFファイルの絶対パス

    Returns:
        JSON文字列 {"success": bool, "notion_page_id": str|null,
                    "title": str|null, "processing_time": float, "error": str|null}
    """
    path = Path(file_path)

    if not path.exists():
        return json.dumps({"success": False, "error": f"ファイルが存在しません: {file_path}"})

    if path.suffix.lower() != ".pdf":
        return json.dumps({"success": False, "error": f"PDFファイルではありません: {file_path}"})

    try:
        result = await paper_manager.process_single_file(str(path))

        # Webアプリと同様にファイルを処理済みフォルダへ移動・記録
        _processed_file_manager.mark_processed(
            str(path),
            result.success,
            result.notion_page_id
        )

        return json.dumps({
            "success": result.success,
            "notion_page_id": result.notion_page_id,
            "title": result.paper_metadata.title if result.paper_metadata else None,
            "authors": result.paper_metadata.authors if result.paper_metadata else [],
            "journal": result.paper_metadata.journal if result.paper_metadata else None,
            "year": result.paper_metadata.publication_year if result.paper_metadata else None,
            "doi": result.paper_metadata.doi if result.paper_metadata else None,
            "processing_time": round(result.processing_time, 1),
            "error": result.error_message,
        }, ensure_ascii=False)

    except Exception as e:
        # 例外時も失敗として移動・記録
        _processed_file_manager.mark_processed(str(path), False, None)
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# ツール2: セマンティック検索
# ---------------------------------------------------------------------------

@mcp.tool()
def search_papers(query: str, n_results: int = 5, mode: str = "fast") -> str:
    """
    ChromaDBを使ったセマンティック検索で論文を探します。

    自然言語クエリや質問形式での検索が可能です。
    deep モードは HyDE + Reranking により高精度ですが時間がかかります。

    Args:
        query: 検索クエリ（日本語・英語どちらでも可）
        n_results: 返す結果数（デフォルト: 5、最大: 20）
        mode: 検索モード "fast"（通常ベクトル検索）または "deep"（HyDE+Reranking）

    Returns:
        JSON文字列 {"results": [...], "mode": str, "count": int}
        各resultは {title, authors, journal, year, doi, pmid, keywords,
                     similarity, notion_url, obsidian_path, summary_preview}
    """
    n_results = min(max(1, n_results), 20)

    try:
        if mode == "deep":
            response = chromadb_service.deep_search(query, n_results=n_results)
            raw_results = response.get("results", [])
            extra = {
                "hyde_query": response.get("hyde_query", ""),
                "stats": response.get("stats", {}),
            }
        else:
            raw_results = chromadb_service.search(query, n_results=n_results)
            extra = {}

        formatted = []
        for r in raw_results:
            meta = r.get("metadata", {})
            summary = meta.get("summary", "") or r.get("document", "")
            formatted.append({
                "title": meta.get("title", ""),
                "authors": meta.get("authors", ""),
                "journal": meta.get("journal", ""),
                "year": meta.get("year", ""),
                "doi": meta.get("doi", ""),
                "pmid": meta.get("pmid", ""),
                "keywords": meta.get("keywords", ""),
                "cited_by_count": meta.get("cited_by_count", "0"),
                "similarity": round(r.get("similarity", 0), 3),
                "notion_url": meta.get("notion_url", ""),
                "obsidian_path": meta.get("obsidian_path", ""),
                "summary_preview": summary[:300] if summary else "",
            })

        return json.dumps(
            {"results": formatted, "mode": mode, "count": len(formatted), **extra},
            ensure_ascii=False
        )

    except Exception as e:
        return json.dumps({"results": [], "mode": mode, "count": 0, "error": str(e)},
                          ensure_ascii=False)


# ---------------------------------------------------------------------------
# ツール3: プロジェクト別論文一覧
# ---------------------------------------------------------------------------

@mcp.tool()
async def get_project_papers(project_name: str, limit: int = 20) -> str:
    """
    Notionデータベースから特定プロジェクトに属する論文一覧を取得します。

    Args:
        project_name: Notionの「プロジェクト」プロパティ値（例: "心不全", "糖尿病"）
        limit: 返す最大件数（デフォルト: 20）

    Returns:
        JSON文字列 {"project": str, "count": int, "papers": [...]}
        各paperは {title, authors, journal, year, doi, pmid, notion_url}
    """
    limit = min(max(1, limit), 100)

    try:
        papers = await notion_service.query_papers_by_project(project_name)

        # limit 適用
        papers = papers[:limit]

        return json.dumps(
            {"project": project_name, "count": len(papers), "papers": papers},
            ensure_ascii=False
        )

    except Exception as e:
        return json.dumps(
            {"project": project_name, "count": 0, "papers": [], "error": str(e)},
            ensure_ascii=False
        )


# ---------------------------------------------------------------------------
# ツール4: 類似論文探索
# ---------------------------------------------------------------------------

@mcp.tool()
def get_similar_papers(notion_page_id: str, n_results: int = 5) -> str:
    """
    指定したNotion IDの論文に意味的に類似した論文を探します（芋づる式探索）。

    ChromaDBのベクトル空間上で近い論文を返します。

    Args:
        notion_page_id: 起点とする論文のNotion ページID
        n_results: 返す類似論文数（デフォルト: 5、最大: 20）

    Returns:
        JSON文字列 {"source_id": str, "count": int, "similar_papers": [...]}
        各similar_paperは {title, authors, journal, year, doi, pmid,
                            similarity_score, notion_url, summary_preview}
    """
    n_results = min(max(1, n_results), 20)

    try:
        results = chromadb_service.get_similar_papers(notion_page_id, n_results=n_results)

        formatted = []
        for r in results:
            meta = r.get("metadata", {})
            summary = meta.get("summary", "") or r.get("document", "")
            formatted.append({
                "title": meta.get("title", ""),
                "authors": meta.get("authors", ""),
                "journal": meta.get("journal", ""),
                "year": meta.get("year", ""),
                "doi": meta.get("doi", ""),
                "pmid": meta.get("pmid", ""),
                "cited_by_count": meta.get("cited_by_count", "0"),
                "similarity_score": round(r.get("similarity_score", 0), 3),
                "notion_url": meta.get("notion_url", ""),
                "obsidian_path": meta.get("obsidian_path", ""),
                "summary_preview": summary[:300] if summary else "",
            })

        return json.dumps(
            {"source_id": notion_page_id, "count": len(formatted), "similar_papers": formatted},
            ensure_ascii=False
        )

    except Exception as e:
        return json.dumps(
            {"source_id": notion_page_id, "count": 0, "similar_papers": [], "error": str(e)},
            ensure_ascii=False
        )


# ---------------------------------------------------------------------------
# ツール5: プロジェクト一覧取得
# ---------------------------------------------------------------------------

@mcp.tool()
async def list_projects() -> str:
    """
    Notionデータベースに存在するプロジェクト名の一覧を取得します。

    get_project_papers や export_project_papers で使用するプロジェクト名を
    確認するために使います。

    Returns:
        JSON文字列 {"projects": [str, ...], "count": int}
    """
    try:
        projects = await notion_service.get_all_projects()
        return json.dumps(
            {"projects": sorted(projects), "count": len(projects)},
            ensure_ascii=False
        )
    except Exception as e:
        return json.dumps({"projects": [], "count": 0, "error": str(e)}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# ツール6: プロジェクト別論文エクスポート（JSONファイル保存）
# ---------------------------------------------------------------------------

@mcp.tool()
async def export_project_papers(project_name: str, output_path: str = "") -> str:
    """
    特定プロジェクトの論文を全件取得してJSONファイルに保存します。
    PaperSearcherのエクスポートタブと同等の機能です。

    Args:
        project_name: Notionの「プロジェクト」プロパティ値（list_projects で確認可能）
        output_path: 保存先ファイルパス（省略時はプロジェクトルートに自動生成）
                     例: "/Users/you/Desktop/papers_心不全.json"

    Returns:
        JSON文字列 {"success": bool, "project": str, "total_count": int,
                    "output_path": str, "exported_at": str, "error": str|null}
    """
    try:
        papers = await notion_service.query_papers_by_project(project_name)

        exported_at = datetime.now().isoformat()

        # 出力パス決定
        if output_path:
            save_path = Path(output_path)
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = PROJECT_ROOT / f"papers_{project_name}_{timestamp}.json"

        # 保存ディレクトリが存在しない場合はエラー
        if not save_path.parent.exists():
            return json.dumps({
                "success": False,
                "error": f"保存先ディレクトリが存在しません: {save_path.parent}"
            }, ensure_ascii=False)

        # JSONデータ構築（PaperSearcherと同じ形式）
        export_data = {
            "project": project_name,
            "exported_at": exported_at,
            "total_count": len(papers),
            "papers": papers,
        }

        save_path.write_text(
            json.dumps(export_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        return json.dumps({
            "success": True,
            "project": project_name,
            "total_count": len(papers),
            "output_path": str(save_path),
            "exported_at": exported_at,
            "error": None,
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# ツール7: データベース統計
# ---------------------------------------------------------------------------

@mcp.tool()
def get_database_stats() -> str:
    """
    ChromaDBに登録されている論文の統計情報を返します。

    Returns:
        JSON文字列 {"total_papers": int, "db_path": str}
    """
    try:
        count = chromadb_service.get_count()
        return json.dumps(
            {"total_papers": count, "db_path": str(chromadb_service.db_path)},
            ensure_ascii=False
        )
    except Exception as e:
        return json.dumps({"total_papers": 0, "error": str(e)}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# エントリーポイント
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run(transport="stdio")
