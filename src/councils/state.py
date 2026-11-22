"""The state database, ``data/state.db``: the one thing that can't be rebuilt from councils' own sites, and what
its backups are called.

It is a small SQLite file opened through the Where They Stand sites' shared package (wts-core,
``wts_core.state``; its docs/adr/0005). The minutes themselves are in Parquet and the search index; nothing here is
needed to rebuild them. Every table in it but two is the shared package's own, named ``wts_…``, and only the package
reads or writes them:

* spending against the caps, the answer cache and saved briefings (``wts_spending``, ``wts_answer_cache``,
  ``wts_briefings``; ``wts_core.usage``);
* readers' reports, statements under the right of reply and items hidden while a concern is decided
  (``wts_reports``, ``wts_statements``, ``wts_statement_log``, ``wts_hidden``; src/councils/replies.py);
* the record of each briefing (``wts_briefing_log`` and the tables beside it; ``wts_core.observe``);
* the day's secret that a visitor's code is made with (``wts_kv``).

The two that are the site's own say which saved briefing is each topic briefing's current one, and what the last
weekly run did with each topic (``topic_versions``, ``topic_checks``; src/councils/topics.py, decision 35).

No address of a visitor is stored. A visitor is a code made from their network and a secret that changes every
day; the code is kept on the day's spending rows, for the daily limit, and forgotten after its day.

Before wts-core the site kept all this in tables of its own (``kv``, ``usage``, ``questions``, ``answer_cache``,
``briefings``, ``reports``, ``statements``). The first time the new code opens a database that has them, their rows
are copied into the ``wts_`` tables, once (``IMPORTS``), and a copy of the whole file as it was is kept beside it
first, as ``state.pre-wts-core.<date>.db``; ``councils tidy`` deletes that copy once it is older than the backups
are kept.

The old tables stay in the file for a while, so that the move can be undone (deploy/undo-wts-core.sql; and made
again with deploy/redo-wts-core.sql, should the old code have run meanwhile), but they are not left to keep what
the site has promised to delete (``OLD_TABLES``): every night ``councils tidy`` takes
out of them what the package has deleted from its own (a statement's confirming address, a report's contact, a
visitor's code after its day, yesterday's secret, answers past their week in the cache), and from 1 February 2027
it drops them. docs/OPERATIONS.md, "The move onto wts-core, and going back", says how to go back, and until when.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import date

from wts_core import observe, replies, usage
from wts_core.ops import AlertWording, BackupSpec
from wts_core.ports import SYSTEM_CLOCK, SYSTEM_RANDOM, Clock, Random
from wts_core.state import Import, Migration, OldTables, StateDB, StateError, columns
from wts_core.usage import BriefingArchive, SqliteAnswerCache, token_id

from councils.config import SITE, Settings

# What the site's backups are called and hold (`councils backup`, `restore`, `offsite`, `backup-check`; cli.py):
# councils-state-YYYY-MM-DD.sqlite.gz, the database gzipped, one a night. The nightly timer keeps 7 on the server
# (deploy/councils-backup.service); 60 are kept off site.
#
# A restore takes only a database with these tables, which every backup made since the move onto the shared
# package has. The tables a restore asks for are the package's, which a sister site's backup has too, so the
# database is also marked as this site's when it is opened (``open_state``), and a backup marked as a sister site's
# is refused. (The topic tables, the site's own, are made when a backup without them is opened.) A backup made
# before the move has none of these tables, and the command refuses it: docs/OPERATIONS.md says how to put one
# back by hand.
BACKUPS = BackupSpec(prefix="councils-state-", keep=14, keep_offsite=60, site=SITE.package,
                     required_tables=("wts_schema", "wts_spending", "wts_briefings", "wts_reports", "wts_statements"))
# Nothing else that holds old rows (the copy of the database made before the one-off import, the weekly reports)
# is kept longer than the backups are: one a night, 60 kept off site, so about two months (the privacy page).
BACKUPS_KEPT_DAYS = BACKUPS.keep_offsite
# where the nightly backup is written on the server (deploy/councils-backup.service), and where the daily check and
# the family's nightly check look for it
BACKUPS_FOLDER = "/backups"

# What `councils backup-check` says when backups or their off-site copies have stopped (each a sentence, as before)
BACKUP_ALERTS = AlertWording(
    no_backups="No backups have been made yet.",
    backup_stale="The last backup was made over two days ago ({name}).",
    server_only="Backups are kept on this server only: no off-site copy is set up.",
    no_offsite_yet="No off-site copy has been made yet; one is made with the next backup.",
    offsite_failed="The last off-site copy failed ({when}): {error}",
    offsite_stale="The last off-site copy was over two days ago ({day}).",
)


# The tables, and the one-off import of the site's old rows


# The site's own tables, beside the package's (a table without the ``wts_`` prefix is the site's, and the package
# never reads or writes it): which saved briefing is each topic's current one (src/councils/topics.py, decision 35).
# Numbered well clear of the package's own migrations.
SITE_MIGRATIONS = (Migration(1000, "councils_topic_versions", (
    # each briefing written for a topic; the newest that is not withdrawn is current
    "CREATE TABLE IF NOT EXISTS topic_versions (briefing_id TEXT PRIMARY KEY, slug TEXT NOT NULL, "
    "prepared_at TEXT NOT NULL, records_from TEXT, records_to TEXT)",
    "CREATE INDEX IF NOT EXISTS topic_versions_slug ON topic_versions (slug, prepared_at)",
    # what the last run did with each topic, for `councils topics list`
    "CREATE TABLE IF NOT EXISTS topic_checks (slug TEXT PRIMARY KEY, checked_at TEXT NOT NULL, "
    "outcome TEXT NOT NULL)",
)),)


def migrations() -> tuple[Migration, ...]:
    """The tables of every part of the shared package this site uses (each module names its own), and the site's
    own."""
    return (*usage.migrations(), *replies.migrations(), *observe.migrations(), *SITE_MIGRATIONS)


# The tables the site kept before the shared package. They are no longer made, read or written by the site; on a
# database that has them they are kept for going back (deploy/undo-wts-core.sql) until the day below.
OLD_TABLE_NAMES = ("kv", "usage", "questions", "answer_cache", "briefings", "reports", "statements")
# Every old database has the first six: they were there from the site's first day (25 October 2026). `statements`
# came with the right of reply on 12 November 2026, so a backup made before then has none.
ALWAYS_THERE = ("kv", "usage", "questions", "answer_cache", "briefings", "reports")
# The day the old tables are dropped. After it, going back to the code before the shared package means putting
# back a backup made before the move, while one is still kept (docs/OPERATIONS.md, "Going back, and coming forward
# again").
OLD_TABLES_GO_ON = date(2027, 2, 1)


def _statements_if_there(*statements: str):
    """Import statements for the old ``statements`` table, which a database from before 12 November 2026 lacks:
    nothing is run on one without it, and the rest of the import carries on."""
    def given(con: sqlite3.Connection) -> tuple[str, ...]:
        return statements if columns(con, "statements") else ()
    return given


def _forget_old_addresses(con: sqlite3.Connection) -> tuple[str, ...]:
    """Each night, on the old ``statements`` table: where the package's row has no confirming address any more
    (deleted three months after the statement ended, or when it lapsed undecided), the old row loses it too, and
    it is taken out of the old row's log and recorded reason, should the owner have written it there. As the
    package does on its own rows: the address in any case, and as JSON writes it."""
    if not columns(con, "statements"):
        return ()
    for row in con.execute("SELECT s.id, s.email, s.log, s.reason FROM statements s JOIN wts_statements w "
                           "ON w.id = s.id WHERE s.email != '' AND w.email IS NULL").fetchall():
        forms = {row["email"], json.dumps(row["email"])[1:-1]}
        address = re.compile("|".join(re.escape(form) for form in sorted(forms, key=len, reverse=True)),
                             re.IGNORECASE)
        con.execute("UPDATE statements SET email = '', log = ?, reason = ? WHERE id = ?",
                    (address.sub("[address deleted]", row["log"] or "[]"),
                     address.sub("[address deleted]", row["reason"]) if row["reason"] else row["reason"], row["id"]))
    return ()


# What becomes of the old tables (wts-core docs/EXTENDING.md, "The old tables, after the import"): left as they were, they would keep what the site has promised to delete, and so would every night's backup. Each
# night, while they are there (`councils tidy`, after the backup), each promise the package keeps on its own
# tables is kept on the old ones:
#
# * a statement's confirming address goes from the old row wherever the package's row has none (above);
# * a report's contact goes from the old row wherever the package's row has none (closed, or open three months);
# * a visitor's code goes from the old spending rows of days gone by, and the old daily counts of days gone by are
#   deleted (they are a visitor's code and a number, and nothing reads them);
# * every old secret for visitors' codes but today's is deleted, as the old code deleted yesterday's;
# * answers in the old cache older than a week are deleted, as the old code deleted them when it stored a new one.
#
# Saved briefings and withdrawn ones were kept without limit before, and are in the package's table: nothing to do.
# From the day above the old tables are dropped, by the same command. The package's tables are never named here.
OLD_TABLES = OldTables(
    tables=OLD_TABLE_NAMES,
    drop_on=OLD_TABLES_GO_ON,
    nightly=(
        _forget_old_addresses,
        "UPDATE reports SET contact = NULL WHERE contact IS NOT NULL AND id IN "
        "(SELECT id FROM wts_reports WHERE contact IS NULL)",
        "UPDATE usage SET visitor = NULL WHERE visitor IS NOT NULL AND day < :today",
        "DELETE FROM questions WHERE day < :today",
        "DELETE FROM kv WHERE key LIKE 'visitor_salt:%' AND key != 'visitor_salt:' || :today",
        "DELETE FROM answer_cache WHERE substr(at, 1, 10) < date(:today, '-7 days')",
    ))

# The one-off copy of the old rows into the package's tables (wts-core docs/adr/0005), in one transaction.
#
# * The day's secret for visitors' codes comes across under its own name, so a visitor's code, and so their count
#   for the day, is the same after the move as before. (The old code kept one secret at a time, the newest day's.)
# * Every spending row, with its visitor's code and kind: the daily limit and the caps are sums over them. A count
#   that was missing (the old table allowed it) is nought. The old ``questions`` table held each visitor's
#   briefings for the day, which is the number of their rows of kind "answer" that day; should it ever say more
#   than the rows do, rows of no cost are added for the difference, so that nobody's count goes down.
# * Cached answers and saved briefings, events and all, byte for byte.
# * Reports: a closed one is recorded as resolved (the old table kept no outcome); an empty page or contact is none.
# * Statements: ``page`` is the ``item``, ``council`` whom it is ``about``. The date a statement is shown with
#   (``shown_on``) becomes the time it was published, from its log, and the time of its last update; the later of
#   the two is the date shown, as before. Its log, kept as JSON in a column, becomes a row for each entry.
IMPORTS = (Import(
    name="councils-state",
    statements=(
        "INSERT OR IGNORE INTO wts_kv (key, value) SELECT key, value FROM kv WHERE key LIKE 'visitor_salt:%' "
        "AND value IS NOT NULL",
        "INSERT INTO wts_spending (at, kind, model, visitor, input_tokens, output_tokens, cache_read_tokens, "
        "cache_write_tokens, cost_usd) SELECT at, kind, model, visitor, coalesce(input_tokens, 0), "
        "coalesce(output_tokens, 0), coalesce(cache_read_tokens, 0), coalesce(cache_write_tokens, 0), cost_usd "
        "FROM usage ORDER BY rowid",
        "WITH RECURSIVE short (day, visitor, missing) AS ("
        "SELECT q.day, q.visitor, q.n - (SELECT count(*) FROM usage u WHERE u.kind = 'answer' AND "
        "u.visitor = q.visitor AND u.day = q.day) FROM questions q "
        "UNION ALL SELECT day, visitor, missing - 1 FROM short WHERE missing > 1) "
        "INSERT INTO wts_spending (at, kind, visitor, cost_usd) "
        "SELECT day || 'T00:00:00+00:00', 'answer', visitor, 0 FROM short WHERE missing > 0",
        "INSERT OR IGNORE INTO wts_answer_cache (key, created_at, events) SELECT key, at, events FROM answer_cache",
        "INSERT OR IGNORE INTO wts_briefings (id, created_at, question, options, events, withdrawn_at, "
        "withdrawn_reason) SELECT id, at, question, options, events, withdrawn_at, withdrawn_reason FROM briefings",
        "INSERT INTO wts_reports (id, at, kind, page, message, contact, status, closed_at) "
        "SELECT id, at, kind, nullif(page, ''), message, nullif(contact, ''), "
        "CASE WHEN closed_at IS NULL THEN 'open' ELSE 'resolved' END, closed_at FROM reports",
        _statements_if_there(
            "INSERT INTO wts_statements (id, at, item, about, name, role, text, link, email, status, published_at, "
            "updated_at, closed_at, reason) SELECT s.id, s.at, s.page, s.council, s.name, s.role, s.text, "
            "nullif(s.link, ''), nullif(s.email, ''), s.status, "
            "CASE WHEN s.shown_on IS NULL THEN NULL ELSE coalesce((SELECT max(json_extract(j.value, '$.at')) "
            "FROM json_each(s.log) j WHERE json_extract(j.value, '$.action') = 'published'), "
            "s.shown_on || 'T00:00:00+00:00') END, "
            "(SELECT max(json_extract(j.value, '$.at')) FROM json_each(s.log) j "
            "WHERE json_extract(j.value, '$.action') = 'updated'), s.ended_at, s.reason FROM statements s",
            "INSERT INTO wts_statement_log (statement, at, action, note) "
            "SELECT s.id, json_extract(j.value, '$.at'), json_extract(j.value, '$.action'), "
            "json_extract(j.value, '$.note') FROM statements s, json_each(s.log) j ORDER BY s.id, j.key"),
    ),
    # only the tables every old database has: one put back from before 12 November 2026 has no `statements`, and
    # an import that needed it would be passed over on that database for good, leaving the site with no spending
    # and no saved briefings
    needs=ALWAYS_THERE,
    # Going back is noticed (wts-core docs/UPGRADING.md, "Going back to the old code"): the
    # column of each old table that holds the time a row was written. If the site is put back on its old code
    # without deploy/undo-wts-core.sql being run, the old code writes to these tables again; the import is marked
    # as done and would not run a second time, so what was written meanwhile would be silently missing. With
    # this, the new code then refuses to open the database, naming the tables and the mend. `kv` and `questions`
    # keep no time of writing and are left out. The nightly tidy of the old tables changes and deletes rows and
    # adds none, so it never trips this.
    written_at={"usage": "at", "answer_cache": "at", "briefings": "at", "reports": "at", "statements": "at"},
),)


# Said after the package's own words when the database is refused because the old code has written to the old
# tables since the move (``Import.written_at``, above). The package says to run "the site's script for undoing the
# move". This site has two, and which is right depends on what happened: deploy/undo-wts-core.sql writes the old
# tables afresh from the package's, so run in that state it would discard the very rows the refusal is about.
WHICH_SCRIPT = ("On Where Councils Stand there are two such scripts, and each discards something. If the old code "
                "was started after the move: deploy/redo-wts-core.sql, which keeps what the old code wrote and "
                "discards what the new code wrote between the move and then. If the old code was never started "
                "after the move (the false alarm): deploy/undo-wts-core.sql, which keeps what the new code wrote "
                "and writes the old tables afresh from it. Do not run undo-wts-core.sql to keep what the old code "
                "wrote: it would discard it. docs/OPERATIONS.md, \"Going back, and coming forward again\".")


def open_state(settings: Settings, clock: Clock = SYSTEM_CLOCK) -> StateDB:
    """The state database, with the shared package's tables made on the way in and the old rows brought across the
    first time. It is marked as this site's the first time it is opened, and a file marked as another site's is
    refused. So is one whose old tables hold rows written after the move (the site was put back on its old code
    without deploy/undo-wts-core.sql): nothing is changed, and the error says which script mends it."""
    try:
        return StateDB(settings.state_db, migrations=migrations(), imports=IMPORTS, old_tables=OLD_TABLES,
                       clock=clock, site=SITE.package)
    except StateError as exc:
        if "newer than the import" not in str(exc):      # some other fault of the database's: as the package says it
            raise
        raise StateError(f"{exc} {WHICH_SCRIPT}") from exc


def new_briefing_id(chance: Random = SYSTEM_RANDOM) -> str:
    """A saved briefing's id, which is its address: /b/ and eleven characters nobody could guess (64 random bits)."""
    return token_id(8, random=chance)


def open_archive(db: StateDB, clock: Clock = SYSTEM_CLOCK) -> BriefingArchive:
    """Saved briefings, for the parts of the site that only read or withdraw them (the web app's come with its
    briefing desk)."""
    return BriefingArchive(db, new_id=new_briefing_id, clock=clock)


def forget_replays(db: StateDB, briefing_id: str, clock: Clock = SYSTEM_CLOCK) -> int:
    """Drop every copy of a saved briefing from the answer cache, and say how many went: for when a briefing is
    withdrawn or hidden, so that the next reader with the same question is not played what was taken down."""
    return SqliteAnswerCache(db, clock=clock).delete_briefing(briefing_id)

