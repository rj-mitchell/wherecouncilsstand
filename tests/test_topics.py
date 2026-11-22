"""Topic briefings (decision 35; src/councils/topics.py): the topics as config/topics.toml gives them, the weekly
refresh through the real pipeline and checks with a stand-in for the model, and the pages the server writes for
them: /topics, each topic's page with its briefing in full (the strip, the marks and the chips, in the HTML), the home
page's list, the share card and the sitemap. Also the timer that runs the refresh, and the server's copy of the
briefing's markup, which the web app's test compares with the app's own (web/src/__tests__/topic.test.tsx)."""

import json
import os
import re
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_api import site_with
from test_pipeline import FakeClient, settings  # noqa: F401 - the fixture
from typer.testing import CliRunner
from wts_core.dates import long_date

from councils import topics
from councils.api import checked
from councils.api.app import create_app
from councils.rag.pipeline import Pipeline

ROOT = Path(__file__).parents[1]
SHOWN = ROOT / "web" / "src" / "__tests__" / "fixtures" / "shown-briefing.json"
SHOWN_HTML = ROOT / "web" / "src" / "__tests__" / "fixtures" / "shown-briefing.html"
DAY = date(2025, 11, 1)          # the made-up record's meetings (February and March 2025) are within a year of it
SLUG = "bins-recycling-and-waste"
SHELL = """<!doctype html>
<html lang="en-GB">
  <head>
    <title>{title}</title>
    <meta name="description" content="A generic description." />
    <meta property="og:image" content="https://wherecouncilsstand.com/family/card.png">
    <meta property="og:image:alt" content="Where Councils Stand. A Where They Stand project.">
  </head>
  <body><main id="main"><div id="app"></div>
  <noscript><p>This page needs JavaScript. The minutes themselves are on each council’s own website.</p></noscript>
  <div id="topics"></div><div id="latest-votes"></div></main></body>
</html>"""


# The topics


def test_the_ten_topics_load_from_the_config_each_a_neutral_question():
    from councils.config import load_settings

    ts = topics.site_topics(load_settings())
    assert [t.slug for t in ts] == [
        "council-tax-and-budgets", "adult-social-care", "housing-and-homelessness",
        "special-educational-needs-and-school-transport", "planning-and-new-homes",
        "roads-potholes-and-traffic-schemes", "bins-recycling-and-waste", "climate-and-net-zero",
        "local-government-reorganisation-and-devolution", "accommodation-for-asylum-seekers"]
    for t in ts:
        # what councils have discussed and decided, over the past twelve months: never a side, never an answer
        assert re.fullmatch(r"What have councils discussed and decided about [a-z ,]+ over the past twelve months\?",
                            t.question), t.question
        assert t.months == 12 and t.kinds == () and t.search and t.description.endswith(".")
        assert t.path == f"/topics/{t.slug}"
        assert not re.search(r"\b(failing|crisis|scandal|waste of|chaos|reckless|cuts? to)\b", t.question.lower())


@pytest.mark.parametrize("entry, error", [
    ('slug = "Bins"', "lower-case words"),
    ('slug = "bins"\ntitle = "Bins"\nquestion = "Bins"\ndescription = "Bins."\nsearch = "bins"', "question mark"),
    ('slug = "bins"\ntitle = "Bins – waste"\nquestion = "Bins?"\ndescription = "Bins."\nsearch = "bins"', "dashes"),
    ('slug = "bins"\ntitle = "Bins"\nquestion = "Bins?"\ndescription = "Bins."', "has no search"),
    ('slug = "bins"\ntitle = "Bins"\nquestion = "Bins?"\ndescription = "B."\nsearch = "b"\nkinds = ["planning"]',
     "kinds are"),
])
def test_a_topic_that_is_not_right_is_refused_by_name(tmp_path, entry, error):
    path = tmp_path / "topics.toml"
    full = entry if "title" in entry else entry + '\ntitle = "B"\nquestion = "B?"\ndescription = "B."\nsearch = "b"'
    path.write_text(f"[[topic]]\n{full}\n")
    with pytest.raises(ValueError, match=error):
        topics.load_topics(path)


def test_the_same_slug_twice_is_refused(tmp_path):
    one = '[[topic]]\nslug = "bins"\ntitle = "B"\nquestion = "B?"\ndescription = "B."\nsearch = "b"\n'
    (tmp_path / "t.toml").write_text(one + one)
    with pytest.raises(ValueError, match="unique"):
        topics.load_topics(tmp_path / "t.toml")


def test_a_topics_question_is_read_from_its_entry_over_its_months():
    t = topics.Topic("bins", "Bins", "What have councils discussed and decided about bins?", "Bins.", "bin collections")
    plan = topics.plan_for(t, date(2026, 3, 31), date(2018, 5, 1))
    assert plan["search_text"] == "bin collections" and plan["group_by"] == "control" and plan["parser"] == "topic"
    assert plan["filters"] == {"date_from": "2025-03-31", "date_to": "2026-03-31", "kinds": []}
    assert topics.months_before(date(2026, 3, 31), 1) == date(2026, 2, 28)
    assert topics.plan_for(replace(t, months=200), date(2026, 3, 31), date(2018, 5, 1))["filters"]["date_from"] == \
        "2018-05-01"   # never before the record starts


# The refresh


def refreshed(cfg, site, fake=None, **kw):
    from test_pipeline import TODAY, as_model
    from wts_core.adapters.hashing import HashingEmbedder

    from councils.engine import Engine

    pipe = Pipeline(cfg, Engine(cfg, HashingEmbedder(64), TODAY), model=as_model(fake or FakeClient()), today=TODAY)
    return topics.refresh(cfg, site.db, pipe, site.parts, today=kw.pop("today", DAY), clock=kw.pop("clock", site.clock),
                          **kw)


def spent(site, kind="topic"):
    with site.db.connect() as con:
        return con.execute("SELECT count(*), coalesce(sum(cost_usd), 0) FROM wts_spending WHERE kind = ?",
                           (kind,)).fetchone()


def test_a_refresh_writes_each_topic_through_the_pipeline_and_counts_its_cost(settings):  # noqa: F811
    _, fake, site, cfg = site_with(settings)
    run = refreshed(cfg, site, fake)
    assert len(run.written) == 10 and not run.needs_attention and run.stopped is None
    assert len(fake.calls) == 10           # one model call each: the question is read from the topic's own entry
    calls, cost = spent(site)
    assert calls == 10 and cost == pytest.approx(run.spent_usd) and cost > 0
    cur = topics.current(site.db, site.parts.archive, SLUG)
    saved = site.parts.archive.get(cur["briefing_id"])
    assert saved.question == topics.find(cfg, SLUG).question
    assert saved.options == {"mode": "summary", "topic": SLUG}
    assert [e["type"] for e in saved.events] == ["plan", "sources", "text", "final"]
    final = saved.events[-1]
    assert final["briefing_id"] == saved.id and "usage" not in final and final["answer"]["citations_total"] >= 1
    plan = saved.events[0]["plan"]
    assert plan["search_text"] == topics.find(cfg, SLUG).search and plan["filters"]["date_from"] == "2024-11-01"
    assert (cur["records_from"], cur["records_to"]) == ("2024-11-01", "2025-11-01")
    # the same week again writes nothing: not due
    again = refreshed(cfg, site, fake)
    assert not again.written and len(fake.calls) == 10
    assert all(o.outcome.startswith("not due") for o in again.outcomes)


def test_a_refresh_a_week_later_with_the_same_evidence_writes_nothing(settings):  # noqa: F811
    _, fake, site, cfg = site_with(settings)
    refreshed(cfg, site, fake, only=[SLUG])
    run = refreshed(cfg, site, fake, only=[SLUG], clock=_Later(7))
    assert [o.outcome for o in run.outcomes] == [
        "evidence unchanged: the same passages as the current briefing, which stays"]
    assert len(fake.calls) == 1 and len(topics.versions(site.db, site.parts.archive, SLUG)) == 1
    forced = refreshed(cfg, site, fake, only=[SLUG], force=True)
    assert len(forced.written) == 1 and len(topics.versions(site.db, site.parts.archive, SLUG)) == 2


class _Later:
    """The system's clock, ``days`` on."""

    def __init__(self, days):
        self.days = days

    def now(self):
        return datetime.now(UTC) + timedelta(days=self.days)

    def monotonic(self):
        import time

        return time.monotonic()


class Failing(FakeClient):
    """The provider fails part-way."""

    def _stream(self, **kw):
        self.calls.append(kw)
        raise RuntimeError("the provider is down")


def test_a_failed_briefing_keeps_the_last_good_one_and_two_failures_stop_the_run(settings):  # noqa: F811
    _, fake, site, cfg = site_with(settings)
    refreshed(cfg, site, fake, only=[SLUG])
    good = topics.current(site.db, site.parts.archive, SLUG)
    for broken in (FakeClient(refuse=True), Failing()):        # the model declines; the provider fails
        run = refreshed(cfg, site, broken, force=True)
        assert run.needs_attention and run.stopped == "2 topics failed in this run" and not run.written
        assert [o.failed for o in run.outcomes[:2]] == [True, True]
        assert all(o.outcome.startswith("not written: 2 topics failed") for o in run.outcomes[2:])
        assert "failed, so the previous briefing stays" in run.outcomes[0].outcome
        assert topics.current(site.db, site.parts.archive, SLUG) == good
    # a declined briefing was paid for, and is counted
    assert spent(site)[0] >= 3


def test_no_records_keeps_the_last_good_briefing(settings):  # noqa: F811
    _, fake, site, cfg = site_with(settings)
    refreshed(cfg, site, fake, only=[SLUG])
    good = topics.current(site.db, site.parts.archive, SLUG)
    run = refreshed(cfg, site, fake, only=[SLUG], force=True, today=date(2030, 1, 1))   # a year with no minutes
    assert [o.outcome for o in run.outcomes] == ["no records found, so the previous briefing stays"]
    assert not run.needs_attention and topics.current(site.db, site.parts.archive, SLUG) == good
    first = refreshed(cfg, site, fake, only=["adult-social-care"], today=date(2030, 1, 1))
    assert [o.outcome for o in first.outcomes] == ["no records found: not written"]
    assert topics.current(site.db, site.parts.archive, "adult-social-care") is None


def test_a_refresh_stops_at_the_sites_spending_cap(settings):  # noqa: F811
    # the next briefing, at its estimate, would take the day's spending over the cap: nothing is written
    _, fake, site, cfg = site_with(settings, daily_spend_cap_usd=0.2, briefing_estimate_usd=0.25)
    run = refreshed(cfg, site, fake)
    assert not run.written and not fake.calls and run.needs_attention
    assert run.stopped.startswith("the site's spending cap would be reached")
    assert all(o.outcome.startswith("not written: the site's spending cap") for o in run.outcomes)


def test_a_refresh_stops_once_it_has_spent_its_own_limit(settings):  # noqa: F811
    _, fake, site, cfg = site_with(settings)
    cfg = replace(cfg, raw={**cfg.raw, "topics": {**cfg.raw["topics"], "max_run_usd": 0.001}})
    run = refreshed(cfg, site, fake)
    assert len(run.written) == 1 and run.stopped.startswith("this run has spent $0.00") and run.needs_attention
    assert len(fake.calls) == 1


def test_a_refresh_without_a_key_writes_nothing(settings):  # noqa: F811
    class NoKey(Pipeline):
        def has_model(self):
            return False

    _, _, site, cfg = site_with(settings)
    run = topics.refresh(cfg, site.db, NoKey(cfg), site.parts, today=DAY)
    assert not run.written and not run.needs_attention and spent(site)[0] == 0
    assert all("no API key" in o.outcome for o in run.outcomes)


def test_an_unknown_topic_is_refused(settings):  # noqa: F811
    _, fake, site, cfg = site_with(settings)
    with pytest.raises(ValueError, match="no topic called nothing-here"):
        refreshed(cfg, site, fake, only=["nothing-here"])


# The pages


@pytest.fixture
def pages(settings, tmp_path):  # noqa: F811
    dist = tmp_path / "dist"
    dist.mkdir()
    for name in ("index", "topics", "topic", "councils", "council", "vote"):
        (dist / f"{name}.html").write_text(SHELL.format(title=name))
    settings.raw.setdefault("paths", {})["web_dist"] = str(dist)
    c, fake, site, cfg = site_with(settings)
    refreshed(cfg, site, fake, only=[SLUG, "climate-and-net-zero"])
    return c, site, cfg


def test_a_topic_page_has_its_briefing_written_in_full_by_the_server(pages):
    c, site, cfg = pages
    t = topics.find(cfg, SLUG)
    cur = topics.current(site.db, site.parts.archive, SLUG)
    html = c.get(t.path).text
    main = html[html.index('<div id="app">'):]
    # the page's own title, description, canonical address and breadcrumbs; listed by search engines
    assert "<title>Bins, recycling and waste: briefing from council minutes | Where Councils Stand</title>" in html
    assert f'<link rel="canonical" href="https://wherecouncilsstand.com{t.path}" />' in html
    assert 'name="robots"' not in html and "This page needs JavaScript" not in html
    assert '"@type": "BreadcrumbList"' in html
    # the title, the question, when it was prepared and the records it used
    prepared = long_date(cur["prepared_at"][:10])
    assert f"<h1>{t.title}</h1>" in main and t.question in main
    assert f"This one was prepared on {prepared}, from 2 records from 2 councils" in main
    assert "from 1 November 2024 to 1 November 2025" in main
    # the strip, the record quotation, the chip and the mark of the sentence with no source, all in the HTML
    assert 'class="wts-check"' in main and "Checked against the council minutes" in main
    assert re.search(r'<span class="wts-check__num">1</span><span>of 1</span></span><span>citation matched', main)
    assert 'class="wts-chip" data-source="1"' in main
    assert re.search(r"Source</span> 1</span><span>(Barnsley Metropolitan|Guildford) Borough Council, full council, "
                     r"\d+ (February|March) 2025</span>", main)
    assert 'class="wts-nosource" id="nosource-' in main and "(no source)" in main
    assert "How this briefing was checked" in main and 'id="sources-heading"' in main
    assert f'href="/b/{cur["briefing_id"]}"' in main and "/corrections?page=" in main
    # what the page's script needs, as data
    data = json.loads(re.search(r'<script type="application/json" id="topic-data">(.*?)</script>', main, re.S)[1])
    assert set(data) == {"answer", "sources"} and data["sources"][0]["n"] == 1
    # its own share card: the topic's question, the counts in words
    assert f'<meta property="og:image" content="https://wherecouncilsstand.com{t.path}/card.png">' in html
    alt = re.search(r'<meta property="og:image:alt" content="([^"]*)">', html)[1]
    assert alt.startswith(t.question + " A briefing written by AI, checked against the council minutes. 1 of 1 ")
    assert alt.endswith(f"Prepared {prepared}. Where Councils Stand.")


def test_a_topic_card_is_drawn_once_with_the_topics_question(pages):
    from PIL import Image

    c, site, cfg = pages
    card = c.get(f"/topics/{SLUG}/card.png")
    assert card.status_code == 200 and card.headers["content-type"] == "image/png"
    kept = list((cfg.data_dir / "cards").glob(f"topic-{SLUG}-*.png"))
    assert len(kept) == 1 and kept[0].read_bytes() == card.content
    with Image.open(kept[0]) as image:
        assert image.size == (1200, 630)
    assert c.get("/topics/adult-social-care/card.png").status_code == 404      # not written yet
    assert c.get("/topics/no-such-topic/card.png").status_code == 404


def test_a_topic_not_written_yet_is_not_listed_and_an_unknown_one_is_404(pages):
    c, _, _ = pages
    waiting = c.get("/topics/adult-social-care")
    assert waiting.status_code == 200 and '<meta name="robots" content="noindex" />' in waiting.text
    assert "has not been written yet" in waiting.text and "/family/card.png" in waiting.text
    missing = c.get("/topics/no-such-topic")
    assert missing.status_code == 404 and "Topic not found" in missing.text and 'content="noindex"' in missing.text


def test_the_topics_list_and_the_home_page_link_each_topic(pages):
    c, site, cfg = pages
    listing = c.get("/topics").text
    assert "<title>Topics | Where Councils Stand</title>" in listing and 'name="robots"' not in listing
    for t in topics.site_topics(cfg):
        assert f'<a href="{t.path}">{t.title}</a>' in listing and t.question in listing
    assert listing.count("Not written yet") == 8 and listing.count("Prepared ") == 2
    home = c.get("/").text
    section = home[home.index('<div id="topics">'):home.index('<div id="latest-votes">')]
    assert '<h2 id="home-topics-heading">Topics</h2>' in section
    assert re.findall(r'<li><a href="(/topics/[^"]+)">', section) == ["/topics/bins-recycling-and-waste",
                                                                      "/topics/climate-and-net-zero"]
    assert '<a href="/topics">Every topic, with the question each one asks</a>' in section


def test_the_sitemap_lists_the_topics_dated_by_their_briefings(pages):
    from test_pages import sitemap_entries

    c, site, _ = pages
    base = "https://wherecouncilsstand.com"
    maps = sitemap_entries(c)
    day = topics.current(site.db, site.parts.archive, SLUG)["prepared_at"][:10]
    assert maps[f"{base}/sitemaps/topics.xml"] == [
        (f"{base}/topics", day), (f"{base}/topics/{SLUG}", day), (f"{base}/topics/climate-and-net-zero", day)]
    assert f"<loc>{base}/sitemaps/topics.xml</loc><lastmod>{day}</lastmod>" in c.get("/sitemap.xml").text


def test_a_withdrawn_or_hidden_topic_briefing_is_not_shown(pages, settings):  # noqa: F811
    c, site, cfg = pages
    first = topics.current(site.db, site.parts.archive, SLUG)
    _, fake, _, _ = site_with(settings)
    refreshed(cfg, site, fake, only=[SLUG], force=True)
    second = topics.current(site.db, site.parts.archive, SLUG)
    assert second != first
    page = c.get(f"/topics/{SLUG}").text
    assert f'href="/b/{second["briefing_id"]}"' in page and "Earlier briefings on this topic" in page
    assert f'<a href="/b/{first["briefing_id"]}">Prepared ' in page
    # withdrawn: the one before it is current again
    site.parts.archive.withdraw(second["briefing_id"], "A test.")
    assert topics.current(site.db, site.parts.archive, SLUG) == first
    assert f'href="/b/{first["briefing_id"]}"' in c.get(f"/topics/{SLUG}").text
    # hidden while a concern is decided: the note in its place, kept out of search engines and the sitemap
    site.replies.hide(f"/b/{first['briefing_id']}", "A made-up note, for testing.")
    fresh = TestClient(create_app(cfg, state=site.db))
    hidden = fresh.get(f"/topics/{SLUG}").text
    assert "This page is hidden while a concern about it is decided." in hidden and "wts-check" not in hidden
    assert '<meta name="robots" content="noindex" />' in hidden
    assert fresh.get(f"/topics/{SLUG}/card.png").status_code == 404
    from test_pages import sitemap_entries

    urls = [u for u, _ in sitemap_entries(fresh)["https://wherecouncilsstand.com/sitemaps/topics.xml"]]
    assert f"https://wherecouncilsstand.com/topics/{SLUG}" not in urls


def test_a_topic_briefing_at_its_own_address_says_whose_question_it_is(pages):
    c, site, _ = pages
    cur = topics.current(site.db, site.parts.archive, SLUG)
    b = c.get(f"/api/briefings/{cur['briefing_id']}").json()
    assert b["topic"] == {"slug": SLUG, "title": "Bins, recycling and waste", "path": f"/topics/{SLUG}"}
    # a reader's has no topic
    site.parts.archive.save("Bins?", {"mode": "summary"}, [{"type": "final", "answer": None}], id="reader01")
    assert "topic" not in c.get("/api/briefings/reader01").json()


def test_the_topic_templates_are_not_pages_of_their_own(pages):
    c, _, _ = pages
    for path in ("/topic", "/topic.html", "/topics.html"):
        assert c.get(path, follow_redirects=False).status_code in (301, 404), path
    assert c.get("/topic").status_code == 404


# The server's copy of the briefing's markup


def test_the_servers_briefing_markup_is_the_apps():
    """The renderer's test answer (as the server shows it) drawn by the server: the strip, the text and the check
    details. web/src/__tests__/topic.test.tsx checks that the app draws the same; set COUNCILS_WRITE_FIXTURES=1 to
    write it again after an intended change."""
    fixture = json.loads(SHOWN.read_text())
    answer, sources = fixture["answer"], fixture["sources"]
    html = (checked.check_strip(answer) + checked.briefing_text(answer["segments"], sources)
            + checked.check_details(answer, len(sources)))
    if os.environ.get("COUNCILS_WRITE_FIXTURES"):
        SHOWN_HTML.write_text(html + "\n")
    assert SHOWN_HTML.read_text().strip() == html
    # each kind of point, marked in words
    assert "(quotation, found word for word in the minutes of source 2)" in html
    assert "Not found word for word" in html and "(no source)" in html and "was removed)" in html
    assert html.count('class="wts-chip"') == 3


def test_the_server_escapes_what_it_writes():
    answer = {"segments": [{"text": "<b>Bins</b> & “recycling <i>is</i> fine” here", "sources": [1],
                            "status": "cited"}], "citations_total": 1, "citations_invalid": 0, "quotes_total": 0}
    html = checked.briefing_text(answer["segments"], [{"n": 1, "council_name": "<script>", "kind": "council",
                                                       "date": "2025-02-26"}])
    assert "<b>" not in html and "<script>" not in html and "&lt;b&gt;Bins&lt;/b&gt; &amp;" in html


# The command and the timer


def test_the_command_says_what_it_did_and_exits_1_when_a_topic_needs_attention(monkeypatch, settings):  # noqa: F811
    from councils import cli

    def fake(run):
        return lambda *a, **k: run

    monkeypatch.setattr(topics, "refresh", fake(topics.Run([topics.Outcome(SLUG, "written (x, $0.07)", "x")],
                                                           0.07)))
    monkeypatch.setenv("COUNCILS_DATA_DIR", str(settings.data_dir))
    ok = CliRunner().invoke(cli.app, ["topics", "refresh"])
    assert ok.exit_code == 0 and "1 written, $0.07 spent" in ok.output
    monkeypatch.setattr(topics, "refresh", fake(topics.Run([topics.Outcome(SLUG, "failed", failed=True)], 0.0)))
    assert CliRunner().invoke(cli.app, ["topics", "refresh"]).exit_code == 1
    monkeypatch.setattr(topics, "refresh", fake(topics.Run([], 0.0, stopped="a cap")))
    stopped = CliRunner().invoke(cli.app, ["topics", "refresh"])
    assert stopped.exit_code == 1 and "stopped: a cap" in stopped.output


def test_the_weekly_timer_runs_the_refresh_on_sunday_evening_without_the_update_lock():
    deploy = ROOT / "deploy"
    service = (deploy / "councils-topics.service").read_text()
    timer = (deploy / "councils-topics.timer").read_text()
    assert "ExecStart=/usr/bin/docker compose run --rm --no-deps -T app councils topics refresh" in service
    assert "flock" not in service.split("ExecStart=")[1] and "OnFailure=alert@%n.service" in service
    assert re.search(r"(?m)^OnCalendar=Sun \*-\*-\* 21:43:00 UTC$", timer) and "Persistent=true" in timer
    # well clear of the nightly update and the backup, and of the weekly report the next morning
    for other, at in (("councils-update", "03:17"), ("councils-backup", "04:30"),
                      ("councils-weekly-report", "06:23")):
        assert at in (deploy / f"{other}.timer").read_text()
    assert "councils-topics" in re.search(r'JOBS="([^"]+)"', (deploy / "update.sh").read_text())[1].split()
