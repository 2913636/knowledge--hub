"""
SQLite 管理数据库 — 团队、用户、文档、查询日志
"""
import sqlite3
import os
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "knowledge_hub.db"


def _get_conn():
    """创建数据库连接（row_factory 设为 Row 以支持字典式访问）"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db():
    """数据库连接上下文管理器 — 自动 commit/close"""
    conn = _get_conn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ====== 数据库初始化 ======

def init_db():
    """初始化数据库表结构和默认数据（幂等）"""
    with get_db() as conn:
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

            CREATE INDEX IF NOT EXISTS idx_documents_team
                ON documents(team_id);
            CREATE INDEX IF NOT EXISTS idx_query_logs_team
                ON query_logs(team_id);
            CREATE INDEX IF NOT EXISTS idx_query_logs_user
                ON query_logs(user_id);
            CREATE INDEX IF NOT EXISTS idx_query_logs_created
                ON query_logs(created_at);
        """)

        # 初始化默认数据
        now = datetime.now().isoformat()
        for tid, tname in [("t1", "售后团队"), ("t2", "产品团队"), ("t3", "运营团队")]:
            conn.execute(
                "INSERT OR IGNORE INTO teams(id, name, created_at) VALUES(?,?,?)",
                (tid, tname, now),
            )
        conn.execute(
            "INSERT OR IGNORE INTO users(id, name, team_id, role, created_at) VALUES(?,?,?,?,?)",
            ("admin", "管理员", None, "admin", now),
        )


def ensure_db():
    """确保数据库已初始化（幂等，可重复调用）"""
    init_db()


# ====== 团队操作 ======

def list_teams():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM teams ORDER BY created_at").fetchall()
    return [dict(r) for r in rows]


def create_team(name: str) -> dict:
    tid = f"t_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO teams(id, name, created_at) VALUES(?,?,?)",
            (tid, name, now),
        )
    return {"id": tid, "name": name}


def delete_team(team_id: str):
    """删除团队及其关联的用户和文档（SQLite 层）"""
    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE team_id=?", (team_id,))
        conn.execute("DELETE FROM documents WHERE team_id=?", (team_id,))
        conn.execute("DELETE FROM query_logs WHERE team_id=?", (team_id,))
        conn.execute("DELETE FROM teams WHERE id=?", (team_id,))


# ====== 用户操作 ======

def list_users(team_id: str = None):
    with get_db() as conn:
        if team_id:
            rows = conn.execute(
                "SELECT * FROM users WHERE team_id=? ORDER BY name", (team_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM users ORDER BY name").fetchall()
    return [dict(r) for r in rows]


def create_user(name: str, team_id: str = None, role: str = "user") -> dict:
    uid = f"u_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO users(id, name, team_id, role, created_at) VALUES(?,?,?,?,?)",
            (uid, name, team_id, role, now),
        )
    return {"id": uid, "name": name, "team_id": team_id, "role": role}


def get_user(user_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    return dict(row) if row else None


# ====== 文档操作 ======

def add_document(team_id: str, filename: str, file_size: int, chunks_count: int) -> dict:
    did = f"doc_{uuid.uuid4().hex[:8]}"
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO documents(id, team_id, filename, file_size, chunks_count, uploaded_at) "
            "VALUES(?,?,?,?,?,?)",
            (did, team_id, filename, file_size, chunks_count, now),
        )
    return {"id": did, "filename": filename}


def list_documents(team_id: str):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM documents WHERE team_id=? ORDER BY uploaded_at DESC",
            (team_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def delete_document(doc_id: str):
    with get_db() as conn:
        conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))


def delete_document_by_filename(team_id: str, filename: str) -> int:
    """按文件名和团队 ID 删除文档记录，返回删除的记录数"""
    with get_db() as conn:
        cur = conn.execute(
            "DELETE FROM documents WHERE team_id=? AND filename=?",
            (team_id, filename),
        )
    return cur.rowcount


def delete_documents_by_team(team_id: str):
    """删除指定团队的所有文档记录（SQLite 层）"""
    with get_db() as conn:
        conn.execute("DELETE FROM documents WHERE team_id=?", (team_id,))


# ====== 查询日志 ======

def log_query(
    user_id: str,
    team_id: str,
    question: str,
    answer_preview: str,
    sources: str,
    retrieval_count: int,
):
    now = datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO query_logs(user_id, team_id, question, answer_preview, "
            "sources, retrieval_count, created_at) VALUES(?,?,?,?,?,?,?)",
            (user_id, team_id, question, answer_preview, sources, retrieval_count, now),
        )


def get_stats(team_id: str = None):
    """获取统计数据 — 总查询数 + 最近 200 条日志"""
    with get_db() as conn:
        base = "FROM query_logs"
        params = []
        where = ""
        if team_id:
            where = " WHERE team_id=?"
            params.append(team_id)

        total = conn.execute(
            f"SELECT COUNT(*) {base}{where}", params
        ).fetchone()[0]

        rows = conn.execute(
            f"SELECT * {base}{where} ORDER BY created_at DESC LIMIT 200",
            params,
        ).fetchall()

    return {
        "total_queries": total,
        "recent_logs": [dict(r) for r in rows],
    }


# ====== 模块加载时自动初始化 ======
# 可通过环境变量 KNOWLEDGE_HUB_AUTO_INIT=0 禁用（用于测试）
_auto_init = os.environ.get("KNOWLEDGE_HUB_AUTO_INIT", "1")
if _auto_init != "0":
    ensure_db()
