"""
Deep Search LLM Service

HyDE（Query Expansion）とReranking機能を提供します。
デフォルトではGemini 3.5 Flashを使用します。
"""

from typing import List, Dict, Any, Optional
import google.generativeai as genai

from app.config import config
from app.utils.logger import get_logger

logger = get_logger(__name__)


class GemmaService:
    """Deep Search用LLMサービスクラス"""

    def __init__(self):
        """初期化"""
        # Gemini API の初期化
        genai.configure(api_key=config.gemini_api_key)

        # モデル設定
        self.model_name = "gemini-3.5-flash"

        self.generation_config = {
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 2048,
        }

        logger.info(f"Deep Search LLM service initialized with model: {self.model_name}")

    def generate_hyde_query(self, user_query: str) -> str:
        """
        HyDE（Hypothetical Document Embeddings）による検索クエリ拡張

        ユーザーの短い質問から、検索に有利な「架空の論文要約」を生成します。

        Args:
            user_query: ユーザーの検索クエリ

        Returns:
            生成された架空の論文要約（日本語）
        """
        try:
            prompt = f"""あなたは医学論文の専門家です。以下の質問に対して、その答えが含まれているであろう架空の医学論文の要約を日本語で生成してください。

【重要な指示】
- 実在する論文ではなく、質問に関連する「理想的な論文」の要約を想像して書いてください
- 医学的に専門的な用語を積極的に使用してください
- 具体的な研究方法や結果の記述を含めてください
- 400-600文字程度で簡潔に記述してください
- 論文タイトルは含めず、要約本文のみを出力してください

【ユーザーの質問】
{user_query}

【架空の論文要約】
"""

            model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config=self.generation_config
            )

            response = model.generate_content(prompt)
            expanded_query = response.text.strip()

            logger.info(f"HyDE query expansion completed. Original: '{user_query}', Expanded length: {len(expanded_query)}")

            return expanded_query

        except Exception as e:
            logger.error(f"HyDE query expansion failed: {e}")
            # フォールバック: 元のクエリをそのまま返す
            logger.warning("Falling back to original query")
            return user_query

    def rerank_results(
        self,
        user_query: str,
        candidates: List[Dict[str, Any]],
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """
        LLMベースのReranking

        ベクトル検索で取得した候補を、ユーザーの質問に基づいて精査・並べ替えます。

        Args:
            user_query: ユーザーの元の質問
            candidates: ベクトル検索で取得した候補リスト
            top_k: 最終的に返す上位件数（デフォルト5）

        Returns:
            Rerankingされた論文リスト（適合度順）
        """
        try:
            if not candidates:
                return []

            # 候補リストをLLMに渡すためのテキスト形式に変換
            candidates_text = []
            for idx, result in enumerate(candidates, 1):
                metadata = result["metadata"]
                title = metadata.get("title", "タイトル不明")
                authors = metadata.get("authors", "著者不明")
                year = metadata.get("year", "")
                journal = metadata.get("journal", "")
                summary = metadata.get("summary", "")[:300]  # 最初の300文字のみ

                candidates_text.append(
                    f"[{idx}] タイトル: {title}\n"
                    f"著者: {authors}\n"
                    f"雑誌: {journal} ({year})\n"
                    f"要約: {summary}...\n"
                )

            candidates_str = "\n".join(candidates_text)

            prompt = f"""あなたは医学論文の専門家です。以下のユーザーの質問に対して、最も関連性が高い論文を選出してください。

【ユーザーの質問】
{user_query}

【候補論文リスト】
{candidates_str}

【指示】
1. 上記の質問に対して、最も関連性が高い順に論文を並べ替えてください
2. 関連性が高いTop {top_k}件の論文番号を選出してください
3. 出力は以下の形式で、選出した論文番号のみをカンマ区切りで記述してください（説明は不要）：
   例: 3,7,1,12,5

【選出した論文番号】
"""

            model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config={
                    **self.generation_config,
                    "temperature": 0.3,  # より決定論的に
                }
            )

            response = model.generate_content(prompt)
            output = response.text.strip()

            # 出力から論文番号を抽出
            try:
                # カンマ区切りの数字を抽出
                selected_indices = []
                for num_str in output.replace(" ", "").split(","):
                    try:
                        idx = int(num_str)
                        if 1 <= idx <= len(candidates):
                            selected_indices.append(idx - 1)  # 0-based index
                    except ValueError:
                        continue

                if not selected_indices:
                    logger.warning(f"No valid indices extracted from reranking output: {output}")
                    # フォールバック: 元の順序のTop k
                    return candidates[:top_k]

                # 選出された論文を順番に並べる
                reranked = [candidates[idx] for idx in selected_indices if idx < len(candidates)]

                # 不足分を元の順序で補完
                if len(reranked) < top_k:
                    remaining = [c for i, c in enumerate(candidates) if i not in selected_indices]
                    reranked.extend(remaining[:top_k - len(reranked)])

                logger.info(f"Reranking completed. Selected {len(reranked)} papers from {len(candidates)} candidates")

                return reranked[:top_k]

            except Exception as e:
                logger.error(f"Failed to parse reranking output: {e}")
                # フォールバック: 元の順序のTop k
                return candidates[:top_k]

        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            # フォールバック: 元の順序のTop k
            logger.warning("Falling back to original order")
            return candidates[:top_k]


# シングルトンインスタンス
gemma_service = GemmaService()
