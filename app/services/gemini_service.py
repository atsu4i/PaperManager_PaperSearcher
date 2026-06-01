"""
Gemini API連携サービス
論文の解析と要約を行う
"""

import asyncio
import json
import re
from typing import Dict, List, Optional, Tuple
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

try:
    from google import genai as google_genai
    from google.genai import types as google_genai_types
    GOOGLE_GENAI_AVAILABLE = True
except ImportError:
    google_genai = None
    google_genai_types = None
    GOOGLE_GENAI_AVAILABLE = False

from ..config import config
from ..models.paper import PaperMetadata
from ..utils.logger import get_logger

logger = get_logger(__name__)


class GeminiService:
    """Gemini API連携クラス"""

    def __init__(self):
        if not config.gemini_api_key:
            raise ValueError("Gemini API キーが設定されていません")

        genai.configure(api_key=config.gemini_api_key)
        self.google_genai_client = None
        if GOOGLE_GENAI_AVAILABLE:
            self.google_genai_client = google_genai.Client(api_key=config.gemini_api_key)

        # メタデータ抽出用モデル
        self.metadata_model = genai.GenerativeModel(
            model_name=config.gemini.metadata_model,
            generation_config=genai.types.GenerationConfig(
                temperature=config.gemini.temperature,
                max_output_tokens=config.gemini.max_tokens,
            ),
            safety_settings={
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
        )

        # 要約作成用モデル
        self.summary_model = genai.GenerativeModel(
            model_name=config.gemini.summary_model,
            generation_config=genai.types.GenerationConfig(
                temperature=config.gemini.temperature,
                max_output_tokens=config.gemini.max_tokens,
            ),
            safety_settings={
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            }
        )

        # 後方互換性のため残す
        self.model = self.metadata_model

        # 使用中のモデルをログ出力
        logger.info(f"Gemini Service初期化完了")
        logger.info(f"  メタデータ抽出用モデル: {config.gemini.metadata_model}")
        logger.info(f"  要約作成用モデル: {config.gemini.summary_model}")
        if (
            self._is_gemma4_model(config.gemini.metadata_model)
            or self._is_gemma4_model(config.gemini.summary_model)
        ):
            if GOOGLE_GENAI_AVAILABLE:
                logger.info("  Gemma 4: ThinkingConfig(thinking_level='MINIMAL') を有効化")
            else:
                logger.warning(
                    "  Gemma 4が選択されていますが google-genai が未インストールです。"
                    "thinking抑制には `pip install google-genai` が必要です。"
                )
    
    async def analyze_paper(self, pdf_text: str, file_name: str) -> PaperMetadata:
        """論文の解析とメタデータ抽出（後方互換性のため残す）"""
        try:
            logger.info(f"論文解析開始: {file_name}")

            # メタデータ抽出
            metadata = await self._extract_metadata(pdf_text)

            # 日本語要約作成
            japanese_summary = await self._create_japanese_summary(pdf_text)

            # PaperMetadataオブジェクトの作成
            paper_metadata = self._create_paper_metadata(metadata, japanese_summary, pdf_text, file_name)

            logger.info(f"論文解析完了: {file_name}")
            return paper_metadata

        except Exception as e:
            logger.error(f"論文解析エラー: {e}")
            raise

    async def extract_metadata_only(self, pdf_text: str, file_name: str) -> PaperMetadata:
        """メタデータのみを抽出（要約なし）

        Raises:
            ValueError: メタデータ検証失敗（必須フィールド欠損）
        """
        try:
            logger.info(f"メタデータ抽出開始: {file_name}")

            # メタデータ抽出
            metadata = await self._extract_metadata(pdf_text)

            # メタデータ検証
            if not self._validate_metadata(metadata, file_name):
                raise ValueError(f"メタデータ検証失敗: 必須フィールド（title）が欠損しています - {file_name}")

            # 要約なしでPaperMetadataオブジェクトを作成
            paper_metadata = self._create_paper_metadata(
                metadata,
                "", # 要約は空
                pdf_text,
                file_name
            )

            logger.info(f"メタデータ抽出完了: {file_name}")
            return paper_metadata

        except ValueError:
            # メタデータ検証失敗は再スロー
            raise
        except Exception as e:
            logger.error(f"メタデータ抽出エラー: {e}")
            raise

    async def add_summary_to_metadata(self, paper_metadata: PaperMetadata, pdf_text: str) -> PaperMetadata:
        """既存のメタデータに日本語要約を追加"""
        try:
            logger.info(f"要約作成開始: {paper_metadata.title[:50]}...")

            # 日本語要約作成
            japanese_summary = await self._create_japanese_summary(pdf_text)

            # 要約を追加
            paper_metadata.summary_japanese = japanese_summary

            logger.info(f"要約作成完了: {len(japanese_summary)}文字")
            return paper_metadata

        except Exception as e:
            logger.error(f"要約作成エラー: {e}")
            raise

    def _create_paper_metadata(self, metadata: Dict, japanese_summary: str,
                               pdf_text: str, file_name: str) -> PaperMetadata:
        """メタデータ辞書からPaperMetadataオブジェクトを作成"""
        # データの安全なクリーニング
        def safe_get_list(data, key, default=None):
            """リスト型フィールドを安全に取得"""
            value = data.get(key, default)
            if value is None:
                return []
            if isinstance(value, list):
                return value
            if isinstance(value, str):
                return [value]
            return []

        def safe_get_str(data, key, default=''):
            """文字列型フィールドを安全に取得"""
            value = data.get(key, default)
            return str(value) if value is not None else default

        # PaperMetadataオブジェクトの作成
        return PaperMetadata(
            title=safe_get_str(metadata, 'title'),
            authors=safe_get_list(metadata, 'authors'),
            publication_year=safe_get_str(metadata, 'publication_year') or None,
            journal=safe_get_str(metadata, 'journal') or None,
            volume=safe_get_str(metadata, 'volume') or None,
            issue=safe_get_str(metadata, 'issue') or None,
            pages=safe_get_str(metadata, 'pages') or None,
            doi=safe_get_str(metadata, 'doi') or None,
            keywords=safe_get_list(metadata, 'keywords'),
            abstract=safe_get_str(metadata, 'abstract') or None,
            summary_japanese=japanese_summary,
            full_text=pdf_text,
            file_path="",  # 後で設定
            file_name=file_name,
            file_size=0  # 後で設定
        )
    
    async def _extract_metadata(self, pdf_text: str) -> Dict:
        """論文からメタデータを抽出"""
        
        # テキストが長すぎる場合は最初の部分のみを使用
        text_to_analyze = pdf_text[:8000] if len(pdf_text) > 8000 else pdf_text
        
        prompt = f"""
以下の医学論文のテキストから、メタデータを抽出してJSON形式で出力してください。

論文テキスト:
{text_to_analyze}

抽出する項目:
- title: 論文タイトル（英語原文）- 文字列型
- authors: 著者名のリスト（姓名順、最大10名）- **必ず配列型 []**
- publication_year: 発行年（YYYY形式）- 文字列型
- journal: 雑誌名 - 文字列型
- volume: 巻号 - 文字列型
- issue: 号数 - 文字列型またはnull
- pages: ページ範囲（例: "123-130"）- 文字列型
- doi: DOI番号（あれば）- 文字列型またはnull
- keywords: キーワードのリスト（論文の主要概念、手法、分野、対象を含む最大20個、英語で。複数形を優先し、ハイフン区切りで表記。例: "large-language-models", "electronic-health-records", "natural-language-processing"）- **必ず配列型 []**
- abstract: 英語の抄録全文 - 文字列型

**重要な注意事項**:
1. JSON形式で出力してください。
2. 情報が見つからない場合はnullを設定してください。
3. **authors と keywords は必ず配列形式 [] で出力してください**（例: ["value1", "value2"]）
4. 著者名は "Last, First" 形式で抽出してください。
5. **フィールド値内（特にabstract）でダブルクォート（"）を使用しないでください。シングルクォート（'）を使用するか、引用符なしで記述してください。**
6. **改行は含めず、すべて1行のテキストにしてください。**

出力例:
{{
  "title": "Effects of...",
  "authors": ["Smith, John", "Johnson, Mary"],
  "publication_year": "2023",
  "journal": "Nature Medicine",
  "volume": "29",
  "issue": "3",
  "pages": "123-130",
  "doi": "10.1038/s41591-023-02345-6",
  "keywords": ["electronic-health-records", "functional-limitations", "geriatrics", "healthcare-data", "activities-of-daily-living", "instrumental-activities-of-daily-living", "mobility-assessments", "aging-research", "clinical-documentation"],
  "abstract": "Background: ... Methods: ... Results: ... Conclusions: ..."
}}
"""

        try:
            # メタデータ抽出用モデルを使用
            response = await self._generate_with_retry(prompt, model=self.metadata_model)

            # JSONを抽出・修復
            metadata = self._extract_and_repair_json(response)

            if metadata and isinstance(metadata, dict):
                logger.info("メタデータJSON抽出成功")
                return metadata
            else:
                logger.error("有効なJSONメタデータを抽出できませんでした")
                logger.error(f"Geminiレスポンス（最初の500文字）: {response[:500]}")
                return {}

        except json.JSONDecodeError as e:
            logger.error(f"JSON解析エラー: {e}")
            logger.error(f"Geminiレスポンス（最初の500文字）: {response[:500] if 'response' in locals() else 'N/A'}")
            return {}
        except Exception as e:
            logger.error(f"メタデータ抽出エラー: {e}")
            logger.exception("詳細なエラー情報:")
            return {}
    
    async def _create_japanese_summary(self, pdf_text: str) -> str:
        """日本語要約を作成"""
        
        # テキストが長すぎる場合は適切な長さに分割
        max_chunk_size = 12000
        if len(pdf_text) > max_chunk_size:
            # 重要な部分（抄録、結論など）を優先的に含める
            chunks = self._split_text_smart(pdf_text, max_chunk_size)
            text_to_summarize = chunks[0]  # 最初のチャンクを使用
        else:
            text_to_summarize = pdf_text
        
        prompt = f"""
あなたは医学論文の専門要約者である。以下の論文を読み、高品質な日本語要約を作成せよ。

【論文テキスト】
{text_to_summarize}

【内部処理（出力禁止）】
- 論文全体を読み、研究の目的・方法・結果・結論を把握する
- 重要な数値データ（対象者数、p値、効果量等）を抽出する
- ただし、思考過程、手順、箇条書きの作業メモ、入力文の再掲は絶対に出力しない

【厳格な出力要件】
1. **文字数**: 1800-1900文字（必ず守る）
2. **文体**: 常体（である調、だ調）を使用。「です・ます調」は禁止
3. **構成**: 必ず以下の要素を含める
   - 研究背景（2-3文）：なぜこの研究が必要か
   - 目的（1-2文）：何を明らかにするか
   - 方法（3-4文）：対象者数、研究デザイン、評価指標
   - 結果（4-6文）：主要な発見と統計データ（p値、効果量を必ず記載）
   - 結論（2-3文）：何が示されたか
   - 意義（2-3文）：臨床的・学術的価値
   - 限界（1-2文）：研究の制約や今後の課題
4. **データの明記**: 以下を必ず含める
   - 対象者数（n=XX）
   - 統計的有意性（p値、信頼区間等）
   - 主要評価項目の具体的数値
   - 研究デザイン（RCT、コホート研究等）

【医学論文特有の注意点】
- 医学専門用語は正確な日本語を使用（例：RCT→ランダム化比較試験）
- 略語は初出時にフル表記を併記（例：HSCT（造血幹細胞移植））
- 統計結果は必ず数値とp値をセットで記載（例：有意に減少した（p=0.004））
- 臨床的意義と研究の限界を必ず明記する
- 論文全体の包括的要約を作成（抄録の単純翻訳ではない）

【出力形式】
- プレフィックス・ヘッダー・説明文は一切不要
- 要約内容のみを直接出力
- 段落分けは自然に行う（改行で区切る）
- 英語の指示文、作業手順、考え方、Markdownの箇条書き、タイトル行を出力しない
- 出力は日本語の完成した要約本文のみ

【良い出力例の文体】
○「本研究では、HSCTを受ける患者21名（介入群11名、対照群10名）を対象に、ペット型ロボットの効果を検証した。」
○「介入群では、ストレスマーカーであるCgA濃度が有意に減少した（p=0.004）。」
○「この知見は、免疫不全患者への安全な精神ケア手段を提供する点で臨床的意義が大きい。」
○「ただし、本研究はサンプルサイズが小さく、今後大規模研究での検証が必要である。」

【悪い出力例】
×「本研究では...を検証しました。」（です・ます調）
×「ストレスが減少した。」（数値データなし）
×「有効性が示された。」（具体性に欠ける）
×（研究の限界に言及なし）

要約を直接出力せよ：
"""

        try:
            # 要約作成用モデルを使用
            summary = await self._generate_with_retry(prompt, model=self.summary_model)
            
            # 包括的なプレフィックス・サフィックス除去
            summary = self._clean_summary_output(summary)

            if not self._contains_japanese(summary) or self._looks_like_prompt_echo(summary):
                logger.warning("要約出力が日本語要約ではない、またはプロンプトのエコーを含む可能性があります。短い再生成を試みます。")
                summary = await self._regenerate_summary_concise(text_to_summarize)
                summary = self._clean_summary_output(summary)
            
            # 文字数確認とログ
            char_count = len(summary)
            logger.info(f"日本語要約作成完了: {char_count}文字")
            
            # 1900文字を超えている場合の警告
            if char_count > 1900:
                logger.warning(f"要約が制限を超過: {char_count}文字 > 1900文字")
                # 文の境界で切り詰め
                summary = self._truncate_at_sentence_boundary(summary, 1900)
                logger.info(f"要約を切り詰め: {len(summary)}文字")
            
            return summary
            
        except Exception as e:
            logger.error(f"要約作成エラー: {e}")
            return "要約の作成に失敗した。"
    
    def _clean_summary_output(self, text: str) -> str:
        """要約出力から不要なプレフィックス・サフィックスを除去"""
        if not text:
            return text

        text = self._remove_thinking_and_prompt_artifacts(text)
        
        # 一般的なプレフィックスパターンを除去
        prefixes_to_remove = [
            r'^要約[:：]?\s*',
            r'^以下.*要約.*[:：]\s*',
            r'^.*要約内容.*[:：]\s*',
            r'^この論文.*要約.*[:：]\s*',
            r'^【要約】\s*',
            r'^\*\*要約\*\*\s*',
            r'^要約を以下に.*[:：]\s*',
            r'^医学論文.*要約.*[:：]\s*'
        ]
        
        for pattern in prefixes_to_remove:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.MULTILINE)
        
        # 一般的なサフィックスパターンを除去
        suffixes_to_remove = [
            r'\s*以上が要約.*$',
            r'\s*これで要約.*$',
            r'\s*要約は以上.*$',
            r'\s*\(.*文字.*\)$'
        ]
        
        for pattern in suffixes_to_remove:
            text = re.sub(pattern, '', text, flags=re.IGNORECASE | re.MULTILINE)
        
        # 前後の空白・改行を除去
        text = text.strip()
        
        # 複数の改行を単一に
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text

    def _remove_thinking_and_prompt_artifacts(self, text: str) -> str:
        """Gemma 4等が出す思考/プロンプトエコーを除去"""
        if not text:
            return text

        # 明示的なthinkingタグ/セクション
        artifact_patterns = [
            r'<think>.*?</think>',
            r'<thinking>.*?</thinking>',
            r'(?is)^\s*(?:thinking|reasoning|analysis)\s*[:：].*?(?=\n\s*(?:本研究|本論文|本稿|本解析|本レビュー)|\Z)',
        ]
        for pattern in artifact_patterns:
            text = re.sub(pattern, '', text, flags=re.DOTALL | re.IGNORECASE)

        # プロンプト末尾や出力指示がエコーされた場合は、その後ろだけを使う
        markers = [
            '要約を直接出力せよ：',
            '要約を直接出力せよ:',
            '日本語要約:',
            '日本語要約：',
        ]
        for marker in markers:
            if marker in text:
                text = text.split(marker)[-1]

        # 英語のロール/作業メモが先頭に混入した場合、日本語要約らしい開始位置から採用
        starts = [
            '本研究', '本論文', '本稿', 'この研究', '本解析', '本レビュー',
            '研究背景', '目的は', '背景として'
        ]
        japanese_positions = [text.find(s) for s in starts if text.find(s) >= 0]
        if japanese_positions:
            first_pos = min(japanese_positions)
            leading = text[:first_pos]
            # 先頭に英語指示や箇条書きが長く入っている場合だけ切る
            if len(leading) > 80 or re.search(r'(Step\s*\d+|Medical paper|summarizer|Output format|Data requirements)', leading, re.I):
                text = text[first_pos:]

        return text

    def _contains_japanese(self, text: str) -> bool:
        """日本語文字が含まれるか"""
        return bool(text and re.search(r'[\u3040-\u30ff\u3400-\u9fff]', text))

    def _looks_like_prompt_echo(self, text: str) -> bool:
        """プロンプトや思考過程のエコーらしい出力か判定"""
        if not text:
            return True

        suspicious_patterns = [
            r'Medical paper summarizer',
            r'Step\s*\d+',
            r'Output format',
            r'Data requirements',
            r'Length:\s*\d+',
            r'Task:',
            r'^\s*[\*\-]\s+Step',
            r'【論文テキスト】',
            r'【厳格な出力要件】',
            r'内部処理',
            r'出力禁止',
        ]
        if any(re.search(pattern, text, re.IGNORECASE | re.MULTILINE) for pattern in suspicious_patterns):
            return True

        # 日本語要約より英語/記号が多すぎる場合
        japanese_chars = len(re.findall(r'[\u3040-\u30ff\u3400-\u9fff]', text))
        ascii_letters = len(re.findall(r'[A-Za-z]', text))
        return ascii_letters > max(300, japanese_chars * 1.2)

    async def _regenerate_summary_concise(self, text_to_summarize: str) -> str:
        """プロンプトエコー時の再生成用。短く明確な指示で出し直す"""
        concise_prompt = f"""
以下の医学論文テキストを日本語で1800字程度に要約せよ。

絶対条件:
- 出力は日本語の要約本文のみ
- 思考過程、手順、箇条書き、英語の説明、入力文の再掲を出力しない
- 常体（である調）
- 背景、目的、方法、結果、結論、意義、限界を自然な段落で含める
- n、p値、信頼区間など本文中にある具体的数値を可能な限り含める

論文テキスト:
{text_to_summarize}

要約本文:
"""
        return await self._generate_with_retry(concise_prompt, model=self.summary_model)
    
    def _truncate_at_sentence_boundary(self, text: str, max_length: int) -> str:
        """文の境界で自然にテキストを切り詰める"""
        if not text or len(text) <= max_length:
            return text
        
        # 日本語の文区切り文字
        sentence_endings = ['。', '．', '！', '？', '!', '?']
        
        # 最大長以内の位置で最後の文区切りを見つける
        best_pos = -1
        
        # 後ろから検索して、適切な文区切りを見つける
        for i in range(min(max_length - 1, len(text) - 1), -1, -1):
            if text[i] in sentence_endings:
                best_pos = i + 1  # 文区切り文字の直後
                break
        
        # 文区切りが見つからない場合は、句読点での区切りを試す
        if best_pos == -1:
            punctuation_marks = ['、', '，', ',']
            for i in range(min(max_length - 1, len(text) - 1), -1, -1):
                if text[i] in punctuation_marks:
                    best_pos = i + 1
                    break
        
        # それでも見つからない場合は、強制的に切り詰め
        if best_pos == -1:
            best_pos = max_length
        
        # 最終的な位置で切り詰め
        truncated = text[:best_pos].rstrip()
        
        return truncated

    def _escape_field_values(self, json_str: str) -> str:
        """JSONフィールド値内の特殊文字を処理

        正規表現では複雑な引用符のネストを扱えないため、
        文字単位で解析してフィールド値を処理します。

        処理内容:
        1. ダブルクォート → シングルクォートに置換（エスケープ不要）
        2. 改行/タブ → エスケープ

        Args:
            json_str: 修復対象のJSON文字列

        Returns:
            特殊文字が処理されたJSON文字列
        """
        result = []
        i = 0
        in_field_value = False

        while i < len(json_str):
            char = json_str[i]

            # フィールドの開始を検出: "field":
            if char == '"' and not in_field_value:
                # フィールド名の開始
                result.append(char)
                i += 1
                # フィールド名をスキップ
                while i < len(json_str) and json_str[i] != '"':
                    if json_str[i] == '\\' and i + 1 < len(json_str):
                        result.append(json_str[i])
                        result.append(json_str[i + 1])
                        i += 2
                    else:
                        result.append(json_str[i])
                        i += 1
                if i < len(json_str):
                    result.append(json_str[i])  # 閉じる"
                    i += 1

                # コロンとスペースをスキップ
                while i < len(json_str) and json_str[i] in ': \t\n':
                    result.append(json_str[i])
                    i += 1

                # 値の開始チェック
                if i < len(json_str) and json_str[i] == '"':
                    in_field_value = True
                    result.append(json_str[i])  # 開始の"
                    i += 1
                continue

            # フィールド値の中
            if in_field_value:
                # エスケープシーケンス処理
                if char == '\\' and i + 1 < len(json_str):
                    next_char = json_str[i + 1]
                    # 既にエスケープされているものはそのまま
                    if next_char in ['"', '\\', '/', 'b', 'f', 'n', 'r', 't']:
                        result.append(char)
                        result.append(next_char)
                        i += 2
                        continue

                # 値の終了を検出
                if char == '"':
                    # 次の文字を確認
                    next_pos = i + 1
                    while next_pos < len(json_str) and json_str[next_pos] in ' \t\n\r':
                        next_pos += 1

                    # 次が } の場合は確実に終了
                    if next_pos < len(json_str) and json_str[next_pos] == '}':
                        in_field_value = False
                        result.append(char)
                        i += 1
                        continue

                    # 次が , の場合は、更にその先を確認
                    if next_pos < len(json_str) and json_str[next_pos] == ',':
                        # カンマの後をチェック
                        check_pos = next_pos + 1
                        while check_pos < len(json_str) and json_str[check_pos] in ' \t\n\r':
                            check_pos += 1

                        # カンマの後が } の場合は終了
                        if check_pos >= len(json_str) or json_str[check_pos] == '}':
                            in_field_value = False
                            result.append(char)
                            i += 1
                            continue

                        # カンマの後が " の場合、それが次のフィールド名かチェック
                        if check_pos < len(json_str) and json_str[check_pos] == '"':
                            # " の後に : があるか確認（次のフィールドの開始）
                            temp_pos = check_pos + 1
                            # フィールド名をスキップ
                            while temp_pos < len(json_str) and json_str[temp_pos] != '"':
                                if json_str[temp_pos] == '\\' and temp_pos + 1 < len(json_str):
                                    temp_pos += 2
                                else:
                                    temp_pos += 1

                            if temp_pos < len(json_str):
                                temp_pos += 1  # 閉じる " をスキップ
                                # : を探す
                                while temp_pos < len(json_str) and json_str[temp_pos] in ' \t\n\r':
                                    temp_pos += 1

                                # : が見つかれば次のフィールド → 現在のフィールド終了
                                if temp_pos < len(json_str) and json_str[temp_pos] == ':':
                                    in_field_value = False
                                    result.append(char)
                                    i += 1
                                    continue

                    # それ以外の場合は値の中のダブルクォート → シングルクォートに置換
                    result.append("'")
                    i += 1
                    continue

                # 値の中の特殊文字を処理
                if char == '\n':
                    result.append('\\n')
                elif char == '\r':
                    result.append('\\r')
                elif char == '\t':
                    result.append('\\t')
                else:
                    result.append(char)
                i += 1
                continue

            # その他の文字はそのまま
            result.append(char)
            i += 1

        return ''.join(result)

    def _repair_array_fields(self, json_str: str) -> str:
        """配列フィールドのブラケット欠損を修復

        Geminiが "keywords": "value1", "value2" のように出力した場合、
        "keywords": ["value1", "value2"] に修復する

        Args:
            json_str: 修復対象のJSON文字列

        Returns:
            修復されたJSON文字列
        """
        # 配列であるべきフィールド
        array_fields = ['keywords', 'authors']

        for field in array_fields:
            # パターン: "field": "value1", "value2", ..., "valueN",
            # 次のフィールド（"XXX":）または終了（}）まで
            # グループ1: フィールド名 "keywords":
            # グループ2: 最初の値 value1
            # グループ3: 残りの値 , "value2", "value3", ...
            # グループ4: 末尾のカンマ
            # グループ5: 次のフィールドまたは終了
            pattern = rf'("{field}":\s*)"([^"]+)"((?:\s*,\s*"[^"]+")*)(\s*,)?(\s*"\w+":|\s*}})'

            def replace_func(match):
                field_name = match.group(1)  # "keywords":
                first_value = match.group(2)  # 最初の値
                remaining_values = match.group(3) or ""  # , "value2", "value3"
                trailing_comma = match.group(4) or ""  # 末尾のカンマ（あれば）
                next_part = match.group(5)  # 次のフィールドまたは}

                # 値を配列に変換
                all_values = f'"{first_value}"'
                if remaining_values:
                    # カンマ区切りの値を抽出
                    all_values += remaining_values

                # 配列形式で返す（末尾のカンマを維持）
                result = f'{field_name}[{all_values}]'
                if trailing_comma:
                    result += ','
                result += next_part

                return result

            json_str = re.sub(pattern, replace_func, json_str)

        return json_str

    def _extract_and_repair_json(self, response: str) -> Dict:
        """GeminiレスポンスからJSONを抽出・修復する

        Args:
            response: Geminiからのレスポンステキスト

        Returns:
            抽出されたメタデータ辞書（失敗時は空辞書）
        """
        try:
            # 1. 標準的なJSON抽出
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if not json_match:
                logger.warning("JSON形式のレスポンスが見つかりません")
                return {}

            json_str = json_match.group()

            # 2. まず素のJSON解析を試行（Geminiが正しいJSONを返した場合）
            try:
                metadata = json.loads(json_str)
                logger.info("素のJSON解析成功（修復不要）")
                return metadata
            except json.JSONDecodeError:
                logger.debug("素のJSON解析失敗、修復処理を開始します")

            # デバッグ用：元のJSON文字列を保存
            original_json_str = json_str

            # 3. 一般的なJSON問題を修復
            # - ダブルクォートの修正（全角→半角）
            json_str = json_str.replace('"', '"').replace('"', '"')

            # - トレーリングカンマを削除（配列・オブジェクトの最後）
            json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)

            # - 配列フィールドの修復（keywords, authorsで[]が欠けている場合）
            # パターン: "keywords": "value1", "value2", ... → "keywords": ["value1", "value2", ...]
            json_str = self._repair_array_fields(json_str)

            # 4. 再度解析を試行
            try:
                metadata = json.loads(json_str)
                logger.info("配列修復後のJSON解析成功")
                return metadata
            except json.JSONDecodeError:
                logger.debug("配列修復後も解析失敗、エスケープ処理を適用します")

            # 5. フィールド値内の特殊文字をエスケープ（最後の手段）
            json_str = self._escape_field_values(json_str)

            # 6. 最終的なJSON解析試行
            try:
                metadata = json.loads(json_str)
                logger.info("エスケープ処理後のJSON解析成功")
                return metadata
            except json.JSONDecodeError as e:
                logger.error(f"JSON解析失敗: {e}")
                logger.error(f"問題のあるJSON（最初の500文字）: {json_str[:500]}")
                # エラー位置をログ出力
                if hasattr(e, 'pos'):
                    error_context = json_str[max(0, e.pos-100):min(len(json_str), e.pos+100)]
                    logger.error(f"エラー位置付近（±100文字）[処理後]: ...{error_context}...")

                    # 元のJSON文字列の同じ位置も表示
                    if 'original_json_str' in locals():
                        original_error_context = original_json_str[max(0, e.pos-100):min(len(original_json_str), e.pos+100)]
                        logger.error(f"エラー位置付近（±100文字）[Gemini出力]: ...{original_error_context}...")
                return {}

        except Exception as e:
            logger.error(f"JSON抽出中の予期しないエラー: {e}")
            return {}

    def _validate_metadata(self, metadata: Dict, file_name: str) -> bool:
        """メタデータの検証

        Args:
            metadata: 検証するメタデータ
            file_name: ファイル名（ログ用）

        Returns:
            True: 有効、False: 無効（必須フィールド欠損）
        """
        # 必須フィールド: title のみ
        title = metadata.get('title', '').strip()
        if not title:
            logger.error(f"メタデータ検証失敗: タイトルが欠損しています - {file_name}")
            return False

        # 警告レベルのチェック
        warnings = []

        if not metadata.get('authors'):
            warnings.append("著者情報")

        if not metadata.get('abstract'):
            warnings.append("抄録")

        if not metadata.get('doi'):
            warnings.append("DOI")

        if warnings:
            logger.warning(f"メタデータ警告 ({file_name}): 以下のフィールドが欠損しています: {', '.join(warnings)}")

        return True

    def _split_text_smart(self, text: str, max_size: int) -> List[str]:
        """テキストを適切に分割"""
        
        # 重要なセクションを特定
        important_sections = [
            'abstract', 'summary', 'conclusion', 'results', 'discussion',
            'introduction', 'background', 'methods', 'methodology'
        ]
        
        chunks = []
        current_chunk = ""
        
        # 段落で分割
        paragraphs = text.split('\n\n')
        
        for paragraph in paragraphs:
            # 現在のチャンクに追加しても制限を超えない場合
            if len(current_chunk + paragraph) <= max_size:
                current_chunk += paragraph + '\n\n'
            else:
                # 現在のチャンクを保存
                if current_chunk:
                    chunks.append(current_chunk.strip())
                
                # 新しいチャンクを開始
                if len(paragraph) <= max_size:
                    current_chunk = paragraph + '\n\n'
                else:
                    # 段落が長すぎる場合は分割
                    chunk_parts = [paragraph[i:i+max_size] for i in range(0, len(paragraph), max_size)]
                    chunks.extend(chunk_parts[:-1])
                    current_chunk = chunk_parts[-1] + '\n\n'
        
        # 最後のチャンクを追加
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    async def _generate_with_retry(self, prompt: str, model=None) -> str:
        """リトライ機能付きでテキスト生成（レート制限対応強化版）

        Args:
            prompt: プロンプトテキスト
            model: 使用するモデル（Noneの場合はself.modelを使用）
        """
        # モデルが指定されていない場合はデフォルトモデルを使用
        if model is None:
            model = self.model

        model_name = self._resolve_model_name(model)

        for attempt in range(config.gemini.max_retries):
            try:
                if self._should_use_google_genai_minimal_thinking(model_name):
                    text = await asyncio.to_thread(
                        self._generate_with_google_genai_minimal_thinking,
                        prompt,
                        model_name
                    )
                else:
                    response = model.generate_content(prompt)
                    text = response.text if getattr(response, "text", None) else ""

                if text:
                    return text
                else:
                    raise ValueError("空のレスポンスが返されました")

            except Exception as e:
                error_message = str(e).lower()
                is_rate_limit_error = (
                    'resource exhausted' in error_message or
                    'rate limit' in error_message or
                    '429' in error_message or
                    'quota' in error_message
                )

                if is_rate_limit_error:
                    # レート制限エラーの場合は長めの待機時間
                    wait_time = config.gemini.retry_delay * (2 ** attempt) * 2  # エクスポネンシャルバックオフ × 2
                    logger.warning(
                        f"Gemini APIレート制限検出 (試行 {attempt + 1}/{config.gemini.max_retries}): "
                        f"{wait_time}秒待機します..."
                    )
                else:
                    # 通常のエラーの場合
                    wait_time = config.gemini.retry_delay * (attempt + 1)
                    logger.warning(
                        f"Gemini API呼び出し失敗 (試行 {attempt + 1}/{config.gemini.max_retries}): {e}"
                    )

                if attempt < config.gemini.max_retries - 1:
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"Gemini API呼び出しが最大試行回数後も失敗: {e}")
                    raise

        raise Exception("Gemini API呼び出しが最大試行回数後も失敗しました")

    def _resolve_model_name(self, model) -> str:
        """GenerativeModelオブジェクトから設定上のモデル名を解決"""
        if model is self.summary_model:
            return config.gemini.summary_model
        if model is self.metadata_model:
            return config.gemini.metadata_model

        model_name = getattr(model, "model_name", "") or getattr(model, "_model_name", "")
        if isinstance(model_name, str):
            return model_name.replace("models/", "")
        return ""

    def _is_gemma4_model(self, model_name: str) -> bool:
        return bool(model_name and model_name.replace("models/", "").startswith("gemma-4-"))

    def _should_use_google_genai_minimal_thinking(self, model_name: str) -> bool:
        """Gemma 4は新SDKでthinkingをMINIMALにする"""
        return (
            self._is_gemma4_model(model_name)
            and GOOGLE_GENAI_AVAILABLE
            and self.google_genai_client is not None
        )

    def _generate_with_google_genai_minimal_thinking(self, prompt: str, model_name: str) -> str:
        """google-genai SDKでGemma 4のthinkingを最小化して生成"""
        normalized_model_name = model_name.replace("models/", "")
        gen_config_kwargs = {
            "temperature": config.gemini.temperature,
            "max_output_tokens": config.gemini.max_tokens,
            "thinking_config": google_genai_types.ThinkingConfig(thinking_level="MINIMAL"),
        }

        response = self.google_genai_client.models.generate_content(
            model=normalized_model_name,
            contents=prompt,
            config=google_genai_types.GenerateContentConfig(**gen_config_kwargs)
        )

        text = getattr(response, "text", None)
        return text.strip() if isinstance(text, str) else ""


# シングルトンインスタンス
gemini_service = GeminiService()
