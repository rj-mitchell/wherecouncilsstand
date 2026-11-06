"""Council and vote pages as the server sends them: their own title, description, canonical link, structured data and
readable text for readers without scripts and search engines (api/plaintext.py), and the sitemap."""

import json
import re
from datetime import date

import pytest
from fastapi.testclient import TestClient
from test_pipeline import BARNSLEY, GUILDFORD, settings  # noqa: F401 - the fixture

from councils import store
from councils.api.app import create_app
from councils.api.plaintext import page_with_meta, with_text
from councils.api.state import StateDB

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
    for name in ("about", "methodology", "press", "status", "404"):
        (dist / f"{name}.html").write_text(f"<!doctype html><title>{name}</title>")
    settings.raw.setdefault("paths", {})["web_dist"] = str(dist)
    store.parquet.write(settings.parquet_dir, "votes", BARNSLEY, [
        {"vote_id": VOTE, "item_id": f"{BARNSLEY}:1:10", "meeting_id": f"{BARNSLEY}:1", "gss": BARNSLEY,
         "date": date(2025, 2, 26), "year": 2025, "question": "motion", "outcome": "lost", "member_id": m,
         "name": n, "vote": side, "excerpt": "Upon being put to the vote the motion was <lost>."}
        for m, n, side in (("1", "Kitching", "for"), ("2", "Houghton", "against"), ("3", "Franklin", "against"))])
    return TestClient(create_app(settings, state=StateDB(settings.data_dir / "state.db")))


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
    assert {f"{base}/about", f"{base}/press", f"{base}/status"} <= set(locs) and f"{base}/404" not in locs
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
