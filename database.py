"""SQLite database layer — tasks and conversation history."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from config import config


@contextmanager
def get_conn():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT    NOT NULL,
                description TEXT,
                priority    TEXT    NOT NULL DEFAULT 'medium',
                status      TEXT    NOT NULL DEFAULT 'pending',
                due_date    TEXT,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                updated_at  TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS conversation_history (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                role      TEXT NOT NULL,
                content   TEXT NOT NULL,
                timestamp TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS knowledge (
                id       TEXT PRIMARY KEY,
                title    TEXT NOT NULL,
                content  TEXT NOT NULL,
                source   TEXT NOT NULL DEFAULT 'manual',
                tags     TEXT NOT NULL DEFAULT '',
                added_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
                id       UNINDEXED,
                title,
                content,
                source   UNINDEXED,
                tags,
                added_at UNINDEXED,
                tokenize = 'porter unicode61'
            );
            """
        )
        # Triggers to keep FTS index in sync with the knowledge table
        conn.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS knowledge_ai
            AFTER INSERT ON knowledge BEGIN
                INSERT INTO knowledge_fts(id, title, content, source, tags, added_at)
                VALUES (new.id, new.title, new.content, new.source, new.tags, new.added_at);
            END;

            CREATE TRIGGER IF NOT EXISTS knowledge_ad
            AFTER DELETE ON knowledge BEGIN
                INSERT INTO knowledge_fts(knowledge_fts, id, title, content, source, tags, added_at)
                VALUES ('delete', old.id, old.title, old.content, old.source, old.tags, old.added_at);
            END;

            CREATE TRIGGER IF NOT EXISTS knowledge_au
            AFTER UPDATE ON knowledge BEGIN
                INSERT INTO knowledge_fts(knowledge_fts, id, title, content, source, tags, added_at)
                VALUES ('delete', old.id, old.title, old.content, old.source, old.tags, old.added_at);
                INSERT INTO knowledge_fts(id, title, content, source, tags, added_at)
                VALUES (new.id, new.title, new.content, new.source, new.tags, new.added_at);
            END;
            """
        )


# ── Conversation history ──────────────────────────────────────────────────────

def save_message(role: str, content) -> None:
    """Persist a single message (content may be str or list of blocks)."""
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO conversation_history (role, content) VALUES (?, ?)",
            (role, json.dumps(content) if not isinstance(content, str) else content),
        )


def load_recent_history(limit: int = 40) -> list[dict]:
    """Load the most recent *limit* messages as {role, content} dicts."""
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT role, content FROM (
                SELECT id, role, content
                FROM conversation_history
                ORDER BY id DESC
                LIMIT ?
            ) ORDER BY id ASC
            """,
            (limit,),
        ).fetchall()

    history = []
    for row in rows:
        try:
            content = json.loads(row["content"])
        except (json.JSONDecodeError, TypeError):
            content = row["content"]
        history.append({"role": row["role"], "content": content})
    return history


def clear_history() -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM conversation_history")
