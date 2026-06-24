"""
RAG 知识库中台 — Streamlit 统一平台
"""
import streamlit as st
from db.models import list_teams, create_team, delete_team, add_document, get_stats
from rag_engine import ask, upload_file, list_team_docs, delete_team_docs

st.set_page_config(page_title="知识库中台", page_icon="📚", layout="wide")

if "user_id" not in st.session_state:
    st.session_state.user_id = "admin"
if "current_team" not in st.session_state:
    st.session_state.current_team = None

# ====== 侧边栏 ======
teams = list_teams()
with st.sidebar:
    st.markdown("### 📚 知识库中台")
    team_names = {t["name"]: t["id"] for t in teams}
    selected_name = st.selectbox(
        "选择团队",
        list(team_names.keys()),
        index=None,
        placeholder="选择一个团队..."
    )
    if selected_name:
        st.session_state.current_team = team_names[selected_name]
    st.markdown("---")
    st.caption(f"用户: {st.session_state.user_id}")

# ====== 头部 ======
st.markdown("## 📚 RAG 知识库中台")
st.caption("多租户隔离 | ChromaDB | DeepSeek | 使用统计")

if st.session_state.current_team is None:
    st.info("👈 请在左侧选择一个团队开始使用")
else:
    team_id = st.session_state.current_team
    team_name = next((t["name"] for t in teams if t["id"] == team_id), "")

    tab1, tab2, tab3, tab4 = st.tabs(["💬 问答", "📁 文档", "👥 团队", "📊 统计"])

    # Tab 1: 问答
    with tab1:
        st.markdown(f"### {team_name} — 知识问答")
        docs = list_team_docs(team_id)
        if not docs:
            st.warning("知识库为空，请先到「文档」页面上传。")

        question = st.text_area("问题", placeholder="在知识库中搜索...", height=80, label_visibility="collapsed")
        if st.button("🔍 提问", type="primary") and question.strip():
            with st.spinner("检索中..."):
                result = ask(team_id, st.session_state.user_id, question.strip())
            st.markdown(result["answer"])
            if result["docs"]:
                with st.expander(f"检索到 {result['retrieval_count']} 条文档"):
                    for d in result["docs"]:
                        st.caption(f"📄 {d['source']}")
                        st.text(d["content"][:300])

    # Tab 2: 文档管理
    with tab2:
        st.markdown(f"### {team_name} — 文档管理")
        uploaded = st.file_uploader("上传文档", type=["txt", "md"], key=f"up_{team_id}")
        if uploaded:
            content = uploaded.read().decode("utf-8")
            chunks = upload_file(team_id, content, uploaded.name)
            add_document(team_id, uploaded.name, len(content), chunks)
            st.success(f"「{uploaded.name}」已上传，{chunks} 切片入库")
            st.rerun()

        docs = list_team_docs(team_id)
        if docs:
            for d in docs:
                col_a, col_b = st.columns([5, 1])
                with col_a:
                    st.markdown(f"📄 {d['filename']} — {d['chunks']} 切片")
                with col_b:
                    if st.button("删除", key=f"del_{d['filename']}_{team_id}"):
                        delete_team_docs(team_id)
                        st.success("已清空知识库")
                        st.rerun()

    # Tab 3: 团队管理
    with tab3:
        st.markdown("### 团队管理")
        col1, col2 = st.columns([4, 1])
        with col1:
            new_name = st.text_input("新建团队", placeholder="团队名称", label_visibility="collapsed")
        with col2:
            if st.button("创建", use_container_width=True) and new_name.strip():
                create_team(new_name.strip())
                st.success(f"「{new_name.strip()}」已创建")
                st.rerun()

        for t in teams:
            col_a, col_b, col_c = st.columns([4, 2, 1])
            with col_a:
                st.markdown(f"🏢 **{t['name']}**")
            with col_b:
                st.caption(f"{len(list_team_docs(t['id']))} 个文档")
            with col_c:
                if t["id"] not in ["t1", "t2", "t3"]:
                    if st.button("删除", key=f"delteam_{t['id']}"):
                        delete_team(t["id"])
                        delete_team_docs(t["id"])
                        st.rerun()

    # Tab 4: 统计
    with tab4:
        st.markdown(f"### {team_name} — 统计")
        stats = get_stats(team_id)
        st.metric("总查询", stats["total_queries"])
        logs = stats["recent_logs"]
        if logs:
            for log in logs[:20]:
                with st.expander(f"{log['question'][:50]}... — {log['created_at'][:16]}"):
                    st.caption(f"检索: {log['retrieval_count']} 条 | 来源: {log['sources']}")
                    st.text(log['answer_preview'][:200])

st.markdown("---")
st.caption("ChromaDB 多租户 | DeepSeek V3 | SQLite | 团队隔离")
