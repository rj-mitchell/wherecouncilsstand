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


def test_sources_only_reads_the_question_with_the_model_only_while_the_caps_allow(client):
    """'Sources only' writes no briefing, but the model reads the question, for a fraction of a penny. Once a
    spending cap is reached that stops too: the free rules read it (as Where MPs Stand). Before, it carried on."""
    from types import SimpleNamespace as NS

    from councils.rag.query_parse import ParsedQuery

    c, fake, state, cfg = client
    read: list[str] = []

    def parse(**kw):
        read.append(kw["messages"][0]["content"])
        return NS(stop_reason="end_turn", parsed_output=ParsedQuery(
            search_text="bin collections", date_from=None, date_to=None, councils=[], control=[], parties=[],
            nations=[], council_types=[], kinds=[], group_by="control", wants_votes=False,
            interpretation="Bin collections, in every council."),
                  usage=NS(input_tokens=1000, output_tokens=100, cache_read_input_tokens=0,
                           cache_creation_input_tokens=0))

    fake.messages.parse = parse
    ask = {"question": "What have councils decided about bin collections?", "sources_only": True}
    evs = events(c.post("/api/ask", json=ask))
    assert len(read) == 1 and evs[0]["plan"]["parser"] == "model" and evs[1]["sources"]
    assert evs[-1]["answer"] is None and evs[-1]["note"].startswith("Sources only")
    with state.connect() as con:
        assert [r[0] for r in con.execute("SELECT kind FROM usage")] == ["parse"]
    for cap in ("daily_spend_cap_usd", "monthly_spend_cap_usd"):
        cfg.raw["usage"].update(daily_spend_cap_usd=3.0, monthly_spend_cap_usd=50.0)
        cfg.raw["usage"][cap] = 0.0
        evs = events(c.post("/api/ask", json=ask))
        assert len(read) == 1, cap                              # no further call to the model
        assert evs[0]["plan"]["parser"] == "offline" and evs[1]["sources"], cap
        assert evs[-1]["answer"] is None and evs[-1]["note"].startswith("Sources only"), cap
    with state.connect() as con:
        assert con.execute("SELECT count(*) FROM usage").fetchone()[0] == 1
    assert not fake.calls                                       # and never a briefing


def test_follow_up_history_is_bounded_and_not_kept_with_the_saved_briefing(client):
    """The earlier questions a follow-up carries go to the model, cut to a fixed length, and into the cache key (the
    answer depends on them). They are not saved with the briefing, nor served with it (as Where MPs Stand and Where
    Countries Stand): a shared page should not carry an earlier conversation."""
    from councils.api.app import AskBody

    body = AskBody.model_validate({"question": "And libraries?", "history": [
        {"question": "x" * 600_000, "answer": "y" * 600_000, "anything": "z" * 9_000}, {"answer": None}]})
    assert [(len(h["question"]), len(h["answer"]), sorted(h)) for h in body.history_dicts()] == [
        (500, 1000, ["answer", "question"]), (0, 0, ["answer", "question"])]
    c, fake, state, _ = client
    assert c.post("/api/ask", json={"question": "And libraries?", "history": [{}] * 7}).status_code == 422
    earlier = [{"question": "What have councils decided about bin collections?", "answer": "A" * 5000}]
    ask = {"question": "And what about Barnsley's bin collections?", "history": earlier}
    final = events(c.post("/api/ask", json=ask))[-1]
    assert final["type"] == "final" and final["answer"] and len(fake.calls) == 1
    prompt = fake.calls[0]["messages"][0]["content"][-1]["text"]
    assert "Q: What have councils decided about bin collections?" in prompt and "A" * 600 in prompt
    saved = state.briefing(final["briefing_id"])
    assert saved["options"] == {"mode": "summary", "plan": None, "sources_only": False}
    assert "A" * 50 not in json.dumps(saved)
    assert c.get(f"/api/briefings/{final['briefing_id']}").json()["options"] == saved["options"]
    # the same follow-up again is answered from the cache; the same question after a different one is not
    assert events(c.post("/api/ask", json=ask))[-1]["cached"] is True and len(fake.calls) == 1
    other = [{"question": "What have councils decided about libraries?", "answer": "B"}]
    assert "cached" not in events(c.post("/api/ask", json={**ask, "history": other}))[-1] and len(fake.calls) == 2
    assert "cached" not in events(c.post("/api/ask", json={"question": ask["question"]}))[-1] and len(fake.calls) == 3
    # a briefing saved before this keeps its row as it is, and is served without the earlier questions
    state.save_briefing("old123", "Bins?", {"mode": "summary", "plan": None, "history": earlier,
                                            "sources_only": False}, [{"type": "final", "answer": None}])
    assert c.get("/api/briefings/old123").json()["options"] == {"mode": "summary", "plan": None, "sources_only": False}
    assert state.briefing("old123")["options"]["history"] == earlier


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
    # a visitor who was refused ("c", and "a" the second time) leaves nothing behind
    assert f.running == {} and f.pending_usd() == 0
    assert f.start("c") is None


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


def test_cost_counts_cache_writes_once_whichever_names_the_usage_uses():
    """The SDK's input_tokens leaves out cache writes and reads; the site's own counts (rag/answer.usage_dict) put
    the writes into input_tokens. Either way each token is priced once: before, the SDK's names were undercounted."""
    from types import SimpleNamespace as NS

    from councils.api.usage import cost_usd
    from councils.rag.answer import usage_dict

    prices = {"price_input_per_mtok": 3.0, "price_output_per_mtok": 15.0, "price_cache_read_per_mtok": 0.3,
              "cache_write_multiplier": 1.25}
    sdk = NS(input_tokens=1_200, output_tokens=800, cache_creation_input_tokens=20_000, cache_read_input_tokens=5_000)
    expected = round(1_200 / 1e6 * 3.0 + 20_000 / 1e6 * 3.0 * 1.25 + 800 / 1e6 * 15.0 + 5_000 / 1e6 * 0.3, 6)
    raw = {"input_tokens": 1_200, "output_tokens": 800, "cache_creation_input_tokens": 20_000,
           "cache_read_input_tokens": 5_000}
    assert cost_usd(raw, prices) == expected == 0.0921
    assert cost_usd(usage_dict(sdk), prices) == expected


def test_token_counts_are_stored_the_same_whichever_names_the_usage_uses(tmp_path):
    """What is written to the usage table (as Where MPs Stand's token_counts): the site's own counts are stored as
    they are, and the SDK's own names are stored the same way, with the cache writes counted into input_tokens.
    Before, the SDK's names were stored with the cache writes left out of the input."""
    from councils.api.usage import cost_usd, record_usage, token_counts

    prices = {"price_input_per_mtok": 3.0, "price_output_per_mtok": 15.0, "price_cache_read_per_mtok": 0.3}
    ours = {"input_tokens": 1500, "output_tokens": 200, "cache_read_tokens": 3000, "cache_write_tokens": 500}
    raw = {"input_tokens": 1000, "output_tokens": 200, "cache_read_input_tokens": 3000,
           "cache_creation_input_tokens": 500}
    assert token_counts(ours) == ours and token_counts(raw) == ours
    assert token_counts({"input_tokens": 1000, "cache_read_input_tokens": None}) == {
        "input_tokens": 1000, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0}
    assert cost_usd({"input_tokens": 1000, "output_tokens": None}, prices) == 0.003   # a missing count is nought
    state = StateDB(tmp_path / "s.db")
    cost = record_usage(state, "v1", "answer", "m", ours, prices)
    assert cost == cost_usd(raw, prices) == record_usage(state, "v1", "answer", "m", raw, prices)
    with state.connect() as con:
        rows = [tuple(r) for r in con.execute(
            "SELECT visitor, kind, model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, "
            "cost_usd FROM usage")]
    assert rows == [("v1", "answer", "m", 1500, 200, 3000, 500, cost)] * 2
    assert record_usage(state, "v1", "answer", "m", None, prices) == 0.0   # no usage: nothing is written
    with state.connect() as con:
        assert con.execute("SELECT count(*) FROM usage").fetchone()[0] == 2


def test_default_prices_are_the_sites_own():
    """Where a price is missing from the settings, the fallback is this site's own: $2 a million tokens in, $10
    out (the other sites fall back to $4 and $20)."""
    from councils.api.usage import cost_usd

    assert cost_usd({"input_tokens": 1_000_000, "output_tokens": 1_000_000}, {}) == 12.0
