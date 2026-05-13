"""
feedback_store.py — Persists command history and corrections for prompt improvement.

Schema:
  sessions(id, timestamp, raw_text, intent_json, action_result, success, correction)
"""

import json
import sqlite3
import logging
from datetime import datetime
from pathlib import Path
import dataclasses
from models.intent_schema import IntentResult, Context

logger = logging.getLogger(__name__)

DB_PATH = Path("data/feedback.db")


class FeedbackStore:
    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(exist_ok=True)
        self.conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._init_schema()

    def _init_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                raw_text TEXT,
                intent_json TEXT,
                context_json TEXT,
                dom_before_json TEXT,
                dom_after_json TEXT,
                action_result TEXT,
                success INTEGER,
                correction TEXT,
                learned_note TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS ui_action_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                timestamp TEXT NOT NULL,
                url TEXT,
                title TEXT,
                action TEXT,
                strategy TEXT,
                labels_json TEXT,
                selectors_json TEXT,
                success INTEGER,
                error TEXT,
                screenshot TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS ui_page_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER,
                timestamp TEXT NOT NULL,
                url TEXT,
                title TEXT,
                structure_json TEXT
            )
        """)
        self._ensure_columns()
        self.conn.commit()

    def _ensure_columns(self):
        existing = {
            row[1] for row in self.conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        columns = {
            "context_json": "TEXT",
            "dom_before_json": "TEXT",
            "dom_after_json": "TEXT",
            "learned_note": "TEXT",
        }
        for name, column_type in columns.items():
            if name not in existing:
                self.conn.execute(f"ALTER TABLE sessions ADD COLUMN {name} {column_type}")

    def log(
        self,
        intent: IntentResult,
        success: bool,
        result_msg: str,
        context: Context | None = None,
        dom_before: dict | None = None,
        dom_after: dict | None = None,
    ) -> int:
        """Log a completed action. Returns row id."""
        learned_note = self._build_learned_note(intent, success, result_msg, dom_before, dom_after)
        cursor = self.conn.execute(
            """INSERT INTO sessions
               (timestamp, raw_text, intent_json, context_json, dom_before_json,
                dom_after_json, action_result, success, learned_note)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.utcnow().isoformat(),
                intent.raw_text,
                json.dumps(dataclasses.asdict(intent)),
                json.dumps(dataclasses.asdict(context)) if context else None,
                json.dumps(dom_before or {}),
                json.dumps(dom_after or {}),
                result_msg,
                int(success),
                learned_note,
            )
        )
        self.conn.commit()
        return cursor.lastrowid

    def add_correction(self, session_id: int, correction: str):
        """Store user correction for a specific session."""
        self.conn.execute(
            "UPDATE sessions SET correction = ? WHERE id = ?",
            (correction, session_id)
        )
        self.conn.commit()
        logger.info(f"Correction logged for session {session_id}: {correction}")

    def get_recent(self, limit: int = 20) -> list[dict]:
        cursor = self.conn.execute(
            "SELECT * FROM sessions ORDER BY id DESC LIMIT ?", (limit,)
        )
        cols = [d[0] for d in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def get_corrections(self) -> list[dict]:
        """Return all sessions that have corrections (for prompt tuning)."""
        cursor = self.conn.execute(
            "SELECT raw_text, intent_json, correction FROM sessions WHERE correction IS NOT NULL"
        )
        return [{"raw": r[0], "parsed": r[1], "correction": r[2]} for r in cursor.fetchall()]

    def get_learning_hints(self, limit: int = 8) -> list[str]:
        """
        Return compact hints from recent corrections and failures. This is the
        practical MVP learning loop: future intent parsing sees what previously
        failed or was corrected without retraining a model.
        """
        cursor = self.conn.execute(
            """
            SELECT raw_text, action_result, correction, learned_note, success
            FROM sessions
            WHERE correction IS NOT NULL OR success = 0 OR learned_note IS NOT NULL
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        hints = []
        for raw_text, action_result, correction, learned_note, success in cursor.fetchall():
            if correction:
                hints.append(f"When user said '{raw_text}', correction was: {correction}")
            elif not success:
                hints.append(f"Previous failure for '{raw_text}': {action_result}")
            elif learned_note:
                hints.append(learned_note)
        hints.extend(self.get_ui_action_hints(limit=limit))
        return hints[:limit]

    def log_ui_action_events(self, session_id: int, events: list[dict]):
        for event in events:
            self.conn.execute(
                """
                INSERT INTO ui_action_events
                (session_id, timestamp, url, title, action, strategy, labels_json,
                 selectors_json, success, error, screenshot)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    datetime.utcnow().isoformat(),
                    event.get("url", ""),
                    event.get("title", ""),
                    event.get("action", ""),
                    event.get("strategy", ""),
                    json.dumps(event.get("labels", [])),
                    json.dumps(event.get("selectors", [])),
                    int(event.get("success", False)),
                    event.get("error", ""),
                    event.get("screenshot", ""),
                ),
            )
        self.conn.commit()

    def log_page_snapshot(self, session_id: int, dom: dict | None):
        if not dom:
            return
        self.conn.execute(
            """
            INSERT INTO ui_page_snapshots
            (session_id, timestamp, url, title, structure_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                session_id,
                datetime.utcnow().isoformat(),
                dom.get("url", ""),
                dom.get("title", ""),
                json.dumps(dom.get("appStructure", {})),
            ),
        )
        self.conn.commit()

    def get_ui_action_hints(self, limit: int = 6) -> list[str]:
        cursor = self.conn.execute(
            """
            SELECT action, strategy, labels_json, url, COUNT(*) as uses
            FROM ui_action_events
            WHERE success = 1
            GROUP BY action, strategy, labels_json, url
            ORDER BY uses DESC, MAX(id) DESC
            LIMIT ?
            """,
            (limit,),
        )
        hints = []
        for action, strategy, labels_json, url, uses in cursor.fetchall():
            try:
                labels = ", ".join(json.loads(labels_json or "[]")[:3])
            except Exception:
                labels = ""
            hints.append(
                f"UI memory: {action} worked using {strategy}"
                f"{' for labels ' + labels if labels else ''}"
                f"{' on ' + url[:80] if url else ''}"
            )
        return hints

    def _build_learned_note(
        self,
        intent: IntentResult,
        success: bool,
        result_msg: str,
        dom_before: dict | None,
        dom_after: dict | None,
    ) -> str:
        if not success:
            return f"Failed {intent.intent} on {intent.app}: {result_msg[:120]}"
        before_url = (dom_before or {}).get("url", "")
        after_url = (dom_after or {}).get("url", "")
        if before_url and after_url and before_url != after_url:
            return f"{intent.intent} on {intent.app} moved from {before_url[:80]} to {after_url[:80]}"
        return f"{intent.intent} on {intent.app} succeeded"

    def close(self):
        self.conn.close()
