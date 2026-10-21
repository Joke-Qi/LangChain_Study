import sqlite3
import json
from datetime import datetime
from contextlib import contextmanager
from utils.path_tool import get_abs_path

DB_PATH = get_abs_path("resource\\cook_chat.db")

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                thread_id  TEXT PRIMARY KEY,
                title      TEXT NOT NULL DEFAULT '新对话',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                thread_id  TEXT NOT NULL,
                role       TEXT NOT NULL,
                content    TEXT,
                image_urls TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (thread_id) REFERENCES conversations(thread_id)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_thread_id ON messages(thread_id)"
        )

def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def create_conversation(thread_id: str) -> dict:
    ts = now_iso()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO conversations(thread_id, title, created_at, updated_at) VALUES (?,?,?,?)",
            (thread_id, "新对话", ts, ts),
        )
    return {"thread_id": thread_id, "title": "新对话", "created_at": ts}

def list_conversations() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT thread_id, title, created_at, updated_at "
            "FROM conversations ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]

def get_conversation(thread_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE thread_id=?", (thread_id,)
        ).fetchone()
    return dict(row) if row else None

def touch_conversation(thread_id: str):
    """更新 updated_at；若标题仍是默认值，暂不处理，由首条消息逻辑更新。"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE conversations SET updated_at=? WHERE thread_id=?",
            (now_iso(), thread_id),
        )

def set_title_if_default(thread_id: str, text: str, max_len: int = 20):
    """首条消息时把默认标题替换为消息前 N 个字。"""
    title = (text or "").strip()[:max_len] or "图片消息"
    with get_conn() as conn:
        conn.execute(
            "UPDATE conversations SET title=? WHERE thread_id=? AND title='新对话'",
            (title, thread_id),
        )

def delete_conversation(thread_id: str) -> bool:
    with get_conn() as conn:
        conn.execute("DELETE FROM messages WHERE thread_id=?", (thread_id,))
        cur = conn.execute("DELETE FROM conversations WHERE thread_id=?", (thread_id,))
    return cur.rowcount > 0

def add_message(thread_id: str, role: str, content: str, image_urls: list[str] | None = None) -> dict:
    """插入一条消息，image_urls 以 JSON 字符串形式落库。"""
    ts = now_iso()
    urls_json = json.dumps(image_urls, ensure_ascii=False) if image_urls else None
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages(thread_id, role, content, image_urls, created_at) VALUES (?,?,?,?,?)",
            (thread_id, role, content, urls_json, ts),
        )
    return {
        "role": role,
        "content": content,
        "image_urls": image_urls or [],
        "created_at": ts,
    }

def list_messages(thread_id: str) -> list[dict]:
    """按时间升序返回某会话的全部消息，image_urls 还原为列表。"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT role, content, image_urls, created_at FROM messages "
            "WHERE thread_id=? ORDER BY id ASC",
            (thread_id,),
        ).fetchall()
    result = []
    for r in rows:
        item = {
            "role": r["role"],
            "content": r["content"] or "",
            "created_at": r["created_at"],
        }
        if r["image_urls"]:
            item["image_urls"] = json.loads(r["image_urls"])
        result.append(item)
    return result

if __name__ == '__main__':
    print(DB_PATH)
