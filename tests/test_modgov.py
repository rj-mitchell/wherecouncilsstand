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
        assert modgov.probe(load_settings(), "X", "https://example.org")[0] == want
