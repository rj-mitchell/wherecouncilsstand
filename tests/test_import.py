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
    command,
    environment,
    kept,
    listed,
    site_settings,
)

from councils.state import OLD_TABLES, open_state  # noqa: E402

MINE, OTHER = shared.visitor_of(shared.ADDRESS), shared.visitor_of("203.0.113.7")
ROOT = Path(__file__).resolve().parents[1]


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
    assert not set(OLD_TABLES) & db.tables() and not list((tmp_path / "new").glob("state.pre-wts-core.*"))
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
    assert reads == golden["reads"] and len(reads) == 11
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
        assert got["exit_code"] == run["exit_code"] == 0 and got["stderr"] == ""
        if run["args"][0] == "list-statements":
            assert got["stdout"] == run["stdout"], run["args"]
        else:
            first = [b for b in listed(run["stdout"]) if "  takedown  " in b and "(closed)" not in b]
            assert listed(got["stdout"]) == first + [b for b in listed(run["stdout"]) if b not in first]


def test_what_nobody_decided_in_three_months_lapses_at_the_first_tidy(tmp_path, monkeypatch):
    """wts-core docs/adr/0008, the second question; AS-BUILT, replies: "The first write after the import can lapse
    old rows at once". A statement that has waited three months is declined with the reason its sender is told, and
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


# ---- going back --------------------------------------------------------------------------------------------------


def old_rows(path: Path) -> dict:
    """The old tables as the old code reads them, with a statement's log read as the list it is."""
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    try:
        out = {t: [dict(r) for r in con.execute(f"SELECT * FROM {t} ORDER BY rowid")] for t in OLD_TABLES}  # noqa: S608
    finally:
        con.close()
    for statement in out["statements"]:
        statement["log"] = json.loads(statement["log"])
    return out


def undo(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript((ROOT / "deploy" / "undo-wts-core.sql").read_text())
    con.close()


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
