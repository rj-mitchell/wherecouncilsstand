"""The site's own small database (SQLite, data/state.db): model spending, the answer cache, saved briefings and
problem reports. The minutes themselves are in Parquet and the search index; nothing here is needed to rebuild them.

No IP address is stored. A visitor is a salted hash that changes every day (usage.visitor_key).
"""

from __future__ import annotations

import json
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS usage (
    at TEXT NOT NULL, day TEXT NOT NULL, visitor TEXT, kind TEXT NOT NULL, model TEXT,
    input_tokens INTEGER, output_tokens INTEGER, cache_read_tokens INTEGER, cache_write_tokens INTEGER,
    cost_usd REAL NOT NULL);
CREATE INDEX IF NOT EXISTS usage_day ON usage (day);
CREATE TABLE IF NOT EXISTS questions (day TEXT NOT NULL, visitor TEXT NOT NULL, n INTEGER NOT NULL,
    PRIMARY KEY (day, visitor));
CREATE TABLE IF NOT EXISTS answer_cache (key TEXT PRIMARY KEY, at TEXT NOT NULL, events TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS briefings (
    id TEXT PRIMARY KEY, at TEXT NOT NULL, question TEXT NOT NULL, options TEXT NOT NULL, events TEXT NOT NULL,
    withdrawn_at TEXT, withdrawn_reason TEXT);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, kind TEXT NOT NULL, page TEXT, message TEXT NOT NULL,
    contact TEXT, closed_at TEXT);
"""


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


class StateDB:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self.connect() as con:
            con.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        with self._lock:
            con = sqlite3.connect(self.path, timeout=30)
            con.row_factory = sqlite3.Row
            try:
                yield con
                con.commit()
            finally:
                con.close()

    # key-value ------------------------------------------------------------------------------------------
    def get(self, key: str) -> str | None:
        with self.connect() as con:
            row = con.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set(self, key: str, value: str) -> None:
        with self.connect() as con:
            con.execute("INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        (key, value))

    # the answer cache -----------------------------------------------------------------------------------
    def cached(self, key: str, max_hours: float) -> list[dict[str, Any]] | None:
        with self.connect() as con:
            row = con.execute("SELECT at, events FROM answer_cache WHERE key = ?", (key,)).fetchone()
        if not row:
            return None
        age = (datetime.now(UTC) - datetime.fromisoformat(row["at"])).total_seconds() / 3600
        return json.loads(row["events"]) if age < max_hours else None

    def store_cached(self, key: str, events: list[dict[str, Any]]) -> None:
        with self.connect() as con:
            con.execute("INSERT OR REPLACE INTO answer_cache (key, at, events) VALUES (?, ?, ?)",
                        (key, utcnow(), json.dumps(events, default=str)))

    # saved briefings ------------------------------------------------------------------------------------
    @staticmethod
    def new_briefing_id() -> str:
        return secrets.token_urlsafe(8)

    def save_briefing(self, bid: str, question: str, options: dict[str, Any], events: list[dict[str, Any]]) -> str:
        with self.connect() as con:
            con.execute("INSERT INTO briefings (id, at, question, options, events) VALUES (?, ?, ?, ?, ?)",
                        (bid, utcnow(), question, json.dumps(options), json.dumps(events, default=str)))
        return bid

    def briefing(self, bid: str) -> dict[str, Any] | None:
        with self.connect() as con:
            row = con.execute("SELECT * FROM briefings WHERE id = ?", (bid,)).fetchone()
        if not row:
            return None
        return {**dict(row), "options": json.loads(row["options"]), "events": json.loads(row["events"])}

    def withdraw_briefing(self, bid: str, reason: str) -> bool:
        with self.connect() as con:
            n = con.execute("UPDATE briefings SET withdrawn_at = ?, withdrawn_reason = ? WHERE id = ?",
                            (utcnow(), reason, bid)).rowcount
        return bool(n)

    # problem reports and takedown requests ----------------------------------------------------------------
    def add_report(self, kind: str, page: str, message: str, contact: str) -> int:
        with self.connect() as con:
            cur = con.execute("INSERT INTO reports (at, kind, page, message, contact) VALUES (?, ?, ?, ?, ?)",
                              (utcnow(), kind, page, message, contact))
            return int(cur.lastrowid)

    def reports(self, open_only: bool = True) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute("SELECT * FROM reports" + (" WHERE closed_at IS NULL" if open_only else "") +
                               " ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]

    def close_report(self, report_id: int) -> bool:
        with self.connect() as con:
            # the contact address is used only to reply, and deleted when the report is dealt with (privacy notice)
            return bool(con.execute("UPDATE reports SET closed_at = ?, contact = '' WHERE id = ? AND closed_at IS NULL",
                                    (utcnow(), report_id)).rowcount)
