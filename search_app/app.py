"""
Paper Searcher - 医学論文セマンティック検索アプリ

ChromaDBに登録された論文をセマンティック検索で検索・表示します。
"""

import sys
from pathlib import Path
import streamlit as st
import asyncio
import json
from datetime import datetime

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.chromadb_service import chromadb_service
from app.services.notion_service import notion_service
from app.config import config
from app.utils.logger import get_logger

logger = get_logger(__name__)

# ページ設定
st.set_page_config(
    page_title="Paper Searcher",
    page_icon="🔍",
    layout="wide",  # PCでは広く表示
    initial_sidebar_state="collapsed"
)

# カスタムCSS（レスポンシブ対応）
st.markdown("""
<style>
    /* 基本レイアウト（PC） */
    .main-header {
        text-align: center;
        padding: 1rem 0 2rem 0;
    }
    .search-box {
        max-width: 900px;
        margin: 0 auto 3rem auto;
        padding: 0 1rem;
    }
    .result-card {
        background-color: #f8f9fa;
        border-left: 4px solid #007bff;
        padding: 1.5rem;
        margin-bottom: 1.5rem;
        border-radius: 0.25rem;
    }
    .result-title {
        font-size: 1.3rem;
        font-weight: 600;
        color: #1a1a1a;
        margin-bottom: 0.5rem;
        line-height: 1.4;
    }
    .result-meta {
        color: #6c757d;
        font-size: 0.9rem;
        margin-bottom: 0.75rem;
        line-height: 1.5;
    }
    .result-summary {
        color: #495057;
        line-height: 1.6;
        margin-bottom: 0.75rem;
    }
    .result-links {
        margin-top: 0.75rem;
    }
    .similarity-badge {
        display: inline-block;
        background-color: #28a745;
        color: white;
        padding: 0.25rem 0.75rem;
        border-radius: 1rem;
        font-size: 0.85rem;
        font-weight: 500;
        margin-right: 0.5rem;
    }

    /* タブレット対応 */
    @media (max-width: 1024px) {
        .main .block-container {
            max-width: 100% !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
        }
        .search-box {
            max-width: 700px;
        }
    }

    /* モバイル対応（スマホ） */
    @media (max-width: 768px) {
        .main .block-container {
            max-width: 100% !important;
            padding-left: 1rem !important;
            padding-right: 1rem !important;
        }
        .main-header {
            padding: 0.5rem 0 1rem 0;
        }
        .main-header h1 {
            font-size: 1.8rem !important;
        }
        .main-header p {
            font-size: 0.9rem !important;
        }
        .search-box {
            max-width: 100%;
            padding: 0 0.5rem;
            margin-bottom: 1.5rem;
        }
        .result-card {
            padding: 1rem;
            margin-bottom: 1rem;
        }
        .result-title {
            font-size: 1.05rem;
            line-height: 1.3;
        }
        .result-meta {
            font-size: 0.8rem;
        }
        .similarity-badge {
            font-size: 0.75rem;
            padding: 0.2rem 0.6rem;
        }
        /* タッチ操作に適したボタンサイズ */
        .stButton button {
            min-height: 3rem !important;
            font-size: 1rem !important;
        }
    }
</style>
""", unsafe_allow_html=True)


def format_authors(authors_str: str, max_display: int = 3) -> str:
    """
    著者リストを整形して表示

    Args:
        authors_str: カンマ区切りの著者リスト
        max_display: 最大表示人数

    Returns:
        整形された著者リスト
    """
    if not authors_str:
        return "著者不明"

    authors = [a.strip() for a in authors_str.split(",")]
    if len(authors) <= max_display:
        return ", ".join(authors)
    else:
        return f"{', '.join(authors[:max_display])}, et al."


def display_search_result(result: dict, index: int):
    """
    検索結果を表示

    Args:
        result: 検索結果ディクショナリ
        index: 結果のインデックス
    """
    metadata = result["metadata"]
    similarity = result["similarity"]

    # 類似度スコアの色分け
    if similarity >= 0.8:
        badge_color = "#28a745"  # 緑
    elif similarity >= 0.6:
        badge_color = "#ffc107"  # 黄
    else:
        badge_color = "#6c757d"  # グレー

    # 引用数バッジを準備（0件の場合も表示）
    citations = metadata.get('cited_by_count', '0')
    try:
        citation_count = int(citations) if citations else 0
    except (ValueError, TypeError):
        citation_count = 0

    citation_badge = f'<span class="similarity-badge" style="background-color: #17a2b8; margin-left: 0.5rem;">📊 引用数: {citation_count}件</span>'

    # メタデータ部分を準備
    authors_text = format_authors(metadata.get('authors', ''))
    journal = metadata.get('journal', '')
    year = metadata.get('year', '')

    meta_parts = [f"<strong>{authors_text}</strong>"]
    if journal:
        meta_parts.append(journal)
    if year:
        meta_parts.append(f"({year})")

    meta_text = ' | '.join(meta_parts)

    # カード表示
    st.markdown(f"""
    <div class="result-card">
        <div class="result-title">
            {index}. {metadata.get('title', '(タイトルなし)')}
        </div>
        <div class="result-meta">
            {meta_text}
        </div>
        <div style="margin-bottom: 0.75rem;">
            <span class="similarity-badge" style="background-color: {badge_color};">
                関連度: {similarity:.1%}
            </span>
            {citation_badge}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 要約を展開可能に
    with st.expander("📄 要約を表示"):
        # documentフィールドから要約全文を取得
        # documentは「タイトル\n\n要約」の形式なので、要約部分を抽出
        document = result.get('document', '')
        if document and '\n\n' in document:
            # タイトル部分をスキップして要約のみ取得
            summary = document.split('\n\n', 1)[1].strip()
        else:
            # フォールバック: metadataのsummaryを使用
            summary = metadata.get('summary', '').strip()

        if summary:
            st.write(summary)
        else:
            st.info("要約がありません")

    # リンク表示（モバイルで見やすく）
    links = []
    if metadata.get('notion_url'):
        links.append(f"[📝 Notion]({metadata['notion_url']})")
    if metadata.get('doi'):
        links.append(f"[📄 DOI]({metadata['doi']})")
    if metadata.get('pmid'):
        pmid = metadata['pmid']
        links.append(f"[🔬 PubMed](https://pubmed.ncbi.nlm.nih.gov/{pmid}/)")

    if links:
        st.markdown("**🔗 リンク:** " + " · ".join(links))
    else:
        st.caption("🔗 リンクなし")

    # 関連論文セクション
    st.markdown("")
    st.markdown("**🔗 関連論文**")

    # 論文IDを取得
    paper_id = result.get('id')
    if not paper_id:
        st.caption("関連論文を取得できません")
    else:
        # ChromaDBから類似論文を取得（5件に絞る）
        similar_papers = chromadb_service.get_similar_papers(paper_id, n_results=5)

        if not similar_papers:
            st.caption("関連論文が見つかりませんでした")
        else:
            # 各関連論文をトグル形式で表示
            for i, sim_paper in enumerate(similar_papers, 1):
                sim_metadata = sim_paper["metadata"]
                similarity_score = sim_paper.get("similarity_score", 0)

                # 類似度に応じた色分け
                if similarity_score >= 0.8:
                    score_color = "🟢"
                elif similarity_score >= 0.6:
                    score_color = "🟡"
                else:
                    score_color = "🟠"

                # タイトル
                title = sim_metadata.get('title', '(タイトルなし)')

                # トグル（expander）で各論文を表示
                with st.expander(f"{score_color} {i}. {title[:60]}{'...' if len(title) > 60 else ''} ({similarity_score:.1%})"):
                    # タイトル全文
                    st.markdown(f"**{title}**")
                    st.caption(f"類似度: {similarity_score:.1%}")
                    st.markdown("")

                    # 著者・雑誌・年
                    info_parts = []
                    authors = sim_metadata.get('authors', '')
                    if authors:
                        info_parts.append(f"👥 {format_authors(authors, max_display=5)}")
                    journal = sim_metadata.get('journal', '')
                    year = sim_metadata.get('year', '')
                    if journal:
                        info_parts.append(f"📚 {journal}")
                    if year:
                        info_parts.append(f"📅 {year}")

                    # 引用数（0件の場合も表示）
                    citations = sim_metadata.get('cited_by_count', '0')
                    try:
                        citation_count = int(citations) if citations else 0
                    except (ValueError, TypeError):
                        citation_count = 0
                    info_parts.append(f"📊 {citation_count}件")

                    if info_parts:
                        st.caption(" | ".join(info_parts))

                    st.markdown("---")

                    # 要約
                    st.markdown("**📝 要約**")
                    document = sim_paper.get('document', '')
                    if document and '\n\n' in document:
                        summary = document.split('\n\n', 1)[1].strip()
                    else:
                        summary = sim_metadata.get('summary', '').strip()

                    if summary:
                        # 要約が長い場合は最初の500文字のみ表示
                        if len(summary) > 500:
                            st.markdown(summary[:500] + "...")
                            st.caption("（要約の一部を表示）")
                        else:
                            st.markdown(summary)
                    else:
                        st.info("要約がありません")

                    st.markdown("---")

                    # リンクボタン
                    st.markdown("**🔗 リンク**")
                    btn_col1, btn_col2, btn_col3 = st.columns(3)

                    with btn_col1:
                        notion_url = sim_metadata.get('notion_url')
                        if notion_url:
                            st.link_button(
                                "📝 Notion",
                                notion_url,
                                use_container_width=True,
                                type="primary"
                            )

                    with btn_col2:
                        doi = sim_metadata.get('doi')
                        if doi:
                            st.link_button("📄 DOI", doi, use_container_width=True)

                    with btn_col3:
                        pmid = sim_metadata.get('pmid')
                        if pmid:
                            st.link_button(
                                "🔬 PubMed",
                                f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                                use_container_width=True
                            )

    st.markdown("---")


@st.dialog("📄 論文詳細", width="large")
def show_paper_dialog(paper):
    """論文詳細をダイアログで表示"""
    metadata = paper["metadata"]

    # タイトル
    st.markdown(f"## {metadata.get('title', '(タイトルなし)')}")

    # メタ情報
    col1, col2, col3 = st.columns([2, 2, 1])

    with col1:
        authors = metadata.get('authors', '')
        if authors:
            st.markdown(f"**👥 著者**")
            st.caption(format_authors(authors, max_display=10))

    with col2:
        journal = metadata.get('journal', '')
        year = metadata.get('year', '')
        if journal or year:
            st.markdown(f"**📚 掲載誌**")
            journal_year = []
            if journal:
                journal_year.append(journal)
            if year:
                journal_year.append(f"({year})")
            st.caption(' '.join(journal_year))

    with col3:
        citations = metadata.get('cited_by_count', '0')
        try:
            citation_count = int(citations) if citations else 0
        except (ValueError, TypeError):
            citation_count = 0
        st.metric("📊 被引用数", f"{citation_count}件")

    st.markdown("---")

    # 要約
    st.markdown("### 📝 要約")
    document = paper.get('document', '')
    if document and '\n\n' in document:
        summary = document.split('\n\n', 1)[1].strip()
    else:
        summary = metadata.get('summary', '').strip()

    if summary:
        st.markdown(summary)
    else:
        st.info("要約がありません")

    st.markdown("---")

    # リンクボタン（3列）
    st.markdown("### 🔗 リンク")
    btn_col1, btn_col2, btn_col3 = st.columns(3)

    with btn_col1:
        notion_url = metadata.get('notion_url')
        if notion_url:
            st.link_button("📝 Notionで開く", notion_url, use_container_width=True, type="primary")
        else:
            st.button("📝 Notionで開く", disabled=True, use_container_width=True)

    with btn_col2:
        doi = metadata.get('doi')
        if doi:
            st.link_button("📄 DOI", doi, use_container_width=True)
        else:
            st.button("📄 DOI", disabled=True, use_container_width=True)

    with btn_col3:
        pmid = metadata.get('pmid')
        if pmid:
            st.link_button("🔬 PubMed", f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", use_container_width=True)
        else:
            st.button("🔬 PubMed", disabled=True, use_container_width=True)

    # 関連論文セクション
    st.markdown("---")
    st.markdown("### 🔗 関連論文")
    st.caption("セマンティックマップで近い位置の論文（ベクトル空間で類似）")

    # 論文IDを取得
    paper_id = paper.get('id')
    if not paper_id:
        st.warning("論文IDが見つかりません")
    else:
        # ChromaDBから類似論文を取得（10件）
        with st.spinner("関連論文を検索中..."):
            similar_papers = chromadb_service.get_similar_papers(paper_id, n_results=10)

        if not similar_papers:
            st.info("関連論文が見つかりませんでした")
        else:
            st.caption(f"**{len(similar_papers)}件の関連論文**")
            st.markdown("")

            # 各関連論文をトグル形式で表示
            for i, sim_paper in enumerate(similar_papers, 1):
                sim_metadata = sim_paper["metadata"]
                similarity_score = sim_paper.get("similarity_score", 0)

                # 類似度に応じた色分け
                if similarity_score >= 0.8:
                    score_color = "🟢"
                elif similarity_score >= 0.6:
                    score_color = "🟡"
                else:
                    score_color = "🟠"

                # タイトル
                title = sim_metadata.get('title', '(タイトルなし)')

                # トグル（expander）で各論文を表示
                with st.expander(f"{score_color} **{i}. {title}** (類似度: {similarity_score:.1%})"):
                    # メタ情報（3列レイアウト）
                    col1, col2, col3 = st.columns([2, 2, 1])

                    with col1:
                        authors = sim_metadata.get('authors', '')
                        if authors:
                            st.markdown(f"**👥 著者**")
                            st.caption(format_authors(authors, max_display=10))

                    with col2:
                        journal = sim_metadata.get('journal', '')
                        year = sim_metadata.get('year', '')
                        if journal or year:
                            st.markdown(f"**📚 掲載誌**")
                            journal_year = []
                            if journal:
                                journal_year.append(journal)
                            if year:
                                journal_year.append(f"({year})")
                            st.caption(' '.join(journal_year))

                    with col3:
                        citations = sim_metadata.get('cited_by_count', '0')
                        try:
                            citation_count = int(citations) if citations else 0
                        except (ValueError, TypeError):
                            citation_count = 0
                        st.metric("📊 被引用数", f"{citation_count}件")

                    st.markdown("---")

                    # 要約
                    st.markdown("**📝 要約**")
                    document = sim_paper.get('document', '')
                    if document and '\n\n' in document:
                        summary = document.split('\n\n', 1)[1].strip()
                    else:
                        summary = sim_metadata.get('summary', '').strip()

                    if summary:
                        st.markdown(summary)
                    else:
                        st.info("要約がありません")

                    st.markdown("---")

                    # リンクボタン（3列）
                    st.markdown("**🔗 リンク**")
                    btn_col1, btn_col2, btn_col3 = st.columns(3)

                    with btn_col1:
                        notion_url = sim_metadata.get('notion_url')
                        if notion_url:
                            st.link_button(
                                f"📝 Notionで開く",
                                notion_url,
                                use_container_width=True,
                                type="primary"
                            )
                        else:
                            st.button("📝 Notionで開く", disabled=True, use_container_width=True)

                    with btn_col2:
                        doi = sim_metadata.get('doi')
                        if doi:
                            st.link_button("📄 DOI", doi, use_container_width=True)
                        else:
                            st.button("📄 DOI", disabled=True, use_container_width=True)

                    with btn_col3:
                        pmid = sim_metadata.get('pmid')
                        if pmid:
                            st.link_button(
                                "🔬 PubMed",
                                f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                                use_container_width=True
                            )
                        else:
                            st.button("🔬 PubMed", disabled=True, use_container_width=True)


def render_semantic_map():
    """セマンティックマップを描画"""
    st.markdown("### 📊 セマンティックマップ")
    st.markdown("論文コレクション全体を2次元空間で可視化します。近い位置にある論文は意味的に関連しています。")

    # 設定オプション
    col1, col2 = st.columns([1, 1])

    with col1:
        limit = st.selectbox(
            "表示する論文数",
            options=[50, 100, 200, 500, None],
            format_func=lambda x: f"{x}件" if x else "全件",
            index=2,
            help="論文数が多いと処理時間が長くなります"
        )

    with col2:
        color_by = st.selectbox(
            "色分け基準",
            options=["citations", "year", "journal"],
            format_func=lambda x: "被引用数" if x == "citations" else ("年度" if x == "year" else "雑誌"),
            index=0
        )

    generate_button = st.button("🗺️ マップ生成", type="primary", use_container_width=True)

    # マップ生成ボタンが押されたら新規生成し、セッションステートに保存
    if generate_button:
        with st.spinner("📊 セマンティックマップを生成中... (数十秒かかる場合があります)"):
            try:
                # マップ生成
                map_data = chromadb_service.generate_semantic_map(limit=limit)

                if not map_data["papers"]:
                    st.error(f"❌ マップ生成失敗: {map_data['stats'].get('error', 'Unknown error')}")
                else:
                    # セッションステートに保存
                    st.session_state.map_data = map_data
                    st.session_state.map_limit = limit
                    st.session_state.map_color_by = color_by

            except Exception as e:
                st.error(f"マップ生成エラー: {e}")
                logger.error(f"Semantic map error: {e}")

    # セッションステートにマップデータがあれば表示
    if st.session_state.get('map_data'):
        try:
            map_data = st.session_state.map_data
            color_by = st.session_state.get('map_color_by', 'citations')

            # Plotlyで散布図作成
            import plotly.graph_objects as go

            papers = map_data["papers"]
            x_coords = map_data["x"]
            y_coords = map_data["y"]

            # プロット作成
            fig = go.Figure()

            if color_by == "citations":
                # 被引用数の場合：対数スケールで色分け
                import numpy as np

                hover_texts = []
                colors = []
                citations_list = []

                for paper in papers:
                    metadata = paper["metadata"]
                    title = metadata.get("title", "タイトル不明")
                    authors = metadata.get("authors", "著者不明")
                    year = metadata.get("year", "N/A")
                    journal = metadata.get("journal", "雑誌不明")
                    citations = metadata.get("cited_by_count", "0")

                    hover_text = f"<b>{title}</b><br>"
                    hover_text += f"著者: {authors}<br>"
                    hover_text += f"雑誌: {journal}<br>"
                    hover_text += f"年度: {year}<br>"
                    hover_text += f"被引用数: {citations}件"
                    hover_texts.append(hover_text)

                    # 被引用数は数値に変換
                    try:
                        citations_num = int(citations) if citations and citations != "0" else 0
                    except (ValueError, TypeError):
                        citations_num = 0
                    citations_list.append(citations_num)

                    # 対数スケールに変換 (log(x + 1)で0も扱える)
                    log_citations = np.log1p(citations_num)  # log(citations + 1)
                    colors.append(log_citations)

                # 統計情報を計算
                max_citations = max(citations_list) if citations_list else 0

                fig.add_trace(go.Scatter(
                    x=x_coords,
                    y=y_coords,
                    mode='markers',
                    marker=dict(
                        size=8,
                        color=colors,
                        colorscale='Plasma',  # 暖色系のカラーマップ（引用数が多いほど明るく）
                        showscale=True,
                        colorbar=dict(
                            title="被引用数<br>(対数)",
                            tickvals=[0, np.log1p(1), np.log1p(10), np.log1p(100), np.log1p(1000)],
                            ticktext=['0', '1', '10', '100', '1000']
                        ),
                        line=dict(width=0.5, color='white'),
                        opacity=0.7
                    ),
                    text=hover_texts,
                    hovertemplate='%{text}<extra></extra>',
                    customdata=[[i] for i in range(len(papers))],  # 論文インデックスを保存
                    showlegend=False
                ))

                # マップの論文データをセッションステートに保存
                st.session_state.map_papers = papers

            elif color_by == "year":
                # 年度の場合：連続的なカラースケール
                hover_texts = []
                colors = []

                for paper in papers:
                    metadata = paper["metadata"]
                    title = metadata.get("title", "タイトル不明")
                    authors = metadata.get("authors", "著者不明")
                    year = metadata.get("year", "N/A")
                    journal = metadata.get("journal", "雑誌不明")

                    hover_text = f"<b>{title}</b><br>"
                    hover_text += f"著者: {authors}<br>"
                    hover_text += f"雑誌: {journal}<br>"
                    hover_text += f"年度: {year}"
                    hover_texts.append(hover_text)

                    # 年度は数値に変換
                    try:
                        year_num = int(year) if year != "N/A" else 2000
                    except (ValueError, TypeError):
                        year_num = 2000
                    colors.append(year_num)

                fig.add_trace(go.Scatter(
                    x=x_coords,
                    y=y_coords,
                    mode='markers',
                    marker=dict(
                        size=8,
                        color=colors,
                        colorscale='Viridis',
                        showscale=True,
                        colorbar=dict(title="年度"),
                        line=dict(width=0.5, color='white'),
                        opacity=0.7
                    ),
                    text=hover_texts,
                    hovertemplate='%{text}<extra></extra>',
                    customdata=[[i] for i in range(len(papers))],  # 論文インデックスを保存
                    showlegend=False
                ))

                # マップの論文データをセッションステートに保存
                st.session_state.map_papers = papers

            else:
                # 雑誌の場合：雑誌ごとにトレースを作成して凡例表示
                # 雑誌ごとにデータをグループ化
                journal_groups = {}
                for i, paper in enumerate(papers):
                    metadata = paper["metadata"]
                    journal = metadata.get("journal", "雑誌不明")[:30]

                    if journal not in journal_groups:
                        journal_groups[journal] = {
                            "x": [],
                            "y": [],
                            "hover_texts": [],
                            "indices": []  # 論文インデックスを追加
                        }

                    journal_groups[journal]["x"].append(x_coords[i])
                    journal_groups[journal]["y"].append(y_coords[i])
                    journal_groups[journal]["indices"].append(i)  # インデックスを保存

                    title = metadata.get("title", "タイトル不明")
                    authors = metadata.get("authors", "著者不明")
                    year = metadata.get("year", "N/A")
                    hover_text = f"<b>{title}</b><br>"
                    hover_text += f"著者: {authors}<br>"
                    hover_text += f"雑誌: {journal}<br>"
                    hover_text += f"年度: {year}"
                    journal_groups[journal]["hover_texts"].append(hover_text)

                # 雑誌の数が多い場合は上位のみ表示、残りは"その他"にまとめる
                max_journals = 15  # 凡例に表示する最大雑誌数
                if len(journal_groups) > max_journals:
                    # 論文数が多い雑誌上位を取得
                    journal_counts = {j: len(data["x"]) for j, data in journal_groups.items()}
                    top_journals = sorted(journal_counts.items(), key=lambda x: x[1], reverse=True)[:max_journals-1]
                    top_journal_names = [j[0] for j in top_journals]

                    # "その他"グループを作成
                    other_group = {"x": [], "y": [], "hover_texts": [], "indices": []}
                    for journal, data in journal_groups.items():
                        if journal not in top_journal_names:
                            other_group["x"].extend(data["x"])
                            other_group["y"].extend(data["y"])
                            other_group["hover_texts"].extend(data["hover_texts"])
                            other_group["indices"].extend(data["indices"])

                    # 上位雑誌のみ残して、その他を追加
                    filtered_groups = {j: journal_groups[j] for j in top_journal_names}
                    if other_group["x"]:
                        filtered_groups["その他"] = other_group
                    journal_groups = filtered_groups

                # 各雑誌ごとにトレース追加
                for journal, data in sorted(journal_groups.items()):
                    fig.add_trace(go.Scatter(
                        x=data["x"],
                        y=data["y"],
                        mode='markers',
                        name=journal,
                        marker=dict(
                            size=8,
                            line=dict(width=0.5, color='white'),
                            opacity=0.7
                        ),
                        text=data["hover_texts"],
                        hovertemplate='%{text}<extra></extra>',
                        customdata=[[idx] for idx in data["indices"]],  # 論文インデックスを保存
                        showlegend=True
                    ))

                # マップの論文データをセッションステートに保存
                st.session_state.map_papers = papers

            fig.update_layout(
                title=f"論文セマンティックマップ ({len(papers)}件)",
                xaxis_title="",
                yaxis_title="",
                hovermode='closest',
                height=700,
                showlegend=False,
                plot_bgcolor='rgba(240, 240, 240, 0.5)',
                xaxis=dict(showgrid=True, zeroline=False, showticklabels=False),
                yaxis=dict(showgrid=True, zeroline=False, showticklabels=False)
            )

            # クリックイベントを有効化
            event = st.plotly_chart(fig, use_container_width=True, on_select="rerun", selection_mode="points", key="semantic_map")

            # 現在の選択状態を取得
            current_selection_id = None
            current_paper_index = None
            if event and event.selection and event.selection.points:
                point = event.selection.points[0]
                if 'customdata' in point and point['customdata']:
                    current_paper_index = point['customdata'][0]
                    current_paper = st.session_state.map_papers[current_paper_index]
                    current_selection_id = current_paper.get('id')

            # 前回の選択と比較
            last_selection_id = st.session_state.get('last_selection_id', None)

            # 新しい選択の場合のみ処理（同じ論文の連続選択を防止）
            if current_selection_id and current_selection_id != last_selection_id:
                selected_paper = st.session_state.map_papers[current_paper_index]
                st.session_state.selected_paper_for_dialog = selected_paper
                st.session_state.last_selection_id = current_selection_id
                st.rerun()

            # 選択が解除された場合（何もない場所をクリックした場合）
            if not current_selection_id and last_selection_id:
                del st.session_state.last_selection_id

            # セッションステートに選択された論文があればダイアログを開く
            if 'selected_paper_for_dialog' in st.session_state:
                selected_paper = st.session_state.selected_paper_for_dialog
                del st.session_state.selected_paper_for_dialog
                show_paper_dialog(selected_paper)

            # 統計情報
            with st.expander("📈 マップ統計情報"):
                stats = map_data["stats"]
                col1, col2, col3 = st.columns(3)

                with col1:
                    st.metric("論文数", f"{stats['total_papers']}件")

                with col2:
                    st.metric("埋め込み次元", f"{stats['embedding_dim']}次元")

                with col3:
                    st.metric("表示次元", "2次元")

                st.markdown(f"**UMAPパラメータ:** n_neighbors={stats['umap_params']['n_neighbors']}, min_dist={stats['umap_params']['min_dist']}")

        except Exception as e:
            st.error(f"マップ表示エラー: {e}")
            logger.error(f"Semantic map display error: {e}")


def main():
    """メイン処理"""
    # ヘッダー
    st.markdown("""
    <div class="main-header">
        <h1>🔍 Paper Searcher</h1>
        <p style="color: #6c757d; font-size: 1.1rem;">Notion論文データベース検索</p>
    </div>
    """, unsafe_allow_html=True)

    # セッションステート初期化
    if 'search_results' not in st.session_state:
        st.session_state.search_results = None
    if 'last_query' not in st.session_state:
        st.session_state.last_query = ""
    if 'search_stats' not in st.session_state:
        st.session_state.search_stats = None
    if 'hyde_query' not in st.session_state:
        st.session_state.hyde_query = None
    if 'selected_paper' not in st.session_state:
        st.session_state.selected_paper = None
    if 'map_papers' not in st.session_state:
        st.session_state.map_papers = None

    # ChromaDB登録数表示
    try:
        db_count = chromadb_service.get_count()
        st.sidebar.success(f"📦 登録論文数: {db_count:,}件")
    except Exception as e:
        st.sidebar.error(f"ChromaDB接続エラー: {e}")
        logger.error(f"ChromaDB connection error: {e}")
        return

    # タブUI
    tab1, tab2, tab3 = st.tabs(["🔍 検索", "📊 セマンティックマップ", "📤 エクスポート"])

    with tab1:
        # サイドバー設定（モバイルではエクスパンダーに格納）
        with st.sidebar:
            st.markdown("### ⚙️ 検索設定")

            # 検索モード選択
            search_mode = st.radio(
                "検索モード",
                options=["Deep Search（HyDE + Rerank）", "Fast Search（通常ベクトル検索）"],
                index=0,
                help="Deep Searchは精度重視、Fast Searchは速度重視"
            )

            n_results = st.slider(
                "表示件数",
                min_value=5,
                max_value=50,
                value=10,
                step=5
            )

            # Deep Search詳細設定
            if search_mode == "Deep Search（HyDE + Rerank）":
                st.markdown("#### Deep Search設定")
                broad_retrieval_size = st.slider(
                    "中間検索件数",
                    min_value=20,
                    max_value=50,
                    value=30,
                    step=10,
                    help="ベクトル検索で取得する候補数（多いほど網羅的、遅い）"
                )
            else:
                broad_retrieval_size = 30  # デフォルト値

        # 検索ボックス
        st.markdown('<div class="search-box">', unsafe_allow_html=True)

        query = st.text_input(
            "検索キーワードを入力してください",
            placeholder="例: 小児ALLの維持療法",
            label_visibility="collapsed",
            key="search_input"
        )

        search_button = st.button("🔍 検索", type="primary", use_container_width=True)

        st.markdown('</div>', unsafe_allow_html=True)

        # 検索実行
        if search_button and query:
            if search_mode == "Deep Search（HyDE + Rerank）":
                # Deep Search（HyDE + Reranking）
                status_container = st.empty()

                try:
                    # Step 1: HyDE
                    status_container.info("🤖 Step 1/3: Geminiが関連用語を思考中...")
                    import time
                    time.sleep(0.5)  # UI表示用の短い待機

                    # Step 2: Vector Search
                    status_container.info("🔍 Step 2/3: 論文データベースを検索中...")
                    time.sleep(0.5)

                    # Step 3: Reranking
                    status_container.info("🎯 Step 3/3: Geminiが論文を精査中...")

                    # Deep Search実行
                    search_result = chromadb_service.deep_search(
                        query,
                        n_results=n_results,
                        broad_retrieval_size=broad_retrieval_size
                    )

                    status_container.success("✅ Deep Search完了!")
                    time.sleep(1)
                    status_container.empty()

                    # 結果を保存
                    st.session_state.search_results = search_result["results"]
                    st.session_state.last_query = query
                    st.session_state.search_stats = search_result["stats"]
                    st.session_state.hyde_query = search_result["hyde_query"]

                except Exception as e:
                    status_container.error(f"検索エラー: {e}")
                    logger.error(f"Deep search error: {e}")
                    return

            else:
                # Fast Search（通常ベクトル検索）
                with st.spinner("🔍 検索中..."):
                    try:
                        results = chromadb_service.search(query, n_results=n_results)
                        st.session_state.search_results = results
                        st.session_state.last_query = query
                        st.session_state.search_stats = None
                        st.session_state.hyde_query = None
                    except Exception as e:
                        st.error(f"検索エラー: {e}")
                        logger.error(f"Search error: {e}")
                        return

        # 検索結果表示
        if st.session_state.search_results is not None:
            results = st.session_state.search_results

            if not results:
                st.info("🔍 検索結果が見つかりませんでした。別のキーワードで試してください。")
            else:
                # 結果ヘッダー
                st.markdown(f"""
                <div style="margin: 2rem 0 1.5rem 0;">
                    <h3>検索結果: <code>{st.session_state.last_query}</code></h3>
                    <p style="color: #6c757d;">見つかった論文: {len(results)}件</p>
                </div>
                """, unsafe_allow_html=True)

                # Deep Search統計情報を表示
                if hasattr(st.session_state, 'search_stats') and st.session_state.search_stats:
                    stats = st.session_state.search_stats
                    with st.expander("📊 Deep Search統計情報", expanded=False):
                        col1, col2, col3 = st.columns(3)

                        with col1:
                            st.metric("候補取得数", f"{stats.get('broad_retrieval_count', 0)}件")

                        with col2:
                            st.metric("最終選出数", f"{stats.get('final_count', 0)}件")

                        with col3:
                            rerank_ratio = (
                                stats.get('final_count', 0) / stats.get('broad_retrieval_count', 1) * 100
                                if stats.get('broad_retrieval_count', 0) > 0 else 0
                            )
                            st.metric("選出率", f"{rerank_ratio:.1f}%")

                        # HyDEクエリを表示
                        if hasattr(st.session_state, 'hyde_query') and st.session_state.hyde_query:
                            st.markdown("**🤖 生成された検索クエリ（HyDE）:**")
                            st.text_area(
                                "HyDE Query",
                                value=st.session_state.hyde_query,
                                height=150,
                                label_visibility="collapsed"
                            )

                # 各結果を表示
                for idx, result in enumerate(results, 1):
                    display_search_result(result, idx)

    with tab2:
        # セマンティックマップタブ
        render_semantic_map()

    with tab3:
        # エクスポートタブ
        st.markdown("### 📤 プロジェクト別論文エクスポート")
        st.markdown("Notionデータベースから特定のプロジェクトに属する論文をJSON形式でエクスポートします。")

        # プロジェクト一覧を取得
        if "projects" not in st.session_state:
            with st.spinner("プロジェクト一覧を読み込み中..."):
                try:
                    projects = asyncio.run(notion_service.get_all_projects())
                    st.session_state.projects = projects
                except Exception as e:
                    st.error(f"プロジェクト一覧の取得に失敗しました: {e}")
                    logger.error(f"Failed to fetch projects: {e}")
                    st.session_state.projects = []

        projects = st.session_state.projects

        if not projects:
            st.warning("プロジェクトが見つかりませんでした。Notionデータベースに「プロジェクト」プロパティ（マルチセレクト型）が設定されているか確認してください。")
            return

        # プロジェクト選択
        st.markdown("#### 1️⃣ プロジェクトを選択")
        selected_project = st.selectbox(
            "プロジェクト",
            options=projects,
            help="エクスポートするプロジェクトを選択してください",
            label_visibility="collapsed"
        )

        # 論文取得ボタン
        col1, col2 = st.columns([1, 1])
        with col1:
            fetch_button = st.button("📚 論文を取得", type="primary", use_container_width=True)
        with col2:
            if st.button("🔄 プロジェクト一覧を再読込", use_container_width=True):
                if "projects" in st.session_state:
                    del st.session_state.projects
                if "export_papers" in st.session_state:
                    del st.session_state.export_papers
                st.rerun()

        # 論文データを取得
        if fetch_button and selected_project:
            with st.spinner(f"プロジェクト '{selected_project}' の論文を取得中..."):
                try:
                    papers = asyncio.run(notion_service.query_papers_by_project(selected_project))
                    st.session_state.export_papers = papers
                    st.session_state.selected_project_name = selected_project
                except Exception as e:
                    st.error(f"論文データの取得に失敗しました: {e}")
                    logger.error(f"Failed to fetch papers for project {selected_project}: {e}")
                    st.session_state.export_papers = []

        # 取得結果の表示
        if "export_papers" in st.session_state and st.session_state.export_papers:
            papers = st.session_state.export_papers
            project_name = st.session_state.selected_project_name

            st.markdown("---")
            st.markdown(f"#### 2️⃣ 取得結果（{len(papers)}件）")

            # プレビュー表示
            with st.expander("📋 論文一覧プレビュー", expanded=True):
                for idx, paper in enumerate(papers[:10], 1):  # 最初の10件のみ
                    st.markdown(f"**{idx}. {paper['title']}**")
                    if paper['authors']:
                        authors_str = ", ".join(paper['authors'][:3])
                        if len(paper['authors']) > 3:
                            authors_str += f" ほか{len(paper['authors']) - 3}名"
                        st.caption(f"👥 {authors_str}")
                    if paper['journal']:
                        st.caption(f"📚 {paper['journal']}")
                    st.markdown("---")

                if len(papers) > 10:
                    st.info(f"他 {len(papers) - 10} 件...")

            # JSON出力
            st.markdown("#### 3️⃣ エクスポート")

            # ファイル名生成
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"papers_{project_name}_{timestamp}.json"

            # JSONデータ作成
            json_data = {
                "project": project_name,
                "exported_at": datetime.now().isoformat(),
                "total_count": len(papers),
                "papers": papers
            }

            json_str = json.dumps(json_data, ensure_ascii=False, indent=2)

            # ダウンロードボタン
            st.download_button(
                label="📥 JSONファイルをダウンロード",
                data=json_str,
                file_name=filename,
                mime="application/json",
                type="primary",
                use_container_width=True
            )

            # JSON内容のプレビュー
            with st.expander("📄 JSON内容プレビュー"):
                # 最初の2件のみ表示（見やすくする）
                preview_data = {
                    "project": project_name,
                    "exported_at": json_data["exported_at"],
                    "total_count": json_data["total_count"],
                    "papers": papers[:2]
                }
                st.json(preview_data)
                if len(papers) > 2:
                    st.info(f"注: プレビューは最初の2件のみ表示しています。完全なデータはダウンロードしたJSONファイルに含まれます。")

            st.success(f"✅ {len(papers)}件の論文をエクスポート準備完了！")

    # サイドバーで選択された論文の詳細を表示
    if st.session_state.selected_paper:
        with st.sidebar:
            st.markdown("### 📄 選択された論文")

            paper = st.session_state.selected_paper
            metadata = paper["metadata"]

            # タイトル
            st.markdown(f"**{metadata.get('title', '(タイトルなし)')}**")

            # 著者
            authors = metadata.get('authors', '')
            if authors:
                st.caption(f"👥 {format_authors(authors, max_display=5)}")

            # 雑誌・年度
            journal = metadata.get('journal', '')
            year = metadata.get('year', '')
            if journal or year:
                journal_year = []
                if journal:
                    journal_year.append(journal)
                if year:
                    journal_year.append(f"({year})")
                st.caption(f"📚 {' '.join(journal_year)}")

            # 被引用数
            citations = metadata.get('cited_by_count', '0')
            try:
                citation_count = int(citations) if citations else 0
            except (ValueError, TypeError):
                citation_count = 0
            st.metric("📊 被引用数", f"{citation_count}件")

            st.markdown("---")

            # 要約を表示
            st.markdown("**📝 要約**")
            # documentフィールドから要約全文を取得
            document = paper.get('document', '')
            if document and '\n\n' in document:
                # タイトル部分をスキップして要約のみ取得
                summary = document.split('\n\n', 1)[1].strip()
            else:
                # フォールバック: metadataのsummaryを使用
                summary = metadata.get('summary', '').strip()

            if summary:
                # 長い要約は最初の500文字のみ表示
                if len(summary) > 500:
                    st.text_area("", summary[:500] + "...", height=200, label_visibility="collapsed")
                    with st.expander("全文を表示"):
                        st.write(summary)
                else:
                    st.text_area("", summary, height=200, label_visibility="collapsed")
            else:
                st.info("要約がありません")

            st.markdown("---")

            # リンクボタン
            st.markdown("**🔗 リンク**")

            notion_url = metadata.get('notion_url')
            if notion_url:
                st.link_button("📝 Notionで開く", notion_url, use_container_width=True, type="primary")

            doi = metadata.get('doi')
            if doi:
                st.link_button("📄 DOI", doi, use_container_width=True)

            pmid = metadata.get('pmid')
            if pmid:
                st.link_button("🔬 PubMed", f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/", use_container_width=True)

            # キーワード
            keywords = metadata.get('keywords', '')
            if keywords:
                st.markdown("---")
                st.markdown("**🏷️ キーワード**")
                keyword_list = [k.strip() for k in keywords.split(',') if k.strip()]
                # キーワードをバッジとして表示
                keyword_html = ' '.join([f'<span style="background-color: #e9ecef; padding: 0.25rem 0.5rem; border-radius: 0.25rem; font-size: 0.8rem; margin-right: 0.25rem; display: inline-block; margin-bottom: 0.25rem;">{kw}</span>' for kw in keyword_list[:10]])
                st.markdown(keyword_html, unsafe_allow_html=True)

            # 閉じるボタン
            st.markdown("---")
            if st.button("✕ 閉じる", use_container_width=True):
                st.session_state.selected_paper = None
                st.rerun()

    # フッター
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #6c757d; padding: 0.5rem 0;">
        <p style="font-size: 0.85rem; margin: 0;">Paper Searcher v1.8</p>
        <p style="font-size: 0.75rem; margin: 0.25rem 0 0 0;">Gemini Embedding + gemma-3-27b-it + ChromaDB</p>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error(f"アプリケーションエラー: {e}")
        logger.error(f"Application error: {e}")
