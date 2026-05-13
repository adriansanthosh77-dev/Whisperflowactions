"""
action_memory.py - Persistent UI action memory for JARVIS.

Stores successful selectors per domain/action/label so common site actions get
faster and survive minor UI changes before falling back to semantic matching.
"""

import json
import sqlite3
from pathlib import Path
from urllib.parse import urlparse


DB_PATH = Path("data/feedback.db")


def domain_of(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def label_key(labels: list[str] | None) -> str:
    cleaned = [str(label).strip().lower() for label in (labels or []) if str(label).strip()]
    return json.dumps(sorted(cleaned), ensure_ascii=True)


class ActionMemory:
    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._init_schema()

    def _init_schema(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS action_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                action TEXT NOT NULL,
                label_key TEXT NOT NULL,
                selector TEXT NOT NULL,
                success_count INTEGER NOT NULL DEFAULT 1,
                failure_count INTEGER NOT NULL DEFAULT 0,
                last_used TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(domain, action, label_key, selector)
            )
            """
        )
        self.conn.commit()

    def remember(self, url: str, action: str, labels: list[str] | None, selector: str):
        domain = domain_of(url)
        if not domain or not selector:
            return
        key = label_key(labels)
        self.conn.execute(
            """
            INSERT INTO action_memory (domain, action, label_key, selector)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(domain, action, label_key, selector)
            DO UPDATE SET
                success_count = success_count + 1,
                last_used = CURRENT_TIMESTAMP
            """,
            (domain, action, key, selector),
        )
        self.conn.commit()

    def recall(self, url: str, action: str, labels: list[str] | None) -> list[str]:
        domain = domain_of(url)
        if not domain:
            return []
        key = label_key(labels)
        cursor = self.conn.execute(
            """
            SELECT selector
            FROM action_memory
            WHERE domain = ? AND action = ? AND label_key = ?
            ORDER BY (success_count - failure_count) DESC, last_used DESC
            LIMIT 3
            """,
            (domain, action, key),
        )
        return [row[0] for row in cursor.fetchall()]

    def mark_failure(self, url: str, action: str, labels: list[str] | None, selector: str):
        domain = domain_of(url)
        if not domain or not selector:
            return
        self.conn.execute(
            """
            UPDATE action_memory
            SET failure_count = failure_count + 1, last_used = CURRENT_TIMESTAMP
            WHERE domain = ? AND action = ? AND label_key = ? AND selector = ?
            """,
            (domain, action, label_key(labels), selector),
        )
        self.conn.commit()
