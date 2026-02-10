"""
メインアプリケーション
論文管理の自動化システム
"""

import asyncio
import signal
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict
from concurrent.futures import ThreadPoolExecutor

from .config import config
from .models.paper import PaperMetadata, ProcessingResult
from .services.pdf_processor import pdf_processor
from .services.gemini_service import gemini_service
from .services.pubmed_service import pubmed_service
from .services.notion_service import notion_service
from .services.slack_service import slack_service
from .services.obsidian_service import obsidian_service
from .services.chromadb_service import chromadb_service
from .services.openalex_service import openalex_service
from .services.file_watcher import FileWatcher
from .utils.logger import get_logger

logger = get_logger(__name__)


class PaperManager:
    """論文管理システムメインクラス"""

    def __init__(self):
        self.file_watcher: Optional[FileWatcher] = None
        self.processing_queue = asyncio.Queue(maxsize=config.file_processing.max_concurrent_files * 2)
        self.is_running = False
        self.executor = ThreadPoolExecutor(max_workers=config.file_processing.max_concurrent_files)
        # スレッドセーフなセマフォで同時処理数を厳密に制限（Gemini APIレート制限対策）
        # threading.Semaphore は複数のイベントループからアクセス可能
        self.processing_semaphore = threading.Semaphore(1)
        
    async def start(self):
        """システム開始"""
        try:
            logger.info("論文管理システムを開始します...")
            logger.info("スレッドセーフな処理セマフォを使用（同時処理数: 1）")

            # 接続テスト
            await self._check_connections()

            # ファイル監視の開始
            self.file_watcher = FileWatcher(
                watch_folder=config.watch_folder,
                callback=self._on_new_file
            )
            self.file_watcher.start()

            # 処理タスクの開始
            self.is_running = True

            # 処理タスクを開始
            tasks = [
                asyncio.create_task(self._periodic_tasks()),
            ]

            # ファイル処理ワーカーを起動
            worker_count = config.file_processing.max_concurrent_files
            for i in range(worker_count):
                tasks.append(asyncio.create_task(self._file_processor_worker(worker_id=i)))

            if worker_count == 1:
                logger.info("システムが正常に開始されました（順次処理モード - スレッドセーフセマフォ制御）")
            else:
                logger.info(f"システムが正常に開始されました（並行処理: {worker_count}ファイル同時 - スレッドセーフセマフォ制御）")
            
            # シグナルハンドラーを設定
            loop = asyncio.get_event_loop()
            for sig in [signal.SIGTERM, signal.SIGINT]:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
            
            # すべてのタスクが完了するまで待機
            await asyncio.gather(*tasks, return_exceptions=True)
            
        except Exception as e:
            logger.error(f"システム開始エラー: {e}")
            await self.stop()
            raise
    
    async def stop(self):
        """システム停止"""
        try:
            logger.info("システムを停止します...")
            
            self.is_running = False
            
            # ファイル監視停止
            if self.file_watcher:
                self.file_watcher.stop()
            
            # エグゼキューターの停止
            self.executor.shutdown(wait=True)
            
            logger.info("システムが正常に停止されました")
            
        except Exception as e:
            logger.error(f"システム停止エラー: {e}")
    
    async def _check_connections(self):
        """外部サービス接続チェック"""
        logger.info("外部サービス接続をチェック中...")
        
        # Notion接続チェック
        if not await notion_service.check_database_connection():
            raise ConnectionError("Notionデータベースに接続できません")
        
        # Slack接続チェック（有効な場合のみ）
        if slack_service.enabled:
            if not await slack_service.test_connection():
                logger.warning("Slack接続に問題がありますが、処理を続行します")
        
        logger.info("すべての外部サービスに正常に接続しました")
    
    def _on_new_file(self, file_path: str):
        """新しいファイル検出時のコールバック"""
        try:
            # キューに追加（ノンブロッキング）
            try:
                self.processing_queue.put_nowait(file_path)
                logger.info(f"処理キューに追加: {Path(file_path).name}")
            except asyncio.QueueFull:
                logger.warning(f"処理キューが満杯です。ファイルをスキップ: {Path(file_path).name}")
                
        except Exception as e:
            logger.error(f"ファイル追加エラー: {e}")
    
    async def _file_processor_worker(self, worker_id: int = 0):
        """ファイル処理ワーカー"""
        logger.info(f"ファイル処理ワーカー {worker_id} を開始")

        while self.is_running:
            try:
                # キューからファイルを取得（タイムアウト付き）
                try:
                    file_path = await asyncio.wait_for(
                        self.processing_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                # スレッドセーフなセマフォを使用して厳密に順次処理を保証
                with self.processing_semaphore:
                    logger.info(f"[Worker {worker_id}] セマフォ取得 - 処理開始: {Path(file_path).name}")

                    # ファイル処理実行
                    await self._process_file(file_path, worker_id)

                    logger.info(f"[Worker {worker_id}] セマフォ解放 - 処理完了: {Path(file_path).name}")

                # 処理間隔
                await asyncio.sleep(config.file_processing.processing_interval)

            except Exception as e:
                logger.error(f"ワーカー {worker_id} エラー: {e}")
                await asyncio.sleep(1)

        logger.info(f"ファイル処理ワーカー {worker_id} を停止")
    
    async def _process_file(self, file_path: str, worker_id: int = 0) -> ProcessingResult:
        """単一ファイルの処理"""
        start_time = time.time()
        file_name = Path(file_path).name
        
        logger.info(f"[Worker {worker_id}] ファイル処理開始: {file_name}")
        
        try:
            # ファイル情報の取得
            file_stat = Path(file_path).stat()

            # 1. PDFからテキスト抽出
            logger.info(f"[Worker {worker_id}] PDF処理中: {file_name}")
            pdf_text = await pdf_processor.extract_text_from_pdf(file_path)

            if not pdf_text or len(pdf_text.strip()) < 100:
                raise ValueError("PDFから十分なテキストを抽出できませんでした")

            # 2. DOI抽出（正規表現、APIなし）
            logger.info(f"[Worker {worker_id}] DOI抽出中: {file_name}")
            extracted_doi = pdf_processor.extract_doi_from_text(pdf_text)

            # 3. DOIで早期重複チェック
            if extracted_doi:
                logger.info(f"[Worker {worker_id}] DOI早期重複チェック: {extracted_doi}")
                existing_page_id = await notion_service.search_existing_paper(
                    None,  # タイトルなし
                    extracted_doi
                )

                if existing_page_id:
                    logger.warning(f"[Worker {worker_id}] DOIで重複検出（早期）: {file_name}")

                    # Slack重複通知
                    if slack_service.enabled:
                        # 最小限のメタデータで通知
                        from app.models.paper import PaperMetadata
                        minimal_metadata = PaperMetadata(
                            title=file_name,
                            authors=[],
                            doi=extracted_doi,
                            summary_japanese="",
                            keywords=[],
                            file_path=file_path,
                            file_name=file_name,
                            file_size=file_stat.st_size
                        )
                        await slack_service.send_duplicate_notification(minimal_metadata, existing_page_id)

                    # Obsidianエクスポート（重複の場合も実行）
                    if obsidian_service.enabled:
                        logger.info(f"[Worker {worker_id}] Obsidianエクスポート（早期重複）: {file_name}")
                        try:
                            from app.models.paper import PaperMetadata
                            minimal_metadata = PaperMetadata(
                                title=file_name,
                                authors=[],
                                doi=extracted_doi,
                                summary_japanese="",
                                keywords=[],
                                file_path=file_path,
                                file_name=file_name,
                                file_size=file_stat.st_size
                            )
                            await obsidian_service.export_paper(minimal_metadata, file_path, existing_page_id)
                            logger.info(f"[Worker {worker_id}] Obsidianエクスポート完了（早期重複）: {file_name}")
                        except Exception as obs_error:
                            logger.error(f"[Worker {worker_id}] Obsidianエクスポートエラー（早期重複）: {obs_error}")

                    # 処理済みとしてマーク
                    if self.file_watcher:
                        self.file_watcher.mark_file_processed(file_path, True, existing_page_id)

                    return ProcessingResult(
                        success=True,
                        paper_metadata=None,
                        notion_page_id=existing_page_id,
                        processing_time=time.time() - start_time
                    )

            # 4. Geminiでメタデータ抽出のみ（要約なし）
            logger.info(f"[Worker {worker_id}] メタデータ抽出中: {file_name}")
            try:
                paper_metadata = await gemini_service.extract_metadata_only(pdf_text, file_name)
            except ValueError as e:
                # メタデータ検証失敗（必須フィールド欠損）
                logger.error(f"[Worker {worker_id}] メタデータ抽出失敗: {e}")
                raise Exception(f"メタデータ抽出失敗: {str(e)}")

            # ファイル情報を設定
            paper_metadata.file_path = file_path
            paper_metadata.file_size = file_stat.st_size

            # 5. PubMed検索
            logger.info(f"[Worker {worker_id}] PubMed検索中: {file_name}")
            pmid = await pubmed_service.search_pmid(paper_metadata)
            pubmed_found = False

            if pmid:
                paper_metadata.pmid = pmid
                paper_metadata.pubmed_url = pubmed_service.create_pubmed_url(pmid)

                # PMIDが取得できた場合、PubMedから正確なメタデータを取得
                logger.info(f"[Worker {worker_id}] PubMedメタデータ取得中: {file_name}")
                pubmed_metadata = await pubmed_service.fetch_metadata_from_pubmed(pmid)

                if pubmed_metadata:
                    # PubMedメタデータでGeminiの結果を更新（より信頼性が高い）
                    paper_metadata = await self._merge_metadata(paper_metadata, pubmed_metadata)
                    logger.info(f"[Worker {worker_id}] PubMedメタデータで更新完了: {file_name}")
                    pubmed_found = True
                else:
                    logger.warning(f"[Worker {worker_id}] PubMedメタデータ取得に失敗: {file_name}")

            # 5.5. OpenAlexメタデータ取得（PubMed未収録の場合は補完、収録済みの場合は被引用数のみ）
            logger.info(f"[Worker {worker_id}] OpenAlexメタデータ取得中: {file_name}")
            try:
                openalex_metadata = await asyncio.to_thread(
                    openalex_service.get_paper_metadata,
                    doi=paper_metadata.doi,
                    title=paper_metadata.title
                )

                if openalex_metadata:
                    # 被引用数は常に更新
                    if openalex_metadata.get('cited_by_count') is not None:
                        paper_metadata.cited_by_count = openalex_metadata['cited_by_count']
                        paper_metadata.openalex_id = openalex_metadata.get('openalex_id')
                        logger.info(f"[Worker {worker_id}] OpenAlex被引用数取得成功: {paper_metadata.cited_by_count}件")

                    # PubMed未収録の場合、OpenAlexメタデータで補完
                    if not pubmed_found:
                        logger.info(f"[Worker {worker_id}] PubMed未収録のため、OpenAlexメタデータで補完します")
                        paper_metadata = await self._merge_metadata_from_openalex(paper_metadata, openalex_metadata)
                        logger.info(f"[Worker {worker_id}] OpenAlexメタデータで更新完了: {file_name}")
                else:
                    logger.warning(f"[Worker {worker_id}] OpenAlexメタデータ取得に失敗: {file_name}")
            except Exception as openalex_error:
                logger.warning(f"[Worker {worker_id}] OpenAlexエラー（処理は続行）: {openalex_error}")
                # OpenAlexエラーは処理全体を失敗にはしない

            # 6. 重複チェック（確認）
            logger.info(f"[Worker {worker_id}] 重複チェック（確認）: {file_name}")
            existing_page_id = await notion_service.search_existing_paper(
                paper_metadata.title,
                paper_metadata.doi
            )

            if existing_page_id:
                logger.warning(f"[Worker {worker_id}] 重複検出（確認）: {file_name}")

                # Slack重複通知
                if slack_service.enabled:
                    await slack_service.send_duplicate_notification(paper_metadata, existing_page_id)

                # Obsidianエクスポート（重複の場合も実行）
                if obsidian_service.enabled:
                    logger.info(f"[Worker {worker_id}] Obsidianエクスポート（重複）: {file_name}")
                    try:
                        await obsidian_service.export_paper(paper_metadata, file_path, existing_page_id)
                        logger.info(f"[Worker {worker_id}] Obsidianエクスポート完了（重複）: {file_name}")
                    except Exception as obs_error:
                        logger.error(f"[Worker {worker_id}] Obsidianエクスポートエラー（重複）: {obs_error}")

                # 処理済みとしてマーク
                if self.file_watcher:
                    self.file_watcher.mark_file_processed(file_path, True, existing_page_id)

                return ProcessingResult(
                    success=True,
                    paper_metadata=paper_metadata,
                    notion_page_id=existing_page_id,
                    processing_time=time.time() - start_time
                )

            # 7. 日本語要約作成（重複なしの場合のみ）
            logger.info(f"[Worker {worker_id}] 日本語要約作成中: {file_name}")
            paper_metadata = await gemini_service.add_summary_to_metadata(paper_metadata, pdf_text)

            # 8. Notionに投稿（PDF付き）
            logger.info(f"[Worker {worker_id}] Notion投稿中 (PDF付き): {file_name}")
            notion_page_id = await notion_service.create_paper_page_with_pdf(paper_metadata)
            
            if not notion_page_id:
                raise Exception("Notion投稿に失敗しました")
            
            # 成功として処理済みマーク
            if self.file_watcher:
                self.file_watcher.mark_file_processed(file_path, True, notion_page_id)

            processing_time = time.time() - start_time
            logger.info(f"[Worker {worker_id}] 処理完了: {file_name} ({processing_time:.1f}秒)")

            # Inbox記録追加
            if config.inbox.enabled:
                await self._append_to_inbox(paper_metadata.title, notion_page_id)

            # Obsidianエクスポート
            if obsidian_service.enabled:
                logger.info(f"[Worker {worker_id}] Obsidianエクスポート中: {file_name}")
                try:
                    await obsidian_service.export_paper(paper_metadata, file_path, notion_page_id)
                    logger.info(f"[Worker {worker_id}] Obsidianエクスポート完了: {file_name}")
                except Exception as obs_error:
                    logger.error(f"[Worker {worker_id}] Obsidianエクスポートエラー: {obs_error}")
                    # Obsidianエラーは処理全体を失敗にはしない

            # ChromaDBにベクトル登録
            logger.info(f"[Worker {worker_id}] ChromaDBにベクトル登録中: {file_name}")
            try:
                notion_url = f"https://www.notion.so/{notion_page_id.replace('-', '')}"
                obsidian_path = None
                if obsidian_service.enabled:
                    # Obsidianファイルパスを取得
                    obsidian_file = obsidian_service.find_file_by_notion_id(notion_page_id)
                    if obsidian_file:
                        obsidian_path = str(obsidian_file)

                await chromadb_service.add_paper(
                    paper_metadata,
                    notion_page_id,
                    notion_url,
                    obsidian_path
                )
                logger.info(f"[Worker {worker_id}] ChromaDBベクトル登録完了: {file_name}")
            except Exception as chroma_error:
                logger.error(f"[Worker {worker_id}] ChromaDBベクトル登録エラー: {chroma_error}")
                # ChromaDBエラーは処理全体を失敗にはしない

            # Slack成功通知
            if slack_service.enabled:
                await slack_service.send_success_notification(paper_metadata, notion_page_id, processing_time)
            
            return ProcessingResult(
                success=True,
                paper_metadata=paper_metadata,
                notion_page_id=notion_page_id,
                processing_time=processing_time
            )
            
        except Exception as e:
            error_msg = f"ファイル処理エラー: {e}"
            logger.error(f"[Worker {worker_id}] {error_msg}")
            
            processing_time = time.time() - start_time
            
            # Slack失敗通知
            if slack_service.enabled:
                await slack_service.send_failure_notification(file_name, error_msg, processing_time)
            
            # 失敗として処理済みマーク
            if self.file_watcher:
                self.file_watcher.mark_file_processed(file_path, False)
            
            return ProcessingResult(
                success=False,
                error_message=error_msg,
                processing_time=processing_time
            )
    
    async def _merge_metadata(self, gemini_metadata: PaperMetadata, pubmed_metadata: Dict) -> PaperMetadata:
        """GeminiとPubMedのメタデータをマージ（PubMedを優先）"""
        try:
            # PubMedメタデータを優先して更新
            if pubmed_metadata.get("title"):
                gemini_metadata.title = pubmed_metadata["title"]

            if pubmed_metadata.get("authors"):
                gemini_metadata.authors = pubmed_metadata["authors"]

            if pubmed_metadata.get("journal"):
                gemini_metadata.journal = pubmed_metadata["journal"]

            if pubmed_metadata.get("publication_year"):
                gemini_metadata.publication_year = pubmed_metadata["publication_year"]

            if pubmed_metadata.get("doi"):
                gemini_metadata.doi = pubmed_metadata["doi"]

            if pubmed_metadata.get("keywords"):
                gemini_metadata.keywords = pubmed_metadata["keywords"]

            # PubMedの抄録がある場合は追加情報として保存
            if pubmed_metadata.get("abstract"):
                # 抄録をadditional_infoに追加
                if not gemini_metadata.additional_info:
                    gemini_metadata.additional_info = {}
                gemini_metadata.additional_info["pubmed_abstract"] = pubmed_metadata["abstract"]

            logger.info(f"メタデータマージ完了: PubMed優先で更新")
            return gemini_metadata

        except Exception as e:
            logger.error(f"メタデータマージエラー: {e}")
            return gemini_metadata

    async def _merge_metadata_from_openalex(self, gemini_metadata: PaperMetadata, openalex_metadata: Dict) -> PaperMetadata:
        """GeminiとOpenAlexのメタデータをマージ（OpenAlexで補完）"""
        try:
            # OpenAlexメタデータで補完（Geminiにない情報を追加、またはより正確なものに更新）
            updated_fields = []

            if openalex_metadata.get("title"):
                gemini_metadata.title = openalex_metadata["title"]
                updated_fields.append("title")

            if openalex_metadata.get("authors"):
                gemini_metadata.authors = openalex_metadata["authors"]
                updated_fields.append("authors")

            if openalex_metadata.get("journal"):
                gemini_metadata.journal = openalex_metadata["journal"]
                updated_fields.append("journal")

            if openalex_metadata.get("publication_year"):
                gemini_metadata.publication_year = openalex_metadata["publication_year"]
                updated_fields.append("year")

            if openalex_metadata.get("doi"):
                gemini_metadata.doi = openalex_metadata["doi"]
                updated_fields.append("doi")

            logger.info(f"メタデータマージ完了: OpenAlexで補完 (更新フィールド: {', '.join(updated_fields)})")
            return gemini_metadata

        except Exception as e:
            logger.error(f"OpenAlexメタデータマージエラー: {e}")
            return gemini_metadata

    async def _append_to_inbox(self, title: str, notion_page_id: str) -> bool:
        """Inbox.mdに論文登録記録を追記"""
        try:
            if not config.inbox.enabled or not config.inbox.file_path:
                return False

            inbox_path = Path(config.inbox.file_path)
            if not inbox_path.exists():
                logger.warning(f"Inboxファイルが存在しません: {inbox_path}")
                return False

            # NotionのURLを生成
            notion_url = f"https://www.notion.so/{notion_page_id.replace('-', '')}"

            # 現在の日時を取得
            now = datetime.now()
            timestamp = now.strftime("%Y/%m/%d %H:%M")

            # 追記する行を作成（改行 + Markdownリンク形式）
            entry = f"\n- [ ] {timestamp} 論文登録：[{title}]({notion_url})"

            # ファイルに追記
            with open(inbox_path, 'a', encoding='utf-8') as f:
                f.write(entry)

            logger.info(f"Inbox記録追加: {title}")
            return True

        except Exception as e:
            logger.error(f"Inbox追記エラー: {e}")
            return False

    async def _periodic_tasks(self):
        """定期実行タスク"""
        while self.is_running:
            try:
                # ファイル監視の定期タスク
                if self.file_watcher:
                    await self.file_watcher.run_periodic_tasks()
                
            except Exception as e:
                logger.error(f"定期タスクエラー: {e}")
                await asyncio.sleep(5)
    
    async def process_single_file(self, file_path: str) -> ProcessingResult:
        """単一ファイルの手動処理（CLI/GUI用）"""
        if not Path(file_path).exists():
            return ProcessingResult(
                success=False,
                error_message=f"ファイルが存在しません: {file_path}"
            )

        # スレッドセーフなセマフォを使用して処理
        with self.processing_semaphore:
            logger.info(f"手動処理開始 (セマフォ制御): {Path(file_path).name}")
            result = await self._process_file(file_path)
            logger.info(f"手動処理完了 (セマフォ解放): {Path(file_path).name}")
            return result


# メインアプリケーションインスタンス
app = PaperManager()


async def main():
    """メイン関数"""
    try:
        await app.start()
    except KeyboardInterrupt:
        logger.info("ユーザーによる中断")
    except Exception as e:
        logger.error(f"アプリケーションエラー: {e}")
    finally:
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())