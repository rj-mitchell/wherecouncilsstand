"""The one-off copy of the site's old rows into the shared package's tables (src/councils/state.py, ``IMPORTS``;
wts-core docs/adr/0005), tested on a state database the site's own code made before the move.

tests/golden/old-state.sql is that database, with rows of every kind: spending in the summer, last month, earlier
this month and today (some with no counts, no visitor and no model, as the old table allowed); each visitor's count
for the day; cached answers, fresh and long expired; saved briefings, shown, withdrawn and one saved with its
follow-up questions; reports open and closed; statements of every status, with their logs, links and addresses,
some already deleted. tests/golden/old-state.json is what the old code gave on it: its figures must be the same
after the move as before.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "golden"))

import pytest  # noqa: E402
import shared  # noqa: E402
from test_parity import (  # noqa: E402
    a_site,
    as_the_old_tables_kept_it,
    briefings_titled_by_date,
    command,
    environment,
    kept,
    listed,
    older_name,
    site_settings,
    statements_marked,
)

from councils.state import OLD_TABLE_NAMES, open_state  # noqa: E402

MINE, OTHER = shared.visitor_of(shared.ADDRESS), shared.visitor_of("203.0.113.7")
ROOT = Path(__file__).resolve().parents[1]

# What `councils tidy` prints before its lines for the old tables and the file, since wts-core 0.3.0: the package's own deletions,
# of which the notes of failed briefings (this site keeps none), the visitor secrets and the cached answers are
# new lines, and then the site's one step, the right of reply's.
def tidy_lines(codes: int, secrets: int, cached: int, right_of_reply: str) -> list[str]:
    def counted(n: int, one: str) -> str:
        return f"{n} {one}{'' if n == 1 else 's'}"

    return ["Deleted 0 records of briefings older than 13 months.",
            "Removed the question from 0 records of failed briefings older than 90 days.",
            "Deleted 0 weekly report files older than 13 months.",
            f"Forgot the visitor codes on {counted(codes, 'spending row')} from before today.",
            "Deleted 0 notes of failed briefings older than 90 days.",
            f"Deleted {counted(secrets, 'visitor secret')} of earlier days.",
            f"Deleted {counted(cached, 'cached answer')} older than the 168 hours the site keeps one.",
            "Deleted 0 copies of the database made before an import, older than 60 days.",
            f"right of reply: {right_of_reply}"]


AFRESH = "Wrote the database out afresh: nothing deleted is left in the file."


def old_database(folder: Path) -> Path:
    """The state database as the old code left it, in the scenario's data folder."""
    folder.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(folder / "state.db")
    con.executescript((shared.GOLDEN / "old-state.sql").read_text())
    con.close()
    return folder / "state.db"


def old_tables(path: Path) -> str:
    """Everything in the database that is not the shared package's, as SQL: the old tables and their rows."""
    con = sqlite3.connect(path)
    try:
        return "\n".join(line for line in con.iterdump() if "wts_" not in line) + "\n"
    finally:
        con.close()


def count(path: Path, table: str, where: str = "1") -> int:
    con = sqlite3.connect(path)
    try:
        return con.execute(f"SELECT count(*) FROM {table} WHERE {where}").fetchone()[0]  # noqa: S608
    finally:
        con.close()


@pytest.fixture
def moved(tmp_path, monkeypatch):
    """The site started on the old database, at the moment the recorder took its figures."""
    tmp, clock = tmp_path.resolve(), shared.Clock()
    monkeypatch.setattr("councils.cli.CLOCK", clock)
    path = old_database(tmp / "old")
    before = old_tables(path)
    assert before == (shared.GOLDEN / "old-state.sql").read_text()
    s, _, app = a_site(tmp / "old", clock, state=open_state(site_settings(tmp / "old"), clock))
    environment(monkeypatch, s.data_dir)
    return tmp, clock, path, app


def test_every_row_arrives_and_the_old_tables_are_left_as_they_were(moved):
    tmp, clock, path, app = moved
    # the old tables, row for row and byte for byte, as the old code left them
    assert old_tables(path) == (shared.GOLDEN / "old-state.sql").read_text()
    for old, new in (("usage", "wts_spending"), ("answer_cache", "wts_answer_cache"), ("briefings", "wts_briefings"),
                     ("reports", "wts_reports"), ("statements", "wts_statements")):
        assert count(path, new) == count(path, old) > 0, old
    logged = sum(len(s["log"]) for s in shared.read("old-state.json")["kept"]["statements"])
    assert count(path, "wts_statement_log") == logged == 18      # a row for each entry of the seven statements' logs
    # the copy of the whole file as it was, kept beside it first and readable by its owner only
    copy = path.with_name("state.pre-wts-core.2026-11-13.db")
    assert copy.exists() and copy.stat().st_mode & 0o777 == 0o600
    assert old_tables(copy) == (shared.GOLDEN / "old-state.sql").read_text()
    assert count(copy, "wts_spending") == count(copy, "wts_statements") == count(copy, "wts_briefings") == 0
    with app.state.councils.db.connect() as con:
        # a count the old table allowed to be missing is nought; a row with no visitor or model has none
        bare = con.execute("SELECT * FROM wts_spending WHERE at = '2026-07-03T10:00:00+00:00'").fetchone()
        assert (bare["kind"], bare["model"], bare["visitor"], bare["input_tokens"], bare["output_tokens"],
                bare["cache_read_tokens"], bare["cache_write_tokens"], bare["cost_usd"]) == (
            "parse", None, None, 0, 0, 0, 0, 0.0004)
        # every spending row in the order it was written, with its cost to the last decimal
        assert [tuple(r) for r in con.execute("SELECT at, kind, model, visitor, cost_usd FROM wts_spending "
                                              "ORDER BY id")] == \
            [tuple(r) for r in con.execute("SELECT at, kind, model, visitor, cost_usd FROM usage ORDER BY rowid")]
        # the day's secret for visitors' codes, under its own name
        assert con.execute("SELECT value FROM wts_kv WHERE key = 'visitor_salt:2026-11-13'").fetchone()[0] == \
            shared.SALT
        # cached answers and saved briefings, events and all, byte for byte
        assert [tuple(r) for r in con.execute("SELECT key, created_at, events FROM wts_answer_cache ORDER BY key")] \
            == [tuple(r) for r in con.execute("SELECT key, at, events FROM answer_cache ORDER BY key")]
        assert [tuple(r) for r in con.execute("SELECT id, created_at, question, options, events, withdrawn_at, "
                                              "withdrawn_reason FROM wts_briefings ORDER BY id")] == \
            [tuple(r) for r in con.execute("SELECT id, at, question, options, events, withdrawn_at, withdrawn_reason "
                                           "FROM briefings ORDER BY id")]
        # a closed report is recorded as resolved (the old table kept no outcome), an open one as open
        assert [tuple(r) for r in con.execute("SELECT id, status, closed_at IS NOT NULL FROM wts_reports "
                                              "ORDER BY id")] == [
            (1, "open", 0), (2, "resolved", 1), (3, "open", 0), (4, "open", 0), (5, "resolved", 1)]
        # the import is recorded, so it never runs twice
        assert [r[0] for r in con.execute("SELECT name FROM wts_schema WHERE name LIKE 'import:%'")] == [
            "import:councils-state"]


def test_a_second_start_imports_nothing(moved):
    tmp, clock, path, app = moved

    def rows() -> dict:
        return {t: count(path, t) for t in ("wts_spending", "wts_answer_cache", "wts_briefings", "wts_reports",
                                            "wts_statements", "wts_statement_log", "wts_kv")}

    first = rows()
    clock.advance(3600)
    for _ in range(2):
        open_state(site_settings(tmp / "old"), clock)
    assert rows() == first
    assert sorted(p.name for p in path.parent.glob("state.pre-wts-core.*")) == ["state.pre-wts-core.2026-11-13.db"]


def test_a_new_site_has_no_old_tables_and_nothing_to_import(tmp_path):
    db = open_state(site_settings(tmp_path / "new"), shared.Clock())
    assert not set(OLD_TABLE_NAMES) & db.tables() and not list((tmp_path / "new").glob("state.pre-wts-core.*"))
    with db.connect() as con:
        assert con.execute("SELECT count(*) FROM wts_schema WHERE name LIKE 'import:%'").fetchone()[0] == 0
        assert con.execute("SELECT value FROM wts_kv WHERE key = 'site'").fetchone()[0] == "councils"


def test_the_sites_figures_are_the_same_after_the_move_as_before(moved, tmp_path):
    """Spending today and this month, each visitor's count, who is refused and why, the cached answers still
    served, the saved briefings still at their addresses, the statements still shown, the status page."""
    from fastapi.testclient import TestClient

    from councils.api.app import build

    tmp, clock, path, app = moved
    golden = shared.read("old-state.json")
    site = app.state.councils
    spending, caps, cache = site.parts.spending, site.parts.caps, site.parts.cache
    assert spending.spent_since("2026-11-13") == golden["spent_today"] == 0.345498
    assert spending.spent_since("2026-11") == golden["spent_this_month"] == 0.372098
    assert {"mine": spending.briefings_today(visitor=MINE), "other": spending.briefings_today(visitor=OTHER),
            "nobody": spending.briefings_today(visitor="nobody")} == golden["briefings_today"]
    tight = build(site_settings(tmp / "old", {"per_visitor_daily_questions": 2, "daily_spend_cap_usd": 0.2}),
                  site.db, clock=clock).parts.caps

    def said(refusal) -> str | None:
        return refusal.message if refusal else None

    assert {"mine": said(caps.refusal(visitor=MINE)), "paused": said(caps.site_paused()),
            "mine, with a limit of two a day": said(tight.refusal(visitor=MINE)),
            "other, with a limit of two a day": said(tight.refusal(visitor=OTHER)),
            "paused, with a cap of 20 cents and 10 pending": said(tight.site_paused(0.1)),
            "paused, with a cap of 20 cents and 13 pending": said(tight.site_paused(0.13))} == golden["refused"]
    assert {key: cache.get(key, 168) for key in golden["cached"]} == golden["cached"]
    assert [k for k, v in golden["cached"].items() if v] == ["an-hour-old", "six-days-old"]
    client = TestClient(app)
    reads = [shared.send(client, {"get": answer["case"]}) for answer in golden["reads"]]
    # a statement about a saved briefing is labelled with the briefing's title, not its question (test_parity.py)
    assert statements_marked(reads, golden["reads"], at_least=1) == briefings_titled_by_date(golden["reads"], app)
    assert len(reads) == 11
    from wts_core.usage import visitor_code

    assert visitor_code(site.db, shared.ADDRESS, clock=clock) == golden["visitor"] == MINE


def test_reports_and_statements_are_kept_and_listed_as_before(moved):
    tmp, clock, path, app = moved
    golden = shared.read("old-state.json")
    replies = app.state.councils.replies
    # Reading what is kept tidies first, in the package as in the site's own listings: the address of the statement
    # withdrawn on 13 August, three months and an hour before, is deleted. The old code's figures show the same
    # address there before its first listing and gone after it, and nothing else changed.
    assert golden["addresses_deleted_at_the_next_tidy"] == 0
    differ = [(a["id"], a["email"], b["email"]) for a, b in zip(golden["kept"]["statements"],
                                                               golden["kept_after_the_tidy"]["statements"], strict=True)
              if a != b]
    assert differ == [(3, "tim@guildford.gov.uk", "")]
    then = golden["kept_after_the_tidy"]
    for report in then["reports"]:           # a row the old table held with no page or contact at all
        report["page"], report["contact"] = report["page"] or "", report["contact"] or ""
    now = as_the_old_tables_kept_it(kept(replies))
    # wts-core docs/adr/0008, "confirming the sender": the note of how a sender was confirmed never holds their
    # address. When the address is deleted it is taken out of the log's notes too, which the old code left there.
    was = then["statements"][2]["log"][1]
    assert was == ["published", "Reply from tim@guildford.gov.uk, 12 August."]
    assert now["statements"][2]["log"][1] == ["published", "Reply from [address deleted], 12 August."]
    then["statements"][2]["log"][1] = now["statements"][2]["log"][1]
    assert now == then
    # the date each published statement is shown with is the date it had
    shown = {s["id"]: s["shown_on"] for s in then["statements"] if s["shown_on"]}
    assert shown == {2: "2026-07-02", 3: "2026-08-12", 4: "2026-11-11", 5: "2026-11-10", 7: "2026-11-10"}
    # the owner's listings: each statement's and report's own lines as before; open takedown requests first now
    for run in golden["listed"]:
        got = command(run["args"], tmp)
        # each was recorded under the name the command had before, which now says so first, on standard error
        # (wts-core 0.3.0), and nothing else
        assert got["exit_code"] == run["exit_code"] == 0 and got["stderr"] == older_name(run["args"][0])
        if run["args"][0] == "list-statements":
            assert got["stdout"] == run["stdout"], run["args"]
        else:
            first = [b for b in listed(run["stdout"]) if "  takedown  " in b and "(closed)" not in b]
            assert listed(got["stdout"]) == first + [b for b in listed(run["stdout"]) if b not in first]


def test_what_nobody_decided_in_three_months_lapses_at_the_first_tidy(tmp_path, monkeypatch):
    """wts-core docs/adr/0008, the second question: the first write after the import can lapse old rows at once. A
    statement that has waited three months is declined with the reason its sender is told, and
    its address deleted; a report open that long keeps its place and loses its contact address."""
    tmp, clock = tmp_path.resolve(), shared.Clock()
    path = old_database(tmp / "old")
    con = sqlite3.connect(path)
    con.execute("UPDATE statements SET at = '2026-08-13T11:59:59+00:00' WHERE id = 6")           # the one waiting
    con.execute("UPDATE reports SET at = '2026-08-01T09:00:00+00:00' WHERE id = 4")              # open, with a contact
    con.commit()
    con.close()
    _, _, app = a_site(tmp / "old", clock, state=open_state(site_settings(tmp / "old"), clock))
    replies = app.state.councils.replies
    waiting = replies.statement(6)
    assert (waiting["status"], waiting["email"]) == ("pending", "leader@guildford.gov.uk")       # as imported
    assert replies.waiting().statements == 0                                                     # the first tidy
    lapsed = replies.statement(6)
    assert (lapsed["status"], lapsed["email"], lapsed["reason"]) == (
        "declined", None, "No decision was made in time; please send it again.")
    assert replies.log(6)[-1]["action"] == "lapsed"
    report = next(r for r in replies.reports() if r["id"] == 4)
    assert report["contact"] is None and report["closed_at"] is None


# Going back


def old_rows(path: Path) -> dict:
    """The old tables as the old code reads them, with a statement's log read as the list it is."""
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        out = {t: [dict(r) for r in con.execute(f"SELECT * FROM {t} ORDER BY rowid")] for t in OLD_TABLE_NAMES}  # noqa: S608
    finally:
        con.close()
    for statement in out["statements"]:
        statement["log"] = json.loads(statement["log"])
    return out


def run_script(path: Path, name: str) -> None:
    """One of the scripts in deploy/, run as docs/OPERATIONS.md says: the whole file, on the database."""
    con = sqlite3.connect(path)
    try:
        con.executescript((ROOT / "deploy" / name).read_text())
    finally:
        con.close()          # a script that stopped part-way is rolled back: nothing is changed


def undo(path: Path) -> None:
    run_script(path, "undo-wts-core.sql")


def redo(path: Path) -> None:
    run_script(path, "redo-wts-core.sql")


def test_going_back_straight_after_the_move_gives_the_old_code_what_it_had(moved):
    """deploy/undo-wts-core.sql writes the old tables again from the package's. Run on a database nothing has
    happened to since the move, the old tables must hold what they held, but for what the script says it folds."""
    tmp, clock, path, app = moved
    before = old_rows(path)
    undo(path)
    after = old_rows(path)
    # a count the old table allowed to be missing has come back as nought
    for row in before["usage"]:
        for column in ("input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens"):
            row[column] = row[column] or 0
    # the old code kept a visitor's count only for the day; the script writes one for each day there are rows for
    def by_visitor(rows: list) -> list:
        return sorted(rows, key=lambda q: (q["day"], q["visitor"]))

    assert by_visitor(before["questions"]) == by_visitor(q for q in after["questions"] if q["day"] == "2026-11-13")
    after["questions"] = before["questions"]
    # a report with no page or contact at all has an empty one, as the old code's own rows have
    for row in before["reports"]:
        row["page"], row["contact"] = row["page"] or "", row["contact"] or ""
    assert after == before


def test_going_back_later_carries_across_what_has_come_in_since(moved, monkeypatch):
    from fastapi.testclient import TestClient

    tmp, clock, path, app = moved
    ids = iter(["newbrief001"])
    monkeypatch.setattr("councils.api.app.new_briefing_id", lambda chance: next(ids))
    client = TestClient(app)
    clock.advance(600)
    assert client.post("/api/report", json={"kind": "error", "page": "/b/abc123", "message": "A wrong date."}
                       ).json() == {"ok": True, "id": 6}
    sid = client.post("/api/statements", json={**shared.FORM, "text": "Sent after the move."}).json()["id"]
    replies = app.state.councils.replies
    replies.publish(sid, checked="Letter.")
    replies.remove(4, "It names an officer.")
    replies.close(3, outcome="dismissed", note="Not ours to change.", public_note="Nothing was changed.")
    replies.hide(f"/votes/{shared.VOTE}", "Hidden while we look into a concern about it.")
    final = shared.events_of(client.post("/api/ask", json={"question": "What have councils decided about bins?"}
                                         ).text)[-1]
    assert final["briefing_id"] == "newbrief001"
    undo(path)
    after = old_rows(path)
    assert after["reports"][-1] == {"id": 6, "at": "2026-11-13T12:10:00+00:00", "kind": "error", "page": "/b/abc123",
                                    "message": "A wrong date.", "contact": "", "closed_at": None}
    assert after["reports"][2]["closed_at"] == "2026-11-13T12:10:00+00:00"
    sent = after["statements"][-1]
    assert (sent["id"], sent["status"], sent["shown_on"], sent["text"], sent["page"], sent["council"]) == (
        8, "published", "2026-11-13", "Sent after the move.", f"/votes/{shared.VOTE}", shared.BARNSLEY)
    assert [(e["action"], e.get("note")) for e in sent["log"]] == [("received", None), ("published", "Letter.")]
    removed = after["statements"][3]
    assert (removed["status"], removed["reason"], removed["log"][-1]["action"]) == (
        "withdrawn", "It names an officer.", "withdrawn")
    assert [b["id"] for b in after["briefings"]][-1] == "newbrief001" and len(after["briefings"]) == 5
    assert [(u["kind"], u["day"], u["visitor"]) for u in after["usage"]][-1] == ("answer", "2026-11-13", MINE)
    assert len(after["usage"]) == 13
    assert {(q["day"], q["visitor"]): q["n"] for q in after["questions"]}[("2026-11-13", MINE)] == 3
    # the new answer, and the two still within their week; the one long expired was dropped when it was stored
    assert {"an-hour-old", "six-days-old"} < {c["key"] for c in after["answer_cache"]}
    assert len(after["answer_cache"]) == 3


# Going back without the undo script, and coming forward again (wts-core 0.3.0)

# The old code's kind of write, as its own tables took one (tests/golden/old-state.sql has their shape): a model
# call recorded, a briefing saved, a reader's report, a statement sent, an answer cached. Each a minute after the move.
AFTER_THE_MOVE = "2026-11-13T12:01:00+00:00"
OLD_CODE_WRITES = {
    "usage": ("INSERT INTO usage (at, day, visitor, kind, model, input_tokens, output_tokens, cache_read_tokens, "
              f"cache_write_tokens, cost_usd) VALUES ('{AFTER_THE_MOVE}', '2026-11-13', '{MINE}', 'answer', "
              "'claude-sonnet-5-5', 9000, 700, 0, 0, 0.0375)"),
    "briefings": ("INSERT INTO briefings (id, at, question, options, events) VALUES ('oldcode0001', "
                  f"'{AFTER_THE_MOVE}', 'Asked of the old code after the move?', '{{}}', '[]')"),
    "reports": ("INSERT INTO reports (at, kind, page, message, contact) VALUES "
                f"('{AFTER_THE_MOVE}', 'error', '', 'Sent to the old code after the move.', '')"),
    "statements": ("INSERT INTO statements (at, page, council, name, role, text) VALUES "
                   f"('{AFTER_THE_MOVE}', '/councils/E08000038', 'E08000038', 'A B', 'Councillor', 'Sent to the old "
                   "code.')"),
    "answer_cache": f"INSERT INTO answer_cache (key, at, events) VALUES ('cached-by-the-old-code', '{AFTER_THE_MOVE}', '[]')",
}


def written_by_the_old_code(path: Path, *tables: str) -> None:
    con = sqlite3.connect(path)
    for table in tables:
        con.execute(OLD_CODE_WRITES[table])
    con.commit()
    con.close()


@pytest.mark.parametrize("table", sorted(OLD_CODE_WRITES))
def test_a_row_the_old_code_wrote_after_the_move_stops_the_new_code_and_the_words_name_the_mend(moved, table):
    """wts-core 0.3.0, `state.StateError` and `Import(written_at=…)`: the site is put back on its old
    code without deploy/undo-wts-core.sql, the old code writes to its own tables, and the new code is deployed
    again. The import is marked as done and would be skipped: what was written meanwhile would be silently
    missing. The new code refuses to open the database, changes nothing, and says what to run."""
    from wts_core.state import StateError

    tmp, clock, path, app = moved
    clock.advance(3600)
    open_state(site_settings(tmp / "old"), clock)                  # as it stands, the database opens
    written_by_the_old_code(path, table)
    before = everything_in(path)
    with pytest.raises(StateError) as refused:
        open_state(site_settings(tmp / "old"), clock)
    said = str(refused.value)
    assert f"{table} has 1 row written after the import 'councils-state' ran (2026-11-13T12:00:00+00:00)" in said
    assert "Nothing has been changed" in said and everything_in(path) == before
    # the package's words for the mend, and then this site's: which of its two scripts, and what each discards
    assert "run the site's script for undoing the move" in said
    assert "deploy/redo-wts-core.sql, which keeps what the old code wrote" in said
    assert "Do not run undo-wts-core.sql to keep what the old code wrote" in said
    assert 'docs/OPERATIONS.md, "Going back, and coming forward again"' in said
    # and the site does not start, nor does a command of the owner's
    from councils.api.app import create_app

    with pytest.raises(StateError):
        create_app(site_settings(tmp / "old"), clock=clock)
    assert isinstance(command(["reports", "list"], tmp)["error"], str)


def test_the_mend_brings_across_what_the_old_code_wrote_meanwhile(moved):
    """deploy/redo-wts-core.sql forgets the move and touches nothing else: the next start of the new code makes
    the move afresh, and what the old code wrote since is there, counted and found."""
    from wts_core.state import StateError

    tmp, clock, path, app = moved
    spent = app.state.councils.parts.spending.spent_since("2026-11-13")
    clock.advance(3600)
    written_by_the_old_code(path, *OLD_CODE_WRITES)
    old_tables_then = old_tables(path)
    with pytest.raises(StateError):
        open_state(site_settings(tmp / "old"), clock)
    redo(path)
    assert old_tables(path) == old_tables_then                     # the old tables are not touched
    assert count(path, "wts_spending") == count(path, "wts_briefings") == count(path, "wts_reports") == 0
    assert count(path, "wts_schema", "name = 'import:councils-state'") == 0
    _, _, again = a_site(tmp / "old", clock, state=open_state(site_settings(tmp / "old"), clock))
    site = again.state.councils
    assert site.parts.spending.spent_since("2026-11-13") == round(spent + 0.0375, 6)
    assert site.parts.spending.briefings_today(visitor=MINE) == 3              # two before the move, and this one
    assert site.parts.archive.get("oldcode0001").question == "Asked of the old code after the move?"
    assert site.parts.cache.get("cached-by-the-old-code", 168) == []
    assert "Sent to the old code after the move." in [r["message"] for r in site.replies.reports()]
    assert site.replies.statement(8)["text"] == "Sent to the old code."
    assert count(path, "wts_schema", "name = 'import:councils-state'") == 1
    open_state(site_settings(tmp / "old"), clock)                  # and it opens from then on
    # a second run of either script on a database whose move has been forgotten changes nothing
    redo(path)
    forgotten = everything_in(path)
    for script in (redo, undo):
        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            script(path)
        assert everything_in(path) == forgotten


def test_the_undo_script_run_in_that_state_would_discard_what_the_old_code_wrote(moved):
    """Why the refusal's words name deploy/redo-wts-core.sql and warn against the other: deploy/undo-wts-core.sql
    writes the old tables afresh from the package's. That is right before the old code is started, and for the
    false alarm (the server's clock put back). Run after the old code has written, it discards those rows, as
    its own heading says."""
    tmp, clock, path, app = moved
    clock.advance(3600)
    written_by_the_old_code(path, "briefings", "reports")
    undo(path)
    assert count(path, "briefings", "id = 'oldcode0001'") == 0
    assert count(path, "reports", "message = 'Sent to the old code after the move.'") == 0
    assert "WHAT THIS DISCARDS. Anything the OLD code has written" in (ROOT / "deploy" / "undo-wts-core.sql").read_text()


def test_the_nightly_tidy_of_the_old_tables_never_looks_like_the_old_code_writing(moved):
    """wts-core docs/EXTENDING.md, section 6: the nightly tidy of the old tables never trips the check on rows
    written since the import, since it changes and deletes rows and adds none. A week of nights on the new code, with readers
    and the owner at work each day: the database opens every morning."""
    from fastapi.testclient import TestClient

    tmp, clock, path, app = moved
    client = TestClient(app)
    for night in range(14, 21):
        # the day's work on the new code: a report, a briefing, an owner's decision (rows of the package's tables)
        client.post("/api/report", json={"kind": "error", "page": "", "message": f"Sent before the night of {night}."})
        client.post("/api/ask", json={"question": f"What have councils decided about bins, asked before {night}?"})
        clock.set(f"2026-11-{night}T04:30:00+00:00")
        tidied = command(["tidy"], tmp)
        assert tidied["exit_code"] == 0, tidied
        assert "Kept the site's old tables within what it promises" in tidied["stdout"]
        clock.set(f"2026-11-{night}T09:00:00+00:00")
        open_state(site_settings(tmp / "old"), clock)
    # the old tables were changed by those nights (codes, counts and the old secret gone), and nothing was added
    assert count(path, "usage", "visitor IS NOT NULL") == 0 and count(path, "questions") == count(path, "kv") == 0
    assert count(path, "usage") == 12 and count(path, "reports") == 5 and count(path, "briefings") == 4


def test_going_back_and_coming_forward_again_counts_nothing_twice(moved):
    """wts-core docs/UPGRADING.md, "Going back to the old code": the undo script ends by
    forgetting the move, with what the package keeps in summary of the spending rows (wts_account_months, and the
    month rows of wts_visitor_days). The old code then runs; the new code, started again, makes the move afresh.
    The spending, and the report of who it was for, are what they were, once."""
    from fastapi.testclient import TestClient

    tmp, clock, path, app = moved
    client = TestClient(app)
    assert shared.events_of(client.post("/api/ask", json={"question": "What have councils decided about bins?"}
                                        ).text)[-1]["type"] == "final"
    clock.set("2026-11-14T04:30:00+00:00")
    assert command(["tidy"], tmp)["exit_code"] == 0               # the night's forgetting: codes, times of day
    spending = app.state.councils.parts.spending
    month, year = spending.spent_since("2026-11"), spending.spent_since("2026")
    lines = spending.by_account("2026-11-01")
    assert count(path, "wts_visitor_days", "who != '*'") > 0      # the public's visitors, by the month
    calls = count(path, "wts_spending", "at >= '2026-11'")
    assert round(sum(line.spent_usd for line in lines), 6) == month and sum(line.calls for line in lines) == calls
    rows = count(path, "wts_spending")

    undo(path)
    # what the old code is given back, as the script's heading says: every row with its day and its cost, exact;
    # of a day gone by, no visitor's code and its day's midnight as its time
    back = old_rows(path)["usage"]
    assert len(back) == rows and round(sum(u["cost_usd"] for u in back if u["day"] >= "2026-11-01"), 6) == month
    assert round(sum(u["cost_usd"] for u in back), 6) == year
    assert all(u["at"] == f"{u['day']}T00:00:00+00:00" and not u["visitor"] for u in back)
    # and the move is forgotten: the package's copies are empty, with what summarised them, and the mark is gone
    for table in ("wts_spending", "wts_account_months", "wts_answer_cache", "wts_briefings", "wts_reports",
                  "wts_statements", "wts_statement_log"):
        assert count(path, table) == 0, table
    assert count(path, "wts_visitor_days", "who != '*'") == 0
    assert count(path, "wts_kv", "key LIKE 'visitor_salt:%'") == 0
    assert count(path, "wts_schema", "name = 'import:councils-state'") == 0
    assert count(path, "wts_kv", "key = 'site'") == 1 and count(path, "wts_briefing_log") > 0   # kept as they are

    # the old code runs for a day, and takes a briefing in
    written_by_the_old_code(path, "usage", "briefings")
    clock.set("2026-11-15T09:00:00+00:00")
    _, _, again = a_site(tmp / "old", clock, state=open_state(site_settings(tmp / "old"), clock))
    spending = again.state.councils.parts.spending
    assert count(path, "wts_spending") == rows + 1                # each row once, and the old code's one
    assert spending.spent_since("2026-11") == round(month + 0.0375, 6)
    assert spending.spent_since("2026") == round(year + 0.0375, 6)
    assert command(["tidy"], tmp)["exit_code"] == 0
    lines = spending.by_account("2026-11-01")
    assert round(sum(line.spent_usd for line in lines), 6) == round(month + 0.0375, 6)
    assert sum(line.calls for line in lines) == calls + 1
    assert again.state.councils.parts.archive.get("oldcode0001") is not None
    assert again.state.councils.parts.archive.get("abc123") is not None


def test_the_two_scripts_forget_the_move_with_the_same_statements():
    def forgetting(name: str) -> list[str]:
        text = (ROOT / "deploy" / name).read_text()
        return [line for line in text[text.index("-- Forgetting the move"):].splitlines()
                if line and not line.startswith("--")]

    assert forgetting("undo-wts-core.sql") == forgetting("redo-wts-core.sql")
    assert "DELETE FROM wts_account_months;" in forgetting("undo-wts-core.sql")
    assert "DELETE FROM wts_visitor_days WHERE who != '*';" in forgetting("undo-wts-core.sql")
    assert forgetting("undo-wts-core.sql")[-2:] == ["DELETE FROM wts_schema WHERE name = 'import:councils-state';",
                                                    "COMMIT;"]


# The old tables after the move: kept within the site's promises, then dropped


def everything_in(path: Path) -> str:
    """Every value of every table of a database, as text: where an address would be if it were kept."""
    con = sqlite3.connect(path)
    try:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
        return "\n".join(repr(tuple(row)) for t in tables for row in con.execute(f'SELECT * FROM "{t}"'))  # noqa: S608
    finally:
        con.close()


def test_the_old_tables_keep_nothing_the_site_has_promised_to_delete_and_then_go(tmp_path, monkeypatch):
    """Left as they were, the old
    tables kept senders' addresses and reports' contacts for good, and so did every night's backup. Every night
    `councils tidy` keeps each promise on the old tables that the package keeps on its own, and from 1 February
    2027 it drops them. Then, 125 days after the move, no address is anywhere in the data folder or in a backup."""
    import gzip

    tmp, clock = tmp_path.resolve(), shared.Clock()
    monkeypatch.setattr("councils.cli.CLOCK", clock)
    path = old_database(tmp / "old")
    con = sqlite3.connect(path)      # and, as an old database could have them: a day gone by, with its secret
    con.execute("INSERT INTO kv VALUES ('visitor_salt:2026-11-12', 'the secret of the day before')")
    con.execute("INSERT INTO questions VALUES ('2026-11-12', 'acodeofthedaybefore', 2)")
    addresses = [r[0] for r in con.execute("SELECT email FROM statements WHERE email != '' UNION "
                                           "SELECT contact FROM reports WHERE contact != ''")]
    codes = {r[0] for r in con.execute("SELECT visitor FROM usage WHERE visitor IS NOT NULL AND day < '2026-11-13'")}
    con.commit()
    con.close()
    assert sorted(addresses) == ["c@d.org", "cllr@barnsley.gov.uk", "dem@barnsley.gov.uk", "leader@guildford.gov.uk",
                                 "recent@barnsley.gov.uk", "tim@guildford.gov.uk"] and len(codes) >= 2
    s = site_settings(tmp / "old")
    environment(monkeypatch, s.data_dir)

    def run(*args: str) -> dict:
        clock.advance(61)
        got = command(list(args), tmp)
        assert got["exit_code"] == 0, got
        return got

    def old(sql: str) -> list[tuple]:
        con = sqlite3.connect(path)
        try:
            return [tuple(r) for r in con.execute(sql)]
        finally:
            con.close()

    # the owner's decisions, on the new code: every statement ended, every report closed
    run("reports", "close", "4", "--note", "Replied.")
    run("reports", "close", "1")
    run("reports", "close", "3")
    run("statements", "withdraw", "4")
    run("statements", "withdraw", "5")
    run("statements", "decline", "6", "--reason", "It is about another councillor's conduct.")
    # until the night's tidy the old rows are as they were, with what the package has already deleted
    assert old("SELECT contact FROM reports WHERE id = 4") == [("c@d.org",)]
    assert old("SELECT email FROM statements WHERE id = 3") == [("tim@guildford.gov.uk",)]
    assert "tim@guildford.gov.uk" in old("SELECT log FROM statements WHERE id = 3")[0][0]

    said = run("tidy")["stdout"]
    # 1. a statement's address: gone from the old row wherever the package's row has none, and out of its old log
    #    (statement 3 was withdrawn three months before; the package deleted its address at the first listing)
    assert old("SELECT email, log FROM statements WHERE id = 3") == [
        ("", old("SELECT log FROM statements WHERE id = 3")[0][0])]
    assert "tim@guildford.gov.uk" not in everything_in(path) and "[address deleted]" in \
        old("SELECT log FROM statements WHERE id = 3")[0][0]
    #    while those ended today keep theirs for three months, in the old row as in the package's
    assert old("SELECT id, email FROM statements WHERE email != '' ORDER BY id") == [
        (4, "cllr@barnsley.gov.uk"), (5, "dem@barnsley.gov.uk"), (6, "leader@guildford.gov.uk"),
        (7, "recent@barnsley.gov.uk")]
    # 2. a closed report's contact
    assert old("SELECT count(*) FROM reports WHERE contact IS NOT NULL AND contact != ''") == [(0,)]
    assert "c@d.org" not in everything_in(path)
    # 3. visitors' codes of days gone by: off the old spending rows, and the old daily counts deleted; today's stay
    assert old("SELECT count(*) FROM usage WHERE visitor IS NOT NULL AND day < '2026-11-13'") == [(0,)]
    assert old("SELECT count(*) FROM usage WHERE visitor IS NOT NULL AND day = '2026-11-13'") != [(0,)]
    assert old("SELECT DISTINCT day FROM questions") == [("2026-11-13",)]
    assert old("SELECT count(*) FROM usage") == [(12,)]                       # the spending itself is all there
    # (in the package's table: the 12 rows, and two of no cost for the two briefings the day before's count held)
    assert count(path, "wts_spending") == 14
    assert not any(code in everything_in(path) for code in codes | {"acodeofthedaybefore"})
    # 4. every old secret but today's
    assert old("SELECT key FROM kv") == [("visitor_salt:2026-11-13",)]
    # 5. answers in the old cache past their week
    assert old("SELECT min(at) >= '2026-11-06' , count(*) FROM answer_cache") == [(1, 2)]
    # What the command says, line by line and in the order it works (wts-core 0.3.0): the package's own deletions; then the site's step,
    # the right of reply's; then the old tables, AFTER it, so an address the right of reply deletes tonight is gone
    # from the old row tonight; and last the file written out afresh. The site's own second pass over the old
    # tables and its own VACUUM, which 0.2.1 needed, are gone (tidy_lines).
    nothing = "0 confirming addresses deleted, 0 statements lapsed undecided, 0 old reports' contact addresses deleted"
    assert said.splitlines() == tidy_lines(codes=6, secrets=1, cached=1, right_of_reply=nothing) + [
        "Kept the site's old tables within what it promises: 11 rows changed or deleted. They are dropped on "
        "2027-02-01.", AFRESH]

    # the next night: the day's codes and secret have had their day
    clock.set("2026-11-14T04:00:00+00:00")
    run("tidy")
    assert old("SELECT count(*) FROM usage WHERE visitor IS NOT NULL") == [(0,)]
    assert old("SELECT count(*) FROM questions") == [(0,)] and old("SELECT count(*) FROM kv") == [(0,)]

    # the day before the old tables go, they are there; on the day, they are dropped, and nothing else is
    clock.set("2027-01-31T04:00:00+00:00")
    run("tidy")
    assert set(OLD_TABLE_NAMES) <= open_state(s, clock).tables()
    clock.set("2027-02-01T04:00:00+00:00")
    # the command's own line says which tables went (0.2.1: the site's own second pass dropped them first, and
    # this line was never printed), after the right of reply's line and before the last
    assert run("tidy")["stdout"].splitlines()[-3:] == [
        "right of reply: 0 confirming addresses deleted, 0 statements lapsed undecided, 0 old reports' contact "
        "addresses deleted",
        "Dropped the site's old tables, kept since it moved to the shared package: kv, usage, questions, "
        "answer_cache, briefings, reports, statements.", AFRESH]
    tables = open_state(s, clock).tables()
    assert not set(OLD_TABLE_NAMES) & tables and {"wts_spending", "wts_briefings", "wts_statements"} <= tables
    assert count(path, "wts_spending") == 14 and count(path, "wts_briefings") > 0 and count(path, "wts_statements") == 7
    # going back by deploy/undo-wts-core.sql is no longer possible, and trying changes nothing
    before = everything_in(path)
    with pytest.raises(sqlite3.OperationalError, match="no such table"):
        undo(path)
    assert everything_in(path) == before

    # 125 days after the move: three months have passed since every statement ended. No address is in any table,
    # in any file of the data folder (the copy made before the import has gone too), or in a backup made now.
    clock.set("2027-03-18T04:00:00+00:00")
    run("tidy")
    run("backup", "--to", str(tmp / "backups"))
    (archive,) = sorted((tmp / "backups").glob("councils-state-*.sqlite.gz"))
    (tmp / "restored.db").write_bytes(gzip.decompress(archive.read_bytes()))
    assert not list(s.data_dir.glob("state.pre-wts-core.*"))
    for address in addresses:
        assert address not in everything_in(path), address
        assert address not in everything_in(tmp / "restored.db"), address
    files = [f for f in s.data_dir.rglob("*") if f.is_file() and f.name.startswith("state")]
    assert [f.name for f in files] == ["state.db"]
    # nor in the bytes of either file: SQLite leaves what it deletes in a file's unused space, and a dropped
    # table's rows whole, so the tidy ends by writing the database out afresh (the package's own last step since
    # wts-core 0.3.0; until then the site's own)
    for address in addresses:
        for file in (path, tmp / "restored.db"):
            assert address.encode() not in file.read_bytes(), (address, file.name)


def test_the_tidy_says_each_thing_it_did_once_and_in_order_on_a_quiet_night(moved):
    """wts-core 0.3.0: the nightly tidy runs in a fixed order and says what it did. The whole of what `councils tidy` prints, on the night of the move and the night after. Nothing is said twice:
    the old tables have one line, the command's own, and the file is written out afresh once, last."""
    tmp, clock, path, app = moved
    nothing = "0 confirming addresses deleted, 0 statements lapsed undecided, 0 old reports' contact addresses deleted"
    first = command(["tidy"], tmp)
    assert (first["exit_code"], first["stderr"]) == (0, "")
    # the night of the move: the codes of the four spending rows of days gone by, the cached answer long past its
    # week (0.2.1 left it until the next answer was stored), and in the old tables what matches both
    assert first["stdout"].splitlines() == tidy_lines(
        codes=4, secrets=0, cached=1, right_of_reply="1 confirming addresses deleted, 0 statements lapsed "
        "undecided, 0 old reports' contact addresses deleted") + [
        "Kept the site's old tables within what it promises: 8 rows changed or deleted. They are dropped on "
        "2027-02-01.", AFRESH]
    clock.set("2026-11-14T04:30:00+00:00")
    second = command(["tidy"], tmp)
    assert (second["exit_code"], second["stderr"]) == (0, "")
    # the next night: the day of the move is over, so its rows' codes and its secret go
    assert second["stdout"].splitlines() == tidy_lines(codes=7, secrets=1, cached=0, right_of_reply=nothing) + [
        "Kept the site's old tables within what it promises: 10 rows changed or deleted. They are dropped on "
        "2027-02-01.", AFRESH]
    again = command(["tidy"], tmp)["stdout"].splitlines()        # run twice in a night: nothing is left to do
    assert again == tidy_lines(codes=0, secrets=0, cached=0, right_of_reply=nothing) + [
        "Kept the site's old tables within what it promises: 0 rows changed or deleted. They are dropped on "
        "2027-02-01.", AFRESH]


def test_a_database_from_before_the_right_of_reply_is_brought_across_without_statements(tmp_path, monkeypatch):
    """The first review's second finding: an import that needs a table an older backup lacks is passed over on that
    database for good. The old `statements` table came on 12 November 2026; a backup from before then, put back
    by hand (docs/OPERATIONS.md), has the other six. Everything in them comes across, and the site runs."""
    from fastapi.testclient import TestClient

    tmp, clock = tmp_path.resolve(), shared.Clock()
    monkeypatch.setattr("councils.cli.CLOCK", clock)
    path = old_database(tmp / "old")
    con = sqlite3.connect(path)
    con.execute("DROP TABLE statements")
    con.commit()
    con.close()
    s, _, app = a_site(tmp / "old", clock, state=open_state(site_settings(tmp / "old"), clock))
    environment(monkeypatch, s.data_dir)
    for was, now in (("usage", "wts_spending"), ("answer_cache", "wts_answer_cache"), ("briefings", "wts_briefings"),
                     ("reports", "wts_reports")):
        assert count(path, now) == count(path, was) > 0, was
    assert count(path, "wts_statements") == 0 and count(path, "wts_schema", "name = 'import:councils-state'") == 1
    client = TestClient(app)
    assert client.get(f"/api/statements?council={shared.BARNSLEY}").json()["statements"] == []
    assert client.get("/api/status").status_code == 200
    # the nightly tidy passes over the table that is not there, and the other six go on their day
    assert command(["tidy"], tmp)["exit_code"] == 0
    clock.set("2027-02-01T04:00:00+00:00")
    assert command(["tidy"], tmp)["exit_code"] == 0
    assert not set(OLD_TABLE_NAMES) & open_state(s, clock).tables()


def test_after_the_old_tables_go_neither_script_changes_anything(moved):
    """From 1 February 2027 the nightly tidy drops the old tables. deploy/redo-wts-core.sql would then forget a
    move it could not make again, and the site would be left with no spending, no saved briefings, no reports and
    no statements. So it first asks for each old table the import needs, and stops ("no such table") before it
    deletes anything. deploy/undo-wts-core.sql writes the old tables before it forgets the move, so it stops at its
    first write. Either way the package's tables and the move's mark are as they were."""
    tmp, clock, path, app = moved
    clock.set("2027-02-01T04:00:00+00:00")
    assert command(["tidy"], tmp)["exit_code"] == 0
    assert not set(OLD_TABLE_NAMES) & open_state(site_settings(tmp / "old"), clock).tables()
    assert min(count(path, t) for t in ("wts_spending", "wts_briefings", "wts_reports", "wts_statements")) > 0
    before = everything_in(path)
    for script in (redo, undo):
        with pytest.raises(sqlite3.OperationalError, match="no such table"):
            script(path)
        assert everything_in(path) == before, script.__name__
        assert count(path, "wts_schema", "name = 'import:councils-state'") == 1


def test_the_redo_script_asks_for_the_tables_the_import_needs_and_no_others(tmp_path):
    """The redo script's first step asks for exactly the old tables the import needs (``ALWAYS_THERE``), before
    anything is deleted. It does not ask for `statements`: a database from before 12 November 2026 never had it,
    and the move is made again on one all the same."""
    from councils.state import ALWAYS_THERE, IMPORTS

    text = (ROOT / "deploy" / "redo-wts-core.sql").read_text()
    asked = [line.removeprefix("SELECT count(*) FROM ").rstrip(";") for line in text.splitlines()
             if line.startswith("SELECT count(*) FROM ")]
    assert asked == list(ALWAYS_THERE) == list(IMPORTS[0].needs)
    assert text.index("\nSELECT count(*) FROM ") < text.index("\nDELETE FROM ")
    clock = shared.Clock()
    path = old_database(tmp_path / "old")
    con = sqlite3.connect(path)
    con.execute("DROP TABLE statements")
    con.commit()
    con.close()
    open_state(site_settings(tmp_path / "old"), clock)
    redo(path)
    assert count(path, "wts_spending") == count(path, "wts_briefings") == 0
    assert count(path, "wts_schema", "name = 'import:councils-state'") == 0
    open_state(site_settings(tmp_path / "old"), clock)             # the next start makes the move again
    assert count(path, "wts_spending") == count(path, "usage") > 0
    assert count(path, "wts_briefings") == count(path, "briefings") > 0
    assert count(path, "wts_schema", "name = 'import:councils-state'") == 1
