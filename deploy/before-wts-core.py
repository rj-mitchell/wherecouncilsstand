"""Look at the state database BEFORE deploying the move onto the shared package (wts-core), on the old code.

It only reads (the database is opened read-only), needs nothing but Python, and prints no address, name or word of
what anyone sent: numbers, dates and ages. Run it on the server while the old site is still running
(docs/OPERATIONS.md, "The state database", says when):

    cd /opt/wherecouncilsstand
    git fetch origin
    git show origin/main:deploy/before-wts-core.py | docker compose -f deploy/docker-compose.yml exec -T app python -

It says two things.

1. What will lapse. Once the new code is running, the first thing that writes to or lists reports and statements
   (a report sent by a reader, any `councils reports` or `councils statements` command, the nightly tidy) declines
   every statement that has waited more than three months, with the reason "No decision was made in time; please
   send it again.", and deletes the contact address of every report open that long. There is no deciding them on
   the new code first: decide them on the old code, before the deploy, or let them lapse.
2. What would stop the import. The old rows are copied into the new tables in one go when the new code first opens
   the database. A row the new tables cannot take stops it: the site then does not start, nothing is half
   copied, and the old tables and the copy of the file made first are as they were. Mend the row, on the old code,
   before deploying.

It ends with status 1 if anything would stop the import, and 0 otherwise.
"""

import calendar
import os
import sqlite3
import sys
from datetime import UTC, datetime

MONTHS = 3      # how long a statement or a report may wait undecided (wts-core docs/adr/0008, the second question)


def months_before(when, months):
    """The same moment so many calendar months earlier (the month's last day where that day does not exist)."""
    y, m = divmod(when.year * 12 + when.month - 1 - months, 12)
    return when.replace(year=y, month=m + 1, day=min(when.day, calendar.monthrange(y, m + 1)[1]))


def look(path, now):
    con = sqlite3.connect("file:" + str(path) + "?mode=ro", uri=True)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "wts_schema" in tables and con.execute("SELECT 1 FROM wts_schema WHERE name = 'import:councils-state'"
                                                  ).fetchone():
            return ["This database has already been moved onto the shared package: nothing to look at."], False
        cutoff = months_before(now, MONTHS).isoformat(timespec="seconds")
        said, stops = [], False

        def age(at):
            return (now.date() - datetime.fromisoformat(at).date()).days

        waiting = con.execute("SELECT id, at FROM statements WHERE status = 'pending' AND at < ? ORDER BY at, id",
                              (cutoff,)).fetchall() if "statements" in tables else []
        reports = con.execute("SELECT id, at FROM reports WHERE closed_at IS NULL AND contact IS NOT NULL AND "
                              "contact != '' AND at < ? ORDER BY at, id", (cutoff,)).fetchall()
        if not waiting and not reports:
            said.append("Nothing will lapse: no statement has waited, and no report with a contact address has been "
                        "open, for more than three months.")
        for sid, at in waiting:
            said.append(f"Statement {sid}, sent {at[:10]} ({age(at)} days ago), will be declined as undecided. To "
                        f'decide it first: councils publish-statement {sid} --checked "...", or councils '
                        f'decline-statement {sid} --reason "...".')
        for rid, at in reports:
            said.append(f"Report {rid}, sent {at[:10]} ({age(at)} days ago), will lose its contact address. To "
                        f"reply first, see councils list-reports; then councils close-report {rid}.")

        # What the new tables cannot take. The old tables' own rules already hold every column the new ones need
        # (a time, a kind, a cost, a message), but for one thing they could not check: a statement's log, which
        # the old code kept as JSON in one column and the new tables keep as a row for each entry.
        for table in ("kv", "usage", "questions", "answer_cache", "briefings", "reports"):
            if table not in tables:
                stops = True
                said.append(f"There is no {table} table: this is not the site's state database as the old code "
                            "keeps it, and the import would be passed over.")
        if "statements" in tables:
            for (sid,) in con.execute("SELECT id FROM statements WHERE NOT json_valid(log) ORDER BY id"):
                stops = True
                said.append(f"Statement {sid} would stop the import: its log is not JSON. To mend it (its log is "
                            f"then empty): UPDATE statements SET log = '[]' WHERE id = {sid};")
            for (sid,) in con.execute("SELECT DISTINCT s.id FROM statements s, json_each(s.log) j WHERE "
                                      "json_valid(s.log) AND (json_extract(j.value, '$.at') IS NULL OR "
                                      "json_extract(j.value, '$.action') IS NULL) ORDER BY s.id"):
                stops = True
                said.append(f"Statement {sid} would stop the import: an entry of its log has no time or says "
                            f"nothing of what was done. Look at it with: SELECT log FROM statements WHERE id = {sid};")
        if not stops:
            said.append("Nothing would stop the import.")
        return said, stops
    finally:
        con.close()


if __name__ == "__main__":
    database = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.environ.get("COUNCILS_DATA_DIR", "/data"),
                                                                 "state.db")
    moment = datetime.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else datetime.now(UTC)
    lines, stopped = look(database, moment)
    print("\n".join(lines))
    sys.exit(1 if stopped else 0)
