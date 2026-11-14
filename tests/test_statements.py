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
from wts_core.replies import Item, Refused, months_before
from wts_core.testing import FixedClock

from councils import store
from councils.api.app import create_app
from councils.cli import app as cli
from councils.replies import MAX_WORDS, NOT_ENDORSED, Items, open_replies
from councils.state import open_archive, open_state

VOTE = f"{BARNSLEY}:1:10:0"
CHECKED = "Reply from the address on the council's website, 12 November."   # how the sender was confirmed
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
    """The site with Barnsley's named vote: its test client, the model's stand-in, reports and statements as the
    site keeps them (``wts_core.replies.Replies``, with this site's items, limits and words), and its settings."""
    c, fake, parts, cfg = client
    with_vote(cfg)
    return c, fake, parts.replies, cfg


def item_address(address: str) -> tuple[str, str | None]:
    """The item at an address and the council it belongs to, as the site reads what a sender pastes."""
    item = Items(lambda: None, None).resolve(address)
    return item.address, item.about


def sent(replies, page: str, council: str | None, name: str, role: str, text: str, link: str, email: str) -> int:
    """A statement as received, beside an item already known (as the form's route passes it)."""
    return replies.submit(name=name, role=role, item=Item(address=page, about=council), text=text, link=link,
                          email=email)


# ---- what the form accepts ---------------------------------------------------------------------------------------
def test_a_statement_is_received_as_waiting_and_not_shown(site):
    c, _, state, _ = site
    r = c.post("/api/statements", json=body())
    assert r.status_code == 200 and r.json()["ok"]
    st = state.statement(r.json()["id"])
    assert st["status"] == "pending" and st["item"] == f"/votes/{VOTE}" and st["about"] == BARNSLEY
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
    ({"link": "https://example.org/a\"onmouseover=\"alert(1)"}, "web address"),
    ({"link": "https://example.org/<script>"}, "web address"),
    ({"link": "https://example.org/it's"}, "web address"),
    ({"name": "    "}, "Give your name"),
    ({"name": " \n\tX "}, "Give your name"),
    ({"role": "\u00a0 \u00a0"}, "Give your role"),
])
def test_a_statement_that_breaks_the_rules_is_refused_with_words_for_the_reader(site, over, says):
    c, _, state, _ = site
    r = c.post("/api/statements", json=body(**over))
    assert r.status_code == 422 and says in r.json()["detail"]
    assert state.statements() == []


@pytest.mark.parametrize("missing", ["name", "role", "page", "text", "email"])
def test_every_required_field_is_required(site, missing):
    c, _, state, _ = site
    b = body()
    del b[missing]
    assert c.post("/api/statements", json=b).status_code == 422
    assert c.post("/api/statements", json=body(**{missing: " "})).status_code == 422
    assert state.statements() == []


def test_a_name_and_role_are_kept_on_one_line(site):
    """A name or role is never blank or only spaces (as Where Countries Stand); spaces around and within are tidied."""
    c, _, state, _ = site
    first = sent(state, f"/votes/{VOTE}", BARNSLEY, "  Cllr  Steve\nHoughton ", "Councillor", "Words.", "", "a@b.gov.uk")
    assert state.statement(first)["name"] == "Cllr Steve Houghton"
    for bad in ("", " ", "X", "  \t ", None):
        with pytest.raises(Refused, match="Give your name"):
            sent(state, f"/votes/{VOTE}", BARNSLEY, bad, "Councillor", "Words.", "", "a@b.gov.uk")
    with pytest.raises(Refused, match="can be up to 200 characters"):
        sent(state, f"/votes/{VOTE}", BARNSLEY, "A Name", "x" * 201, "Words.", "", "a@b.gov.uk")
    r = c.post("/api/statements", json=body(name="  Steve   Houghton ", role=" Leader of  the council "))
    st = state.statement(r.json()["id"])
    assert (st["name"], st["role"]) == ("Steve Houghton", "Leader of the council")


def test_a_statement_beside_a_withdrawn_briefing_is_refused(site):
    c, _, state, _ = site
    archive = c.app.state.councils.parts.archive
    archive.save("Bins?", {}, [{"type": "final", "answer": None}], id="abc123")
    assert c.post("/api/statements", json=body(page="/b/abc123")).status_code == 200
    assert archive.withdraw("abc123", "It misattributed a decision.")
    r = c.post("/api/statements", json=body(page="/b/abc123"))
    assert r.status_code == 422 and "no page at that address" in r.json()["detail"]
    assert len(state.statements()) == 1


def test_a_stored_link_is_checked_again_where_it_is_shown():
    """The form checks a link (as Where MPs Stand's does: no quotes, angle brackets or spaces). The pages check it
    again, so a row that reached the database another way can never be shown as a link that runs a script."""
    from wts_core.replies import safe_link

    from councils.api.plaintext import statements_text

    good = "https://barnsley.moderngov.co.uk/ieListDocuments.aspx?CId=137&MId=1"
    assert safe_link(good) == good
    for bad in ("javascript:alert(1)", "data:text/html,x", "https://example.org/a b", "//example.org", "", None,
                "https://example.org/\"x", "ftp://example.org/minutes"):
        assert safe_link(bad) is None, bad
    row = {"id": 1, "page": "/votes/x", "council": BARNSLEY, "name": "N", "role": "R", "text": "Words.",
           "shown_on": "2026-11-12", "link": good}
    assert "The record they point to" in statements_text([row], "/votes/x")
    shown = statements_text([{**row, "link": "javascript:alert(1)"}], "/votes/x")
    assert "javascript" not in shown and "The record they point to" not in shown and "Words." in shown


def test_exactly_150_words_and_no_link_are_accepted(site):
    c, _, _, _ = site
    r = c.post("/api/statements", json=body(text=" ".join(["word"] * MAX_WORDS), link=""))
    assert r.status_code == 200


def test_an_address_is_read_as_the_item_it_names():
    assert item_address(f"wherecouncilsstand.com/votes/{BARNSLEY.lower()}:1:10:0/") == (f"/votes/{VOTE}", BARNSLEY)
    assert item_address(f"https://www.wherecouncilsstand.com/councils/{BARNSLEY.lower()}?x=1#y") == \
        (f"/councils/{BARNSLEY}", BARNSLEY)
    assert item_address("/b/AbC_12") == ("/b/AbC_12", None)
    with pytest.raises(Refused):
        item_address("ftp://wherecouncilsstand.com/votes/x")


def test_the_report_form_takes_the_policys_routes_and_keeps_its_old_ones(site):
    c, _, state, _ = site
    for kind in ("error", "unfair", "takedown", "other"):
        assert c.post("/api/report", json={"kind": kind, "message": "Something to say"}).status_code == 200
    assert c.post("/api/report", json={"kind": "dispute", "message": "Something to say"}).status_code == 422
    # the newest first, but a request to take a person's name down before everything else
    assert [r["kind"] for r in state.reports()] == ["takedown", "other", "unfair", "error"]


# ---- the owner's commands ----------------------------------------------------------------------------------------
@pytest.fixture
def owners(tmp_path, monkeypatch, settings):  # noqa: F811
    """The owner's command line on the made-up record, and the site's reports, statements and saved briefings as
    the commands themselves open them."""
    monkeypatch.setenv("COUNCILS_DATA_DIR", str(settings.data_dir))
    with_vote(settings)
    from councils.api.data import Data

    db = open_state(settings)
    archive = open_archive(db)
    record = Data(settings)
    return open_replies(db, lambda: record, archive), archive


def test_the_owner_lists_publishes_updates_declines_and_withdraws_statements(owners):
    state, archive = owners
    first = sent(state, f"/votes/{VOTE}", BARNSLEY, "Steve Houghton", "Councillor", WORDS, "", "a@b.gov.uk")
    archive.save("Bins?", {}, [{"type": "final", "answer": None}], id="abc123")
    second = sent(state, "/b/abc123", None, "Barnsley Council", "Democratic services", "Our view.", "",
                  "dem@barnsley.gov.uk")
    run = CliRunner().invoke

    out = run(cli, ["statements", "list"]).output
    assert f"#{first}" in out and f"#{second}" in out and "pending" in out and "confirm with: a@b.gov.uk" in out
    assert "(on no council's page: --council)" in out and f"(on {BARNSLEY}'s page)" in out and "(25 words)" in out
    assert run(cli, ["list-statements"]).output == out          # the name the command had before still works

    # publishing needs a note of how the sender was confirmed: kept in the log, never shown
    r = run(cli, ["statements", "publish", str(first)])
    assert r.exit_code == 2 and "checked" in r.output and state.statement(first)["status"] == "pending"
    r = run(cli, ["statements", "publish", str(first), "--checked", "   "])
    assert r.exit_code == 1 and "say how you confirmed who sent it" in r.output
    # nor may the note hold the sender's address, which the privacy notice promises to delete
    r = run(cli, ["statements", "publish", str(first), "--checked", "Reply from A@b.gov.uk"])
    assert r.exit_code == 1 and "leave their email address out of it" in r.output
    assert state.statement(first)["status"] == "pending"
    assert run(cli, ["statements", "publish", str(first), "--checked", CHECKED]).output.strip() == "published"
    assert state.log(first)[-1] == {"at": state.log(first)[-1]["at"], "action": "published", "note": CHECKED,
                                    "previous": None}
    r = run(cli, ["statements", "publish", str(first), "--checked", CHECKED])
    assert r.exit_code == 1 and r.output.strip() == f"error: statement {first} is published, not pending"
    assert run(cli, ["statements", "publish", str(second), "--council", "barnsley", "--checked", CHECKED]) \
        .output.strip() == "published"
    shown = state.published(about=BARNSLEY)
    assert [s["id"] for s in shown] == [first, second] and "email" not in shown[0]
    assert all("log" not in s and CHECKED not in json.dumps(s) for s in shown)
    assert CHECKED not in run(cli, ["statements", "list", "--all"]).output
    said = run(cli, ["statements", "publish", "--help"]).output          # as --help prints it
    said = " ".join(said.replace("│", " ").split())
    assert "never shown on the site" in said and "Do not put the sender's email address in it" in said

    long = " ".join(["word"] * (MAX_WORDS + 1))
    r = run(cli, ["statements", "update", str(first), "--text", long])
    assert r.exit_code == 1 and "up to 150 words" in r.output
    assert run(cli, ["statements", "update", str(first), "--text", "New words.", "--role", "Leader"]) \
        .output.strip() == "updated"
    st = state.statement(first)
    assert st["text"] == "New words." and st["role"] == "Leader" and st["status"] == "published"
    for field in ("--name", "--role"):      # a name or role can't be changed to nothing
        r = run(cli, ["statements", "update", str(first), field, "   "])
        assert r.exit_code == 1 and f"Give a {field[2:]}" in r.output
    assert (state.statement(first)["name"], state.statement(first)["role"]) == ("Steve Houghton", "Leader")
    assert [e["action"] for e in state.log(first)] == ["received", "published", "updated"]
    # the words an update replaced are kept in the log, for the owner
    assert state.log(first)[-1]["previous"] == {"text": WORDS, "role": "Councillor"}

    assert run(cli, ["statements", "withdraw", str(first)]).output.strip() == "withdrawn"
    assert state.statement(first)["reason"] == "Withdrawn by its author."
    r = run(cli, ["statements", "withdraw", str(first)])
    assert r.exit_code == 1 and "is withdrawn, not pending or published" in r.output

    third = sent(state, f"/councils/{BARNSLEY}", BARNSLEY, "X Y", "Z W", "Vote for me.", "", "x@y.org")
    assert run(cli, ["statements", "decline", str(third), "--reason", "It appeals for votes."]).output.strip() == \
        "declined"
    r = run(cli, ["statements", "decline", str(third), "--reason", "again"])
    assert r.exit_code == 1 and r.output.strip() == f"error: statement {third} is declined, not pending"
    # a command that changed nothing exits 1; one that worked exits 0
    for failed in (["statements", "publish", str(first), "--checked", CHECKED], ["statements", "withdraw", str(first)],
                   ["statements", "decline", str(third), "--reason", "again"],
                   ["statements", "decline", "999", "--reason", "x"],
                   ["statements", "update", str(first), "--role", "Mayor"], ["statements", "update", str(second)],
                   ["reports", "close", "999"], ["withdraw", "nosuchid", "--reason", "x"],
                   ["close-report", "999"], ["decline-statement", "999", "--reason", "x"]):
        assert run(cli, failed).exit_code == 1, failed
    rid = state.report(kind="error", page="/votes/x", message="Something is wrong here.", contact="me@example.org")
    for worked, says in ((["reports", "close", str(rid)], "closed"),
                         (["statements", "update", str(second), "--role", "Clerk"], "updated"),
                         (["statements", "list"], f"#{second}"), (["reports", "list", "--all"], f"#{rid}")):
        r = run(cli, worked)
        assert r.exit_code == 0 and says in r.output, worked
    assert run(cli, ["reports", "close", str(rid)]).exit_code == 1      # already closed
    out = run(cli, ["statements", "list"]).output
    assert f"#{third}" not in out and f"#{first}" not in out and f"#{second}" in out
    out = run(cli, ["statements", "list", "--all"]).output
    assert "declined: It appeals for votes." in out and "withdrawn: Withdrawn by its author." in out
    assert [s["id"] for s in state.published(about=BARNSLEY)] == [second]
    # withdrawing the briefing it sits beside takes the statement off the council's page with it
    r = run(cli, ["withdraw", "abc123", "--reason", "Wrong."])
    assert r.exit_code == 0 and "withdrawn" in r.output


def test_a_statement_that_breaks_the_rules_is_removed_and_the_log_says_why(owners):
    """New with the shared package: `statements remove`, for a published statement the site takes down (the policy,
    7.2: "The charity can remove a statement that breaks these rules, and says why"). Withdrawing is for when its
    author asks. `statements show` and `statements log` read everything done to one."""
    state, _ = owners
    sid = sent(state, f"/votes/{VOTE}", BARNSLEY, "Steve Houghton", "Councillor", WORDS, "", "a@b.gov.uk")
    run = CliRunner().invoke
    r = run(cli, ["statements", "remove", str(sid), "--reason", "It names an officer."])
    assert r.exit_code == 1 and "is pending, not published" in r.output          # only what is shown
    run(cli, ["statements", "publish", str(sid), "--checked", CHECKED])
    assert run(cli, ["statements", "remove", str(sid)]).exit_code == 2           # the reason must be given
    r = run(cli, ["statements", "remove", str(sid), "--reason", "It names an officer."])
    assert (r.exit_code, r.output.strip()) == (0, "removed")
    st = state.statement(sid)
    assert (st["status"], st["reason"]) == ("removed", "It names an officer.") and state.published(about=BARNSLEY) == []
    out = run(cli, ["statements", "show", str(sid)]).output
    assert "removed: It names an officer." in out and f"published: {CHECKED}" in out
    assert run(cli, ["statements", "log", str(sid)]).output.splitlines()[-1].endswith("removed: It names an officer.")
    assert "0 reports and 0 statements waiting; 0 items hidden" in run(cli, ["waiting"]).output


def test_the_confirming_address_is_deleted_three_months_after_a_statement_ends(tmp_path, settings):  # noqa: F811
    clock = FixedClock("2026-01-10T09:00:00+00:00")
    db = open_state(settings, clock)
    state = open_replies(db, lambda: None, open_archive(db, clock), clock)
    archive = open_archive(db, clock)
    archive.save("Bins?", {}, [{"type": "final", "answer": None}], id="abc123")
    shown = sent(state, "/b/abc123", BARNSLEY, "A B", "B C", "Words.", "", "shown@x.gov.uk")
    gone = sent(state, "/b/abc123", BARNSLEY, "A B", "B C", "Words.", "", "gone@x.gov.uk")
    no = sent(state, "/b/abc123", BARNSLEY, "A B", "B C", "Words.", "", "no@x.gov.uk")
    state.publish(shown, checked=CHECKED)
    state.publish(gone, checked=CHECKED)
    state.withdraw(gone, "Withdrawn by its author.")
    state.decline(no, "It names a member of the public.")
    assert state.forget_old_emails() == 0                          # not yet
    clock.set("2026-04-10T10:00:00+00:00")
    assert state.forget_old_emails() == 2
    assert state.statement(gone)["email"] is None and state.statement(no)["email"] is None
    assert state.statement(shown)["email"] == "shown@x.gov.uk"         # kept while it is shown
    assert months_before(datetime(2026, 5, 31, tzinfo=UTC), 3) == datetime(2026, 2, 28, tzinfo=UTC)
    assert months_before(datetime(2026, 2, 10, tzinfo=UTC), 3) == datetime(2025, 11, 10, tzinfo=UTC)


def test_the_address_is_kept_for_just_under_three_months(tmp_path, settings):  # noqa: F811
    clock = FixedClock("2026-08-13T12:00:00+00:00")
    db = open_state(settings, clock)
    archive = open_archive(db, clock)
    archive.save("Bins?", {}, [{"type": "final", "answer": None}], id="abc123")
    state = open_replies(db, lambda: None, archive, clock)
    sid = sent(state, "/b/abc123", BARNSLEY, "A B", "B C", "Words.", "", "a@x.gov.uk")
    state.decline(sid, "Off topic.")
    clock.set("2026-11-13T11:00:00+00:00")
    assert state.forget_old_emails() == 0
    clock.set("2026-11-13T13:00:00+00:00")
    assert state.forget_old_emails() == 1
    assert state.statement(sid)["email"] is None


# ---- how a statement is shown ------------------------------------------------------------------------------------
def test_a_published_statement_is_shown_beside_its_item_and_on_its_councils_page(site):
    c, _, state, _ = site
    sid = c.post("/api/statements", json=body()).json()["id"]
    state.publish(sid, checked=CHECKED)
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
    t = TestClient(create_app(cfg, state=state.db))
    sid = sent(state, f"/votes/{VOTE}", BARNSLEY, "Steve <Houghton>", "Councillor", "First para.\n\nSecond.",
               "https://example.org/r", "a@b.gov.uk")
    state.publish(sid, checked=CHECKED)
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
    state.withdraw(sid, "Withdrawn by its author.")
    assert "Statement from" not in t.get(f"/votes/{VOTE}").text


# ---- never part of the record ------------------------------------------------------------------------------------
def test_a_statement_never_reaches_the_ai_model_or_the_search(site):
    c, fake, state, _ = site
    for page in (f"/votes/{VOTE}", f"/councils/{BARNSLEY}"):
        state.publish(sent(state, page, BARNSLEY, "Steve Houghton", "Councillor",
                           f"bin collections weekly {WORDS}", "", "a@b.gov.uk"), checked=CHECKED)
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
