"""The state database, ``data/state.db``: the one thing that can't be rebuilt from councils' own sites, and what
its backups are called.

It is a small SQLite file opened through the Where They Stand sites' shared package (wts-core,
``wts_core.state``; its docs/adr/0005). The minutes themselves are in Parquet and the search index; nothing here is
needed to rebuild them. Every table in it is the shared package's own, named ``wts_…``, and only the package reads
or writes them:

* spending against the caps, the answer cache and saved briefings (``wts_spending``, ``wts_answer_cache``,
  ``wts_briefings``; ``wts_core.usage``);
* readers' reports, statements under the right of reply and items hidden while a concern is decided
  (``wts_reports``, ``wts_statements``, ``wts_statement_log``, ``wts_hidden``; src/councils/replies.py);
* the record of each briefing (``wts_briefing_log`` and the tables beside it; ``wts_core.observe``);
* the day's secret that a visitor's code is made with (``wts_kv``).

No address of a visitor is stored. A visitor is a code made from their network and a secret that changes every
day; the code is kept on the day's spending rows, for the daily limit, and forgotten after its day.

Before wts-core the site kept all this in tables of its own (``kv``, ``usage``, ``questions``, ``answer_cache``,
``briefings``, ``reports``, ``statements``). The first time the site starts on a database that has them, their rows
are copied into the ``wts_`` tables, once (``IMPORTS``). The old tables are left exactly as they were, and a copy
of the whole file as it was is kept beside it first, as ``state.pre-wts-core.<date>.db``; ``councils tidy`` deletes
that copy once it is older than the backups are kept. docs/OPERATIONS.md, "The state database", says how to go
back.
"""

from __future__ import annotations

from wts_core import observe, replies, usage
from wts_core.ops import AlertWording, BackupSpec
from wts_core.ports import SYSTEM_CLOCK, SYSTEM_RANDOM, Clock, Random
from wts_core.state import Import, Migration, StateDB
from wts_core.usage import BriefingArchive, token_id

from councils.config import SITE, Settings

# What the site's backups are called and hold (`councils backup`, `restore`, `offsite`, `backup-check`; cli.py):
# councils-state-YYYY-MM-DD.sqlite.gz, the database gzipped, one a night. The nightly timer keeps 7 on the server
# (deploy/councils-backup.service); 60 are kept off site.
#
# A restore takes only a database with these tables, which every backup made since the move onto the shared
# package has. The site has no table of its own that a sister site lacks, so the database is also marked as this
# site's when it is opened (``open_state``), and a backup marked as a sister site's is refused. A backup made
# before the move has none of these tables, and the command refuses it: docs/OPERATIONS.md says how to put one
# back by hand.
BACKUPS = BackupSpec(prefix="councils-state-", keep=14, keep_offsite=60, site=SITE.package,
                     required_tables=("wts_schema", "wts_spending", "wts_briefings", "wts_reports", "wts_statements"))
# Nothing else that holds old rows (the copy of the database made before the one-off import, the weekly reports)
# is kept longer than the backups are: one a night, 60 kept off site, so about two months (the privacy page).
BACKUPS_KEPT_DAYS = BACKUPS.keep_offsite

# What `councils backup-check` says when backups or their off-site copies have stopped (each a sentence, as before)
BACKUP_ALERTS = AlertWording(
    no_backups="No backups have been made yet.",
    backup_stale="The last backup was made over two days ago ({name}).",
    server_only="Backups are kept on this server only: no off-site copy is set up.",
    no_offsite_yet="No off-site copy has been made yet; one is made with the next backup.",
    offsite_failed="The last off-site copy failed ({when}): {error}",
    offsite_stale="The last off-site copy was over two days ago ({day}).",
)


# ---- the tables, and the one-off import of the site's old rows ----------------------------------------------------


def migrations() -> tuple[Migration, ...]:
    """The tables of every part of the shared package this site uses. Each module names its own."""
    return (*usage.migrations(), *replies.migrations(), *observe.migrations())


# The tables the site kept before the shared package. They are no longer made, read or written; on a database that
# has them they are left as they were, for going back (deploy/undo-wts-core.sql).
OLD_TABLES = ("kv", "usage", "questions", "answer_cache", "briefings", "reports", "statements")

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
        "json_extract(j.value, '$.note') FROM statements s, json_each(s.log) j ORDER BY s.id, j.key",
    ),
    needs=OLD_TABLES,
),)


def open_state(settings: Settings, clock: Clock = SYSTEM_CLOCK) -> StateDB:
    """The state database, with the shared package's tables made on the way in and the old rows brought across the
    first time. It is marked as this site's the first time it is opened, and a file marked as another site's is
    refused."""
    return StateDB(settings.state_db, migrations=migrations(), imports=IMPORTS, clock=clock, site=SITE.package)


def new_briefing_id(chance: Random = SYSTEM_RANDOM) -> str:
    """A saved briefing's id, which is its address: /b/ and eleven characters nobody could guess (64 random bits)."""
    return token_id(8, random=chance)


def open_archive(db: StateDB, clock: Clock = SYSTEM_CLOCK) -> BriefingArchive:
    """Saved briefings, for the parts of the site that only read or withdraw them (the web app's come with its
    briefing desk)."""
    return BriefingArchive(db, new_id=new_briefing_id, clock=clock)


def forget_old_secret(db: StateDB, clock: Clock = SYSTEM_CLOCK) -> list[str]:
    """Delete, from the table the site kept before the shared package (``kv``), the secret visitors' codes were
    made with on any day before today, and say so if one was deleted. The old code deleted yesterday's secret
    itself when the next day's first visitor came; nothing reads that table now, so the nightly ``councils tidy``
    does it, and the secret of the day of the move does not outlive its day there. (The package deletes its own,
    in ``wts_kv``.) Without its secret a visitor's code cannot be tried against addresses."""
    if "kv" not in db.tables():
        return []
    with db.connect() as con:
        gone = con.execute("DELETE FROM kv WHERE key LIKE 'visitor_salt:%' AND key != ?",
                           (f"visitor_salt:{clock.now():%Y-%m-%d}",)).rowcount
    return ["Deleted an earlier day's secret for visitors' codes from the table kept before the shared package."] \
        if gone else []
