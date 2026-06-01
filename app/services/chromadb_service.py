"""
ChromaDB Vector Database Service

Gemini Embedding APIを使用した論文のベクトル化とChromaDBへの保存・検索を管理します。
"""

import os
from pathlib import Path
from typing import List, Dict, Any, Optional
import chromadb
from chromadb.config import Settings
import google.generativeai as genai

from app.config import config
from app.utils.logger import get_logger
from app.models.paper import PaperMetadata
from app.services.gemma_service import gemma_service

logger = get_logger(__name__)


class ChromaDBService:
    """ChromaDBサービスクラス"""

    def __init__(self):
        """初期化"""
        # プロジェクトルートを取得
        project_root = Path(__file__).parent.parent.parent
        self.db_path = project_root / "data" / "chroma_db"
        self.db_path.mkdir(parents=True, exist_ok=True)

        # ChromaDB クライアントの初期化
        self.client = chromadb.PersistentClient(
            path=str(self.db_path),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )

        # コレクション取得または作成
        self.collection = self.client.get_or_create_collection(
            name="papers",
            metadata={"description": "Medical papers vector store"}
        )

        # Gemini API の初期化
        genai.configure(api_key=config.gemini_api_key)
        self.embedding_model = "models/gemini-embedding-001"
        self.embedding_dimensionality = 768

        logger.info(f"ChromaDB initialized at {self.db_path}")
        logger.info(f"Collection 'papers' ready (count: {self.collection.count()})")

    def _generate_embedding(self, text: str) -> List[float]:
        """
        Gemini Embedding APIを使ってテキストをベクトル化

        Args:
            text: ベクトル化するテキスト

        Returns:
            ベクトル (List[float])
        """
        try:
            result = genai.embed_content(
                model=self.embedding_model,
                content=text,
                task_type="retrieval_document",
                output_dimensionality=self.embedding_dimensionality
            )
            return result['embedding']
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise

    def _generate_query_embedding(self, query: str) -> List[float]:
        """
        検索クエリ用のベクトル生成

        Args:
            query: 検索クエリ

        Returns:
            ベクトル (List[float])
        """
        try:
            result = genai.embed_content(
                model=self.embedding_model,
                content=query,
                task_type="retrieval_query",
                output_dimensionality=self.embedding_dimensionality
            )
            return result['embedding']
        except Exception as e:
            logger.error(f"Query embedding generation failed: {e}")
            raise

    async def add_paper(
        self,
        paper: PaperMetadata,
        notion_page_id: str,
        notion_url: Optional[str] = None,
        obsidian_path: Optional[str] = None
    ) -> bool:
        """
        論文をベクトル化してChromaDBに追加

        Args:
            paper: 論文メタデータ
            notion_page_id: Notion ページID
            notion_url: Notion URL (オプション)
            obsidian_path: Obsidian ファイルパス (オプション)

        Returns:
            成功したらTrue
        """
        try:
            # タイトル + 要約をベクトル化
            text_to_embed = f"{paper.title}\n\n{paper.summary_japanese}"
            embedding = self._generate_embedding(text_to_embed)

            # メタデータ準備
            metadata = {
                "title": paper.title,
                "authors": ", ".join(paper.authors) if paper.authors else "",
                "journal": paper.journal or "",
                "year": paper.publication_year or "",
                "doi": paper.doi or "",
                "pmid": paper.pmid or "",
                "keywords": ", ".join(paper.keywords) if paper.keywords else "",
                "summary": paper.summary_japanese,  # 全文保存
                "cited_by_count": str(paper.cited_by_count) if paper.cited_by_count is not None else "0",
                "notion_page_id": notion_page_id,
                "notion_url": notion_url or "",
                "obsidian_path": obsidian_path or ""
            }

            # ChromaDBに追加
            self.collection.add(
                embeddings=[embedding],
                documents=[text_to_embed],
                metadatas=[metadata],
                ids=[notion_page_id]
            )

            logger.info(f"Paper added to ChromaDB: {paper.title} (ID: {notion_page_id})")
            return True

        except Exception as e:
            logger.error(f"Failed to add paper to ChromaDB: {e}")
            return False

    def _generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        複数のテキストを一度にベクトル化（バッチ処理）

        Args:
            texts: ベクトル化するテキストのリスト（最大100件）

        Returns:
            ベクトルのリスト
        """
        try:
            if len(texts) > 100:
                raise ValueError(f"Batch size {len(texts)} exceeds maximum of 100")

            result = genai.embed_content(
                model=self.embedding_model,
                content=texts,
                task_type="retrieval_document",
                output_dimensionality=self.embedding_dimensionality
            )
            return result['embedding']
        except Exception as e:
            logger.error(f"Batch embedding generation failed: {e}")
            raise

    async def add_papers_batch(
        self,
        papers_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        複数論文をバッチでベクトル化してChromaDBに追加

        Args:
            papers_data: 論文データのリスト
                各要素は以下のキーを持つ辞書:
                - paper: PaperMetadata
                - notion_page_id: str
                - notion_url: Optional[str]
                - obsidian_path: Optional[str]

        Returns:
            結果の辞書 {"success": int, "failed": int, "failed_ids": List[str]}
        """
        try:
            if not papers_data:
                return {"success": 0, "failed": 0, "failed_ids": []}

            if len(papers_data) > 100:
                raise ValueError(f"Batch size {len(papers_data)} exceeds maximum of 100")

            # テキストとメタデータを準備
            texts_to_embed = []
            metadatas = []
            ids = []
            documents = []

            for data in papers_data:
                paper = data["paper"]
                notion_page_id = data["notion_page_id"]
                notion_url = data.get("notion_url", "")
                obsidian_path = data.get("obsidian_path", "")

                # タイトル + 要約
                text_to_embed = f"{paper.title}\n\n{paper.summary_japanese}"
                texts_to_embed.append(text_to_embed)
                documents.append(text_to_embed)
                ids.append(notion_page_id)

                # メタデータ
                metadata = {
                    "title": paper.title,
                    "authors": ", ".join(paper.authors) if paper.authors else "",
                    "journal": paper.journal or "",
                    "year": paper.publication_year or "",
                    "doi": paper.doi or "",
                    "pmid": paper.pmid or "",
                    "keywords": ", ".join(paper.keywords) if paper.keywords else "",
                    "summary": paper.summary_japanese,  # 全文保存
                    "cited_by_count": str(paper.cited_by_count) if paper.cited_by_count is not None else "0",
                    "notion_page_id": notion_page_id,
                    "notion_url": notion_url,
                    "obsidian_path": obsidian_path
                }
                metadatas.append(metadata)

            # バッチでベクトル化
            logger.info(f"Batch embedding generation for {len(texts_to_embed)} papers...")
            embeddings = self._generate_embeddings_batch(texts_to_embed)

            # ChromaDBに一括追加
            self.collection.add(
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
                ids=ids
            )

            logger.info(f"Batch added {len(papers_data)} papers to ChromaDB")
            return {
                "success": len(papers_data),
                "failed": 0,
                "failed_ids": []
            }

        except Exception as e:
            logger.error(f"Failed to add papers batch to ChromaDB: {e}")
            # エラー時は個別に処理
            return await self._fallback_individual_add(papers_data)

    async def _fallback_individual_add(
        self,
        papers_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        バッチ処理失敗時のフォールバック: 個別に追加

        Args:
            papers_data: 論文データのリスト

        Returns:
            結果の辞書
        """
        logger.warning(f"Falling back to individual add for {len(papers_data)} papers")
        success_count = 0
        failed_count = 0
        failed_ids = []

        for data in papers_data:
            try:
                result = await self.add_paper(
                    data["paper"],
                    data["notion_page_id"],
                    data.get("notion_url"),
                    data.get("obsidian_path")
                )
                if result:
                    success_count += 1
                else:
                    failed_count += 1
                    failed_ids.append(data["notion_page_id"])
            except Exception as e:
                logger.error(f"Individual add failed for {data['notion_page_id']}: {e}")
                failed_count += 1
                failed_ids.append(data["notion_page_id"])

        return {
            "success": success_count,
            "failed": failed_count,
            "failed_ids": failed_ids
        }

    def search(
        self,
        query: str,
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        セマンティック検索を実行

        Args:
            query: 検索クエリ
            n_results: 取得する結果数
            where: メタデータフィルタ (オプション)

        Returns:
            検索結果のリスト
        """
        try:
            # クエリをベクトル化
            query_embedding = self._generate_query_embedding(query)

            # ChromaDBで検索
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where,
                include=["metadatas", "documents", "distances"]
            )

            # 結果を整形
            formatted_results = []
            if results and results['ids'] and len(results['ids'][0]) > 0:
                for i in range(len(results['ids'][0])):
                    result = {
                        "id": results['ids'][0][i],
                        "metadata": results['metadatas'][0][i],
                        "document": results['documents'][0][i],
                        "distance": results['distances'][0][i],
                        "similarity": 1 - results['distances'][0][i]  # 類似度スコア
                    }
                    formatted_results.append(result)

            logger.info(f"Search completed: {len(formatted_results)} results for '{query}'")
            return formatted_results

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def get_paper(self, notion_page_id: str) -> Optional[Dict[str, Any]]:
        """
        Notion IDで論文を取得

        Args:
            notion_page_id: Notion ページID

        Returns:
            論文データ (見つからない場合はNone)
        """
        try:
            result = self.collection.get(
                ids=[notion_page_id],
                include=["metadatas", "documents"]
            )

            if result and result['ids']:
                return {
                    "id": result['ids'][0],
                    "metadata": result['metadatas'][0],
                    "document": result['documents'][0]
                }
            return None

        except Exception as e:
            logger.error(f"Failed to get paper: {e}")
            return None

    async def update_paper(
        self,
        notion_page_id: str,
        paper: PaperMetadata,
        notion_url: Optional[str] = None,
        obsidian_path: Optional[str] = None
    ) -> bool:
        """
        既存論文のデータを更新

        Args:
            notion_page_id: Notion ページID
            paper: 更新後の論文メタデータ
            notion_url: Notion URL (オプション)
            obsidian_path: Obsidian ファイルパス (オプション)

        Returns:
            成功したらTrue
        """
        try:
            # 既存データを削除
            self.collection.delete(ids=[notion_page_id])

            # 新しいデータを追加
            return await self.add_paper(paper, notion_page_id, notion_url, obsidian_path)

        except Exception as e:
            logger.error(f"Failed to update paper: {e}")
            return False

    def delete_paper(self, notion_page_id: str) -> bool:
        """
        論文をChromaDBから削除

        Args:
            notion_page_id: Notion ページID

        Returns:
            成功したらTrue
        """
        try:
            self.collection.delete(ids=[notion_page_id])
            logger.info(f"Paper deleted from ChromaDB: {notion_page_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete paper: {e}")
            return False

    def get_count(self) -> int:
        """
        登録されている論文の総数を取得

        Returns:
            論文数
        """
        return self.collection.count()

    def deep_search(
        self,
        query: str,
        n_results: int = 10,
        broad_retrieval_size: int = 30,
        where: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Deep Search（HyDE + Reranking）による高精度検索

        3段階プロセス:
        1. HyDE（Query Expansion）: LLMで架空の論文要約を生成
        2. Broad Retrieval: ベクトル検索でTop 30を取得
        3. Reranking: LLMで精査してTop N に絞る

        Args:
            query: ユーザーの検索クエリ
            n_results: 最終的に返す結果数（デフォルト10）
            broad_retrieval_size: 中間検索で取得する件数（デフォルト30）
            where: メタデータフィルタ (オプション)

        Returns:
            検索結果の辞書 {
                "results": List[Dict],
                "hyde_query": str,
                "stats": Dict
            }
        """
        try:
            stats = {
                "original_query": query,
                "hyde_query": "",
                "broad_retrieval_count": 0,
                "final_count": 0
            }

            # Step 1: HyDE（Query Expansion）
            logger.info(f"Step 1: HyDE query expansion for '{query}'")
            hyde_query = gemma_service.generate_hyde_query(query)
            stats["hyde_query"] = hyde_query

            # Step 2: Broad Retrieval（ベクトル検索でTop 30）
            logger.info(f"Step 2: Broad retrieval (Top {broad_retrieval_size})")
            broad_results = self.search(
                hyde_query,
                n_results=broad_retrieval_size,
                where=where
            )
            stats["broad_retrieval_count"] = len(broad_results)

            if not broad_results:
                logger.warning("No results from broad retrieval")
                return {
                    "results": [],
                    "hyde_query": hyde_query,
                    "stats": stats
                }

            # Step 3: Reranking（LLMで精査してTop N）
            logger.info(f"Step 3: Reranking to Top {n_results}")
            final_results = gemma_service.rerank_results(
                query,  # 元の質問を使用
                broad_results,
                top_k=n_results
            )
            stats["final_count"] = len(final_results)

            logger.info(f"Deep search completed: {stats['final_count']} results")

            return {
                "results": final_results,
                "hyde_query": hyde_query,
                "stats": stats
            }

        except Exception as e:
            logger.error(f"Deep search failed: {e}")
            # フォールバック: 通常のsearchを実行
            logger.warning("Falling back to normal search")
            return {
                "results": self.search(query, n_results=n_results, where=where),
                "hyde_query": query,
                "stats": {
                    "original_query": query,
                    "hyde_query": query,
                    "broad_retrieval_count": 0,
                    "final_count": n_results,
                    "error": str(e)
                }
            }

    def get_all_papers_with_embeddings(
        self,
        limit: Optional[int] = None,
        where: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        すべての論文データとそのembeddingを取得（新しい順）

        Args:
            limit: 取得する最大件数（Noneの場合は全件）
            where: メタデータフィルタ（オプション）

        Returns:
            論文データのリスト（embedding含む、年の降順でソート）
        """
        try:
            # 全件数取得
            total_count = self.collection.count()

            logger.info(f"Fetching papers with embeddings from ChromaDB (total: {total_count})")

            # まず全IDとメタデータを取得（ソートのため）
            try:
                metadata_result = self.collection.get(
                    include=["metadatas"]  # IDとメタデータのみ
                )
                all_ids = metadata_result["ids"]
                all_metadatas = metadata_result["metadatas"]
            except Exception as e:
                logger.error(f"Failed to fetch IDs and metadata: {e}")
                # フォールバック: クエリを使って取得
                logger.info("Trying alternative method with query...")
                return self._get_papers_via_query(limit, where)

            if not all_ids:
                logger.warning("No paper IDs found")
                return []

            # メタデータの年でソート（新しい順）
            # (id, metadata)のペアを作成
            id_metadata_pairs = list(zip(all_ids, all_metadatas))

            # 年でソート（降順）、年がない場合は最後に
            def get_year(pair):
                metadata = pair[1]
                year_str = metadata.get("year", "")
                try:
                    return int(year_str) if year_str else 0
                except (ValueError, TypeError):
                    return 0

            sorted_pairs = sorted(id_metadata_pairs, key=get_year, reverse=True)

            # limit適用
            if limit:
                sorted_pairs = sorted_pairs[:limit]

            logger.info(f"Selected {len(sorted_pairs)} papers (sorted by year, newest first)")

            # 各IDについて個別に取得（問題のあるIDをスキップ）
            papers = []
            failed_ids = []

            for paper_id, _ in sorted_pairs:
                try:
                    result = self.collection.get(
                        ids=[paper_id],
                        include=["embeddings", "metadatas", "documents"]
                    )

                    if result and result["ids"]:
                        papers.append({
                            "id": result["ids"][0],
                            "embedding": result["embeddings"][0],
                            "metadata": result["metadatas"][0],
                            "document": result["documents"][0]
                        })
                except Exception as e:
                    logger.warning(f"Failed to fetch paper {paper_id}: {e}")
                    failed_ids.append(paper_id)
                    continue

            if failed_ids:
                logger.warning(f"Failed to fetch {len(failed_ids)} papers with IDs: {failed_ids[:5]}...")

            logger.info(f"Successfully fetched {len(papers)} papers (failed: {len(failed_ids)})")
            return papers

        except Exception as e:
            logger.error(f"Failed to fetch papers with embeddings: {e}")
            return []

    def _get_papers_via_query(
        self,
        limit: Optional[int] = None,
        where: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        queryメソッドを使ってデータを取得（フォールバック）

        Args:
            limit: 取得する最大件数
            where: メタデータフィルタ

        Returns:
            論文データのリスト（年の降順でソート）
        """
        try:
            # ダミークエリで全件取得
            # embeddingのゼロベクトルを使用
            total_count = self.collection.count()

            # 空のクエリベクトル（embeddingの次元数を取得するため、1件取得）
            sample = self.collection.get(limit=1, include=["embeddings"])
            if not sample or not sample["embeddings"]:
                logger.error("Cannot determine embedding dimension")
                return []

            embedding_dim = len(sample["embeddings"][0])
            zero_vector = [0.0] * embedding_dim

            # queryで全件取得（ソートのため）
            result = self.collection.query(
                query_embeddings=[zero_vector],
                n_results=total_count,
                where=where,
                include=["embeddings", "metadatas", "documents"]
            )

            papers = []
            if result and result["ids"] and result["ids"][0]:
                for i in range(len(result["ids"][0])):
                    papers.append({
                        "id": result["ids"][0][i],
                        "embedding": result["embeddings"][0][i],
                        "metadata": result["metadatas"][0][i],
                        "document": result["documents"][0][i]
                    })

            # 年でソート（新しい順）
            def get_year(paper):
                year_str = paper["metadata"].get("year", "")
                try:
                    return int(year_str) if year_str else 0
                except (ValueError, TypeError):
                    return 0

            papers.sort(key=get_year, reverse=True)

            # limit適用
            if limit:
                papers = papers[:limit]

            logger.info(f"Fetched {len(papers)} papers via query method (sorted by year)")
            return papers

        except Exception as e:
            logger.error(f"Query method also failed: {e}")
            return []

    def get_similar_papers(
        self,
        notion_page_id: str,
        n_results: int = 5
    ) -> List[Dict[str, Any]]:
        """
        指定された論文に類似した論文を取得

        Args:
            notion_page_id: Notion ページID
            n_results: 取得する類似論文数

        Returns:
            類似論文のリスト
        """
        try:
            # 指定された論文を取得（embeddingも含む）
            result = self.collection.get(
                ids=[notion_page_id],
                include=["embeddings", "metadatas", "documents"]
            )

            if not result or not result['ids']:
                logger.warning(f"Paper not found: {notion_page_id}")
                return []

            # embeddingを取得
            paper_embedding = result['embeddings'][0]

            # そのembeddingで類似論文を検索（自分自身も含まれるので+1件取得）
            similar_results = self.collection.query(
                query_embeddings=[paper_embedding],
                n_results=n_results + 1,  # 自分自身を除外するため+1
                include=["metadatas", "documents", "distances"]
            )

            # 結果を整形（自分自身を除外）
            formatted_results = []
            for i, paper_id in enumerate(similar_results['ids'][0]):
                # 自分自身をスキップ
                if paper_id == notion_page_id:
                    continue

                # 類似度スコアを計算（距離→類似度に変換）
                distance = similar_results['distances'][0][i]
                similarity_score = max(0, 1 - distance)

                result = {
                    "id": paper_id,
                    "metadata": similar_results['metadatas'][0][i],
                    "document": similar_results['documents'][0][i],
                    "similarity_score": similarity_score,
                    "distance": distance
                }
                formatted_results.append(result)

                # 必要数に達したら終了
                if len(formatted_results) >= n_results:
                    break

            logger.info(f"Found {len(formatted_results)} similar papers for {notion_page_id}")
            return formatted_results

        except Exception as e:
            logger.error(f"Failed to get similar papers: {e}")
            return []

    def generate_semantic_map(
        self,
        limit: Optional[int] = None,
        where: Optional[Dict[str, Any]] = None,
        n_neighbors: int = 15,
        min_dist: float = 0.1,
        random_state: int = 42
    ) -> Dict[str, Any]:
        """
        UMAPを使ってセマンティックマップを生成

        Args:
            limit: マップに含める論文数の上限
            where: メタデータフィルタ
            n_neighbors: UMAPのn_neighborsパラメータ（デフォルト15）
            min_dist: UMAPのmin_distパラメータ（デフォルト0.1）
            random_state: 乱数シード（再現性のため）

        Returns:
            マップデータの辞書 {
                "papers": List[Dict],  # 各論文の情報
                "x": List[float],      # X座標
                "y": List[float],      # Y座標
                "stats": Dict          # 統計情報
            }
        """
        try:
            import numpy as np
            from umap import UMAP

            # 論文データ取得
            papers = self.get_all_papers_with_embeddings(limit=limit, where=where)

            if len(papers) < 2:
                logger.warning("Not enough papers to generate semantic map")
                return {
                    "papers": [],
                    "x": [],
                    "y": [],
                    "stats": {"error": "Not enough papers"}
                }

            logger.info(f"Generating semantic map for {len(papers)} papers")

            # Embeddingsを抽出
            embeddings = np.array([paper["embedding"] for paper in papers])

            # UMAPで2次元に圧縮
            logger.info("Running UMAP dimensionality reduction...")
            umap_model = UMAP(
                n_components=2,
                n_neighbors=min(n_neighbors, len(papers) - 1),
                min_dist=min_dist,
                metric="cosine",
                random_state=random_state,
                verbose=False
            )

            coords_2d = umap_model.fit_transform(embeddings)

            # 結果を整形
            x_coords = coords_2d[:, 0].tolist()
            y_coords = coords_2d[:, 1].tolist()

            # 統計情報
            stats = {
                "total_papers": len(papers),
                "embedding_dim": len(papers[0]["embedding"]),
                "umap_params": {
                    "n_neighbors": n_neighbors,
                    "min_dist": min_dist
                }
            }

            logger.info("Semantic map generation completed")

            return {
                "papers": papers,
                "x": x_coords,
                "y": y_coords,
                "stats": stats
            }

        except ImportError as e:
            logger.error(f"UMAP not installed: {e}")
            return {
                "papers": [],
                "x": [],
                "y": [],
                "stats": {"error": "UMAP library not installed"}
            }
        except Exception as e:
            logger.error(f"Failed to generate semantic map: {e}")
            return {
                "papers": [],
                "x": [],
                "y": [],
                "stats": {"error": str(e)}
            }


# シングルトンインスタンス
chromadb_service = ChromaDBService()
