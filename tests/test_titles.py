"""What a named vote is called (api/titles.py): a label for each vote on an agenda item, read from the words before
it, and the titles, headings and descriptions made from it; and the pages that use them.

Many items hold more than one named vote, and all of them had the item's title as their page's title and heading,
so search engines took them for copies of one page (the audit of November 2026). The passages below follow the
layouts of real councils' minutes (Rushmoor, East Sussex, South Cambridgeshire, Stoke-on-Trent, Trafford, Edinburgh,
Torbay, Essex); the names are made up."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from test_pages import SHELL, ld
from test_pipeline import BARNSLEY, item, meeting, member, settings  # noqa: F401 - the fixture

from councils import store
from councils.api import titles
from councils.api.app import create_app
from councils.state import open_state


def label(excerpt: str, question: str = "") -> str | None:
    return titles.derive_label(titles.before_vote(excerpt), question, titles.headings(excerpt))


@pytest.mark.parametrize(("excerpt", "question", "expected"), [
    # East Sussex: whose amendment, said plainly
    ("57.4 A recorded vote on Councillor Webb's amendment was taken. The amendment was LOST, the votes being cast as "
     "follows: FOR THE AMENDMENT Councillors Adams, Brown and Cole. AGAINST THE AMENDMENT Councillors Dean and Ellis.",
     "amendment", "Amendment by Cllr Webb"),
    # South Cambridgeshire: the motion and its mover
    ("A vote was taken (2 voting in favour, 3 voting against) on the motion moved by Councillor Ann Smith, which was "
     "defeated. Councillors In Favour: Adams, Brown Against: Cole, Dean, Ellis",
     "", "Motion by Cllr Ann Smith"),
    # Stoke-on-Trent: the substantive motion
    ("At the conclusion of the debate, the outcome of the vote on the substantive motion was as follows: For the "
     "motion (3): Councillors Adams, Brown and Cole. Against the motion (2): Councillors Dean and Ellis.",
     "motion", "Substantive motion"),
    # Trafford: a second amendment
    ("The second amendment was then put to the vote. For: Councillors Adams, Brown and Cole. Against: Councillors "
     "Dean and Ellis.", "amendment", "Second amendment"),
    # Torbay: "further amendments" is not what the vote was on, and nothing else says
    ("authorised to make any further amendments deemed necessary to the proposal. The voting was taken by roll call "
     "as follows: For: Councillors Adams, Brown and Cole; Against: Councillors Dean and Ellis",
     "", None),
    # a heading's own word stands when the words before it say nothing plain
    ("The voting was as follows: For the recommendation: Councillors Adams, Brown and Cole. Against the "
     "recommendation: Councillors Dean and Ellis.", "recommendation", "Recommendation"),
    # Edinburgh: a division between the motion and a numbered amendment
    ("Voting The voting was as follows: For the Motion: Councillors Adams, Brown and Cole. For Amendment 2 (as "
     "adjusted): Councillors Dean and Ellis.", "motion or amendment", "Motion or amendment 2"),
    # Essex: an amendment that became the substantive motion is still the amendment, by its mover
    ("The amendment moved by Councillor Whyte and seconded by Councillor Bell was put to the meeting and was carried "
     "and became the substantive motion. Those Members voting for the amendment to the motion were Councillors: "
     "Adams, Brown, Cole", "amendment", "Amendment by Cllr Whyte"),
    # "the motion" read where the heading says the amendment: the heading wins
    ("Prior to voting on the amendment, five members requested that the vote on the motion be recorded. The voting "
     "was as follows: For the amendment: Councillors Adams, Brown and Cole. Against the amendment: Councillors Dean "
     "and Ellis.", "amendment", "Amendment"),
])
def test_a_label_is_read_only_where_the_words_say_plainly_what_the_vote_was_on(excerpt, question, expected):
    assert label(excerpt, question) == expected


def test_not_a_regulation_nor_work_carried_out():
    """"(Amendment) Regulations 2014" names no amendment, and "costings had been carried out" is no vote's result."""
    assert label("A recorded vote took place under The Local Authorities (Standing Orders) (England) (Amendment) "
                 "Regulations 2014. Voting was recorded as follows: For the Proposal (2): Councillors Adams, Brown, "
                 "Against the Proposal (3): Councillors Cole, Dean, Ellis", "proposal") == "Proposal"
    assert titles._OUTCOME_WORDS.search("whether full costings had been carried out") is None
    assert titles._OUTCOME_WORDS.search("and the Amendment was DECLARED LOST .")


# An item's whole minutes, laid out as Rushmoor's budget minutes are: each amendment numbered, moved, debated and put
# to a recorded vote. Each vote's extract holds only the 200 characters before its lists, which don't say which
# amendment it was; the minutes do.
NAMES = ("FOR: Cllrs A. Adams, B. Brown and C. Cole (3); AGAINST: Cllrs D. Dean and E. Ellis (2); ABSTAIN: the Mayor "
         "(Cllr F. Ford) (1)")
DEBATE = ("During debate, some of those opposing expressed concern about the absence of supporting details and "
          "whether full costings had been carried out. In support, it was noted that the proposal was affordable and "
          "had been discussed at the Overview and Scrutiny Committee earlier in the year. In a recorded vote, there "
          "voted ")
MINUTES = ("Cllr Dean introduced the Report of the Cabinet, which recommended the approval of the General Fund Budget. "
           "The Council were advised that the opposition wished to propose three amendments. "
           + "".join(f"Amendment {n} – It was MOVED by Cllr A. Adams and SECONDED by Cllr B. Brown that an amendment be "
                     f"made, as set out below: “To add £{n}0,000 for street cleaning.” {DEBATE}{NAMES} and the "
                     "Amendment was DECLARED LOST . " for n in (1, 2, 3))
           + "Following debate, the Recommendations at (i) (1)-(7) above, were put to the meeting. In a recorded vote, "
             f"there voted {NAMES} and the Recommendations were DECLARED CARRIED.")


def excerpts(minutes: str) -> list[str]:
    """Each vote's extract as the reader of votes stores it: up to 200 characters before its first list, from the end
    of the lists before it."""
    out, after = [], 0
    while (start := minutes.find("FOR: Cllrs", after)) >= 0:
        out.append(minutes[max(after, start - 200):start + 150])
        after = start + len(NAMES)
    return out


def test_an_amendments_number_is_read_from_the_items_minutes_before_its_vote():
    found = excerpts(MINUTES)
    assert len(found) == 4 and all(label(x) in (None, "Amendment") for x in found[:3])     # the extract alone
    contexts = titles.minutes_context(MINUTES, found)
    assert all(c is not None for c in contexts)
    labels = [titles.derive_label(c, "", titles.headings(x)) for c, x in zip(contexts, found, strict=True)]
    assert labels == ["Amendment 1", "Amendment 2", "Amendment 3", "Recommendations"]
    # an extract no longer in the minutes (read again since): its own words are used instead
    assert titles.minutes_context("Something else entirely.", found) == [None] * 4


def test_labels_on_one_item_are_never_shared():
    shown = titles.item_labels([{"vote_id": f"x:{n}", "label": lab} for n, lab in
                                enumerate(["Amendment", "Amendment", None, "Substantive motion"])])
    assert [shown[f"x:{n}"]["label"] for n in range(4)] == [
        "Amendment (vote 1 of 4)", "Amendment (vote 2 of 4)", "Vote 3 of 4 on this item", "Substantive motion"]
    # a vote alone on its item needs no "Motion"; an amendment, though, says what the item's title doesn't
    assert titles.item_labels([{"vote_id": "y:0", "label": "Motion"}])["y:0"]["label"] is None
    assert titles.item_labels([{"vote_id": "y:0", "label": "Amendment"}])["y:0"]["label"] == "Amendment"


def test_items_in_capitals_are_written_in_sentence_case_keeping_acronyms():
    assert titles.sentence_case("2026/27 REVENUE BUDGET, MTFS AND HRA BUSINESS PLAN") == \
        "2026/27 Revenue budget, MTFS and HRA business plan"
    assert titles.sentence_case("LOCAL TRANSPORT PLAN 5 FOR HEREFORDSHIRE", keep="Herefordshire Council") == \
        "Local transport plan 5 for Herefordshire"
    assert titles.sentence_case("General Fund Budget 2026/27") == "General Fund Budget 2026/27"     # as written


def vote(**kw):
    return {"vote_id": "E07000092:1559:11918:0", "date": "2026-02-26", "kind": "council", "outcome": "lost",
            "question": "", "partial": False, "counts": {"for": 10, "against": 19, "abstain": 2},
            "item": "General Fund Budget 2026/27 and Medium-Term Financial Strategy 2026/27 to 2029/30", **kw}


def test_titles_lead_with_the_label_and_count_and_fit():
    t = titles.title(vote(label="Amendment 7"), "Rushmoor Borough Council", "Rushmoor")
    assert t == "Amendment 7, lost 10–19: General Fund Budget… – Rushmoor, 26 Feb 2026"
    assert len(t) <= titles.TITLE_MAX
    # a budget item's single vote reads as a search for it would
    t = titles.title(vote(label=None, item="COUNCIL TAX 2020/21", outcome="carried",
                          counts={"for": 30, "against": 12, "abstain": 0}, date="2020-02-27"),
                     "Blackpool Borough Council", "Blackpool")
    assert t == "How councillors voted: Council tax 2020/21 – Blackpool, 27 Feb 2020"
    assert len(t) <= titles.TITLE_MAX
    # the whole meeting's minutes held as one item: the meeting is named instead of "Minutes"
    assert titles.heading({"item": "Minutes", "kind": "council", "label": "Vote 2 of 3 on this item"}) == \
        "Vote 2 of 3 on this item: Full council meeting"
    # a result that contradicts the count (read from the sentence about another vote) is left out
    assert titles.tally(vote(outcome="carried")) == "10 for, 19 against"


def test_descriptions_lead_with_the_label_and_count():
    d = titles.description(vote(label="Amendment 7"), "Rushmoor Borough Council")
    assert d.startswith("Amendment 7: lost, 10 for, 19 against, 2 abstained. Rushmoor Borough Council, full council, "
                        "26 February 2026: General Fund Budget") and len(d) <= titles.DESCRIPTION_MAX


# The pages: three named votes on one budget item at Barnsley, from its minutes

BUDGET_MINUTES = (
    "Councillor Houghton moved the recommendations of the Cabinet on the budget. "
    "Amendment 1 – It was MOVED by Councillor Kitching that an amendment be made to add £50,000 for street "
    "cleaning. During debate, some members asked how it would be paid for. A recorded vote was taken as follows: "
    "For: Councillors Kitching. Against: Councillors Houghton and Franklin. The Amendment was declared LOST. "
    "Amendment 2 – It was MOVED by Councillor Kitching that an amendment be made to restore weekly bin "
    "collections. Some members asked about the cost of the vehicles. A recorded vote was taken as follows: "
    "For: Councillors Kitching. Against: Councillors Houghton and Franklin. The Amendment was declared LOST. "
    "The substantive motion was then put to the vote. A recorded vote was taken as follows: For: Councillors "
    "Houghton and Franklin. Against: Councillors Kitching. The motion was declared CARRIED.")


@pytest.fixture
def site(settings, tmp_path):  # noqa: F811
    dist = tmp_path / "dist"
    dist.mkdir()
    for name, title in (("index", "Where Councils Stand"), ("councils", "Councils"), ("council", "Council"),
                        ("vote", "Named vote")):
        (dist / f"{name}.html").write_text(SHELL.format(title=title))
    settings.raw.setdefault("paths", {})["web_dist"] = str(dist)
    root = settings.parquet_dir
    d = date(2026, 2, 26)
    store.parquet.write(root, "meetings", BARNSLEY, [meeting(BARNSLEY, 5, d)])
    store.parquet.write(root, "items", BARNSLEY, [item(BARNSLEY, 5, 50, d, "BUDGET 2026/27 AND COUNCIL TAX",
                                                        BUDGET_MINUTES)])
    store.parquet.write(root, "attendance", BARNSLEY, [
        member(BARNSLEY, 5, d, "1", "Councillor Hannah Kitching", "LD"),
        member(BARNSLEY, 5, d, "2", "Councillor Sir Steve Houghton", "LAB"),
        member(BARNSLEY, 5, d, "3", "Councillor Robin Franklin", "LAB")])
    rows = []
    starts = [i for i in range(len(BUDGET_MINUTES)) if BUDGET_MINUTES.startswith("For: Councillors", i)]
    for block, start in enumerate(starts):
        after = starts[block - 1] + 70 if block else 0          # the end of the lists of the vote before
        excerpt = BUDGET_MINUTES[max(after, start - 200):start + 120]
        sides = ((("1", "Kitching", "for"), ("2", "Houghton", "against"), ("3", "Franklin", "against")) if block < 2
                 else (("2", "Houghton", "for"), ("3", "Franklin", "for"), ("1", "Kitching", "against")))
        rows += [{"vote_id": f"{BARNSLEY}:5:50:{block}", "item_id": f"{BARNSLEY}:5:50", "meeting_id": f"{BARNSLEY}:5",
                  "gss": BARNSLEY, "date": d, "year": 2026, "question": "", "outcome": "carried" if block == 2 else
                  "lost", "member_id": m, "name": n, "vote": side, "excerpt": excerpt} for m, n, side in sides]
    store.parquet.write(root, "votes", BARNSLEY, rows)
    return TestClient(create_app(settings, state=open_state(settings)))


def head(html: str, tag: str) -> str:
    return html.split(f"<{tag}>")[1].split(f"</{tag}>")[0]


def test_each_vote_on_an_item_has_its_own_title_heading_and_description(site):
    pages = [site.get(f"/votes/{BARNSLEY}:5:50:{n}").text for n in range(3)]
    found = [head(p, "title") for p in pages]
    assert found == [
        # about 70 characters before the site's name: the item's title is cut at a word to fit
        "Amendment 1, lost 1–2: Budget 2026/27… – Barnsley, 26 Feb 2026 | Where Councils Stand",
        "Amendment 2, lost 1–2: Budget 2026/27… – Barnsley, 26 Feb 2026 | Where Councils Stand",
        "Substantive motion, carried 2–1: Budget 2026/27… – Barnsley, 26 Feb 2026 | Where Councils Stand"]
    assert [head(p, "h1") for p in pages] == ["Amendment 1: Budget 2026/27 and council tax",
                                             "Amendment 2: Budget 2026/27 and council tax",
                                             "Substantive motion: Budget 2026/27 and council tax"]
    descriptions = {p.split('<meta name="description" content="')[1].split('"')[0] for p in pages}
    assert len(descriptions) == 3 and all(d.startswith(("Amendment", "Substantive")) for d in descriptions)
    # the app sets the same title as the server (vote.tsx): the API gives it
    api = site.get(f"/api/votes/{BARNSLEY}:5:50:0").json()
    assert f"{api['title']} | Where Councils Stand" == found[0] and api["heading"] == head(pages[0], "h1")
    # each links to the others on the item, by their labels
    assert "<h2>Other named votes on this item</h2>" in pages[0]
    assert f'<a href="/votes/{BARNSLEY}:5:50:1">Amendment 2: Budget 2026/27 and council tax</a>' in pages[0]
    assert f'<a href="/votes/{BARNSLEY}:5:50:0">' not in pages[0].split("Other named votes on this item")[1]
    assert ld(pages[0])["@type"] == "WebPage"


def test_a_councils_page_links_to_each_vote_by_its_label(site):
    html = site.get(f"/councils/{BARNSLEY}").text
    for n, name in enumerate(("Amendment 1", "Amendment 2", "Substantive motion")):
        assert f'<a href="/votes/{BARNSLEY}:5:50:{n}">{name}: Budget 2026/27 and council tax</a>' in html
    # in the minutes' order within the item
    votes = site.get(f"/api/councils/{BARNSLEY}").json()["votes"]
    assert [v["label"] for v in votes] == ["Amendment 1", "Amendment 2", "Substantive motion"]


def test_a_hidden_vote_is_not_linked_from_the_others(site):
    site.app.state.councils.replies.hide(f"/votes/{BARNSLEY}:5:50:1", "A concern is being looked into.")
    page = site.get(f"/votes/{BARNSLEY}:5:50:0").text
    assert f"/votes/{BARNSLEY}:5:50:1" not in page
    assert [s["vote_id"] for s in site.get(f"/api/votes/{BARNSLEY}:5:50:0").json()["siblings"]] == \
        [f"{BARNSLEY}:5:50:2"]


def test_every_vote_can_be_reached_by_a_link(site, monkeypatch):
    """Half the votes were past the first 25 a council's page showed, behind a button search engines don't press,
    and the readable text stopped at 60. Now every vote is linked from its council's page, in a list for each year,
    and each vote's page links to the votes before and after it and at the same meeting."""
    from councils.api import plaintext

    monkeypatch.setattr(plaintext, "LATEST", 1)
    html = site.get(f"/councils/{BARNSLEY}").text
    detailed = html.split("<ol>")[1].split("</ol>")[0]
    assert detailed.count("<li>") == 1 and "The latest 1, then every named vote by year." in html
    years = html.split("<h2>Every named vote, by year</h2>")[1]
    assert '<details class="vote-year" open><summary>2026: 3 named votes</summary>' in years
    for n in range(3):
        assert f'<a href="/votes/{BARNSLEY}:5:50:{n}">' in years
    page = site.get(f"/votes/{BARNSLEY}:5:50:1").text
    steps = page.split('<nav class="vote-steps"')[1].split("</nav>")[0]
    assert f"Earlier named vote at Barnsley Metropolitan Borough Council: <a href=\"/votes/{BARNSLEY}:5:50:0\">" in steps
    assert f"Later named vote at Barnsley Metropolitan Borough Council: <a href=\"/votes/{BARNSLEY}:5:50:2\">" in steps
    api = site.get(f"/api/votes/{BARNSLEY}:5:50:0").json()
    assert api["earlier"] is None and api["later"]["vote_id"] == f"{BARNSLEY}:5:50:1" and api["same_meeting"] == []


def test_a_councils_page_lists_its_budget_and_council_tax_votes_year_by_year(site):
    """Searches for a council's council tax landed on single vote pages, never its own page, with each year's vote
    competing with the others. The council's page gathers them; the site gives no amounts of council tax."""
    html = site.get(f"/councils/{BARNSLEY}").text
    section = html.split("<h2>Budget and council tax votes, year by year</h2>")[1].split("<h2>Named votes")[0]
    assert section.startswith("<p>Named votes on agenda items about the budget, council tax or a precept.</p>"
                              "<h3>2026</h3>")
    assert [f"/votes/{BARNSLEY}:5:50:{n}" in section for n in range(3)] == [True] * 3
    assert "£" not in section
    assert titles.is_budget({"item": "Setting the Council Tax 2026/27"}) and titles.is_budget({"item": "Precepts"})
    assert not titles.is_budget({"item": "Notice of Motion - Weekly Bin Collections"})
