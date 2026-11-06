"""The web service on the synthetic store from test_pipeline, with a fake Claude client (no network, no API key)."""

import json
from datetime import date

import pytest
from fastapi.testclient import TestClient
from test_pipeline import BARNSLEY, TODAY, FakeClient, settings  # noqa: F401 - the fixture

from councils import store
from councils.api.app import create_app
from councils.api.state import StateDB
from councils.embed.base import HashingEmbedder
from councils.engine import Engine
from councils.rag.pipeline import Pipeline


def events(response) -> list[dict]:
    out = []
    for chunk in response.text.split("\n\n"):
        for line in chunk.splitlines():
            if line.startswith("data: "):
                out.append(json.loads(line[6:]))
    return out


@pytest.fixture
def client(settings):  # noqa: F811
    fake = FakeClient()
    pipe = Pipeline(settings, Engine(settings, HashingEmbedder(64), TODAY), client=fake, today=TODAY)
    state = StateDB(settings.data_dir / "state.db")
    app = create_app(settings, pipeline=pipe, state=state)
    return TestClient(app), fake, state, settings


def test_ask_streams_a_briefing_saves_it_and_answers_again_from_the_cache(client):
    c, fake, state, _ = client
    r = c.post("/api/ask", json={"question": "What have councils decided about bin collections?"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    evs = events(r)
    assert [e["type"] for e in evs][0:2] == ["plan", "sources"]
    final = evs[-1]
    assert final["type"] == "final" and final["answer"]["citations_total"] == 1 and "usage" not in final
    bid = final["briefing_id"]
    saved = c.get(f"/api/briefings/{bid}").json()
    assert saved["question"].startswith("What have councils") and saved["events"][-1]["briefing_id"] == bid
    # the same question again: from the cache, no second call to the model
    again = events(c.post("/api/ask", json={"question": "what have councils decided about  bin collections?"}))
    assert len(fake.calls) == 1 and again[-1]["cached"] is True
    with state.connect() as con:
        assert con.execute("SELECT count(*) FROM usage WHERE kind = 'answer'").fetchone()[0] == 1


def test_over_the_daily_cap_the_sources_are_still_shown(client):
    c, fake, state, cfg = client
    cfg.raw["usage"]["daily_spend_cap_usd"] = 0.0
    evs = events(c.post("/api/ask", json={"question": "What have councils decided about bin collections?"}))
    assert not fake.calls
    assert evs[1]["type"] == "sources" and evs[1]["sources"]
    assert evs[-1]["answer"] is None and "limit" in evs[-1]["note"]


def test_search_councils_votes_and_reports(client):
    c, _, state, cfg = client
    r = c.post("/api/search", json={"question": "bin collections in Barnsley"})
    assert r.status_code == 200 and r.json()["sources"]
    directory = c.get("/api/councils").json()
    assert directory["totals"]["loaded"] == 2
    barnsley = next(x for x in directory["councils"] if x["gss"] == BARNSLEY)
    assert barnsley["control"]["name"] == "Labour" and barnsley["region_name"] == "Yorkshire and the Humber"
    store.parquet.write(cfg.parquet_dir, "votes", BARNSLEY, [
        {"vote_id": f"{BARNSLEY}:1:10:0", "item_id": f"{BARNSLEY}:1:10", "meeting_id": f"{BARNSLEY}:1", "gss": BARNSLEY,
         "date": date(2025, 2, 26), "year": 2025, "question": "motion", "outcome": "lost", "member_id": m,
         "name": n, "vote": side, "excerpt": "Upon being put to the vote the motion was lost."}
        for m, n, side in (("1", "Kitching", "for"), ("2", "Houghton", "against"), ("3", "Franklin", "against"))])
    page = c.get(f"/api/councils/{BARNSLEY}").json()
    assert page["votes"][0]["counts"] == {"for": 1, "against": 2, "abstain": 0}
    assert page["votes"][0]["by_party"]["against"] == [{"party": "Labour", "n": 2}]
    vote = c.get(f"/api/votes/{BARNSLEY}:1:10:0").json()
    assert vote["control"] == "Labour" and [m["name"] for m in vote["members"]][0] == "Hannah Kitching"
    assert c.get("/api/votes/E07000209:9:9:0").status_code == 404
    assert c.get("/api/councils/E99999999").status_code == 404
    r = c.post("/api/report", json={"kind": "takedown", "page": "/votes/x", "message": "Please remove my name."})
    assert r.json()["ok"] and state.reports()[0]["kind"] == "takedown"


def test_rate_limit(client):
    _, _, _, cfg = client
    cfg.raw["usage"]["requests_per_minute"] = 2
    app = create_app(cfg, state=StateDB(cfg.data_dir / "s3.db"))
    t = TestClient(app)
    codes = [t.post("/api/report", json={"message": "hello there"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_briefings_in_progress_count_against_the_daily_cap(client):
    """Many questions at once mustn't all pass the cap before any is counted: a briefing being written is reserved
    at its estimated cost, so the next one sees the cap reached and gets the sources only."""
    import threading

    c, fake, _, cfg = client
    cfg.raw["usage"].update(daily_spend_cap_usd=0.15, briefing_estimate_usd=0.15)
    writing, release = threading.Event(), threading.Event()
    stream = fake._stream

    def slow(**kw):
        writing.set()
        release.wait(10)
        return stream(**kw)

    fake.beta.messages.stream = fake.messages.stream = slow
    first: list = []
    worker = threading.Thread(target=lambda: first.extend(events(c.post(
        "/api/ask", json={"question": "What have councils decided about bin collections?"}))))
    worker.start()
    assert writing.wait(10)
    second = events(c.post("/api/ask", json={"question": "What have councils decided about public toilets?"}))
    release.set()
    worker.join(10)
    assert first[-1]["type"] == "final" and first[-1]["answer"]
    assert second[-1]["answer"] is None and "today's limit" in second[-1]["note"]
    assert len(fake.calls) == 1

def test_in_flight_reservations():
    from councils.api.usage import InFlight

    f = InFlight(per_key=1, total=2, estimate_usd=0.1)
    assert f.start("a") is None and f.start("a").startswith("A briefing is already")
    assert f.start("b") is None and f.start("c").startswith("Many briefings")
    assert f.pending_usd(besides=1) == 0.1
    f.finish("a")
    f.finish("b")
    assert f.pending_usd() == 0 and f.start("c") is None


def test_a_saved_briefing_is_checked_again_when_shown(client):
    """Marks made by older checks are judged again by the current ones; nothing is newly marked."""
    c, _, state, _ = client
    answer = {"markdown": "", "unsupported_segments": 2, "loaded_words": 2, "grounded_ratio": 0.5, "segments": [
        {"text": "March 2025", "sources": [], "status": "unsupported", "loaded": []},
        {"text": "The minutes record that the motion was lost.", "sources": [1], "status": "cited",
         "loaded": [{"start": 4, "end": 11, "word": "minutes"}]},
        {"text": " It was a fiasco that residents across the borough opposed for many months.", "sources": [],
         "status": "unsupported",
         "loaded": [{"start": 10, "end": 16, "word": "fiasco"}]},
    ]}
    state.save_briefing("abc123", "Bins?", {}, [{"type": "final", "answer": answer}])
    shown = c.get("/api/briefings/abc123").json()["events"][-1]["answer"]
    assert [s["status"] for s in shown["segments"]] == ["connective", "cited", "unsupported"]
    assert shown["unsupported_segments"] == 1 and shown["loaded_words"] == 1
    assert shown["segments"][2]["loaded"] == [{"start": 10, "end": 16, "word": "fiasco"}]


def test_old_answers_are_deleted_from_the_cache(tmp_path):
    state = StateDB(tmp_path / "state.db")
    with state.connect() as con:
        con.execute("INSERT INTO answer_cache (key, at, events) VALUES ('old', '2026-01-01T00:00:00+00:00', '[]')")
    state.store_cached("new", [{"type": "final"}], max_hours=168)
    with state.connect() as con:
        assert [r[0] for r in con.execute("SELECT key FROM answer_cache")] == ["new"]


def test_head_requests_are_answered_like_get(client, tmp_path):
    """Uptime checkers send HEAD, and read 405 as the site being down."""
    _, _, state, cfg = client
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Where Councils Stand</title>")
    (dist / "about.html").write_text("<!doctype html><title>About</title>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    cfg.raw.setdefault("paths", {})["web_dist"] = str(dist)
    t = TestClient(create_app(cfg, state=state))
    for path in ("/", "/about", "/assets/app.js", "/api/health", "/api/councils"):
        get, head = t.get(path), t.head(path)
        assert head.status_code == get.status_code == 200, path
        assert head.content == b"" and head.headers["content-type"] == get.headers["content-type"], path
    assert t.head("/no-such-page").status_code == 404
    assert t.head("/api/ask").status_code == 405           # a POST route stays POST only


def test_no_interactive_api_pages(client):
    """Swagger and ReDoc load scripts from a CDN that the content security policy blocks: they are switched off."""
    c, _, _, _ = client
    assert c.get("/api/docs").status_code == 404 and c.get("/redoc").status_code == 404
    assert c.get("/api/openapi.json").json()["info"]["title"] == "Where Councils Stand"


def test_an_ipv6_visitor_is_counted_by_their_slash_64(client):
    """One home or phone connection is given a whole IPv6 /64: its addresses are one visitor (as Where MPs Stand)."""
    from councils.api.usage import network_of, visitor_key

    _, _, state, _ = client
    assert network_of("2001:db8:1:2:aaaa::1") == network_of("2001:db8:1:2:ffff::9") == "2001:db8:1:2::/64"
    assert network_of("2001:db8:1:3::1") != network_of("2001:db8:1:2::1")
    assert network_of("203.0.113.7") == "203.0.113.7" and network_of("::ffff:203.0.113.7") == "203.0.113.7"
    assert network_of("::1") == "::1" and network_of(None) == "-" and network_of("testclient") == "testclient"
    assert visitor_key(state, "2001:db8:1:2::1") == visitor_key(state, "2001:db8:1:2:9::9")
    assert visitor_key(state, "203.0.113.7") != visitor_key(state, "203.0.113.8")


def test_status(client):
    c, _, _, cfg = client
    s = c.get("/api/status").json()
    assert s["loaded"] == 2 and s["councils"] > 300 and s["meetings"] == 2
    assert s["latest_meeting"] == "2025-03-05" and s["start"] == "2018-05-01"
    assert s["briefings"] == "available" and s["briefings_note"] is None and s["last_update"] is None
    (cfg.data_dir / "updates.jsonl").write_text(json.dumps(
        {"finished": "2026-10-24T03:40:00", "councils": 2, "changed": 1, "new_meetings": 3, "failed": ["E07000209"],
         "needs_attention": False}) + "\n")
    last = c.get("/api/status").json()["last_update"]
    assert last == {"finished": "2026-10-24T03:40:00", "councils": 2, "changed": 1, "new_meetings": 3, "failed": 1,
                    "ok": True}
    cfg.raw["usage"]["daily_spend_cap_usd"] = 0.0
    s = c.get("/api/status").json()
    assert s["briefings"] == "paused" and "today's limit" in s["briefings_note"]
