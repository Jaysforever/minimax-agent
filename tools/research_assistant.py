"""
科研助手（合并论文阅读 + 文献搜索）。
功能：
  1. 论文阅读：上传 PDF → 分析/问答
  2. 文献搜索：Semantic Scholar API → 搜索论文 → AI 总结
  3. 研究报告：基于搜索结果生成结构化报告
"""

import re
import requests
import streamlit as st
from core.model import chat
from prompts.research import PROMPTS_DICT, ANALYSIS_BUTTONS

# Semantic Scholar API（免费，无需 key，有限流）
S2_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
S2_FIELDS = "title,abstract,authors,year,citationCount,url,venue,publicationDate"

# arXiv API（免费，无限流）
ARXIV_SEARCH_URL = "http://export.arxiv.org/api/query"


# ====================== 工具函数 ======================

def _call_api_and_stream(messages: list[dict], system_prompt: str = "", placeholder=None) -> str:
    """调用 API 流式输出，实时更新 placeholder。"""
    full_text = ""
    for chunk in chat(messages=messages, system_prompt=system_prompt):
        full_text += chunk
        if placeholder:
            placeholder.markdown(full_text + "▌")
    if placeholder:
        placeholder.markdown(full_text)
    return full_text


def extract_pdf_text(uploaded_file) -> str:
    """从上传的 PDF 提取全文。"""
    try:
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(uploaded_file.getvalue()))
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n\n"
        return text.strip()
    except Exception as e:
        st.error(f"PDF 解析失败: {e}")
        return ""


def _search_semantic_scholar(query: str, limit: int, year_from: int = None) -> list[dict] | None:
    """Semantic Scholar 搜索。"""
    params = {"query": query, "limit": min(limit, 20), "fields": S2_FIELDS}
    if year_from:
        params["year"] = f"{year_from}-"
    try:
        resp = requests.get(S2_SEARCH_URL, params=params, timeout=30)
        if resp.status_code != 200:
            return None
        data = resp.json()
        papers = []
        for p in data.get("data", []):
            authors = ", ".join(a.get("name", "") for a in (p.get("authors") or [])[:3])
            if len(p.get("authors") or []) > 3:
                authors += " et al."
            papers.append({
                "title": p.get("title", ""),
                "abstract": p.get("abstract", "") or "(无摘要)",
                "authors": authors,
                "year": p.get("year", ""),
                "citations": p.get("citationCount", 0),
                "url": p.get("url", ""),
                "venue": p.get("venue", ""),
            })
        return papers
    except Exception:
        return None


def _search_arxiv(query: str, limit: int, year_from: int = None) -> list[dict] | None:
    """arXiv 搜索（备选）。"""
    try:
        import xml.etree.ElementTree as ET
        params = {"search_query": f"all:{query}", "start": 0, "max_results": min(limit, 20)}
        resp = requests.get(ARXIV_SEARCH_URL, params=params, timeout=30)
        if resp.status_code != 200:
            return None

        root = ET.fromstring(resp.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        papers = []
        for entry in root.findall("atom:entry", ns):
            title = entry.find("atom:title", ns)
            summary = entry.find("atom:summary", ns)
            published = entry.find("atom:published", ns)
            link = entry.find("atom:id", ns)
            authors = entry.findall("atom:author/atom:name", ns)

            year = published.text[:4] if published is not None else ""
            if year_from and year and int(year) < year_from:
                continue

            author_names = [a.text for a in authors[:3]]
            if len(authors) > 3:
                author_names.append("et al.")

            papers.append({
                "title": title.text.strip().replace("\n", " ") if title is not None else "",
                "abstract": summary.text.strip()[:500] if summary is not None else "(无摘要)",
                "authors": ", ".join(author_names),
                "year": year,
                "citations": 0,
                "url": link.text if link is not None else "",
                "venue": "arXiv",
            })
        return papers
    except Exception:
        return None


def search_papers(query: str, limit: int = 10, year_from: int = None) -> list[dict] | None:
    """
    搜索论文。优先 Semantic Scholar，失败自动切 arXiv。
    返回 [{"title", "abstract", "authors", "year", "citations", "url", "venue"}, ...]
    """
    # 先试 Semantic Scholar
    papers = _search_semantic_scholar(query, limit, year_from)
    if papers:
        return papers

    # 失败则切 arXiv
    st.info("Semantic Scholar 不可用，已切换到 arXiv...")
    papers = _search_arxiv(query, limit, year_from)
    if papers:
        return papers

    st.error("两个搜索源都不可用，请稍后重试")
    return None


# ====================== Tab 1: 论文阅读 ======================

def _render_paper_reader():
    """论文阅读：支持上传多个 PDF → 分析/问答。"""
    st.subheader("📄 上传论文（支持多篇）")

    uploaded_files = st.file_uploader("上传 PDF 论文", type=["pdf"], accept_multiple_files=True, key="paper_upload")

    if uploaded_files:
        # 解析所有 PDF
        papers = []
        for f in uploaded_files:
            text = extract_pdf_text(f)
            if text:
                papers.append({"name": f.name, "text": text})

        if papers:
            st.session_state.paper_list = papers
            st.success(f"✅ 已解析 {len(papers)} 篇论文：" + "、".join(p["name"] for p in papers))

    if not st.session_state.get("paper_list"):
        return

    papers = st.session_state.paper_list

    # 论文选择（单篇 or 全部）
    paper_options = ["📑 全部论文（综合分析）"] + [f"📄 {p['name']}" for p in papers]
    selected = st.selectbox("选择分析范围", paper_options, key="paper_scope")

    if selected.startswith("📑"):
        # 全部论文：拼接内容
        all_text = "\n\n---\n\n".join(
            f"【{p['name']}】\n{p['text'][:4000]}" for p in papers
        )
        paper_text = all_text
        scope_label = f"全部 {len(papers)} 篇"
    else:
        # 单篇
        idx = paper_options.index(selected) - 1
        paper_text = papers[idx]["text"]
        scope_label = papers[idx]["name"]

    # 一键分析按钮
    st.divider()
    st.subheader(f"🔬 一键分析 — {scope_label}")
    cols = st.columns(len(ANALYSIS_BUTTONS))
    for idx, btn in enumerate(ANALYSIS_BUTTONS):
        with cols[idx]:
            if st.button(btn["label"], key=f"paper_{btn['key']}", use_container_width=True):
                prompt = PROMPTS_DICT[btn["prompt_key"]]
                st.session_state.paper_conversation.append({"role": "user", "content": prompt})
                with st.chat_message("user"):
                    st.markdown(prompt)
                with st.chat_message("assistant"):
                    placeholder = st.empty()
                    answer = _call_api_and_stream(
                        messages=[{"role": "user", "content": f"论文内容：\n{paper_text[:12000]}\n\n问题：{prompt}"}],
                        system_prompt=PROMPTS_DICT["paper_system"],
                        placeholder=placeholder,
                    )
                st.session_state.paper_conversation.append({"role": "assistant", "content": answer})
                st.rerun()

    # 多轮对话
    st.divider()
    st.subheader(f"💬 追问 — {scope_label}")

    for msg in st.session_state.get("paper_conversation", []):
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if user_q := st.chat_input("基于论文内容提问...", key="paper_chat"):
        st.session_state.paper_conversation.append({"role": "user", "content": user_q})
        with st.chat_message("user"):
            st.markdown(user_q)

        messages = [{"role": "user", "content": f"论文内容：\n{paper_text[:12000]}\n\n问题：{user_q}"}]
        with st.chat_message("assistant"):
            placeholder = st.empty()
            answer = _call_api_and_stream(
                messages=messages,
                system_prompt=PROMPTS_DICT["paper_system"],
                placeholder=placeholder,
            )
        st.session_state.paper_conversation.append({"role": "assistant", "content": answer})

    # 清空按钮
    if st.session_state.get("paper_conversation"):
        if st.button("🗑️ 清空对话", key="paper_clear"):
            st.session_state.paper_conversation = []
            st.rerun()


# ====================== Tab 2: 文献搜索 ======================

def _render_paper_search():
    """文献搜索：Semantic Scholar → AI 总结。"""
    st.subheader("🔍 搜索论文")

    col1, col2 = st.columns([3, 1])
    with col1:
        query = st.text_input("搜索关键词", placeholder="例如：large language model, transformer, diffusion model", key="search_query")
    with col2:
        limit = st.slider("数量", 5, 20, 10, key="search_limit")

    col3, col4 = st.columns(2)
    with col3:
        year_from = st.number_input("起始年份（可选）", min_value=1990, max_value=2026, value=2023, step=1, key="search_year")
    with col4:
        st.markdown("<br>", unsafe_allow_html=True)
        search_btn = st.button("🔍 搜索", type="primary", disabled=not query.strip(), use_container_width=True)

    if search_btn:
        with st.spinner(f"正在搜索「{query}」..."):
            papers = search_papers(query, limit=limit, year_from=year_from)
            if papers:
                st.session_state.search_results = papers
                st.session_state.search_query_text = query
            else:
                st.session_state.search_results = []

    # 显示搜索结果
    if st.session_state.get("search_results"):
        papers = st.session_state.search_results
        st.divider()
        st.subheader(f"📋 搜索结果（{len(papers)} 篇）")

        # 按引用量排序
        papers_sorted = sorted(papers, key=lambda p: p.get("citations", 0), reverse=True)

        for idx, p in enumerate(papers_sorted):
            with st.expander(
                f"**{idx+1}. {p['title']}** "
                f"({p['year']}) — 引用: {p['citations']} — {p['venue'] or 'N/A'}",
                expanded=False,
            ):
                st.markdown(f"**作者**: {p['authors']}")
                st.markdown(f"**摘要**: {p['abstract'][:500]}{'...' if len(p['abstract']) > 500 else ''}")
                if p['url']:
                    st.markdown(f"**链接**: [{p['url']}]({p['url']})")

        # AI 总结按钮
        st.divider()
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("🤖 AI 分类总结", type="primary", use_container_width=True):
                papers_text = ""
                for i, p in enumerate(papers_sorted[:15]):
                    papers_text += f"{i+1}. [{p['year']}] {p['title']} (引用:{p['citations']})\n   摘要: {p['abstract'][:200]}\n\n"

                prompt = PROMPTS_DICT["search_summary_prompt"].format(
                    query=st.session_state.get("search_query_text", ""),
                    count=len(papers_sorted),
                    papers_text=papers_text,
                )

                st.session_state.search_summary = ""
                with st.spinner("AI 正在分析..."):
                    summary = _call_api_and_stream(
                        messages=[{"role": "user", "content": prompt}],
                        system_prompt=PROMPTS_DICT["search_summary_system"],
                    )
                    st.session_state.search_summary = summary
                st.rerun()

        with col_b:
            if st.button("📝 生成研究报告", use_container_width=True):
                papers_text = ""
                for i, p in enumerate(papers_sorted[:15]):
                    papers_text += f"{i+1}. [{p['year']}] {p['title']} (引用:{p['citations']})\n   摘要: {p['abstract'][:300]}\n\n"

                with st.spinner("AI 正在生成报告..."):
                    report = _call_api_and_stream(
                        messages=[{"role": "user", "content": f"请根据以下论文生成研究报告：\n\n{papers_text}"}],
                        system_prompt=PROMPTS_DICT["report_system"],
                    )
                    st.session_state.search_report = report
                st.rerun()

    # 显示 AI 总结
    if st.session_state.get("search_summary"):
        st.divider()
        st.subheader("🤖 AI 分类总结")
        st.markdown(st.session_state.search_summary)

    # 显示研究报告
    if st.session_state.get("search_report"):
        st.divider()
        st.subheader("📝 研究报告")
        st.markdown(st.session_state.search_report)
        st.download_button(
            label="⬇️ 下载报告",
            data=st.session_state.search_report,
            file_name=f"research_report_{st.session_state.get('search_query_text', 'report')}.md",
            mime="text/markdown",
            use_container_width=True,
        )


# ====================== Tab 3: 每日精读 ======================

def _render_daily_reading():
    """每日精读：自动推荐高价值论文 → AI 精讲 → 边看 PDF 边提问。"""
    st.subheader("📚 每日论文精读")
    st.caption("自动从多个热门方向筛选近期高价值论文，无需输入关键词")

    # ---- 自动搜索（首次进入或点击刷新） ----
    HOT_TOPICS = [
        "large language model",
        "multimodal large language model",
        "AI agent",
        "retrieval augmented generation",
        "diffusion model",
        "reasoning chain of thought",
    ]

    col_r1, col_r2 = st.columns([4, 1])
    with col_r1:
        if not st.session_state.daily_papers:
            st.info("点击右侧按钮，AI 将自动从 6 个热门方向筛选近期最值得学习的论文")
    with col_r2:
        refresh_btn = st.button("🔄 刷新推荐", type="primary", use_container_width=True)

    # 首次进入自动搜索
    if not st.session_state.daily_papers or refresh_btn:
        all_papers = []
        with st.spinner("正在从多个热门方向搜索高价值论文..."):
            for topic in HOT_TOPICS:
                papers = search_papers(topic, limit=5, year_from=2024)
                if papers:
                    all_papers.extend(papers)

        if all_papers:
            # 去重（按标题）
            seen = set()
            unique = []
            for p in all_papers:
                key = p["title"].lower().strip()
                if key not in seen:
                    seen.add(key)
                    unique.append(p)

            # 按引用量排序，取前 10
            papers_sorted = sorted(unique, key=lambda p: p.get("citations", 0), reverse=True)[:10]
            st.session_state.daily_papers = papers_sorted
            st.session_state.daily_selected = -1
            st.session_state.daily_explanations = {}
            st.session_state.daily_chats = {}
        else:
            st.warning("搜索失败，请稍后重试")
        st.rerun()

    # ---- 论文列表 ----
    if st.session_state.daily_papers:
        papers = st.session_state.daily_papers
        st.divider()
        st.subheader(f"📋 推荐论文（{len(papers)} 篇）— {st.session_state.daily_topic}")

        for idx, p in enumerate(papers):
            is_selected = st.session_state.daily_selected == idx
            icon = "⭐" if is_selected else "📄"
            citation_badge = f"🔥{p['citations']}" if p['citations'] > 50 else f"引用:{p['citations']}"

            col_btn, col_info = st.columns([1, 5])
            with col_btn:
                if st.button(f"{icon} 精读", key=f"daily_btn_{idx}", use_container_width=True):
                    st.session_state.daily_selected = idx
                    st.rerun()
            with col_info:
                st.markdown(
                    f"**{idx+1}. {p['title']}** "
                    f"({p['year']}) — {citation_badge} — {p['venue'] or 'N/A'}"
                )
                st.caption(f"👤 {p['authors']}")

    # ---- 精读区域 ----
    if st.session_state.daily_selected >= 0 and st.session_state.daily_papers:
        idx = st.session_state.daily_selected
        paper = st.session_state.daily_papers[idx]

        st.divider()
        st.subheader(f"📖 精读：{paper['title']}")

        # 左右布局：PDF 预览 + AI 讲解/提问
        col_pdf, col_ai = st.columns([1, 1])

        # ---- 左侧：PDF 预览 ----
        with col_pdf:
            st.markdown("**📄 论文预览**")
            pdf_url = paper.get("url", "")
            # arXiv 论文转 PDF 链接
            if "arxiv.org" in pdf_url:
                arxiv_id = pdf_url.split("/abs/")[-1] if "/abs/" in pdf_url else pdf_url.split("/")[-1]
                pdf_viewer_url = f"https://arxiv.org/pdf/{arxiv_id}"
            else:
                pdf_viewer_url = pdf_url

            if pdf_viewer_url:
                st.markdown(f"🔗 [在新标签页打开 PDF]({pdf_viewer_url})")
                # 嵌入 PDF（直接用 PDF URL，浏览器原生渲染）
                st.markdown(
                    f'<iframe src="{pdf_viewer_url}" '
                    f'style="width:100%;height:600px;border:1px solid #ddd;border-radius:8px;" '
                    f'frameborder="0"></iframe>',
                    unsafe_allow_html=True,
                )
            else:
                st.info("无 PDF 链接可用")

            # 论文基本信息
            with st.expander("📋 论文信息", expanded=False):
                st.markdown(f"**标题**: {paper['title']}")
                st.markdown(f"**作者**: {paper['authors']}")
                st.markdown(f"**年份**: {paper['year']}")
                st.markdown(f"**引用**: {paper['citations']}")
                st.markdown(f"**期刊/会议**: {paper['venue'] or 'N/A'}")
                st.markdown(f"**摘要**: {paper['abstract']}")

        # ---- 右侧：AI 讲解 + 提问 ----
        with col_ai:
            st.markdown("**🤖 AI 精讲**")

            # 生成精讲按钮
            if idx not in st.session_state.daily_explanations:
                if st.button("🎓 让 AI 精讲这篇论文", type="primary", key=f"daily_explain_{idx}", use_container_width=True):
                    with st.spinner("AI 正在深度解读论文..."):
                        explain_prompt = (
                            f"请对以下论文进行深度精讲，帮助学生理解：\n\n"
                            f"标题：{paper['title']}\n"
                            f"作者：{paper['authors']}\n"
                            f"摘要：{paper['abstract']}\n\n"
                            f"请按以下结构讲解：\n"
                            f"1. **论文背景**：这篇论文解决什么问题？为什么重要？\n"
                            f"2. **核心方法**：用了什么技术？关键创新点是什么？\n"
                            f"3. **实验结果**：主要结果是什么？和之前的方法比如何？\n"
                            f"4. **个人点评**：这篇论文的优缺点？对后续研究的启发？\n"
                            f"5. **关键概念**：列出 3-5 个需要了解的核心概念\n\n"
                            f"用中文讲解，通俗易懂，适合研究生阅读。"
                        )
                        explanation = _call_api_and_stream(
                            messages=[{"role": "user", "content": explain_prompt}],
                            system_prompt="你是一位资深科研导师，擅长用通俗易懂的方式讲解学术论文。",
                        )
                        st.session_state.daily_explanations[idx] = explanation
                    st.rerun()
            else:
                # 显示已有精讲
                st.markdown(st.session_state.daily_explanations[idx])

            # ---- 提问区域 ----
            st.divider()
            st.markdown("**💬 针对这篇论文提问**")

            # 初始化该论文的对话
            if idx not in st.session_state.daily_chats:
                st.session_state.daily_chats[idx] = []

            # 显示对话历史
            for msg in st.session_state.daily_chats[idx]:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])

            # 提问输入
            if user_q := st.chat_input(f"关于「{paper['title'][:30]}...」提问", key=f"daily_chat_{idx}"):
                st.session_state.daily_chats[idx].append({"role": "user", "content": user_q})
                with st.chat_message("user"):
                    st.markdown(user_q)

                context = f"论文标题：{paper['title']}\n摘要：{paper['abstract']}"
                if idx in st.session_state.daily_explanations:
                    context += f"\n\nAI 精讲内容：\n{st.session_state.daily_explanations[idx][:2000]}"

                messages = [
                    {"role": "user", "content": f"{context}\n\n用户问题：{user_q}"}
                ]
                with st.chat_message("assistant"):
                    placeholder = st.empty()
                    answer = _call_api_and_stream(
                        messages=messages,
                        system_prompt="你是一位科研导师，根据论文内容和精讲内容回答学生问题。用中文回答。",
                        placeholder=placeholder,
                    )
                st.session_state.daily_chats[idx].append({"role": "assistant", "content": answer})

            # 清空对话
            if st.session_state.daily_chats.get(idx):
                if st.button("🗑️ 清空对话", key=f"daily_clear_{idx}"):
                    st.session_state.daily_chats[idx] = []
                    st.rerun()


# ====================== 主入口 ======================

def render():
    st.title("🔬 科研助手")
    st.caption("论文阅读 · 文献搜索 · 研究报告")

    # 会话状态
    defaults = {
        "paper_text": "",
        "paper_conversation": [],
        "search_results": [],
        "search_query_text": "",
        "search_summary": "",
        "search_report": "",
        "daily_papers": [],           # 每日精读论文列表
        "daily_topic": "",            # 精读主题
        "daily_selected": -1,         # 当前选中的论文索引
        "daily_explanations": {},      # {index: explanation_text}
        "daily_chats": {},            # {index: [{"role": ..., "content": ...}]}
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

    tab1, tab2, tab3 = st.tabs(["📄 论文阅读", "🔍 文献搜索", "📚 每日精读"])

    with tab1:
        st.caption("上传 PDF → 一键分析 / 多轮问答")
        _render_paper_reader()

    with tab2:
        st.caption("搜索最新论文 → AI 分类总结 → 生成研究报告")
        _render_paper_search()

    with tab3:
        st.caption("自动推荐近期高价值论文 → AI 精讲 → 边看 PDF 边提问")
        _render_daily_reading()
