"""
PDF処理サービス
Google Cloud Vision APIまたはGLM-OCR（Ollama）を使用してPDFからテキストを抽出
"""

import asyncio
import base64
import logging
import time
import re
from pathlib import Path
from typing import Optional, Tuple
import io
import tempfile
import os

import requests

from ..config import config
from ..utils.logger import get_logger

logger = get_logger(__name__)

# Vision API関連のインポート（vision_api使用時のみ）
try:
    from google.cloud import vision
    from google.cloud import storage
    from google.api_core import retry
    VISION_API_AVAILABLE = True
except ImportError:
    VISION_API_AVAILABLE = False
    logger.warning("Google Cloud Vision APIがインストールされていません")

# PyMuPDF（GLM-OCR用のPDF→画像変換に使用）
try:
    import fitz  # PyMuPDF
    from PIL import Image
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False
    logger.warning("PyMuPDFがインストールされていません（GLM-OCRには必要）")


class PDFProcessor:
    """PDF処理クラス"""

    def __init__(self):
        self.ocr_engine = config.ocr.engine
        logger.info(f"OCRエンジン: {self.ocr_engine}")

        # Vision API用のクライアント初期化
        if self.ocr_engine == "vision_api":
            if not VISION_API_AVAILABLE:
                raise RuntimeError("Vision APIを使用するにはgoogle-cloud-visionのインストールが必要です")
            self.vision_client = vision.ImageAnnotatorClient()
            self.storage_client = storage.Client()
            self.bucket_name = self._get_or_create_bucket()

        # GLM-OCR用の設定
        elif self.ocr_engine == "glm_ocr":
            if not PYMUPDF_AVAILABLE:
                raise RuntimeError("GLM-OCRを使用するにはPyMuPDFとPillowのインストールが必要です: pip install PyMuPDF Pillow")
            self.ollama_host = config.ocr.ollama_host
            self.ollama_model = config.ocr.ollama_model
            self.ocr_timeout = config.ocr.timeout
            # Ollamaの接続確認
            self._check_ollama_connection()

        else:
            raise ValueError(f"未知のOCRエンジン: {self.ocr_engine}")

    def _check_ollama_connection(self):
        """Ollamaサーバーへの接続確認"""
        try:
            response = requests.get(f"{self.ollama_host}/api/tags", timeout=5)
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                if not any(self.ollama_model in name for name in model_names):
                    logger.warning(f"Ollamaに{self.ollama_model}モデルがありません。`ollama pull {self.ollama_model}`を実行してください")
                else:
                    logger.info(f"Ollama接続確認OK: {self.ollama_model}")
            else:
                logger.warning(f"Ollamaサーバーに接続できません: {response.status_code}")
        except requests.exceptions.ConnectionError:
            logger.warning(f"Ollamaサーバーに接続できません: {self.ollama_host}")

    def _get_or_create_bucket(self) -> str:
        """GCSバケットを取得または作成"""
        bucket_name = f"paper-manager-temp-{int(time.time())}"
        try:
            bucket = self.storage_client.bucket(bucket_name)
            if not bucket.exists():
                bucket = self.storage_client.create_bucket(bucket_name, location="us-central1")
                logger.info(f"一時バケットを作成しました: {bucket_name}")
            return bucket_name
        except Exception as e:
            logger.error(f"バケット作成エラー: {e}")
            raise

    async def extract_text_from_pdf(self, pdf_path: str) -> str:
        """PDFからテキストを抽出"""
        try:
            logger.info(f"PDF処理開始: {pdf_path}")

            # PDFファイルの検証
            if not self._validate_pdf_file(pdf_path):
                raise ValueError(f"無効なPDFファイル: {pdf_path}")

            # OCRエンジンに応じて処理を分岐
            if self.ocr_engine == "vision_api":
                logger.info("Vision APIでOCR処理を実行")
                return await self._extract_text_with_vision_api(pdf_path)
            elif self.ocr_engine == "glm_ocr":
                logger.info("GLM-OCR（Ollama）でOCR処理を実行")
                return await self._extract_text_with_glm_ocr(pdf_path)
            else:
                raise ValueError(f"未知のOCRエンジン: {self.ocr_engine}")

        except Exception as e:
            logger.error(f"PDF処理エラー: {e}")
            raise
    
    def _validate_pdf_file(self, pdf_path: str) -> bool:
        """PDFファイルの検証"""
        path = Path(pdf_path)
        
        if not path.exists():
            logger.error(f"ファイルが存在しません: {pdf_path}")
            return False
        
        if path.stat().st_size == 0:
            logger.error(f"空のファイルです: {pdf_path}")
            return False
        
        if path.stat().st_size > config.file_processing.max_pdf_size * 1024 * 1024:
            logger.error(f"ファイルサイズが上限を超えています: {pdf_path}")
            return False
        
        # PDFヘッダーの確認
        try:
            with open(pdf_path, 'rb') as f:
                header = f.read(8)
                if not header.startswith(b'%PDF-'):
                    logger.error(f"PDFヘッダーが不正です: {pdf_path}")
                    return False
        except Exception as e:
            logger.error(f"ファイル読み込みエラー: {e}")
            return False
        
        return True
    
    def _extract_text_simple(self, pdf_path: str) -> str:
        """PyMuPDF機能は無効化済み - Vision APIを使用"""
        logger.info("PyMuPDF機能は無効化されています。Vision APIを使用します。")
        return ""
    
    async def _extract_text_with_vision_api(self, pdf_path: str) -> str:
        """Vision APIを使用したOCRテキスト抽出"""
        try:
            # PDFをGCSにアップロード
            gcs_uri = await self._upload_to_gcs(pdf_path)
            logger.info(f"GCSアップロード完了: {gcs_uri}")
            
            # Vision APIで処理
            text = await self._process_with_vision_api(gcs_uri)
            
            # 一時ファイルを削除
            await self._cleanup_gcs_file(gcs_uri)
            
            return text
            
        except Exception as e:
            logger.error(f"Vision API処理エラー: {e}")
            raise
    
    async def _upload_to_gcs(self, pdf_path: str) -> str:
        """PDFファイルをGCSにアップロード"""
        try:
            bucket = self.storage_client.bucket(self.bucket_name)
            file_name = f"temp_pdf_{int(time.time())}_{Path(pdf_path).name}"
            blob = bucket.blob(file_name)
            
            # ファイルをアップロード
            blob.upload_from_filename(pdf_path)
            
            gcs_uri = f"gs://{self.bucket_name}/{file_name}"
            logger.info(f"GCSアップロード成功: {gcs_uri}")
            return gcs_uri
            
        except Exception as e:
            logger.error(f"GCSアップロードエラー: {e}")
            raise
    
    async def _process_with_vision_api(self, gcs_uri: str) -> str:
        """Vision APIでPDFを処理"""
        try:
            # ファイルサイズによって処理方式を選択
            file_size = await self._get_file_size_from_gcs(gcs_uri)
            logger.info(f"PDFファイルサイズ: {file_size / (1024*1024):.1f}MB")
            
            # 5MB未満の場合は同期処理を試行、それ以外は非同期処理
            if file_size < 5 * 1024 * 1024:  # 5MB未満
                logger.info("小さなファイルのため同期処理を試行")
                try:
                    text = await self._process_with_vision_api_simple_with_timeout(gcs_uri, timeout=120)
                    if text and len(text.strip()) > 100:
                        logger.info(f"同期処理成功: {len(text)}文字のテキストを抽出")
                        return text
                    else:
                        logger.warning("同期処理で十分なテキストが取得できませんでした。非同期処理にフォールバック")
                except asyncio.TimeoutError:
                    logger.warning("同期処理がタイムアウトしました。非同期処理にフォールバック")
                except Exception as sync_error:
                    logger.warning(f"同期処理失敗: {sync_error}. 非同期処理にフォールバック")
            else:
                logger.info("大きなファイルのため非同期処理を使用")
            
            # 非同期処理を実行（タイムアウト付き）
            logger.info("非同期処理を開始します...")
            try:
                text = await asyncio.wait_for(
                    self._process_with_vision_api_async(gcs_uri),
                    timeout=900  # 15分のタイムアウト
                )
                logger.info(f"非同期処理成功: {len(text)}文字のテキストを抽出")
                return text
            except asyncio.TimeoutError:
                logger.error("Vision API非同期処理が15分でタイムアウトしました")
                raise Exception("Vision API処理がタイムアウトしました（15分）")
            
        except Exception as e:
            logger.error(f"Vision API処理エラー: {e}")
            raise
    
    async def _process_with_vision_api_simple(self, gcs_uri: str) -> str:
        """Vision APIでPDFを処理（同期版）"""
        try:
            # PDFファイル用の同期処理設定
            feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
            gcs_source = vision.GcsSource(uri=gcs_uri)
            input_config = vision.InputConfig(gcs_source=gcs_source, mime_type='application/pdf')
            
            # AnnotateFileRequestを作成（PDFファイル用）
            request = vision.AnnotateFileRequest(
                features=[feature],
                input_config=input_config
            )
            
            logger.info("Vision API同期処理を開始")
            # batch_annotate_filesを使用してPDFを処理
            response = self.vision_client.batch_annotate_files(requests=[request])
            
            # レスポンスからテキストを抽出
            text_parts = []
            
            # batch_annotate_filesのレスポンス構造を正しく処理
            if hasattr(response, 'responses') and response.responses:
                for file_response in response.responses:
                    # AnnotateFileResponseの構造
                    if hasattr(file_response, 'responses') and file_response.responses:
                        # 各ページのレスポンスを処理
                        for page_response in file_response.responses:
                            if hasattr(page_response, 'full_text_annotation') and page_response.full_text_annotation:
                                if hasattr(page_response.full_text_annotation, 'text'):
                                    text_parts.append(page_response.full_text_annotation.text)
            
            full_text = '\n'.join(text_parts)
            logger.info(f"Vision API同期処理で抽出されたテキスト: {len(full_text)}文字")
            
            return full_text
            
        except Exception as e:
            logger.warning(f"Vision API同期処理エラー: {e}")
            raise
    
    async def _get_vision_api_result(self, output_uri: str) -> str:
        """Vision APIの結果を取得"""
        try:
            bucket_name = output_uri.split('/')[2]
            prefix = '/'.join(output_uri.split('/')[3:])
            
            bucket = self.storage_client.bucket(bucket_name)
            blobs = bucket.list_blobs(prefix=prefix)
            
            text_parts = []
            for blob in blobs:
                if blob.name.endswith('.json'):
                    json_content = blob.download_as_text()
                    import json
                    data = json.loads(json_content)
                    
                    for response in data.get('responses', []):
                        if 'fullTextAnnotation' in response:
                            text_parts.append(response['fullTextAnnotation']['text'])
            
            return '\n'.join(text_parts)
            
        except Exception as e:
            logger.error(f"Vision API結果取得エラー: {e}")
            raise
    
    async def _get_vision_api_result_with_retry(self, output_uri: str, max_retries: int = 5) -> str:
        """Vision APIの結果を取得（リトライ機能付き）"""
        import asyncio
        
        for attempt in range(max_retries):
            try:
                # 最初の試行では少し待機
                if attempt > 0:
                    wait_time = min(2 ** attempt, 30)  # 指数バックオフ（最大30秒）
                    logger.info(f"Vision API結果取得リトライ {attempt + 1}/{max_retries}（{wait_time}秒後）")
                    await asyncio.sleep(wait_time)
                
                bucket_name = output_uri.split('/')[2]
                prefix = '/'.join(output_uri.split('/')[3:])
                
                bucket = self.storage_client.bucket(bucket_name)
                blobs = list(bucket.list_blobs(prefix=prefix))
                
                if not blobs:
                    logger.warning(f"Vision API結果ファイルが見つかりません（試行 {attempt + 1}）")
                    continue
                
                text_parts = []
                for blob in blobs:
                    if blob.name.endswith('.json'):
                        try:
                            json_content = blob.download_as_text()
                            import json
                            data = json.loads(json_content)
                            
                            for response in data.get('responses', []):
                                if 'fullTextAnnotation' in response:
                                    text_parts.append(response['fullTextAnnotation']['text'])
                        except Exception as blob_error:
                            logger.warning(f"ファイル読み込みエラー {blob.name}: {blob_error}")
                            continue
                
                if text_parts:
                    result_text = '\n'.join(text_parts)
                    logger.info(f"Vision API結果取得成功（試行 {attempt + 1}）: {len(result_text)}文字")
                    return result_text
                else:
                    logger.warning(f"テキストが抽出できませんでした（試行 {attempt + 1}）")
                
            except Exception as e:
                logger.warning(f"Vision API結果取得エラー（試行 {attempt + 1}）: {e}")
                if attempt == max_retries - 1:
                    raise
        
        raise Exception("Vision API結果取得に失敗しました（最大リトライ回数に到達）")
    
    async def _get_file_size_from_gcs(self, gcs_uri: str) -> int:
        """GCSファイルのサイズを取得"""
        try:
            bucket_name = gcs_uri.split('/')[2]
            file_name = '/'.join(gcs_uri.split('/')[3:])
            
            bucket = self.storage_client.bucket(bucket_name)
            blob = bucket.blob(file_name)
            
            blob.reload()
            return blob.size or 0
            
        except Exception as e:
            logger.warning(f"GCSファイルサイズ取得エラー: {e}")
            return 0
    
    async def _process_with_vision_api_simple_with_timeout(self, gcs_uri: str, timeout: int = 60) -> str:
        """Vision APIを使用したOCRテキスト抽出（タイムアウト付き）"""
        try:
            # asyncio.wait_forを使用してタイムアウトを実装
            return await asyncio.wait_for(
                self._process_with_vision_api_simple(gcs_uri),
                timeout=timeout
            )
        except asyncio.TimeoutError:
            logger.warning(f"Vision API同期処理がタイムアウトしました（{timeout}秒）")
            raise
        except Exception as e:
            logger.error(f"Vision APIタイムアウト処理エラー: {e}")
            raise
    
    async def _process_with_vision_api_async(self, gcs_uri: str) -> str:
        """Vision APIを使用した非同期OCRテキスト抽出"""
        try:
            # 非同期バッチ処理の設定
            bucket_name = gcs_uri.split('/')[2]
            file_name = '/'.join(gcs_uri.split('/')[3:])
            output_uri = f"gs://{bucket_name}/{file_name}_output/"
            
            # 非同期処理用の設定
            feature = vision.Feature(type_=vision.Feature.Type.DOCUMENT_TEXT_DETECTION)
            gcs_source = vision.GcsSource(uri=gcs_uri)
            input_config = vision.InputConfig(gcs_source=gcs_source, mime_type='application/pdf')
            
            gcs_destination = vision.GcsDestination(uri=output_uri)
            output_config = vision.OutputConfig(gcs_destination=gcs_destination, batch_size=1)
            
            # 非同期リクエスト作成
            async_request = vision.AsyncAnnotateFileRequest(
                features=[feature],
                input_config=input_config,
                output_config=output_config
            )
            
            logger.info("Vision API非同期処理を開始")
            operation = self.vision_client.async_batch_annotate_files(
                requests=[async_request]
            )
            
            # 処理完了を待機（最大10分）
            logger.info("Vision API非同期処理の完了を待機中...")
            
            # ポーリングで結果を確認
            max_wait_time = 600  # 10分
            poll_interval = 10   # 10秒間隔
            
            for elapsed in range(0, max_wait_time, poll_interval):
                await asyncio.sleep(poll_interval)
                
                if operation.done():
                    logger.info(f"Vision API非同期処理完了（{elapsed + poll_interval}秒経過）")
                    break
                    
                if elapsed % 60 == 0:  # 1分ごとにログ出力
                    logger.info(f"Vision API処理継続中（{elapsed + poll_interval}秒経過）...")
            else:
                # タイムアウト
                logger.error("Vision API非同期処理がタイムアウトしました")
                raise asyncio.TimeoutError("Vision API async processing timeout")
            
            # 結果を取得
            text = await self._get_vision_api_result_with_retry(output_uri)
            
            # 出力ファイルをクリーンアップ
            try:
                bucket = self.storage_client.bucket(bucket_name)
                blobs = bucket.list_blobs(prefix=f"{file_name}_output/")
                for blob in blobs:
                    blob.delete()
            except Exception as cleanup_error:
                logger.warning(f"出力ファイルクリーンアップエラー: {cleanup_error}")
            
            return text
            
        except Exception as e:
            logger.error(f"Vision API非同期処理エラー: {e}")
            raise

    async def _cleanup_gcs_file(self, gcs_uri: str):
        """GCSの一時ファイルを削除"""
        try:
            bucket_name = gcs_uri.split('/')[2]
            file_name = '/'.join(gcs_uri.split('/')[3:])
            
            bucket = self.storage_client.bucket(bucket_name)
            blob = bucket.blob(file_name)
            
            if blob.exists():
                blob.delete()
                logger.info(f"一時ファイル削除: {gcs_uri}")
            
            # 出力ディレクトリも削除
            output_prefix = f"{file_name}_output/"
            blobs = bucket.list_blobs(prefix=output_prefix)
            for blob in blobs:
                blob.delete()
                
        except Exception as e:
            logger.warning(f"一時ファイル削除エラー: {e}")

    # =========================================================================
    # GLM-OCR（Ollama）処理
    # =========================================================================

    async def _extract_text_with_glm_ocr(self, pdf_path: str) -> str:
        """GLM-OCR（Ollama）を使用したOCRテキスト抽出"""
        try:
            # PDFを画像に変換
            images = self._pdf_to_images(pdf_path)
            logger.info(f"PDFを{len(images)}ページの画像に変換しました")

            # 各ページをOCR処理
            all_text = []
            for page_num, img in enumerate(images):
                logger.info(f"ページ {page_num + 1}/{len(images)} をOCR処理中...")
                text = await self._ocr_image_with_glm(img, page_num)
                if text:
                    all_text.append(text)

            full_text = "\n\n".join(all_text)
            logger.info(f"GLM-OCR完了: {len(full_text)}文字を抽出")
            return full_text

        except Exception as e:
            logger.error(f"GLM-OCR処理エラー: {e}")
            raise

    def _pdf_to_images(self, pdf_path: str) -> list:
        """PDFをPIL Imageのリストに変換"""
        if not PYMUPDF_AVAILABLE:
            raise RuntimeError("PyMuPDFがインストールされていません")

        images = []
        doc = fitz.open(pdf_path)

        for page_num in range(len(doc)):
            page = doc[page_num]
            # 高解像度で変換（300 DPI相当）
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            images.append(img)

        doc.close()
        return images

    def _image_to_base64(self, img) -> str:
        """PIL ImageをBase64エンコード"""
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("utf-8")

    async def _ocr_image_with_glm(self, img, page_num: int) -> str:
        """GLM-OCRで1ページをOCR処理"""
        try:
            img_base64 = self._image_to_base64(img)

            payload = {
                "model": self.ollama_model,
                "prompt": "Text Recognition:",
                "images": [img_base64],
                "stream": False
            }

            # 同期リクエストを非同期で実行
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: requests.post(
                    f"{self.ollama_host}/api/generate",
                    json=payload,
                    timeout=self.ocr_timeout
                )
            )

            if response.status_code == 200:
                result = response.json()
                text = result.get("response", "")
                logger.debug(f"ページ {page_num + 1}: {len(text)}文字を抽出")
                return text
            else:
                logger.error(f"GLM-OCRエラー（ページ {page_num + 1}）: {response.status_code} - {response.text}")
                return ""

        except requests.exceptions.Timeout:
            logger.error(f"GLM-OCRタイムアウト（ページ {page_num + 1}）: {self.ocr_timeout}秒")
            return ""
        except Exception as e:
            logger.error(f"GLM-OCRエラー（ページ {page_num + 1}）: {e}")
            return ""

    # =========================================================================
    # ユーティリティ
    # =========================================================================

    def extract_doi_from_text(self, text: str) -> Optional[str]:
        """PDFテキストからDOIを抽出（正規表現）

        Args:
            text: PDFから抽出されたテキスト

        Returns:
            DOI文字列、見つからない場合はNone
        """
        if not text:
            return None

        # DOI抽出パターン（優先度順）
        patterns = [
            # doi: 10.xxxx/xxxxx 形式
            r'doi:\s*(10\.\d+/[^\s\]]+)',
            # DOI: 10.xxxx/xxxxx 形式（大文字）
            r'DOI:\s*(10\.\d+/[^\s\]]+)',
            # https://doi.org/10.xxxx/xxxxx 形式
            r'https?://doi\.org/(10\.\d+/[^\s\]]+)',
            # dx.doi.org/10.xxxx/xxxxx 形式
            r'https?://dx\.doi\.org/(10\.\d+/[^\s\]]+)',
            # 裸のDOI（10.xxxx/xxxxx）
            r'\b(10\.\d{4,}/[^\s\]]+)\b',
        ]

        # テキストの最初の3000文字のみを検索（DOIは通常最初のページにある）
        search_text = text[:3000]

        for pattern in patterns:
            match = re.search(pattern, search_text, re.IGNORECASE)
            if match:
                doi = match.group(1)
                # 末尾の句読点を除去
                doi = doi.rstrip('.,;:')
                logger.info(f"DOI抽出成功: {doi}")
                return doi

        logger.debug("DOIが見つかりませんでした")
        return None


# シングルトンインスタンス
pdf_processor = PDFProcessor()