"""
多租户 RAG 引擎 — 每个团队独立的 ChromaDB Collection
"""
from pathlib import Path
from datetime import datetime
import chromadb
from chromadb.utils import embedding_functions
from config import client
from db.models import log_query

CHROMA_PATH = Path(__file__).parent / "chroma_db"
_chroma_client = None
_embed_fn = None


def _get_chroma():
    global _chroma_client, _embed_fn
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        _embed_fn = embedding_functions.DefaultEmbeddingFunction()
    return _chroma_client, _embed_fn


def get_collection(team_id: str):
    cl, emb_fn = _get_chroma()
    name = f"team_{team_id}"
    try:
        return cl.get_collection(name, embedding_function=emb_fn)
    except Exception:
        return cl.create_collection(name, embedding_function=emb_fn)


def upload_file(team_id: str, file_content: str, filename: str) -> int:
    collection = get_collection(team_id)
    chunks = []
    current = ""
    for line in file_content.split("\n"):
        current += line + " "
        if len(current) > 400:
            chunks.append(current.strip())
            current = current[-100:] if len(current) > 100 else ""
    if current:
        chunks.append(current.strip())
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


def search(team_id: str, question: str, top_k: int = 3) -> list:
    try:
        collection = get_collection(team_id)
        if collection.count() == 0:
            return []
        results = collection.query(query_texts=[question], n_results=top_k)
        docs = []
        if results["documents"] and results["documents"][0]:
            for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
                docs.append({"content": doc, "source": meta.get("filename", "未知")})
        return docs
    except Exception:
        return []


def ask(team_id: str, user_id: str, question: str) -> dict:
    docs = search(team_id, question)

    if docs:
        ctx = "\n\n".join([f"[{d['source']}]\n{d['content'][:500]}" for d in docs])
        system_prompt = f"你是知识库助手，基于文档回答。不知道就说不知道。\n\n文档:\n{ctx}"
    else:
        system_prompt = "你是知识库助手。知识库中暂无相关文档，请告知用户并建议上传。"

    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=0.3,
            max_tokens=800,
        )
        answer = resp.choices[0].message.content
    except Exception as e:
        answer = f"调用失败: {e}"

    sources = ",".join(set(d["source"] for d in docs)) if docs else "无"
    log_query(user_id, team_id, question, answer[:200], sources, len(docs))

    return {
        "answer": answer,
        "sources": [d["source"] for d in docs],
        "docs": docs,
        "retrieval_count": len(docs),
    }


def list_team_docs(team_id: str):
    collection = get_collection(team_id)
    if collection.count() == 0:
        return []
    data = collection.get()
    files = {}
    for meta in data["metadatas"]:
        fname = meta.get("filename", "未知")
        files[fname] = files.get(fname, 0) + 1
    return [{"filename": k, "chunks": v} for k, v in files.items()]


def delete_team_docs(team_id: str):
    cl, _ = _get_chroma()
    try:
        cl.delete_collection(f"team_{team_id}")
    except Exception:
        pass
