"""The two things the site gains with the shared package (docs/DECISIONS.md, 24; the impartiality policy, section
7): the public corrections log, and hiding an item, with a note in its place, while a concern about it is decided.

On the made-up record of test_pipeline, with Barnsley's named vote from test_statements and a stand-in for the
model. The owner's commands are run as the owner runs them, on the same data folder as the site."""

import re
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from test_api import events, site_with
from test_pipeline import BARNSLEY, GUILDFORD, settings  # noqa: F401 - the fixture
from test_statements import CHECKED, MARKER, VOTE, body, with_vote
from typer.testing import CliRunner

from councils import cli
from councils.replies import HIDDEN_LEAD

sys.path.insert(0, str(Path(__file__).parent / "golden"))
import shared  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
BINS = "What have councils decided about bin collections?"
NOTE = "We are checking a report that the sides of this vote were read the wrong way round."
VOTE_PAGE, COUNCIL_PAGE = f"/votes/{VOTE}", f"/councils/{BARNSLEY}"


@pytest.fixture
def site(settings, tmp_path, monkeypatch):  # noqa: F811
    """The site with its pages (cut down to what the server fills in, and the real corrections page), Barnsley's
    named vote, and the owner's commands on the same data folder: the test client, the model's stand-in, the
    site's parts, and a function that runs a command and gives its result."""
    pages = shared.web_pages(tmp_path / "dist")
    (pages / "corrections.html").write_text((ROOT / "web" / "corrections.html").read_text())
    cfg = replace(settings, raw={**settings.raw, "paths": {**settings.raw["paths"], "web_dist": str(pages)}})
    with_vote(cfg)
    monkeypatch.setenv("COUNCILS_DATA_DIR", str(cfg.data_dir))
    c, fake, parts, cfg = site_with(cfg)

    def run(*words: str):
        return CliRunner().invoke(cli.app, list(words))

    return c, fake, parts, run


def ask(c, question: str = BINS) -> dict:
    return events(c.post("/api/ask", json={"question": question}))[-1]


def given_to_the_model(fake) -> str:
    """Everything in the last request to the model: its sources' titles and texts."""
    return repr(fake.calls[-1]["messages"])


# ---- the corrections log -------------------------------------------------------------------------------------------


def test_the_corrections_log_starts_empty_and_says_so(site):
    c, _, _, _ = site
    assert c.get("/api/corrections").json() == {"corrections": []}
    page = c.get("/corrections")
    assert page.status_code == 200 and "<h2 id=\"log\">Corrections log</h2>" in page.text
    assert "Nothing has been corrected or withdrawn so far." in page.text
    assert "can't be shown just now" not in page.text       # the line the page keeps for when the log can't be read
    assert 'name="kind"' not in page.text and '<div id="report"></div>' in page.text    # the form is still the app's


def test_the_log_lists_withdrawn_briefings_and_public_notes_and_nothing_a_reader_sent(site):
    c, _, parts, run = site
    secret = "Mr Example of 5 Acacia Avenue"
    bid = ask(c, f"What did Barnsley decide about bin collections, and about {secret}?")["briefing_id"]
    for page_given in (f"https://wherecouncilsstand.com{VOTE_PAGE}", f"the page that names {secret}", ""):
        r = c.post("/api/report", json={"kind": "error", "page": page_given, "contact": "reporter@example.org",
                                        "message": f"Councillor Houghton voted for, not against. Ask {secret}."})
        assert r.status_code == 200
    first, second, third = (r["id"] for r in sorted(parts.replies.reports(), key=lambda r: r["id"]))
    assert run("reports", "close", str(first), "--note", "Private: checked against the minutes.", "--public-note",
               "Councillor Houghton's vote was shown on the wrong side. It is now shown as against.").exit_code == 0
    assert run("reports", "close", str(second), "--public-note", "A name was removed from a briefing.").exit_code == 0
    assert run("reports", "close", str(third), "--note", "Nothing to change.").exit_code == 0      # no public note
    assert run("withdraw", bid, "--reason", "It named someone who is not a councillor.").exit_code == 0
    # a statement the site removed is not in the log: why is said to its author
    sid = c.post("/api/statements", json=body()).json()["id"]
    assert run("statements", "publish", str(sid), "--checked", CHECKED).exit_code == 0
    assert run("statements", "remove", str(sid), "--reason", "It was about another person's conduct.").exit_code == 0

    log = c.get("/api/corrections").json()["corrections"]
    today = parts.clock.now().date().isoformat()
    assert sorted(log, key=lambda e: e["note"]) == [
        {"date": today, "heading": "Correction", "note": "A name was removed from a briefing.", "page": None},
        {"date": today, "heading": "Correction", "page": VOTE_PAGE,
         "note": "Councillor Houghton's vote was shown on the wrong side. It is now shown as against."},
        {"date": today, "heading": "Briefing withdrawn", "note": "It named someone who is not a councillor.",
         "page": None},
    ]
    page = c.get("/corrections").text
    listed = page[page.index('<ol class="corrections-log">'):]
    assert listed[:listed.index("</ol>")].count("<li>") == 3
    assert f'<a href="{VOTE_PAGE}">The page this is about</a>' in page
    assert "<strong>Briefing withdrawn</strong>" in page and "<strong>Correction</strong>" in page
    # never the withdrawn briefing's question, what a reporter wrote or pasted, their address, the owner's
    # private note, or anything of a statement
    for kept_back in (secret, "Acacia", "reporter@example.org", "Private:", "Nothing to change", "voted for, not",
                      MARKER, "another person's conduct"):
        assert kept_back not in page and kept_back not in repr(log), kept_back


# ---- hiding an item while a concern is decided ---------------------------------------------------------------------


def test_only_a_page_of_the_three_kinds_can_be_hidden_and_it_is_filed_under_its_own_address(site):
    c, _, parts, run = site
    for not_an_item in ("/about", "https://example.org/votes/x", "bins"):
        r = run("hide", not_an_item, "--note", NOTE)
        assert r.exit_code == 1 and "only a council's page, a named vote or a briefing can be hidden" in r.output
    r = run("hide", f"/votes/{BARNSLEY}:9:9:9", "--note", NOTE)
    assert r.exit_code == 1 and "there is no page at" in r.output
    assert run("hide", VOTE_PAGE).exit_code != 0                                       # a note is required
    assert parts.replies.all_hidden() == []
    # pasted as a reader would copy it, in another case, with a slash on the end
    r = run("hide", f"https://wherecouncilsstand.com/votes/{VOTE.lower()}/", "--note", NOTE)
    assert r.exit_code == 0, r.output
    assert [(h["item"], h["note"]) for h in parts.replies.all_hidden()] == [(VOTE_PAGE, NOTE)]
    assert VOTE_PAGE in run("hidden").output and "1" in run("waiting").output
    assert run("hide", VOTE_PAGE, "--note", "Again.").exit_code == 1                   # already hidden
    assert run("unhide", f"wherecouncilsstand.com{VOTE_PAGE}").exit_code == 0
    assert parts.replies.all_hidden() == [] and run("unhide", VOTE_PAGE).exit_code == 1


def test_a_hidden_named_vote_shows_the_note_and_is_left_out_of_lists_and_sources(site):
    c, fake, parts, run = site
    sid = c.post("/api/statements", json=body()).json()["id"]
    assert run("statements", "publish", str(sid), "--checked", CHECKED).exit_code == 0
    before = {path: c.get(path) for path in (VOTE_PAGE, f"/api{VOTE_PAGE}", f"/api{COUNCIL_PAGE}", "/sitemap.xml")}
    assert "Houghton" in before[VOTE_PAGE].text and MARKER in before[VOTE_PAGE].text
    first = ask(c)
    assert "Named vote recorded in these minutes" in given_to_the_model(fake) and len(fake.calls) == 1
    assert ask(c)["cached"] and len(fake.calls) == 1

    assert run("hide", VOTE_PAGE, "--note", NOTE).exit_code == 0
    # its page: the note in its place, nothing of the record or of the statement beside it, and not for indexing
    page = c.get(VOTE_PAGE)
    assert page.status_code == 403 and f"{HIDDEN_LEAD} {NOTE}" in page.text and "<h1>Named vote</h1>" in page.text
    assert 'content="noindex' in page.text
    for of_the_record in ("Houghton", "Kitching", "Notice of Motion", MARKER, "application/ld+json"):
        assert of_the_record not in page.text, of_the_record
    api = c.get(f"/api{VOTE_PAGE}")
    assert api.status_code == 403 and api.json() == {"detail": f"{HIDDEN_LEAD} {NOTE}"}
    # lists: its council's votes (the page for readers without scripts too), the sitemap, statements
    assert c.get(f"/api{COUNCIL_PAGE}").json()["votes"] == [] and before[f"/api{COUNCIL_PAGE}"].json()["votes"]
    assert VOTE not in c.get(COUNCIL_PAGE).text and VOTE in before["/sitemap.xml"].text
    assert VOTE not in c.get("/sitemap.xml").text and COUNCIL_PAGE in c.get("/sitemap.xml").text
    assert c.get("/api/statements", params={"page": VOTE_PAGE}).json()["statements"] == []
    assert c.get("/api/statements", params={"council": BARNSLEY}).json()["statements"] == []
    # search and the sources of a briefing: the item's minutes are still found, without the site's reading of
    # who voted which way; and the answer written before it was hidden is not replayed
    found = c.post("/api/search", json={"question": BINS}).json()["sources"]
    assert {s["gss"] for s in found} == {BARNSLEY, GUILDFORD} and all(s["votes"] == [] for s in found)
    again = ask(c)
    assert len(fake.calls) == 2 and not again.get("cached") and again["briefing_id"] != first["briefing_id"]
    assert "Named vote recorded in these minutes" not in given_to_the_model(fake)
    assert "weekly bin collections be restored" in given_to_the_model(fake)

    # shown again: everything as it was, and the answer from before is replayed once more
    assert run("unhide", VOTE_PAGE).exit_code == 0
    for path, was in before.items():
        now = c.get(path)
        assert (now.status_code, now.text) == (was.status_code, was.text), path
    assert ask(c)["briefing_id"] == first["briefing_id"] and len(fake.calls) == 2


def test_a_hidden_councils_page_shows_the_note_and_its_minutes_are_left_out_of_search(site):
    c, fake, parts, run = site
    note = "We are checking a report that the party in control is shown wrongly."
    listed = len(c.get("/api/councils").json()["councils"])
    assert run("hide", COUNCIL_PAGE.lower(), "--note", note).exit_code == 0
    assert parts.replies.all_hidden()[0]["item"] == COUNCIL_PAGE
    page = c.get(COUNCIL_PAGE)
    assert page.status_code == 403 and f"{HIDDEN_LEAD} {note}" in page.text and "<h1>Council</h1>" in page.text
    assert "Barnsley" not in page.text and 'content="noindex' in page.text
    assert c.get(f"/api{COUNCIL_PAGE}").json() == {"detail": f"{HIDDEN_LEAD} {note}"}
    # each of its named votes' pages shows the council's note
    assert c.get(VOTE_PAGE).status_code == 403 and note in c.get(VOTE_PAGE).text
    assert c.get(f"/api{VOTE_PAGE}").json() == {"detail": f"{HIDDEN_LEAD} {note}"}
    # lists: the list of councils (for readers without scripts too) and the sitemap, with its votes
    rows = c.get("/api/councils").json()["councils"]
    assert len(rows) == listed - 1 and BARNSLEY not in {r["gss"] for r in rows}
    assert COUNCIL_PAGE not in c.get("/councils").text and f"/councils/{GUILDFORD}" in c.get("/councils").text
    sitemap = c.get("/sitemap.xml").text
    assert BARNSLEY not in sitemap and GUILDFORD in sitemap
    # search, and so the sources of a briefing written meanwhile: none of its minutes
    found = c.post("/api/search", json={"question": BINS}).json()["sources"]
    assert {s["gss"] for s in found} == {GUILDFORD}
    final = ask(c)
    assert final["answer"] and "Barnsley" not in given_to_the_model(fake) and "Guildford" in given_to_the_model(fake)
    only = c.post("/api/search", json={"question": BINS, "plan": {"filters": {"councils": [BARNSLEY]}}}).json()
    assert only["sources"] == []
    # shown again
    assert run("unhide", COUNCIL_PAGE).exit_code == 0
    assert c.get(COUNCIL_PAGE).status_code == 200 and c.get(VOTE_PAGE).status_code == 200
    assert {s["gss"] for s in c.post("/api/search", json={"question": BINS}).json()["sources"]} == {BARNSLEY,
                                                                                                 GUILDFORD}


def test_a_hidden_briefing_shows_the_note_and_is_not_replayed(site):
    c, fake, parts, run = site
    bid = ask(c)["briefing_id"]
    note = "We are checking a report that this briefing misstates a decision."
    r = run("hide", f"https://wherecouncilsstand.com/b/{bid}", "--note", note)
    assert r.exit_code == 0, r.output
    api = c.get(f"/api/briefings/{bid}")
    assert api.status_code == 403 and api.json() == {"detail": f"{HIDDEN_LEAD} {note}"}
    again = ask(c)
    assert again["briefing_id"] != bid and len(fake.calls) == 2         # written afresh, not replayed
    assert run("unhide", f"/b/{bid}").exit_code == 0
    shown = c.get(f"/api/briefings/{bid}")
    assert shown.status_code == 200 and shown.json()["question"] == BINS
    # a withdrawn briefing has no page to hide
    assert run("withdraw", bid, "--reason", "Wrong.").exit_code == 0
    assert run("hide", f"/b/{bid}", "--note", note).exit_code == 1


def test_what_is_hidden_reaches_the_search_as_codes_and_never_as_anything_of_the_right_of_reply(site):
    """The engine and the pipeline are told which councils and votes to leave out, as plain codes: they still
    read nothing of the site's own database (tests/test_statements.py checks their imports)."""
    c, fake, parts, run = site
    assert run("hide", VOTE_PAGE, "--note", NOTE).exit_code == 0
    ask(c)
    assert NOTE not in given_to_the_model(fake) and not re.search(r"hidden", given_to_the_model(fake), re.I)
