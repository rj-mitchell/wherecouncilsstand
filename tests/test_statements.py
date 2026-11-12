"""Statements under the right of reply (decision 22; the impartiality policy, section 7.2): what the form accepts,
the owner's commands, how a published statement is shown, that its confirming address is deleted in time, and that a
statement never reaches the AI model or the search index."""

import ast
import json
import re
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_api import client, events  # noqa: F401 - the fixture
from test_pipeline import BARNSLEY, settings  # noqa: F401 - the fixture
from typer.testing import CliRunner

from councils import store
from councils.api.app import create_app
from councils.api.state import StateDB, months_before
from councils.api.statements import MAX_WORDS, NOT_ENDORSED, item_address
from councils.cli import app as cli

VOTE = f"{BARNSLEY}:1:10:0"
MARKER = "Zanzibarquokka"   # a word found nowhere in the record, to follow a statement's text
WORDS = ("I voted against this motion because the council had already agreed a review of collections, and the "
         f"minutes of that meeting set it out. {MARKER}.")


def with_vote(cfg) -> None:
    store.parquet.write(cfg.parquet_dir, "votes", BARNSLEY, [
        {"vote_id": VOTE, "item_id": f"{BARNSLEY}:1:10", "meeting_id": f"{BARNSLEY}:1", "gss": BARNSLEY,
         "date": date(2025, 2, 26), "year": 2025, "question": "motion", "outcome": "lost", "member_id": m,
         "name": n, "vote": side, "excerpt": "Upon being put to the vote the motion was lost."}
        for m, n, side in (("1", "Kitching", "for"), ("2", "Houghton", "against"), ("3", "Franklin", "against"))])


def body(**over) -> dict:
    return {"page": f"https://wherecouncilsstand.com/votes/{VOTE}", "name": "Steve Houghton",
            "role": "Councillor, Barnsley Metropolitan Borough Council", "text": WORDS,
            "link": "https://barnsley.moderngov.co.uk/ieListDocuments.aspx?MId=1", "email": "cllr@barnsley.gov.uk",
            "acting": True, **over}


@pytest.fixture
def site(client):  # noqa: F811
    c, fake, state, cfg = client
    with_vote(cfg)
    return c, fake, state, cfg


# ---- what the form accepts ---------------------------------------------------------------------------------------
def test_a_statement_is_received_as_waiting_and_not_shown(site):
    c, _, state, _ = site
    r = c.post("/api/statements", json=body())
    assert r.status_code == 200 and r.json()["ok"]
    st = state.statement(r.json()["id"])
    assert st["status"] == "pending" and st["page"] == f"/votes/{VOTE}" and st["council"] == BARNSLEY
    assert st["email"] == "cllr@barnsley.gov.uk" and st["text"] == WORDS
    assert c.get("/api/statements", params={"page": f"/votes/{VOTE}"}).json()["statements"] == []


@pytest.mark.parametrize("over, says", [
    ({"text": " ".join(["word"] * (MAX_WORDS + 1))}, "up to 150 words; this one is 151"),
    ({"text": "   "}, "Write the statement"),
    ({"text": "x" * 1550}, "up to 150 words"),
    ({"email": "not an address"}, "email address"),
    ({"email": ""}, "email address"),
    ({"acting": False}, "act for them"),
    ({"page": "https://example.org/votes/x"}, "a page on wherecouncilsstand.com"),
    ({"page": "/about"}, "a council's page, a named vote or a briefing"),
    ({"page": ""}, "Give the address"),
    ({"page": f"/votes/{BARNSLEY}:9:9:9"}, "no page at that address"),
    ({"page": "/b/nosuchbriefing"}, "no page at that address"),
    ({"link": "javascript:alert(1)"}, "web address"),
])
def test_a_statement_that_breaks_the_rules_is_refused_with_words_for_the_reader(site, over, says):
    c, _, state, _ = site
    r = c.post("/api/statements", json=body(**over))
    assert r.status_code == 422 and says in r.json()["detail"]
    assert state.statements(open_only=False) == []


@pytest.mark.parametrize("missing", ["name", "role", "page", "text", "email"])
def test_every_required_field_is_required(site, missing):
    c, _, state, _ = site
    b = body()
    del b[missing]
    assert c.post("/api/statements", json=b).status_code == 422
    assert c.post("/api/statements", json=body(**{missing: " "})).status_code == 422
    assert state.statements(open_only=False) == []


def test_exactly_150_words_and_no_link_are_accepted(site):
    c, _, _, _ = site
    r = c.post("/api/statements", json=body(text=" ".join(["word"] * MAX_WORDS), link=""))
    assert r.status_code == 200


def test_an_address_is_read_as_the_item_it_names():
    assert item_address(f"wherecouncilsstand.com/votes/{BARNSLEY.lower()}:1:10:0/") == (f"/votes/{VOTE}", BARNSLEY)
    assert item_address(f"https://www.wherecouncilsstand.com/councils/{BARNSLEY.lower()}?x=1#y") == \
        (f"/councils/{BARNSLEY}", BARNSLEY)
    assert item_address("/b/AbC_12") == ("/b/AbC_12", None)
    with pytest.raises(ValueError):
        item_address("ftp://wherecouncilsstand.com/votes/x")


def test_the_report_form_takes_the_policys_routes_and_keeps_its_old_ones(site):
    c, _, state, _ = site
    for kind in ("error", "unfair", "takedown", "other"):
        assert c.post("/api/report", json={"kind": kind, "message": "Something to say"}).status_code == 200
    assert c.post("/api/report", json={"kind": "dispute", "message": "Something to say"}).status_code == 422
    assert [r["kind"] for r in state.reports()] == ["other", "takedown", "unfair", "error"]


# ---- the owner's commands ----------------------------------------------------------------------------------------
def test_the_owner_lists_publishes_updates_declines_and_withdraws_statements(tmp_path, monkeypatch):
    monkeypatch.setenv("COUNCILS_DATA_DIR", str(tmp_path))
    state = StateDB(tmp_path / "state.db")
    first = state.add_statement(f"/votes/{VOTE}", BARNSLEY, "Steve Houghton", "Councillor", WORDS, "", "a@b.gov.uk")
    second = state.add_statement("/b/abc123", None, "Barnsley Council", "Democratic services", "Our view.", "",
                                 "dem@barnsley.gov.uk")
    run = CliRunner().invoke

    out = run(cli, ["list-statements"]).output
    assert f"#{first}" in out and f"#{second}" in out and "pending" in out and "confirm with: a@b.gov.uk" in out
    assert "(on no council's page: --council)" in out and f"(on {BARNSLEY}'s page)" in out and "(25 words)" in out

    assert run(cli, ["publish-statement", str(first)]).output.strip() == "published"
    assert run(cli, ["publish-statement", str(first)]).output.strip() == "no waiting statement with that number"
    assert run(cli, ["publish-statement", str(second), "--council", "barnsley"]).output.strip() == "published"
    shown = state.published_statements(council=BARNSLEY)
    assert [s["id"] for s in shown] == [first, second] and "email" not in shown[0]

    long = " ".join(["word"] * (MAX_WORDS + 1))
    r = run(cli, ["update-statement", str(first), "--text", long])
    assert r.exit_code == 1 and "up to 150 words" in r.output
    assert run(cli, ["update-statement", str(first), "--text", "New words.", "--role", "Leader"]).output.strip() == \
        "updated"
    st = state.statement(first)
    assert st["text"] == "New words." and st["role"] == "Leader" and st["status"] == "published"
    assert [e["action"] for e in st["log"]] == ["received", "published", "updated"]

    assert run(cli, ["withdraw-statement", str(first)]).output.strip() == "withdrawn"
    assert state.statement(first)["reason"] == "Withdrawn by its author."
    assert run(cli, ["withdraw-statement", str(first)]).output.strip() == \
        "no waiting or published statement with that number"

    third = state.add_statement(f"/councils/{BARNSLEY}", BARNSLEY, "X", "Y", "Vote for me.", "", "x@y.org")
    assert run(cli, ["decline-statement", str(third), "--reason", "It appeals for votes."]).output.strip() == \
        "declined"
    assert run(cli, ["decline-statement", str(third), "--reason", "again"]).output.strip() == \
        "no waiting statement with that number"
    out = run(cli, ["list-statements"]).output
    assert f"#{third}" not in out and f"#{first}" not in out and f"#{second}" in out
    out = run(cli, ["list-statements", "--all"]).output
    assert "declined: It appeals for votes." in out and "withdrawn: Withdrawn by its author." in out
    assert [s["id"] for s in state.published_statements(council=BARNSLEY)] == [second]


def test_the_confirming_address_is_deleted_three_months_after_a_statement_ends(tmp_path):
    state = StateDB(tmp_path / "state.db")
    shown = state.add_statement(f"/councils/{BARNSLEY}", BARNSLEY, "A", "B", "Words.", "", "shown@x.gov.uk")
    gone = state.add_statement(f"/councils/{BARNSLEY}", BARNSLEY, "A", "B", "Words.", "", "gone@x.gov.uk")
    no = state.add_statement(f"/councils/{BARNSLEY}", BARNSLEY, "A", "B", "Words.", "", "no@x.gov.uk")
    state.publish_statement(shown)
    state.publish_statement(gone)
    state.withdraw_statement(gone, "Withdrawn by its author.")
    state.decline_statement(no, "It names a member of the public.")
    assert state.forget_statement_emails() == 0                          # not yet
    with state.connect() as con:
        con.execute("UPDATE statements SET ended_at = '2026-01-10T09:00:00+00:00' WHERE ended_at IS NOT NULL")
    assert state.forget_statement_emails(datetime(2026, 4, 10, 10, 0, tzinfo=UTC)) == 2
    assert state.statement(gone)["email"] == "" and state.statement(no)["email"] == ""
    assert state.statement(shown)["email"] == "shown@x.gov.uk"         # kept while it is shown
    assert months_before(datetime(2026, 5, 31, tzinfo=UTC), 3) == datetime(2026, 2, 28, tzinfo=UTC)
    assert months_before(datetime(2026, 2, 10, tzinfo=UTC), 3) == datetime(2025, 11, 10, tzinfo=UTC)


def test_the_address_is_kept_for_just_under_three_months(tmp_path):
    state = StateDB(tmp_path / "state.db")
    sid = state.add_statement(f"/councils/{BARNSLEY}", BARNSLEY, "A", "B", "Words.", "", "a@x.gov.uk")
    state.decline_statement(sid, "Off topic.")
    with state.connect() as con:
        con.execute("UPDATE statements SET ended_at = '2026-08-13T12:00:00+00:00' WHERE id = ?", (sid,))
    assert state.forget_statement_emails(datetime(2026, 11, 13, 11, 0, tzinfo=UTC)) == 0
    assert state.forget_statement_emails(datetime(2026, 11, 13, 13, 0, tzinfo=UTC)) == 1
    assert state.statement(sid)["email"] == ""


# ---- how a statement is shown ------------------------------------------------------------------------------------
def test_a_published_statement_is_shown_beside_its_item_and_on_its_councils_page(site):
    c, _, state, _ = site
    sid = c.post("/api/statements", json=body()).json()["id"]
    state.publish_statement(sid)
    beside = c.get("/api/statements", params={"page": f"https://wherecouncilsstand.com/votes/{VOTE}"}).json()
    assert beside["note"] == NOT_ENDORSED == "In their own words. Not checked or endorsed by Where Councils Stand."
    [st] = beside["statements"]
    assert st["name"] == "Steve Houghton" and st["text"] == WORDS and st["shown_on"] == date.today().isoformat()
    assert set(st) == {"id", "page", "council", "name", "role", "text", "link", "shown_on"}    # never the address
    [on_page] = c.get("/api/statements", params={"council": BARNSLEY.lower()}).json()["statements"]
    assert on_page["about"].startswith("Notice of Motion - Weekly Bin Collections, 26 February 2025")
    assert c.get("/api/statements").status_code == 422
    assert "cllr@barnsley.gov.uk" not in json.dumps(beside) + json.dumps(on_page)


def test_the_pages_sent_to_readers_without_scripts_carry_the_statement_after_the_record(site, tmp_path):
    c, _, state, cfg = site
    dist = tmp_path / "dist"
    dist.mkdir()
    shell = ('<!doctype html><html><head><title>x</title></head><body><main id="main"><div id="app"></div>'
             "</main></body></html>")
    for name in ("council", "vote"):
        (dist / f"{name}.html").write_text(shell)
    cfg.raw.setdefault("paths", {})["web_dist"] = str(dist)
    t = TestClient(create_app(cfg, state=state))
    sid = state.add_statement(f"/votes/{VOTE}", BARNSLEY, "Steve <Houghton>", "Councillor", "First para.\n\nSecond.",
                              "https://example.org/r", "a@b.gov.uk")
    state.publish_statement(sid)
    vote = t.get(f"/votes/{VOTE}").text
    today = date.today()
    heading = f"<h2>Statement from Steve &lt;Houghton&gt;, {today.day} {today.strftime('%B %Y')}</h2>"
    assert heading in vote and "<p>First para.</p><p>Second.</p>" in vote
    assert "<em>In their own words. Not checked or endorsed by Where Councils Stand.</em>" in vote
    assert vote.index("From the minutes") < vote.index("Statement from")
    meta = re.search(r'<meta name="description" content="([^"]*)"', vote).group(1)
    ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', vote, re.S).group(1)
    assert "First para" not in meta and "First para" not in ld and "Houghton&gt;" not in ld
    council = t.get(f"/councils/{BARNSLEY}").text
    assert "<h2>Statements in their own words</h2>" in council and heading.replace("h2", "h3") in council
    assert f'About: <a href="/votes/{VOTE}">Notice of Motion - Weekly Bin Collections' in council
    state.withdraw_statement(sid, "Withdrawn by its author.")
    assert "Statement from" not in t.get(f"/votes/{VOTE}").text


# ---- never part of the record ------------------------------------------------------------------------------------
def test_a_statement_never_reaches_the_ai_model_or_the_search(site):
    c, fake, state, _ = site
    for page in (f"/votes/{VOTE}", f"/councils/{BARNSLEY}"):
        state.publish_statement(state.add_statement(page, BARNSLEY, "Steve Houghton", "Councillor",
                                                    f"bin collections weekly {WORDS}", "", "a@b.gov.uk"))
    evs = events(c.post("/api/ask", json={"question": "What has Barnsley decided about weekly bin collections?"}))
    assert fake.calls and evs[-1]["type"] == "final"
    assert MARKER not in json.dumps(fake.calls, default=str) and MARKER not in json.dumps(evs)
    found = c.post("/api/search", json={"question": "weekly bin collections in Barnsley"}).json()
    assert found["sources"] and MARKER not in json.dumps(found)


ROOT = Path(__file__).resolve().parents[1] / "src" / "councils"


def test_nothing_that_builds_the_record_or_briefings_reads_the_sites_own_database():
    """The search index, the engine and the briefing pipeline never import the state database or the statements
    module, so a statement can't become part of the record, the index or what the model is given."""
    record = [*ROOT.glob("rag/*.py"), *ROOT.glob("index/*.py"), *ROOT.glob("embed/*.py"), *ROOT.glob("rank/*.py"),
              ROOT / "engine.py", ROOT / "extract.py", ROOT / "load.py", ROOT / "ingest.py"]
    assert len(record) > 10
    for path in record:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import | ast.ImportFrom) for a in n.names} | \
                {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        assert not any("state" in x or "statements" in x for x in names), path
