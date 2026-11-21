import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.getenv("DB_PATH", "data/it_agent.db"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    with connect() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, id);
            """
        )


def create_conversation(title: str = "New session") -> dict:
    cid, now = uuid.uuid4().hex, _now()
    with connect() as db:
        db.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (cid, title, now, now),
        )
    return {"id": cid, "title": title, "created_at": now, "updated_at": now}


def list_conversations() -> list[dict]:
    with connect() as db:
        rows = db.execute(
            "SELECT id, title, created_at, updated_at FROM conversations ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_conversation(cid: str) -> dict | None:
    with connect() as db:
        row = db.execute(
            "SELECT id, title, created_at, updated_at FROM conversations WHERE id = ?", (cid,)
        ).fetchone()
    return dict(row) if row else None


def get_messages(cid: str) -> list[dict]:
    with connect() as db:
        rows = db.execute(
            "SELECT role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY id",
            (cid,),
        ).fetchall()
    return [dict(r) for r in rows]


def add_message(cid: str, role: str, content: str) -> None:
    now = _now()
    with connect() as db:
        db.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (cid, role, content, now),
        )
        db.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, cid))


def set_title(cid: str, title: str) -> None:
    with connect() as db:
        db.execute("UPDATE conversations SET title = ? WHERE id = ?", (title, cid))


def delete_conversation(cid: str) -> None:
    with connect() as db:
        db.execute("DELETE FROM conversations WHERE id = ?", (cid,))
