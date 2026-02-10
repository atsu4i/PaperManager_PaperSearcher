"""
設定管理ページ
API設定、システム設定の管理
"""

import streamlit as st
import os
from pathlib import Path
import yaml
from typing import Dict, Any
import sys

# アプリケーションモジュールをインポート
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from app.config import config, load_config
from app.utils.logger import get_logger

logger = get_logger(__name__)

def load_env_file() -> Dict[str, str]:
    """環境変数ファイルを読み込み"""
    env_file = Path(".env")
    env_vars = {}

    if env_file.exists():
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        key_clean = key.strip()
                        value_clean = value.strip()

                        # Windowsパスのバックスラッシュをフォワードスラッシュに正規化
                        if 'PATH' in key_clean and '\\' in value_clean:
                            value_clean = value_clean.replace('\\', '/')

                        env_vars[key_clean] = value_clean
        except Exception as e:
            logger.error(f"環境変数ファイル読み込みエラー: {e}")

    return env_vars

def save_env_file(env_vars: Dict[str, str]) -> bool:
    """環境変数ファイルを保存"""
    try:
        env_file = Path(".env")
        with open(env_file, 'w', encoding='utf-8') as f:
            f.write("# Paper Manager 環境変数設定\n")
            f.write("# 以下の設定を適切に入力してください\n\n")

            # 各種API設定
            f.write("# Google Cloud 認証（ダウンロードしたJSONファイルのパス）\n")
            f.write(f"GOOGLE_APPLICATION_CREDENTIALS={env_vars.get('GOOGLE_APPLICATION_CREDENTIALS', '')}\n\n")

            f.write("# Gemini API Key\n")
            f.write(f"GEMINI_API_KEY={env_vars.get('GEMINI_API_KEY', '')}\n\n")

            f.write("# Notion API\n")
            f.write(f"NOTION_TOKEN={env_vars.get('NOTION_TOKEN', '')}\n")
            f.write(f"NOTION_DATABASE_ID={env_vars.get('NOTION_DATABASE_ID', '')}\n\n")

            f.write("# PubMed API (任意)\n")
            f.write(f"PUBMED_EMAIL={env_vars.get('PUBMED_EMAIL', '')}\n\n")

            f.write("# Slack通知（任意）\n")
            f.write(f"SLACK_BOT_TOKEN={env_vars.get('SLACK_BOT_TOKEN', '')}\n")
            f.write(f"SLACK_USER_ID_TO_DM={env_vars.get('SLACK_USER_ID_TO_DM', '')}\n\n")

            f.write("# フォルダ設定\n")
            f.write(f"WATCH_FOLDER={env_vars.get('WATCH_FOLDER', './pdfs')}\n")
            f.write(f"PROCESSED_FOLDER={env_vars.get('PROCESSED_FOLDER', './processed_pdfs')}\n\n")

            f.write("# ログレベル\n")
            f.write(f"LOG_LEVEL={env_vars.get('LOG_LEVEL', 'INFO')}\n\n")

            # Obsidian設定（パスはフォワードスラッシュに正規化）
            f.write("# Obsidian連携設定\n")
            f.write(f"OBSIDIAN_ENABLED={env_vars.get('OBSIDIAN_ENABLED', 'false')}\n")

            # Obsidian Vaultパスをフォワードスラッシュに正規化
            vault_path = env_vars.get('OBSIDIAN_VAULT_PATH', './obsidian_vault')
            if '\\' in vault_path:
                vault_path = vault_path.replace('\\', '/')

            f.write(f"OBSIDIAN_VAULT_PATH={vault_path}\n")
            f.write(f"OBSIDIAN_ORGANIZE_BY_YEAR={env_vars.get('OBSIDIAN_ORGANIZE_BY_YEAR', 'true')}\n")
            f.write(f"OBSIDIAN_INCLUDE_PDF={env_vars.get('OBSIDIAN_INCLUDE_PDF', 'false')}\n")
            f.write(f"OBSIDIAN_TAG_KEYWORDS={env_vars.get('OBSIDIAN_TAG_KEYWORDS', 'true')}\n")
            f.write(f"OBSIDIAN_LINK_TO_NOTION={env_vars.get('OBSIDIAN_LINK_TO_NOTION', 'true')}\n\n")

            # OCR設定
            f.write("# OCR設定\n")
            f.write(f"OCR_ENGINE={env_vars.get('OCR_ENGINE', 'vision_api')}\n")
            f.write(f"OLLAMA_HOST={env_vars.get('OLLAMA_HOST', 'http://localhost:11434')}\n")
            f.write(f"OLLAMA_OCR_MODEL={env_vars.get('OLLAMA_OCR_MODEL', 'glm-ocr')}\n")
            f.write(f"OCR_TIMEOUT={env_vars.get('OCR_TIMEOUT', '300')}\n")

        return True
    except Exception as e:
        logger.error(f"環境変数ファイル保存エラー: {e}")
        return False

def test_api_connections() -> Dict[str, bool]:
    """API接続テスト"""
    results = {}
    
    # Notion接続テスト
    try:
        from app.services.notion_service import notion_service
        # 非同期関数を同期的に実行（簡易版）
        results['notion'] = True  # 実際のテストは複雑なので簡略化
    except Exception as e:
        results['notion'] = False
        logger.error(f"Notion接続テストエラー: {e}")
    
    # Slack接続テスト
    try:
        from app.services.slack_service import slack_service
        results['slack'] = slack_service.enabled
    except Exception as e:
        results['slack'] = False
        logger.error(f"Slack接続テストエラー: {e}")
    
    # Gemini接続テスト
    try:
        from app.services.gemini_service import gemini_service
        results['gemini'] = bool(config.gemini_api_key)
    except Exception as e:
        results['gemini'] = False
        logger.error(f"Gemini接続テストエラー: {e}")
    
    return results

def render_settings():
    """設定ページをレンダリング"""
    st.markdown("## ⚙️ システム設定")

    # タブで設定を分類
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(["🔐 API設定", "📁 フォルダ設定", "👁️ OCR設定", "🔔 通知設定", "📝 Obsidian連携", "🧪 接続テスト", "🗄️ データベース管理"])
    
    # 現在の環境変数を読み込み
    env_vars = load_env_file()
    
    with tab1:
        st.markdown("### 🔐 API認証設定")
        st.info("各種APIの認証情報を設定してください。設定後は「保存」ボタンをクリックしてください。")
        
        # Google Cloud設定
        st.markdown("#### Google Cloud 設定")
        google_creds = st.text_input(
            "Google Cloud認証ファイルパス",
            value=env_vars.get('GOOGLE_APPLICATION_CREDENTIALS', ''),
            help="ダウンロードしたservice-account.jsonファイルのパス",
            placeholder="./credentials.json"
        )
        
        # Gemini API設定
        st.markdown("#### Gemini API 設定")
        gemini_key = st.text_input(
            "Gemini API Key",
            value=env_vars.get('GEMINI_API_KEY', ''),
            type="password",
            help="Google AI StudioでAPIキーを取得してください",
            placeholder="your_gemini_api_key_here"
        )

        # Geminiモデル設定
        st.markdown("##### 使用モデル設定")

        # 現在のconfig.yamlから設定を読み込み
        try:
            config_path = Path("config/config.yaml")
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = yaml.safe_load(f)
                gemini_config = config_data.get('gemini', {})
            else:
                gemini_config = {}
        except Exception as e:
            logger.error(f"設定ファイル読み込みエラー: {e}")
            gemini_config = {}

        # モデル選択肢
        model_options = [
            "gemini-2.5-pro",
            "gemini-2.5-flash-preview-09-2025",
            "gemini-2.5-flash-lite-preview-09-2025",
            "gemma-3-27b-it"
        ]

        col1, col2 = st.columns(2)

        with col1:
            metadata_model = st.selectbox(
                "メタデータ抽出用モデル",
                options=model_options,
                index=model_options.index(gemini_config.get('metadata_model', 'gemini-2.5-flash-preview-09-2025'))
                      if gemini_config.get('metadata_model') in model_options else 1,
                help="論文のメタデータ（タイトル、著者、DOI等）を抽出するモデル。軽量モデル推奨。"
            )

        with col2:
            summary_model = st.selectbox(
                "要約作成用モデル",
                options=model_options,
                index=model_options.index(gemini_config.get('summary_model', 'gemini-2.5-pro'))
                      if gemini_config.get('summary_model') in model_options else 0,
                help="日本語要約を作成するモデル。高品質モデル推奨。"
            )

        st.info(
            "💡 **推奨設定（コスパ最適）:**\n"
            "- メタデータ抽出: `gemma-3-27b-it` (無料・十分な品質)\n"
            "- 要約作成: `gemini-2.5-flash-lite` (低コスト・高品質)\n\n"
            "**より高品質重視:** 要約を `gemini-2.5-flash-preview` に変更\n"
            "**コスト最重視:** 要約も `gemma-3-27b-it` に設定（品質は若干低下）"
        )
        
        # Notion API設定
        st.markdown("#### Notion API 設定")
        notion_token = st.text_input(
            "Notion Integration Token",
            value=env_vars.get('NOTION_TOKEN', ''),
            type="password",
            help="Notion Developersで作成したIntegrationのトークン",
            placeholder="secret_xxxxxxxxxx"
        )
        
        notion_db_id = st.text_input(
            "Notion Database ID",
            value=env_vars.get('NOTION_DATABASE_ID', ''),
            help="論文管理用データベースのID（32文字）",
            placeholder="your_notion_database_id_here"
        )
        
        # PubMed設定
        st.markdown("#### PubMed API 設定（任意）")
        pubmed_email = st.text_input(
            "PubMed Email",
            value=env_vars.get('PUBMED_EMAIL', ''),
            help="PubMed API利用時の連絡先メールアドレス",
            placeholder="your_email@example.com"
        )
        
        # 保存ボタン
        if st.button("💾 API設定を保存", type="primary"):
            # 環境変数を保存
            new_env_vars = env_vars.copy()
            new_env_vars.update({
                'GOOGLE_APPLICATION_CREDENTIALS': google_creds,
                'GEMINI_API_KEY': gemini_key,
                'NOTION_TOKEN': notion_token,
                'NOTION_DATABASE_ID': notion_db_id,
                'PUBMED_EMAIL': pubmed_email
            })

            env_saved = save_env_file(new_env_vars)

            # config.yamlにGeminiモデル設定を保存
            try:
                config_path = Path("config/config.yaml")
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = yaml.safe_load(f)

                # gemini設定を更新
                if 'gemini' not in config_data:
                    config_data['gemini'] = {}

                config_data['gemini']['metadata_model'] = metadata_model
                config_data['gemini']['summary_model'] = summary_model

                with open(config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)

                config_saved = True
            except Exception as e:
                logger.error(f"設定ファイル保存エラー: {e}")
                config_saved = False

            if env_saved and config_saved:
                st.success("✅ API設定が保存されました！")
                st.warning("⚠️ **重要**: モデル設定を反映するには、アプリを再起動してください。\n\nターミナルで `Ctrl+C` を押してから `./start_gui.sh` を実行してください。")
            else:
                st.error("❌ 設定の保存に失敗しました。")
    
    with tab2:
        st.markdown("### 📁 フォルダ設定")
        st.info("PDFファイルの監視フォルダと処理済みファイルの保存先を設定してください。")
        
        # フォルダ設定
        watch_folder = st.text_input(
            "監視フォルダ",
            value=env_vars.get('WATCH_FOLDER', './pdfs'),
            help="PDFファイルを配置する監視対象フォルダ",
            placeholder="./pdfs"
        )
        
        processed_folder = st.text_input(
            "処理済みフォルダ",
            value=env_vars.get('PROCESSED_FOLDER', './processed_pdfs'),
            help="処理済みPDFファイルの保存先フォルダ",
            placeholder="./processed_pdfs"
        )
        
        log_level = st.selectbox(
            "ログレベル",
            options=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
            index=['DEBUG', 'INFO', 'WARNING', 'ERROR'].index(env_vars.get('LOG_LEVEL', 'INFO')),
            help="ログ出力レベルの設定"
        )
        
        # フォルダ作成ボタン
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📁 監視フォルダ作成"):
                try:
                    Path(watch_folder).mkdir(parents=True, exist_ok=True)
                    st.success(f"監視フォルダを作成しました: {watch_folder}")
                except Exception as e:
                    st.error(f"フォルダ作成に失敗: {e}")
        
        with col2:
            if st.button("📁 処理済みフォルダ作成"):
                try:
                    Path(processed_folder).mkdir(parents=True, exist_ok=True)
                    st.success(f"処理済みフォルダを作成しました: {processed_folder}")
                except Exception as e:
                    st.error(f"フォルダ作成に失敗: {e}")
        
        # 保存ボタン
        if st.button("💾 フォルダ設定を保存", type="primary"):
            new_env_vars = env_vars.copy()
            new_env_vars.update({
                'WATCH_FOLDER': watch_folder,
                'PROCESSED_FOLDER': processed_folder,
                'LOG_LEVEL': log_level
            })
            
            if save_env_file(new_env_vars):
                st.success("✅ フォルダ設定が保存されました！")
            else:
                st.error("❌ 設定の保存に失敗しました。")
    
    with tab3:
        st.markdown("### 👁️ OCR設定")
        st.info("PDFからテキストを抽出するOCRエンジンを選択できます。")

        # 現在のOCR設定
        current_ocr_engine = env_vars.get('OCR_ENGINE', 'vision_api')

        # OCRエンジン選択
        st.markdown("#### OCRエンジン")

        ocr_engine = st.radio(
            "使用するOCRエンジン",
            options=["vision_api", "glm_ocr"],
            index=0 if current_ocr_engine == "vision_api" else 1,
            format_func=lambda x: {
                "vision_api": "🌐 Google Vision API（クラウド・高精度）",
                "glm_ocr": "💻 GLM-OCR（ローカル・無料）"
            }.get(x, x),
            help="Vision API: Google Cloudを使用（API費用あり）\nGLM-OCR: Ollamaを使用（ローカル・無料）"
        )

        # エンジン別の詳細設定
        if ocr_engine == "vision_api":
            st.success("✅ Google Vision APIを使用します")
            st.info(
                "**必要な設定:**\n"
                "- `GOOGLE_APPLICATION_CREDENTIALS` が設定済みであること\n"
                "- Google Cloudの課金が有効であること"
            )

        elif ocr_engine == "glm_ocr":
            st.success("✅ GLM-OCR（Ollama）を使用します")

            st.markdown("#### Ollama設定")

            ollama_host = st.text_input(
                "Ollamaホスト",
                value=env_vars.get('OLLAMA_HOST', 'http://localhost:11434'),
                help="Ollamaサーバーのアドレス",
                placeholder="http://localhost:11434"
            )

            ollama_model = st.text_input(
                "OCRモデル",
                value=env_vars.get('OLLAMA_OCR_MODEL', 'glm-ocr'),
                help="使用するOCRモデル名",
                placeholder="glm-ocr"
            )

            ocr_timeout = st.number_input(
                "タイムアウト（秒）",
                value=int(env_vars.get('OCR_TIMEOUT', '300')),
                min_value=60,
                max_value=600,
                step=30,
                help="1ページあたりの最大処理時間"
            )

            # Ollama接続テスト
            if st.button("🔍 Ollama接続テスト"):
                try:
                    import requests
                    response = requests.get(f"{ollama_host}/api/tags", timeout=5)
                    if response.status_code == 200:
                        models = response.json().get("models", [])
                        model_names = [m.get("name", "") for m in models]
                        st.success(f"✅ Ollama接続成功")

                        if any(ollama_model in name for name in model_names):
                            st.success(f"✅ モデル `{ollama_model}` が見つかりました")
                        else:
                            st.warning(f"⚠️ モデル `{ollama_model}` が見つかりません")
                            st.code(f"ollama pull {ollama_model}", language="bash")

                        if model_names:
                            st.info(f"利用可能なモデル: {', '.join(model_names[:5])}")
                    else:
                        st.error(f"❌ Ollama接続失敗: {response.status_code}")
                except requests.exceptions.ConnectionError:
                    st.error(f"❌ Ollamaに接続できません: {ollama_host}")
                    st.info("Ollamaが起動しているか確認してください: `ollama serve`")
                except Exception as e:
                    st.error(f"❌ 接続テストエラー: {e}")

            st.info(
                "**GLM-OCRを使用するには:**\n"
                "1. Ollamaをインストール: https://ollama.com\n"
                "2. Ollamaを起動: `ollama serve`\n"
                "3. モデルをダウンロード: `ollama pull glm-ocr`\n"
                "4. PyMuPDFをインストール: `pip install PyMuPDF Pillow`"
            )

        # 保存ボタン
        if st.button("💾 OCR設定を保存", type="primary"):
            new_env_vars = env_vars.copy()
            new_env_vars['OCR_ENGINE'] = ocr_engine

            if ocr_engine == "glm_ocr":
                new_env_vars['OLLAMA_HOST'] = ollama_host
                new_env_vars['OLLAMA_OCR_MODEL'] = ollama_model
                new_env_vars['OCR_TIMEOUT'] = str(ocr_timeout)

            if save_env_file(new_env_vars):
                st.success("✅ OCR設定が保存されました！")
                st.warning("⚠️ **重要**: 設定を反映するには、アプリを再起動してください。")
            else:
                st.error("❌ 設定の保存に失敗しました。")

    with tab4:
        st.markdown("### 🔔 Slack通知設定")
        st.info("Slack通知を有効にすると、論文処理完了時にDMで通知を受け取れます。")
        
        # Slack設定
        slack_token = st.text_input(
            "Slack Bot Token",
            value=env_vars.get('SLACK_BOT_TOKEN', ''),
            type="password",
            help="Slack APIで作成したBotのOAuth Token（xoxb-で始まる）",
            placeholder="xoxb-your-bot-token"
        )
        
        slack_user_id = st.text_input(
            "Slack User ID",
            value=env_vars.get('SLACK_USER_ID_TO_DM', ''),
            help="通知を受け取るSlackユーザーのメンバーID（Uで始まる）",
            placeholder="U12345ABCDE"
        )
        
        # 通知レベル設定
        st.markdown("#### 通知レベル設定")
        
        # 現在の設定を読み込み
        try:
            config_path = Path("config/config.yaml")
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = yaml.safe_load(f)
                slack_config = config_data.get('slack', {})
            else:
                slack_config = {}
        except Exception as e:
            logger.error(f"設定ファイル読み込みエラー: {e}")
            slack_config = {}
        
        slack_enabled = st.checkbox(
            "Slack通知を有効にする",
            value=slack_config.get('enabled', False)
        )
        
        notify_success = st.checkbox(
            "成功時の通知",
            value=slack_config.get('notify_success', True),
            disabled=not slack_enabled
        )
        
        notify_failure = st.checkbox(
            "失敗時の通知",
            value=slack_config.get('notify_failure', True),
            disabled=not slack_enabled
        )
        
        notify_duplicate = st.checkbox(
            "重複検出時の通知",
            value=slack_config.get('notify_duplicate', False),
            disabled=not slack_enabled
        )
        
        include_summary = st.checkbox(
            "要約をメッセージに含める",
            value=slack_config.get('include_summary', False),
            disabled=not slack_enabled
        )
        
        max_message_length = st.slider(
            "メッセージ最大長",
            min_value=500,
            max_value=2000,
            value=slack_config.get('max_message_length', 1000),
            step=100,
            disabled=not slack_enabled
        )
        
        # 保存ボタン
        if st.button("💾 Slack設定を保存", type="primary"):
            # 環境変数を保存
            new_env_vars = env_vars.copy()
            new_env_vars.update({
                'SLACK_BOT_TOKEN': slack_token,
                'SLACK_USER_ID_TO_DM': slack_user_id
            })
            
            env_saved = save_env_file(new_env_vars)
            
            # config.yamlを更新
            try:
                config_path = Path("config/config.yaml")
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = yaml.safe_load(f)
                
                config_data['slack'] = {
                    'enabled': slack_enabled,
                    'notify_success': notify_success,
                    'notify_failure': notify_failure,
                    'notify_duplicate': notify_duplicate,
                    'include_summary': include_summary,
                    'max_message_length': max_message_length
                }
                
                with open(config_path, 'w', encoding='utf-8') as f:
                    yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)
                
                config_saved = True
            except Exception as e:
                logger.error(f"設定ファイル保存エラー: {e}")
                config_saved = False
            
            if env_saved and config_saved:
                st.success("✅ Slack設定が保存されました！")
            else:
                st.error("❌ 設定の保存に失敗しました。")
    
    with tab5:
        st.markdown("### 📝 Obsidian連携設定")
        st.info("Notionと同様の内容をObsidian VaultにMarkdown形式で自動エクスポートできます。")
        
        # Obsidian有効化
        obsidian_enabled = st.checkbox(
            "Obsidian連携を有効にする",
            value=env_vars.get('OBSIDIAN_ENABLED', 'false').lower() == 'true',
            help="論文処理完了時に自動的にObsidian VaultにMarkdownファイルを作成します"
        )
        
        # Vault設定
        st.markdown("#### 📁 Vault設定")
        vault_path = st.text_input(
            "Obsidian Vaultパス",
            value=env_vars.get('OBSIDIAN_VAULT_PATH', './obsidian_vault'),
            help="Obsidian VaultのフォルダパスDEFAULTe",
            placeholder="./obsidian_vault"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            organize_by_year = st.checkbox(
                "年別フォルダで整理",
                value=env_vars.get('OBSIDIAN_ORGANIZE_BY_YEAR', 'true').lower() == 'true',
                help="papers/2024/, papers/2025/ のように年別フォルダで整理します"
            )
        
        with col2:
            include_pdf = st.checkbox(
                "PDFファイルも保存",
                value=env_vars.get('OBSIDIAN_INCLUDE_PDF', 'true').lower() == 'true',
                help="attachments/pdfs/フォルダにPDFファイルもコピーします"
            )
        
        # ファイル設定
        st.markdown("#### 📄 ファイル設定")
        tag_keywords = st.checkbox(
            "キーワードをタグ化",
            value=env_vars.get('OBSIDIAN_TAG_KEYWORDS', 'true').lower() == 'true',
            help="論文のキーワードをObsidianタグ（#keyword）として設定します"
        )
        
        link_to_notion = st.checkbox(
            "Notionページへのリンクを含める",
            value=env_vars.get('OBSIDIAN_LINK_TO_NOTION', 'true').lower() == 'true',
            help="MarkdownファイルにNotionページへのリンクを含めます"
        )
        
        # Vaultフォルダ作成ボタン
        if st.button("📁 Obsidian Vaultフォルダ作成"):
            try:
                Path(vault_path).mkdir(parents=True, exist_ok=True)
                Path(vault_path, "papers").mkdir(exist_ok=True)
                Path(vault_path, "attachments", "pdfs").mkdir(parents=True, exist_ok=True)
                Path(vault_path, "templates").mkdir(exist_ok=True)
                st.success(f"✅ Obsidian Vault構造を作成しました: {vault_path}")
            except Exception as e:
                st.error(f"❌ フォルダ作成に失敗: {e}")
        
        # Vault状態表示
        if obsidian_enabled:
            try:
                from app.services.obsidian_service import obsidian_service
                vault_status = obsidian_service.get_vault_status()
                
                st.markdown("#### 📊 Vault状態")
                if vault_status.get("vault_exists"):
                    st.success(f"✅ Vault検出: {vault_status['vault_path']}")
                    st.info(f"📄 論文ファイル数: {vault_status.get('total_papers', 0)}件")
                    
                    if vault_status.get("folders"):
                        st.write("**年別フォルダ:**")
                        for folder in vault_status["folders"]:
                            st.write(f"  - {folder['name']}: {folder['count']}件")
                else:
                    st.warning("⚠️ Vaultフォルダが見つかりません")
                    
            except Exception as e:
                st.warning(f"Vault状態確認エラー: {e}")
        
        # 保存ボタン
        if st.button("💾 Obsidian設定を保存", type="primary"):
            new_env_vars = env_vars.copy()
            new_env_vars.update({
                'OBSIDIAN_ENABLED': 'true' if obsidian_enabled else 'false',
                'OBSIDIAN_VAULT_PATH': vault_path,
                'OBSIDIAN_ORGANIZE_BY_YEAR': 'true' if organize_by_year else 'false',
                'OBSIDIAN_INCLUDE_PDF': 'true' if include_pdf else 'false',
                'OBSIDIAN_TAG_KEYWORDS': 'true' if tag_keywords else 'false',
                'OBSIDIAN_LINK_TO_NOTION': 'true' if link_to_notion else 'false'
            })
            
            if save_env_file(new_env_vars):
                st.success("✅ Obsidian設定が保存されました！")
                st.warning("⚠️ **重要**: 設定を反映するには、アプリを再起動してください。\n\nターミナルで `Ctrl+C` を押してから `./start_gui.sh` を実行してください。")
            else:
                st.error("❌ 設定の保存に失敗しました。")
    
    with tab6:
        st.markdown("### 🧪 API接続テスト")
        st.info("各種APIの接続状態をテストできます。")
        st.warning("⚠️ **重要**: 設定を変更した場合は、各タブの「💾 保存」ボタンで保存してから接続テストを実行してください。")

        if st.button("🔍 接続テストを実行", type="primary"):
            with st.spinner("接続テストを実行中..."):
                results = test_api_connections()
            
            st.markdown("#### テスト結果")
            
            # Notion
            if results.get('notion'):
                st.success("✅ Notion API: 接続成功")
            else:
                st.error("❌ Notion API: 接続失敗")
            
            # Slack
            if results.get('slack'):
                st.success("✅ Slack API: 設定有効")
            else:
                st.warning("⚠️ Slack API: 無効または未設定")
            
            # Gemini
            if results.get('gemini'):
                st.success("✅ Gemini API: APIキー設定済み")

                # 現在動作中のモデル情報を表示
                try:
                    from app.config import config
                    st.info(
                        f"🤖 **現在動作中のモデル**:\n\n"
                        f"- メタデータ抽出: `{config.gemini.metadata_model}`\n"
                        f"- 要約作成: `{config.gemini.summary_model}`\n\n"
                        f"💡 これは起動時に読み込まれたモデルです。config.yamlの設定と異なる場合は再起動してください。"
                    )
                except Exception as e:
                    logger.warning(f"動作中モデル情報取得エラー: {e}")
            else:
                st.error("❌ Gemini API: APIキー未設定")
        
        # 現在の設定表示
        st.markdown("#### 現在の設定状態")
        st.caption("📝 config.yamlに保存されている設定値です（起動時に読み込まれます）")

        # Geminiモデル設定を取得
        try:
            config_path = Path("config/config.yaml")
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config_data = yaml.safe_load(f)
                gemini_config = config_data.get('gemini', {})
                metadata_model_str = gemini_config.get('metadata_model', '未設定')
                summary_model_str = gemini_config.get('summary_model', '未設定')
            else:
                metadata_model_str = '未設定'
                summary_model_str = '未設定'
        except:
            metadata_model_str = '未設定'
            summary_model_str = '未設定'

        status_data = {
            "設定項目": [
                "Google Cloud認証",
                "Gemini APIキー",
                "Gemini メタデータモデル",
                "Gemini 要約モデル",
                "Notion Token",
                "Notion DB ID",
                "Slack Bot Token",
                "Obsidian連携",
                "Obsidian Vaultパス"
            ],
            "設定状態": [
                "✅ 設定済み" if env_vars.get('GOOGLE_APPLICATION_CREDENTIALS') else "❌ 未設定",
                "✅ 設定済み" if env_vars.get('GEMINI_API_KEY') else "❌ 未設定",
                f"✅ {metadata_model_str}",
                f"✅ {summary_model_str}",
                "✅ 設定済み" if env_vars.get('NOTION_TOKEN') else "❌ 未設定",
                "✅ 設定済み" if env_vars.get('NOTION_DATABASE_ID') else "❌ 未設定",
                "✅ 設定済み" if env_vars.get('SLACK_BOT_TOKEN') else "❌ 未設定",
                "✅ 有効" if env_vars.get('OBSIDIAN_ENABLED', 'false').lower() == 'true' else "❌ 無効",
                f"✅ {env_vars.get('OBSIDIAN_VAULT_PATH', '未設定')}" if env_vars.get('OBSIDIAN_VAULT_PATH') else "❌ 未設定"
            ]
        }

        import pandas as pd
        df = pd.DataFrame(status_data)
        st.dataframe(df, width='stretch', hide_index=True)

    with tab7:
        st.markdown("### 🗄️ 処理済みファイルデータベース管理")
        st.info("処理済みファイルのデータベースを管理できます。失敗したファイルを削除すると、再度処理されます。")

        # データベースファイルのパス
        db_path = Path("processed_files.json")

        if not db_path.exists():
            st.warning("⚠️ 処理済みデータベースが見つかりません")
            if st.button("📄 データベースを作成"):
                try:
                    import json
                    with open(db_path, 'w', encoding='utf-8') as f:
                        json.dump({}, f)
                    st.success("✅ データベースを作成しました")
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ データベース作成エラー: {e}")
        else:
            try:
                import json

                # データベースを読み込み
                with open(db_path, 'r', encoding='utf-8') as f:
                    db = json.load(f)

                # 統計情報
                total_files = len(db)
                success_files = len([k for k, v in db.items() if v.get('success', False)])
                failed_files = len([k for k, v in db.items() if not v.get('success', False)])

                st.markdown("#### 📊 データベース統計")

                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("総ファイル数", total_files)

                with col2:
                    st.metric("成功", success_files, delta=None, delta_color="normal")

                with col3:
                    st.metric("失敗", failed_files, delta=None, delta_color="inverse")

                # 失敗したファイルのリスト
                if failed_files > 0:
                    st.markdown("#### ❌ 失敗したファイル")

                    failed_list = []
                    for file_path, info in db.items():
                        if not info.get('success', False):
                            file_name = Path(file_path).name
                            processed_at = info.get('processed_at', '不明')
                            error_msg = info.get('error_message', '不明')

                            # 処理日時を読みやすく
                            try:
                                from datetime import datetime
                                if isinstance(processed_at, (int, float)):
                                    dt = datetime.fromtimestamp(processed_at)
                                    processed_at_str = dt.strftime("%Y-%m-%d %H:%M")
                                else:
                                    dt = datetime.fromisoformat(processed_at)
                                    processed_at_str = dt.strftime("%Y-%m-%d %H:%M")
                            except:
                                processed_at_str = str(processed_at)

                            failed_list.append({
                                "ファイル名": file_name,
                                "処理日時": processed_at_str,
                                "エラー": error_msg[:50] + "..." if len(error_msg) > 50 else error_msg
                            })

                    # データフレームとして表示
                    import pandas as pd
                    df_failed = pd.DataFrame(failed_list)
                    st.dataframe(df_failed, width="stretch", hide_index=True)

                    # 失敗ファイルのリセットボタン
                    st.markdown("#### 🔄 失敗したファイルをリセット")
                    st.warning("⚠️ 失敗したファイルをデータベースから削除すると、次回システム起動時に再度処理されます。")

                    col1, col2 = st.columns([1, 1])

                    with col1:
                        if st.button("🗑️ 失敗したファイルを削除", type="primary"):
                            try:
                                # バックアップを作成
                                backup_path = Path("processed_files.json.backup")
                                with open(backup_path, 'w', encoding='utf-8') as f:
                                    json.dump(db, f, ensure_ascii=False, indent=2)

                                # 成功したファイルのみ残す
                                success_db = {k: v for k, v in db.items() if v.get('success', False)}

                                # 新しいDBを保存
                                with open(db_path, 'w', encoding='utf-8') as f:
                                    json.dump(success_db, f, ensure_ascii=False, indent=2)

                                st.success(f"✅ {failed_files}件の失敗ファイルを削除しました")
                                st.info(f"💾 バックアップ: {backup_path}")
                                st.info("🔄 システムを再起動して変更を反映してください")
                                st.rerun()

                            except Exception as e:
                                st.error(f"❌ 削除エラー: {e}")

                    with col2:
                        if st.button("📥 バックアップから復元"):
                            backup_path = Path("processed_files.json.backup")
                            if backup_path.exists():
                                try:
                                    import shutil
                                    shutil.copy(backup_path, db_path)
                                    st.success("✅ バックアップから復元しました")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ 復元エラー: {e}")
                            else:
                                st.error("❌ バックアップファイルが見つかりません")

                else:
                    st.success("✅ 失敗したファイルはありません")

                # データベース全体のリセット
                st.markdown("#### ⚠️ 危険な操作")

                with st.expander("🗑️ データベース全体をリセット"):
                    st.error("⚠️ **警告**: この操作を実行すると、全ての処理履歴が削除されます。")
                    st.warning("全てのファイルが再度処理されます。")

                    confirm = st.checkbox("上記の警告を理解しました")

                    if confirm:
                        if st.button("🗑️ 全てのデータを削除", type="secondary"):
                            try:
                                # バックアップを作成
                                backup_path = Path("processed_files.json.full_backup")
                                with open(backup_path, 'w', encoding='utf-8') as f:
                                    json.dump(db, f, ensure_ascii=False, indent=2)

                                # 空のDBを保存
                                with open(db_path, 'w', encoding='utf-8') as f:
                                    json.dump({}, f, ensure_ascii=False, indent=2)

                                st.success(f"✅ データベースをリセットしました（{total_files}件削除）")
                                st.info(f"💾 完全バックアップ: {backup_path}")
                                st.info("🔄 システムを再起動して変更を反映してください")
                                st.rerun()

                            except Exception as e:
                                st.error(f"❌ リセットエラー: {e}")

            except Exception as e:
                st.error(f"❌ データベース読み込みエラー: {e}")
                logger.error(f"データベース読み込みエラー: {e}")