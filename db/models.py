"""
SQLite 管理数据库 — 团队、用户、文档、查询日志
"""
import sqlite3
import os
import uuid
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "knowledge_hub.db"


def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS teams (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            team_id TEXT,
            role TEXT DEFAULT 'user',
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            team_id TEXT,
            filename TEXT,
            file_size INTEGER,
            chunks_count INTEGER,
            uploaded_at TEXT
        );

        CREATE TABLE IF NOT EXISTS query_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            team_id TEXT,
            question TEXT,
            answer_preview TEXT,
            sources TEXT,
            retrieval_count INTEGER,
            created_at TEXT
        );
    """)
    conn.commit()

    # 初始化默认数据
    now = datetime.now().isoformat()
    # 默认团队
    for tid, tname in [("t1", "售后团队"), ("t2", "产品团队"), ("t3", "运营团队")]:
        conn.execute(
            "INSERT OR IGNORE INTO teams(id, name, created_at) VALUES(?,?,?)",
            (tid, tname, now)
        )
    # 默认管理员
    conn.execute(
        "INSERT OR IGNORE INTO users(id, name, team_id, role, created_at) VALUES(?,?,?,?,?)",
        ("admin", "管理员", None, "admin", now)
    )
    conn.commit()
    conn.close()


# ====== 团队操作 ======
def list_teams():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM teams ORDER BY created_at").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_team(name: str) -> dict:
    conn = get_conn()
    tid = f"t_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    conn.execute("INSERT INTO teams(id, name, created_at) VALUES(?,?,?)", (tid, name, now))
    conn.commit()
    conn.close()
    return {"id": tid, "name": name}


def delete_team(team_id: str):
    conn = get_conn()
    conn.execute("DELETE FROM teams WHERE id=?", (team_id,))
    conn.execute("DELETE FROM users WHERE team_id=?", (team_id,))
    conn.execute("DELETE FROM documents WHERE team_id=?", (team_id,))
    conn.commit()
    conn.close()


# ====== 文档操作 ======
def add_document(team_id: str, filename: str, file_size: int, chunks_count: int) -> dict:
    conn = get_conn()
    did = f"doc_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO documents(id, team_id, filename, file_size, chunks_count, uploaded_at) VALUES(?,?,?,?,?,?)",
        (did, team_id, filename, file_size, chunks_count, now)
    )
    conn.commit()
    conn.close()
    return {"id": did, "filename": filename}


def list_documents(team_id: str):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM documents WHERE team_id=? ORDER BY uploaded_at DESC", (team_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_document(doc_id: str):
    conn = get_conn()
    conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    conn.commit()
    conn.close()


# ====== 查询日志 ======
def log_query(user_id: str, team_id: str, question: str, answer_preview: str, sources: str, retrieval_count: int):
    conn = get_conn()
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO query_logs(user_id, team_id, question, answer_preview, sources, retrieval_count, created_at) VALUES(?,?,?,?,?,?,?)",
        (user_id, team_id, question, answer_preview, sources, retrieval_count, now)
    )
    conn.commit()
    conn.close()


def get_stats(team_id: str = None):
    """获取统计数据"""
    conn = get_conn()
    query = "SELECT * FROM query_logs"
    params = []
    if team_id:
        query += " WHERE team_id=?"
        params.append(team_id)
    rows = conn.execute(query + " ORDER BY created_at DESC LIMIT 200", params).fetchall()

    total = conn.execute("SELECT COUNT(*) FROM query_logs" + (" WHERE team_id=?" if team_id else ""), params).fetchone()[0]

    conn.close()

    return {
        "total_queries": total,
        "recent_logs": [dict(r) for r in rows],
    }


# 初始化
init_db()
