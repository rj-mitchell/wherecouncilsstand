"""The site's own small database (SQLite, data/state.db): model spending, the answer cache, saved briefings, problem
reports and statements under the right of reply (api/statements.py). The minutes themselves are in Parquet and the search index; nothing here is needed to rebuild them.

No IP address is stored. A visitor is a salted hash that changes every day (usage.visitor_key).
"""

from __future__ import annotations

import calendar
import json
import secrets
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
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
CREATE TABLE IF NOT EXISTS statements (
    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, page TEXT NOT NULL, council TEXT, name TEXT NOT NULL,
    role TEXT NOT NULL, text TEXT NOT NULL, link TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending', shown_on TEXT, ended_at TEXT, reason TEXT, log TEXT NOT NULL DEFAULT '[]');
CREATE INDEX IF NOT EXISTS statements_page ON statements (status, page);
"""
# How long the address used to confirm who wrote a statement is kept after it is withdrawn or declined (the privacy
# notice, "Statements under the right of reply"; decision 22). While a statement is shown it is kept, so that its
# author can update or withdraw it.
STATEMENT_EMAIL_MONTHS = 3
# what the public sees of a statement: never its author's email address or the owner's notes
PUBLIC_STATEMENT = ("id", "page", "council", "name", "role", "text", "link", "shown_on")


def utcnow() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def months_before(when: datetime, months: int) -> datetime:
    """The same day ``months`` calendar months earlier (the month's last day where that day doesn't exist)."""
    y, m = divmod(when.month - 1 - months, 12)
    year, month = when.year + y, m + 1
    return when.replace(year=year, month=month, day=min(when.day, calendar.monthrange(year, month)[1]))


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

    def store_cached(self, key: str, events: list[dict[str, Any]], max_hours: float) -> None:
        """Keep an answer for ``max_hours``. Answers older than that are deleted as each new one is stored: they
        are never read again, and would otherwise fill the database (as Where Countries Stand)."""
        since = (datetime.now(UTC) - timedelta(hours=max_hours)).isoformat(timespec="seconds")
        with self.connect() as con:
            con.execute("DELETE FROM answer_cache WHERE at < ?", (since,))
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

    # statements under the right of reply (api/statements.py) ---------------------------------------------
    def add_statement(self, page: str, council: str | None, name: str, role: str, text: str, link: str,
                      email: str) -> int:
        """A statement as sent, waiting for the owner to confirm who sent it and publish or decline it."""
        self.forget_statement_emails()
        with self.connect() as con:
            cur = con.execute("INSERT INTO statements (at, page, council, name, role, text, link, email, log) "
                              "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                              (utcnow(), page, council, name, role, text, link, email,
                               json.dumps([{"at": utcnow(), "action": "received"}])))
            return int(cur.lastrowid)

    def statement(self, sid: int) -> dict[str, Any] | None:
        with self.connect() as con:
            row = con.execute("SELECT * FROM statements WHERE id = ?", (sid,)).fetchone()
        return {**dict(row), "log": json.loads(row["log"])} if row else None

    def statements(self, open_only: bool = True) -> list[dict[str, Any]]:
        """For the owner: waiting and published statements (every one with ``open_only`` off), newest first."""
        with self.connect() as con:
            rows = con.execute("SELECT * FROM statements" +
                               (" WHERE status IN ('pending', 'published')" if open_only else "") +
                               " ORDER BY id DESC").fetchall()
        return [{**dict(r), "log": json.loads(r["log"])} for r in rows]

    def published_statements(self, page: str | None = None, council: str | None = None) -> list[dict[str, Any]]:
        """What the public sees: the published statements beside one item, or all of one council's (on its page),
        oldest first. Never the author's email address."""
        where, args = ["status = 'published'"], []
        if page:
            where.append("page = ?")
            args.append(page)
        if council:
            where.append("council = ?")
            args.append(council)
        with self.connect() as con:
            rows = con.execute(f"SELECT {', '.join(PUBLIC_STATEMENT)} FROM statements WHERE {' AND '.join(where)} "
                               "ORDER BY shown_on, id", args).fetchall()
        return [dict(r) for r in rows]

    def _change_statement(self, sid: int, from_status: tuple[str, ...], action: str, note: str = "",
                          **fields: Any) -> bool:
        with self.connect() as con:
            row = con.execute("SELECT status, log FROM statements WHERE id = ?", (sid,)).fetchone()
            if not row or row["status"] not in from_status:
                return False
            log = json.loads(row["log"]) + [{"at": utcnow(), "action": action, **({"note": note} if note else {})}]
            fields["log"] = json.dumps(log)
            con.execute(f"UPDATE statements SET {', '.join(f'{k} = ?' for k in fields)} WHERE id = ?",
                        (*fields.values(), sid))
        return True

    def publish_statement(self, sid: int, council: str | None = None, *, checked: str) -> bool:
        """Show a waiting statement, dated today, once the owner has confirmed who sent it. ``checked`` says how
        (policy 7.2; as Where Landlords Stand): it is kept in the log's entry for the publishing, which only the owner
        sees, and should not hold the sender's email address, which the privacy notice promises to delete.
        ``council`` puts it on that council's page too (needed for a statement about a briefing, which belongs to no
        one council)."""
        checked = " ".join((checked or "").split())
        if not checked:
            raise ValueError("Say how you confirmed who sent it (--checked), for the log.")
        extra = {"council": council} if council else {}
        return self._change_statement(sid, ("pending",), "published", checked, status="published", shown_on=today(),
                                      **extra)

    def decline_statement(self, sid: int, reason: str) -> bool:
        return self._change_statement(sid, ("pending",), "declined", reason, status="declined", ended_at=utcnow(),
                                      reason=reason)

    def update_statement(self, sid: int, **changes: str) -> bool:
        """The author's new wording, name, role or link, as they sent it. A published statement is dated afresh."""
        changes = {k: v for k, v in changes.items() if k in ("text", "name", "role", "link") and v is not None}
        if not changes:
            return False
        with self.connect() as con:
            row = con.execute("SELECT status FROM statements WHERE id = ?", (sid,)).fetchone()
        if row and row["status"] == "published":
            changes["shown_on"] = today()
        return self._change_statement(sid, ("pending", "published"), "updated", ", ".join(sorted(changes)), **changes)

    def withdraw_statement(self, sid: int, reason: str) -> bool:
        """Take a statement down: at its author's request, or because it breaks the rules (policy 7.2)."""
        return self._change_statement(sid, ("pending", "published"), "withdrawn", reason, status="withdrawn",
                                      ended_at=utcnow(), reason=reason)

    def forget_statement_emails(self, now: datetime | None = None) -> int:
        """Delete the confirming address of every statement withdrawn or declined more than three months ago (the
        privacy notice). Run as each statement arrives, by every owner's command on statements, and nightly by
        ``councils update``."""
        cutoff = months_before(now or datetime.now(UTC), STATEMENT_EMAIL_MONTHS).isoformat(timespec="seconds")
        with self.connect() as con:
            return con.execute("UPDATE statements SET email = '' WHERE status IN ('withdrawn', 'declined') "
                               "AND email != '' AND ended_at < ?", (cutoff,)).rowcount
