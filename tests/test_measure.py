"""Measurement for Google Ad Grants (docs/DECISIONS.md, 36; api/measure.py): built, and off.

Off, as it ships, every page is sent as it was built: no script, no banner, no "Measurement choices", and /privacy is
the notice of today. On, with a valid tag and a finished notice, every page the server sends loads the family kit's
measure.js with this site's conversions, the footer gains "Measurement choices", and /privacy is the measurement
notice; the site will not start with the notice still a draft."""

import re
import tomllib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_pipeline import BARNSLEY, settings  # noqa: F401 - the fixture

from councils.api import checked, measure
from councils.api.app import create_app
from councils.config import REPO_ROOT, load_settings
from councils.state import open_state

WEB = REPO_ROOT / "web"
TAG = "AW-123456789"
FOOTER = ('<footer class="site-footer">\n  <div class="footer">\n    <div class="wrap">\n      <p class="licence">'
          'Independent. Quotations link to <a href="https://example.org/">the council’s own record</a>.</p>\n'
          "    </div>\n  </div>\n</footer>")
SHELL = """<!doctype html>
<html lang="en-GB">
  <head>
    <meta charset="utf-8" />
    <title>{title}</title>
  </head>
  <body>
    <main id="main"><div id="app">{body}</div></main>
    {footer}
  </body>
</html>"""
PAGES = ("index", "councils", "council", "vote", "topics", "topic", "about", "methodology", "privacy", "corrections",
         "named", "accessibility", "terms", "press", "status", "404")
# every kind of page the server sends: written by the app, sent as built, the corrections page, a 404
ADDRESSES = ("/", "/councils", f"/councils/{BARNSLEY}", "/topics", "/about", "/privacy", "/corrections", "/named",
             "/status", "/no-such-page", "/b/nosuchbriefing")


def a_dist(tmp_path: Path, notice: str | None) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir(parents=True)
    for name in PAGES:
        (dist / f"{name}.html").write_text(SHELL.format(title=name, body=f"<h1>{name}</h1>", footer=FOOTER))
    if notice is not None:
        (dist / f"{measure.NOTICE}.html").write_text(
            SHELL.format(title="privacy", body=f'<h2 id="measurement">Measuring</h2><p>{notice}</p>', footer=FOOTER))
    return dist


def an_app(settings, dist: Path, ads: dict | None) -> TestClient:  # noqa: F811
    settings.raw.setdefault("paths", {})["web_dist"] = str(dist)
    if ads is not None:
        settings.raw["ads"] = ads
    return TestClient(create_app(settings, state=open_state(settings)))


def finished() -> str:
    return "Where They Stand (charity number 1234567) is the data controller. Last updated 1 March 2027."


# ---------- off ----------


def test_the_switch_ships_off():
    ads = tomllib.loads((REPO_ROOT / "config" / "settings.toml").read_text())["ads"]
    assert ads == {"measurement": False, "tag": ""}
    assert measure.tag(load_settings(env={})) == ""


@pytest.mark.parametrize("ads", [None, {"measurement": False, "tag": TAG}, {"measurement": True, "tag": ""},
                                 {"measurement": True, "tag": "UA-1234"}, {"measurement": True, "tag": "AW-1 2"}],
                         ids=["as it ships", "off with a tag", "on without a tag", "an old tag", "not a tag"])
def test_off_every_page_is_sent_as_it_was_built(settings, tmp_path, ads):  # noqa: F811
    dist = a_dist(tmp_path, notice="Draft: charity number NNNNNNN. Last updated 21 November 2026 (draft).")
    site = an_app(settings, dist, ads)       # a draft notice stops nothing while the switch is off
    for address in ADDRESSES:
        html = site.get(address).text
        assert "measure.js" not in html and "Measurement choices" not in html and "data-wts-measure" not in html, \
            address
        assert "google" not in html.lower(), address
    # pages sent as they are: byte for byte the built file, with the headers they had
    about = site.get("/about")
    assert about.content == (dist / "about.html").read_bytes() and "accept-ranges" in about.headers
    assert site.get("/privacy").content == (dist / "privacy.html").read_bytes()
    # the measurement notice is never at an address of its own, or in the sitemap
    for address in ("/privacy-measurement", "/privacy-measurement.html"):
        assert site.get(address, follow_redirects=False).status_code == 404
    assert "privacy-measurement" not in site.get("/sitemaps/pages.xml").text
    assert "content-security-policy" not in site.get("/").headers


# ---------- on ----------


def test_on_the_site_will_not_start_with_the_notice_a_draft(settings, tmp_path):  # noqa: F811
    for draft in ("Where They Stand (charity number NNNNNNN). Last updated 1 March 2027.",
                  "Where They Stand (charity number 1234567). Last updated 21 November 2026 (draft, for later)."):
        with pytest.raises(RuntimeError, match="isn't finished"):
            an_app(settings, a_dist(tmp_path / str(len(draft)), notice=draft), {"measurement": True, "tag": TAG})
    with pytest.raises(RuntimeError, match="no .*privacy-measurement.html"):
        an_app(settings, a_dist(tmp_path / "none", notice=None), {"measurement": True, "tag": TAG})


def test_on_every_page_loads_the_kit_and_offers_measurement_choices(settings, tmp_path):  # noqa: F811
    dist = a_dist(tmp_path, notice=finished())
    site = an_app(settings, dist, {"measurement": True, "tag": TAG})
    script = (f'<script src="/family/measure.js" data-tag="{TAG}" data-privacy="/privacy" '
              'data-measures="briefing_read source_opened donate_click report_sent" defer></script>')
    for address in ADDRESSES:
        html = site.get(address).text
        assert html.count(script) == 1, address
        assert html.index(script) < html.index("</head>"), address
        # "Measurement choices" on a line of its own, straight after the footer's notice, a link to the notice's
        # section so that it leads somewhere without the script
        assert re.search(r'</p>\n      <p class="measure-choices"><a href="/privacy#measurement" data-wts-measure-open>'
                         r"Measurement choices</a></p>\n    </div>\n  </div>\n</footer>", html), address
        assert html.count("Measurement choices") == 1, address
    # /privacy is the measurement notice, and it is still never at an address of its own
    assert 'id="measurement"' in site.get("/privacy").text and "1234567" in site.get("/privacy").text
    assert site.get("/privacy-measurement").status_code == 404
    # nothing else changes: the API, the status codes, what isn't a page
    assert site.get("/no-such-page").status_code == 404
    assert "measure" not in site.get("/api/health").text
    assert site.head("/about").status_code == 200 and site.head("/about").content == b""
    assert "content-security-policy" not in site.get("/").headers     # the front door's (docs/DEPLOY.md)


def test_the_switch_can_be_set_on_the_server():
    s = load_settings(env={"COUNCILS_ADS_MEASUREMENT": "true", "COUNCILS_ADS_TAG": f" {TAG} "})
    assert s.section("ads")["measurement"] is True and measure.tag(s) == TAG
    assert measure.tag(load_settings(env={"COUNCILS_ADS_TAG": TAG})) == ""      # a tag alone turns nothing on


# ---------- the notice and the marks ----------


def test_the_measurement_notice_is_a_draft_beside_todays_and_says_what_the_kit_does():
    notice = (WEB / "privacy-measurement.html").read_text(encoding="utf-8")
    today = (WEB / "privacy.html").read_text(encoding="utf-8")
    assert measure.unfinished(notice) and not measure.unfinished(today)
    assert notice.count("NNNNNNN") == 1 and notice.count("(draft") == 1
    # the glossary's words once the charity is registered (family/GLOSSARY.md, "Who runs it, once registered")
    assert ("Where They Stand, a charitable incorporated organisation registered in England and Wales (charity number "
            "NNNNNNN), is the data controller.") in notice
    assert '<h2 id="measurement">' in notice and '<link rel="canonical" href="https://wherecouncilsstand.com/privacy"' \
        in notice
    # what is measured, by whom, the basis, how long, how to refuse or withdraw, and no ads
    for words in ("finish reading a briefing", "open a source", "follow the Donate link", "send a report or a statement",
                  "independent controller", "Google Ads Controller-Controller Data Protection Terms",
                  "https://business.safety.google/privacy/", "The legal basis is your consent", "90 days",
                  "how Google retains data", "“Accept” and “Reject”", "“Measurement choices” at the foot of any page",
                  "No ads are ever shown", "nothing on them is personalised"):
        assert words in notice, words
    assert "download" not in notice.lower()      # this site has no downloads, and measure.js isn't told of any
    assert "download" not in measure.MEASURES
    # everything today's notice says about visitors and the people named is still said
    for item in re.findall(r"<li>(.*?)</li>", today, re.S):
        assert item in notice or item.split(". If you agreed")[0] in notice, item[:60]


def test_the_server_written_briefing_carries_the_kits_marks():
    source = {"n": 1, "url": "https://example.org/minutes", "council_name": "Barnsley", "committee": "Cabinet",
              "date": "2025-02-26", "gss": BARNSLEY, "kind": "cabinet", "item_title": "Libraries", "group": "",
              "votes": []}
    assert 'data-wts-conversion="source_opened"' in checked.chip(1, source, 0)
    assert '<a href="https://example.org/minutes" rel="noreferrer" data-wts-conversion="source_opened">' in \
        checked.sources_list([source])
    end = checked.check_details({"citations_total": 1}, 1, "abc123")
    assert end.startswith('<section class="check-details" id="check-details" aria-labelledby="check-details-head" '
                          'data-wts-conversion="briefing_read" data-wts-briefing="abc123">')
    assert 'data-wts-briefing' not in checked.check_details({"citations_total": 1}, 1)
