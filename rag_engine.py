"""
多租户 RAG 引擎 — 每个团队独立的 ChromaDB Collection

改进：
- 中文友好的嵌入模型（text2vec-base-chinese）
- 智能文本切片（段落 + 句子边界感知）
- 线程安全初始化
- 多轮对话支持
"""
import re
import threading
from pathlib import Path
from datetime import datetime

import chromadb
from chromadb.utils import embedding_functions

from config import client
from db.models import log_query

CHROMA_PATH = Path(__file__).parent / "chroma_db"
_chroma_client = None
_embed_fn = None
_lock = threading.Lock()

# 每个团队的对话历史 {team_id: [{role, content}, ...]}
_conversations: dict[str, list[dict]] = {}
MAX_HISTORY_ROUNDS = 5  # 保留最近 N 轮对话


def _get_chroma():
    """线程安全的 ChromaDB 客户端懒加载"""
    global _chroma_client, _embed_fn
    if _chroma_client is None:
        with _lock:
            if _chroma_client is None:  # double-check
                _chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
                try:
                    _embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
                        model_name="shibing624/text2vec-base-chinese"
                    )
                except Exception:
                    # 如果 sentence-transformers 不可用，回退到默认嵌入
                    _embed_fn = embedding_functions.DefaultEmbeddingFunction()
    return _chroma_client, _embed_fn


def get_collection(team_id: str):
    """获取或创建团队的 ChromaDB Collection"""
    cl, emb_fn = _get_chroma()
    name = f"team_{team_id}"
    return cl.get_or_create_collection(name, embedding_function=emb_fn)


# ====== 智能文本切片 ======

def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 100) -> list[str]:
    """
    智能文本切片 — 优先按段落边界切分，其次按句子边界，最后按固定长度。
    保证每个切片不截断句子，并提供重叠上下文。
    """
    if not text or not text.strip():
        return []

    # Step 1: 按段落切分（连续空行）
    paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[str] = []

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        if len(para) <= chunk_size:
            chunks.append(para)
        else:
            # Step 2: 段落过长 → 按句子边界切分（中英文句尾标点）
            sentences = re.split(r"(?<=[。！？.!?])\s*", para)
            current = ""
            for sent in sentences:
                sent = sent.strip()
                if not sent:
                    continue
                if len(current) + len(sent) <= chunk_size:
                    current += sent
                else:
                    if current:
                        chunks.append(current.strip())
                    # Step 3: 单句超过 chunk_size → 按长度切分并保留 overlap
                    if len(sent) > chunk_size:
                        for i in range(0, len(sent), chunk_size - overlap):
                            chunks.append(sent[i : i + chunk_size].strip())
                        current = ""
                    else:
                        current = sent
            if current.strip():
                chunks.append(current.strip())

    return chunks


# ====== 文档管理 ======

def upload_file(team_id: str, file_content: str, filename: str) -> int:
    """上传文档内容，智能切片后存入 ChromaDB"""
    collection = get_collection(team_id)
    chunks = _chunk_text(file_content)
    if not chunks:
        return 0

    ts = datetime.now().timestamp()
    ids = [f"{team_id}_{ts}_{i}" for i in range(len(chunks))]
    collection.add(
        documents=chunks,
        metadatas=[{"team_id": team_id, "filename": filename} for _ in chunks],
        ids=ids,
    )
    return len(chunks)


def delete_document(team_id: str, filename: str) -> int:
    """删除指定文件的所有切片"""
    collection = get_collection(team_id)
    try:
        result = collection.get(where={"filename": filename})
        if result and result["ids"]:
            collection.delete(ids=result["ids"])
            return len(result["ids"])
    except Exception:
        pass
    return 0


def delete_team_docs(team_id: str):
    """清空团队的整个知识库（删除 Collection）"""
    cl, _ = _get_chroma()
    try:
        cl.delete_collection(f"team_{team_id}")
    except Exception:
        pass


def list_team_docs(team_id: str) -> list[dict]:
    """列出团队知识库中的所有文件及切片数"""
    try:
        collection = get_collection(team_id)
        if collection.count() == 0:
            return []
        data = collection.get()
        files: dict[str, int] = {}
        for meta in data["metadatas"]:
            fname = meta.get("filename", "未知")
            files[fname] = files.get(fname, 0) + 1
        return [{"filename": k, "chunks": v} for k, v in files.items()]
    except Exception:
        return []


# ====== 检索 ======

def search(team_id: str, question: str, top_k: int = 3) -> list[dict]:
    """在团队知识库中检索相关文档"""
    try:
        collection = get_collection(team_id)
        if collection.count() == 0:
            return []
        results = collection.query(query_texts=[question], n_results=top_k)
        docs = []
        if results.get("documents") and results["documents"][0]:
            for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
                docs.append({"content": doc, "source": meta.get("filename", "未知")})
        return docs
    except Exception:
        return []


# ====== 对话管理 ======

def get_conversation_history(team_id: str) -> list[dict]:
    """获取团队的对话历史"""
    return _conversations.get(team_id, [])


def clear_conversation(team_id: str):
    """清空团队的对话历史"""
    _conversations.pop(team_id, None)


def _append_to_history(team_id: str, role: str, content: str):
    """向对话历史追加一条消息，自动裁剪到 MAX_HISTORY_ROUNDS 轮"""
    if team_id not in _conversations:
        _conversations[team_id] = []
    _conversations[team_id].append({"role": role, "content": content})
    # 保留最近 N 轮（每轮 = user + assistant）
    max_messages = MAX_HISTORY_ROUNDS * 2
    if len(_conversations[team_id]) > max_messages:
        _conversations[team_id] = _conversations[team_id][-max_messages:]


# ====== 问答 ======

def ask(
    team_id: str,
    user_id: str,
    question: str,
    history: list[dict] | None = None,
) -> dict:
    """
    基于团队知识库回答问题。

    Args:
        team_id: 团队 ID
        user_id: 用户 ID
        question: 用户问题
        history: 对话历史（可选），格式 [{"role": "user/assistant", "content": "..."}]
    """
    docs = search(team_id, question)

    # 构建系统提示
    if docs:
        ctx = "\n\n".join(
            [f"[{d['source']}]\n{d['content'][:500]}" for d in docs]
        )
        system_prompt = (
            "你是知识库助手，严格基于提供的文档回答问题。"
            "如果文档中没有相关信息，请明确告知用户并建议上传相关文档。\n\n"
            f"参考文档:\n{ctx}"
        )
    else:
        system_prompt = (
            "你是知识库助手。知识库中暂无相关文档，"
            "请告知用户并建议上传相关文件。"
        )

    # 构建消息列表
    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    # 如果有历史对话，加入上下文
    if history:
        messages.extend(history)

    messages.append({"role": "user", "content": question})

    # 调用 LLM
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.3,
            max_tokens=800,
        )
        answer = resp.choices[0].message.content
    except Exception as e:
        answer = f"模型调用失败: {e}"

    # 记录日志
    sources = ",".join(set(d["source"] for d in docs)) if docs else "无"
    log_query(user_id, team_id, question, answer[:200], sources, len(docs))

    # 保存对话历史
    _append_to_history(team_id, "user", question)
    _append_to_history(team_id, "assistant", answer)

    return {
        "answer": answer,
        "sources": [d["source"] for d in docs],
        "docs": docs,
        "retrieval_count": len(docs),
    }
