"""The Modern.gov probe."""

from councils.config import load_settings


def test_a_firewall_page_is_a_refusal_not_no_site(monkeypatch):
    """Found by the coverage research (November 2026): Knowsley's firewall answers 500, Southampton's bot check 200,
    and a Cloudflare timeout 522. None of them means the council has no Modern.gov site."""
    import httpx

    from councils.sources import modgov

    class R:
        def __init__(self, status, text):
            self.status_code, self.text = status, text

    for status, text, want in [(500, "<h1>The URL you requested has been blocked</h1>", "blocked"),
                               (200, "<script src='/_Incapsula_Resource?x=1'></script>", "blocked"),
                               (200, "<title>Connection denied by Geolocation</title>", "blocked"),
                               (522, "<html>Connection timed out</html>", "unreachable"),
                               (404, "<html>Not found</html>", "none")]:
        monkeypatch.setattr(httpx, "get", lambda *a, status=status, text=text, **k: R(status, text))
        monkeypatch.setattr(modgov.robots, "check", lambda url, ua: "allowed")
        assert modgov.probe(load_settings(), "X", "https://example.org")[0] == want


# robots.txt (decision 21) -------------------------------------------------------------------------------------------

def test_a_site_whose_robots_txt_forbids_the_web_service_is_not_asked(monkeypatch):
    """East Sussex's and 43 other councils' Modern.gov sites say "User-agent: * / Disallow: /" (6 November 2026)."""
    import httpx

    from councils.sources import modgov

    monkeypatch.setattr(modgov.robots, "check", lambda url, ua: "forbidden")
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("asked")))
    assert modgov.probe(load_settings(), "X", "https://democracy.eastsussex.gov.uk") == ("robots", 0)


def test_robots_rules_as_councils_write_them():
    """The rules found on Modern.gov sites, 6 November 2026: everything forbidden but Google's calendar feed; two
    groups for everyone, the second forbidding all (Bedford, Cornwall); only the web service forbidden (King's Lynn and
    West Norfolk); a rule for this crawler by name; and paths compared ignoring case."""
    from councils.sources import robots

    ua = load_settings().modgov["user_agent"]
    cases = [
        ("User-agent: *\nDisAllow: /\n\nUser-agent: Googlebot\nDisAllow: /\nAllow: /mgRss.aspx\n", "forbidden"),
        ("User-agent: *\nDisallow: /x.html\nCrawl-delay: 1\nUser-agent: *\r\nDisAllow: /\r\n", "forbidden"),
        ("User-agent: *\nCrawl-delay: 5\nDisallow: /mgCalendarWeekView.aspx\nDisallow: /mgWebService.asmx\n", "forbidden"),
        ("User-agent: *\nDisallow: /mgwebservice.asmx\n", "forbidden"),
        ("User-agent: WhereCouncilsStand\nAllow: /\n\nUser-agent: *\nDisallow: /\n", "allowed"),
        ("User-agent: *\nDisallow: /mgCalendarMonthView.aspx\n", "allowed"),
        ("", "allowed"),
    ]
    name, path = robots.robot_name(ua), "/mgWebService.asmx/GetCommittees"
    for text, want in cases:
        assert robots.Robots.parse(text).allows(name, path) == (want == "allowed"), text
    # wildcards and an end anchor (Hertfordshire's "Disallow: /*.asmx$")
    rp = robots.Robots.parse("User-agent: *\nDisallow: /*.asmx$\n")
    assert not rp.allows("WhereCouncilsStand", "/mgWebService.asmx") and rp.allows("x", "/mgWebService.asmx/GetX")


def test_the_reader_stops_at_a_forbidding_robots_txt_and_keeps_what_is_stored(tmp_path, monkeypatch):
    """Nothing is asked, the cached copy isn't read in its place, and the stored meetings stay as they were."""
    from dataclasses import replace

    import pytest

    from councils import ingest, store
    from councils.registry import get
    from councils.sources import modgov

    s = replace(load_settings(**{"modgov.read_documents": False}), data_dir=tmp_path)
    gss = "E07000209"
    cached = tmp_path / "raw" / "modgov" / gss / "committees.xml"
    cached.parent.mkdir(parents=True)
    cached.write_text("<committees><committee><committeeid>1</committeeid><committeetitle>Council</committeetitle>"
                      "</committee></committees>")
    store.parquet.write(s.parquet_dir, "meetings", gss, [{"meeting_id": f"{gss}:1", "gss": gss, "kind": "council"}])
    monkeypatch.setattr(modgov.robots, "check", lambda url, ua: "forbidden")
    monkeypatch.setattr(modgov.robots, "crawl_delay", lambda url, ua: 0.0)
    with modgov.Client(s, gss, "https://example.org") as c, pytest.raises(modgov.Refused):
        c.committees(refresh=True)
    res = ingest.load(s, get(gss), update=True)
    assert res.error == modgov.ROBOTS_ERROR
    assert [m["meeting_id"] for m in store.parquet.read(s.parquet_dir, "meetings", gss)] == [f"{gss}:1"]


def test_a_robots_txt_that_cant_be_fetched_is_a_server_that_is_down(tmp_path, monkeypatch):
    """The cached copy is used, as when the web service itself doesn't answer."""
    from dataclasses import replace

    from councils.sources import modgov

    s = replace(load_settings(), data_dir=tmp_path)
    cached = tmp_path / "raw" / "modgov" / "X" / "committees.xml"
    cached.parent.mkdir(parents=True)
    cached.write_text("<committees><committee><committeeid>1</committeeid><committeetitle>Council</committeetitle>"
                      "</committee></committees>")
    monkeypatch.setattr(modgov.robots, "check", lambda url, ua: "unknown")
    with modgov.Client(s, "X", "https://example.org") as c:
        assert [x.title for x in c.committees(refresh=True)] == ["Council"]


def test_documents_robots_txt_forbids_are_not_fetched(tmp_path, monkeypatch):
    """Hertfordshire's robots.txt forbids /documents/ as well as everything else."""
    from dataclasses import replace

    from councils.sources import modgov

    s = replace(load_settings(), data_dir=tmp_path)
    monkeypatch.setattr(modgov.robots, "check", lambda url, ua: "forbidden" if "/documents/" in url else "allowed")
    with modgov.Client(s, "X", "https://example.org") as c:
        c.http.get = lambda *a, **k: (_ for _ in ()).throw(AssertionError("asked"))
        assert c.document("https://example.org/documents/s123/Minutes.pdf") is None
