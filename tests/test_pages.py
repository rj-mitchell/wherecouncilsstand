"""Council and vote pages as the server sends them: their own title, description, canonical link, structured data and
readable text for readers without scripts and search engines (api/plaintext.py), and the sitemap."""

import json
import re
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_pipeline import BARNSLEY, GUILDFORD, settings  # noqa: F401 - the fixture

from councils import store
from councils.api.app import create_app
from councils.api.plaintext import page_with_meta, with_text
from councils.state import open_state

SHELL = """<!doctype html>
<html lang="en-GB">
  <head>
    <meta charset="utf-8" />
    <meta property="og:image" content="https://wherecouncilsstand.com/family/card.png">
    <title>{title}</title>
    <meta name="description" content="A generic description." />
  </head>
  <body>
    <main id="main">
      <div id="app"></div>
      <noscript><p>This page needs JavaScript. The minutes themselves are on each council's own website.</p></noscript>
    </main>
  </body>
</html>"""
VOTE = f"{BARNSLEY}:1:10:0"


@pytest.fixture
def site(settings, tmp_path):  # noqa: F811
    dist = tmp_path / "dist"
    dist.mkdir()
    for name, title in (("index", "Where Councils Stand"), ("councils", "Councils"), ("council", "Council"),
                        ("vote", "Named vote")):
        (dist / f"{name}.html").write_text(SHELL.format(title=title))
    for name in ("about", "methodology", "press", "status", "named", "404"):
        (dist / f"{name}.html").write_text(f"<!doctype html><title>{name}</title>")
    settings.raw.setdefault("paths", {})["web_dist"] = str(dist)
    store.parquet.write(settings.parquet_dir, "votes", BARNSLEY, [
        {"vote_id": VOTE, "item_id": f"{BARNSLEY}:1:10", "meeting_id": f"{BARNSLEY}:1", "gss": BARNSLEY,
         "date": date(2025, 2, 26), "year": 2025, "question": "motion", "outcome": "lost", "member_id": m,
         "name": n, "vote": side, "excerpt": "Upon being put to the vote the motion was <lost>."}
        for m, n, side in (("1", "Kitching", "for"), ("2", "Houghton", "against"), ("3", "Franklin", "against"))])
    return TestClient(create_app(settings, state=open_state(settings)))


def ld(html: str) -> dict:
    return json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html).group(1))


def test_a_council_page_carries_its_own_details_and_readable_text(site):
    r = site.get(f"/councils/{BARNSLEY.lower()}")
    html = r.text
    assert r.status_code == 200
    assert "<title>Barnsley Metropolitan Borough Council — Where Councils Stand</title>" in html
    assert html.count("<title>") == 1 and "A generic description" not in html
    assert f'<link rel="canonical" href="https://wherecouncilsstand.com/councils/{BARNSLEY}" />' in html
    assert re.search(r'<meta name="description" content="Barnsley [^"]*In overall control: Labour', html)
    assert 'property="og:image"' in html and 'property="og:title"' in html and "noindex" not in html
    data = ld(html)
    assert data["about"]["@type"] == "GovernmentOrganization" and data["about"]["identifier"]["value"] == BARNSLEY
    # the readable text is in the app's root, where the app draws the page, and the "needs JavaScript" note is gone
    app = html[html.index('<div id="app">'):html.index("</main>")]
    assert "<h1>Barnsley Metropolitan Borough Council</h1>" in app and "Members by party" in app
    assert "Labour: 2" in app and "Liberal Democrats: 1" in app and "Latest meetings" in app
    assert f'<a href="/votes/{VOTE}">Notice of Motion - Weekly Bin Collections</a>' in app
    assert "For 1, Against 2, Abstained 0" in app
    assert "needs JavaScript" not in html


def test_a_vote_page_names_each_councillor_and_their_party(site):
    html = site.get(f"/votes/{VOTE}").text
    assert "<title>Notice of Motion - Weekly Bin Collections, Barnsley Metropolitan Borough Council — Where Councils " \
           "Stand</title>" in html
    assert f'href="https://wherecouncilsstand.com/votes/{VOTE}"' in html
    assert "Hannah Kitching (Liberal Democrats)" in html and "<h2>Against (2)</h2>" in html
    assert "the motion was &lt;lost&gt;." in html and "<lost>" not in html    # every value escaped
    assert ld(html)["about"][1]["startDate"] == "2025-02-26"


def test_unknown_councils_and_votes_are_404_and_not_indexed(site):
    r = site.get("/councils/E99999999")
    assert r.status_code == 404 and "Council not found" in r.text and 'content="noindex"' in r.text
    r = site.get(f"/votes/{GUILDFORD}:9:9:0")
    assert r.status_code == 404 and "Named vote not found" in r.text


def test_the_list_of_councils_and_the_home_page_can_be_read_without_scripts(site):
    html = site.get("/councils").text
    assert f'<a href="/councils/{BARNSLEY}">Barnsley Metropolitan Borough Council</a>' in html
    assert "Not covered yet" in html and 'rel="canonical" href="https://wherecouncilsstand.com/councils"' in html
    home = site.get("/").text
    assert "<h1>What has your council decided?</h1>" in home and ld(home)["@type"] == "WebSite"
    assert 'rel="canonical" href="https://wherecouncilsstand.com/"' in home


def test_sitemap_lists_every_council_and_vote(site):
    r = site.get("/sitemap.xml")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/xml")
    locs = re.findall(r"<loc>(.*?)</loc>", r.text)
    base = "https://wherecouncilsstand.com"
    assert locs[:2] == [f"{base}/", f"{base}/councils"]
    assert {f"{base}/about", f"{base}/press", f"{base}/status", f"{base}/named"} <= set(locs)
    assert f"{base}/404" not in locs
    assert f"{base}/councils/{BARNSLEY}" in locs and len([u for u in locs if "/councils/" in u]) > 300
    assert f"{base}/votes/{VOTE}" in locs


def test_a_page_is_sent_as_it_is_if_the_record_cannot_be_read(site, monkeypatch):
    from councils.api import data

    monkeypatch.setattr(data.Data, "council", lambda self, gss: 1 / 0)
    r = site.get(f"/councils/{BARNSLEY}")
    assert r.status_code == 200 and "<title>Council</title>" in r.text and '<div id="app"></div>' in r.text


def test_shell_helpers_escape_and_replace():
    page = page_with_meta(SHELL.format(title="Old"), title='A "quoted" <title>', description="D & E",
                          url="https://x/y", data={"name": "</script><b>"})
    assert "<title>A &quot;quoted&quot; &lt;title&gt;</title>" in page and "Old" not in page
    assert 'content="D &amp; E"' in page and "</script><b>" not in page and "<\\/script>" in page
    assert with_text(page, None) == page and "needs JavaScript" not in with_text(page, "<p>x</p>")


SOUTH_YORKSHIRE = "E47000002"


def test_an_authority_page_and_its_councils_pages_link_both_ways(site, settings):  # noqa: F811
    """South Yorkshire's board with Barnsley's leader on it (made-up rows): the authority's page names its kind,
    mayor, constituent councils and members by role; Barnsley's page says it is part of the authority."""
    from test_pipeline import item, meeting

    d = date(2025, 3, 19)
    m = {**meeting(SOUTH_YORKSHIRE, 5, d), "kind": "board", "committee_title": "Mayoral Combined Authority Board"}
    store.parquet.write(settings.parquet_dir, "meetings", SOUTH_YORKSHIRE, [m])
    store.parquet.write(settings.parquet_dir, "items", SOUTH_YORKSHIRE, [item(
        SOUTH_YORKSHIRE, 5, 50, d, "Budget", "RESOLVED that the mayor's budget be approved.")])
    base = {"meeting_id": f"{SOUTH_YORKSHIRE}:5", "gss": SOUTH_YORKSHIRE, "date": d, "year": 2025, "member_type": "U",
            "attendance": "Present, as expected", "ward": ""}
    store.parquet.write(settings.parquet_dir, "attendance", SOUTH_YORKSHIRE, [
        {**base, "member_id": "1", "name": "Mayor Oliver Coppard", "role": "Chair", "party_label": "LAB",
         "party": "LAB", "member_role": "mayor", "party_source": "as elected", "representing": "SYMCA"},
        {**base, "member_id": "2", "name": "Councillor Sir Steve Houghton", "role": "Committee Member",
         "party_label": "LAB", "party": "LAB", "member_role": "constituent", "party_source": "home council",
         "home_gss": BARNSLEY, "representing": "Barnsley Council"},
        {**base, "member_id": "", "name": "[name removed]", "role": "Committee Member", "party_label": "",
         "party": "", "member_role": "appointed", "representing": "Business Advisory Board"}])
    store.parquet.write(settings.parquet_dir, "votes", SOUTH_YORKSHIRE, [])

    page = site.get(f"/api/councils/{SOUTH_YORKSHIRE}").json()
    assert page["loaded"] and page["kind_name"] == "Mayoral combined authority"
    assert page["control"]["name"] == "Mayor: Labour" and page["control"]["mayor"] == "Oliver Coppard"
    assert [c["name"] for c in page["constituents"]][0] == "Barnsley Metropolitan Borough Council"
    members = page["members"]["members"]
    assert [x["role"] for x in members] == ["mayor", "constituent", "appointed"]
    assert members[1]["name"] == "Sir Steve Houghton" and members[1]["home"]["gss"] == BARNSLEY
    assert members[2]["name"] is None
    html = site.get(f"/councils/{SOUTH_YORKSHIRE}").text
    app = html[html.index('<div id="app">'):html.index("</main>")]
    assert "Mayoral combined authority" in app and "Mayor: Oliver Coppard (Labour)" in app
    assert f'<a href="/councils/{BARNSLEY}">Barnsley Metropolitan Borough Council</a>' in app
    assert "Name not shown (not a councillor)" in app and "Business Advisory" not in app
    assert ld(html)["about"]["additionalType"] == "Mayoral combined authority"
    barnsley = site.get(f"/councils/{BARNSLEY}").text
    assert f'Part of: <a href="/councils/{SOUTH_YORKSHIRE}">South Yorkshire Mayoral Combined Authority</a>' in barnsley
    assert ld(barnsley)["about"]["memberOf"][0]["name"] == "South Yorkshire Mayoral Combined Authority"
    listing = site.get("/councils").text
    assert "<h2>Strategic authorities</h2>" in listing and "Greater London Authority" in listing
    totals = site.get("/api/status").json()
    assert totals["authorities"] == 20 and totals["authorities_loaded"] == 1
    assert f"/councils/{SOUTH_YORKSHIRE}" in site.get("/sitemap.xml").text


WEB = Path(__file__).resolve().parents[1] / "web"
TIMES = "We reply within 5 working days, and decide within 20 working days."


def test_if_youre_named_is_in_every_footer_beside_corrections_and_built():
    """The page for people named on the site (decision 22), in the family's words (the charity's glossary)."""
    assert ('<a href="/corrections">Corrections</a>\n      <a href="/named">If you\'re named</a>'
            in (WEB / "partials" / "footer.html").read_text())
    assert '"corrections", "named"' in (WEB / "vite.config.ts").read_text()


def test_if_youre_named_uses_the_familys_words():
    page = (WEB / "named.html").read_text()
    assert "<h1>If you're named</h1>" in page and "<title>If you're named — Where Councils Stand</title>" in page
    for route in ("Something is wrong", "You've been characterised unfairly", "Add a statement in your own words"):
        assert f"<h3>{route}</h3>" in page
    for kind in ("error", "unfair", "statement", "takedown"):
        assert f"/corrections?kind={kind}" in page
    assert "Statement from [your name], [date]" in page and TIMES in page
    assert "In their own words. Not checked or endorsed by Where Councils Stand." in page
    assert not re.search(r"right to reply|rebuttal", page, re.I)


def test_the_corrections_page_gives_the_response_times_and_links_to_if_youre_named():
    page = (WEB / "corrections.html").read_text()
    assert TIMES in page and '<a href="/named">If you\'re named on this site</a>' in page
