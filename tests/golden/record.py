"""Record what Where Councils Stand's own code gave before it moved onto wts-core (14 November 2026).

Run on the code as it was (the commit this file was added in, or any before the switch):

    uv run python tests/golden/record.py [folder to write into; default: this one]

It writes the JSON files beside it, which tests/test_parity.py compares with what the site gives now, and
``old-state.sql``, a state database made by the old code with rows of every kind, which the import is tested on.
It needs the modules the switch deleted (``councils.api.state``, ``councils.api.usage``, ``councils.backup``,
``councils.offsite``, ``councils.rag.verify`` and the rest), so it does not run on the code as it is now: check out
the old commit to record again.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import sqlite3
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent))

import shared  # noqa: E402
from councils.api.state import StateDB  # noqa: E402
from councils.embed.base import HashingEmbedder  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

from councils import backup, cli, offsite, store  # noqa: E402
from councils.api import app as web  # noqa: E402
from councils.api import state as state_module  # noqa: E402
from councils.api import usage  # noqa: E402
from councils.config import REPO_ROOT, load_settings  # noqa: E402
from councils.engine import Engine  # noqa: E402
from councils.index.build import Indexer, embed_pending  # noqa: E402
from councils.rag import british, neutral, verify  # noqa: E402
from councils.rag.pipeline import Pipeline  # noqa: E402
from councils.rag.sources import Source  # noqa: E402

REAL_ID = StateDB.new_briefing_id
REAL_OFFLINE = web.parse_offline


def the_time_is(clock: shared.Clock) -> None:
    """The old code reads the clock itself: every module of it that does is given the scenario's."""
    state_module.datetime = backup.datetime = offsite.datetime = shared.frozen(clock)
    usage.time = SimpleNamespace(monotonic=clock.monotonic)


def environment(data_dir: Path, **more: str) -> None:
    for key in [k for k in os.environ if k.startswith("COUNCILS_")]:
        del os.environ[key]
    os.environ.update({"COUNCILS_DATA_DIR": str(data_dir), **more})


def stored(value, tmp: Path):
    return shared.plain(value, (tmp, "<tmp>"), (REPO_ROOT, "<root>"))


def site_settings(folder: Path, limits: dict | None = None, pages: bool = False):
    """The site's real settings, with its data in a folder of the scenario's and the scenario's limits."""
    s = load_settings(**{"embedding.backend": "hashing", "embedding.dim": 64})
    raw = {**s.raw, "usage": {**s.raw["usage"], **(limits or {})}}
    if pages:
        raw["paths"] = {**raw.get("paths", {}), "web_dist": str(shared.web_pages(folder / "dist"))}
    folder.mkdir(parents=True, exist_ok=True)
    return replace(s, raw=raw, data_dir=folder)


def new_state(path: Path) -> StateDB:
    state = StateDB(path)
    with state.connect() as con:
        con.execute("INSERT OR REPLACE INTO kv (key, value) VALUES (?, ?)",
                    (f"visitor_salt:{state_module.today()}", shared.SALT))
    return state


def numbered_ids() -> None:
    ids = (f"briefing{n:03d}" for n in range(1, 100))
    StateDB.new_briefing_id = staticmethod(lambda: next(ids))


# ---- settings ------------------------------------------------------------------------------------------------------


def settings(tmp: Path) -> list[dict]:
    out = []
    for case in shared.SETTINGS_CASES:
        for key in [k for k in os.environ if k.startswith("COUNCILS_")]:
            del os.environ[key]
        os.environ.update({k: v.replace("<tmp>", str(tmp)) for k, v in case["env"].items()})
        if case.get("local"):
            (tmp / "with-local").mkdir(exist_ok=True)
            (tmp / "with-local" / "settings.local.toml").write_text(case["local"])
        argument = None
        if case["config"] != "real":
            path = tmp / "sample.toml"
            path.write_text(case["config"].format(data_dir=case["data_dir"].replace("<tmp>", str(tmp))))
            if case.get("as_argument"):
                argument = path
            else:
                os.environ["COUNCILS_CONFIG"] = str(path)
        s = load_settings(argument, **case.get("overrides", {}))
        out.append({**case, "gives": stored(shared.settings_given(s), tmp)})
    return out


# ---- the per-minute limit, a visitor's code, cost, the cache's key, the caps ----------------------------------------


def limits(tmp: Path) -> dict:
    clock = shared.Clock()
    the_time_is(clock)
    cfg = load_settings().usage
    limiter = usage.RateLimiter(int(cfg.get("requests_per_minute", 20)))
    allowed, at = [], 0.0
    for t, who in shared.LIMITER_SCRIPT:
        clock.advance(t - at)
        at = t
        allowed.append(limiter.allow(who))

    state = new_state(tmp / "visitors.db")
    codes = {repr(a): usage.visitor_key(state, a) for a in shared.ADDRESSES}
    networks = {repr(a): usage.network_of(a) for a in shared.ADDRESSES}
    clock.set("2026-11-14T00:00:01+00:00")
    tomorrow = usage.visitor_key(state, shared.ADDRESS)
    with state.connect() as con:
        kept = [r["key"] for r in con.execute("SELECT key FROM kv ORDER BY key")]

    prices = load_settings().usage
    cost = [{"usage": n, "model": m, "cost_usd": usage.cost_usd(u, prices, m)}
            for n, u in enumerate(shared.USAGES) for m in shared.MODELS]
    counts = [usage.token_counts(u) for u in shared.USAGES]

    s = load_settings()
    keys = []
    for body in shared.KEY_BODIES:
        asked = web.AskBody(**body)
        for stamp in shared.KEY_STAMPS:
            keys.append({"body": body, "stamp": stamp, "key": web.cache_key({
                "q": " ".join(asked.question.lower().split()), **asked.model_dump(exclude={"question"}),
                "data": stamp, "model": s.answer.get("model"), "v": web.INSTRUCTIONS_VERSION})})
    return {
        "limiter": {"per_minute": limiter.per_minute, "script": shared.LIMITER_SCRIPT, "allowed": allowed},
        "visitors": {"salt": shared.SALT, "codes": codes, "networks": networks,
                     "the_next_day": {"code_differs": tomorrow != codes[repr(shared.ADDRESS)], "secrets_kept": kept}},
        "cost": cost, "token_counts": counts,
        "cost_with_no_prices_set": usage.cost_usd({"input_tokens": 1_000_000, "output_tokens": 1_000_000,
                                                   "cache_read_tokens": 1_000_000, "cache_write_tokens": 400_000}, {}),
        "cache_keys": {"instructions_version": web.INSTRUCTIONS_VERSION, "model": s.answer.get("model"),
                       "keys": keys},
    }


def caps(tmp: Path) -> dict:
    clock = shared.Clock(shared.CAPS_START)
    the_time_is(clock)
    cfg = {**load_settings().usage, **shared.CAPS_LIMITS}
    state = StateDB(tmp / "caps.db")
    steps = []
    for step in shared.CAPS_SCRIPT:
        what = step[0]
        if what == "spend":
            _, kind, model, n, visitor = step
            used = shared.USAGES[n] if n is not None else None
            gives = usage.record_usage(state, visitor, kind, model, used, cfg)
            if kind == "answer" and used and visitor:
                usage.count_question(state, visitor)
        elif what == "check":
            gives = usage.blocked(state, step[1], cfg, step[2]) if step[1] else usage.site_paused(state, cfg, step[2])
        elif what == "paused":
            gives = usage.site_paused(state, cfg, step[1])
        elif what == "count":
            gives = usage.questions_today(state, step[1])
        elif what == "spent":
            today = state_module.today()
            gives = [usage.spent(state, today), usage.spent(state, today[:8] + "01")]
        else:
            clock.set(step[1])
            gives = None
        steps.append({"step": step, "gives": gives})

    places = usage.InFlight(shared.IN_PROGRESS["per_key"], shared.IN_PROGRESS["total"],
                            shared.IN_PROGRESS["estimate_usd"])
    in_progress = []
    for what, arg in shared.IN_PROGRESS_SCRIPT:
        gives = places.start(arg) if what == "start" else places.finish(arg) if what == "finish" \
            else places.pending_usd(arg)
        in_progress.append({"step": [what, arg], "gives": gives})

    clock = shared.Clock()
    the_time_is(clock)
    cache_state = StateDB(tmp / "cache.db")
    cache = []
    for step in shared.CACHE_SCRIPT:
        if step[0] == "put":
            gives = cache_state.store_cached(step[1], shared.CACHE_EVENTS, step[2])
        elif step[0] == "get":
            gives = cache_state.cached(step[1], step[2])
        elif step[0] == "advance":
            gives = clock.advance(step[1])
        else:
            with cache_state.connect() as con:
                gives = [r["key"] for r in con.execute("SELECT key FROM answer_cache ORDER BY key")]
        cache.append({"step": step, "gives": gives})
    return {"limits": shared.CAPS_LIMITS, "start": shared.CAPS_START, "steps": steps, "in_progress": in_progress,
            "cache": json.loads(json.dumps(cache, default=str))}


# ---- /api/ask over a scripted pipeline ----------------------------------------------------------------------------

REQUEST = SimpleNamespace(client=SimpleNamespace(host=shared.ADDRESS), headers={}, cookies={})


def asks(tmp: Path) -> list[dict]:
    made = [0]

    def build(limits: dict, has_model: bool) -> shared.Side:
        made[0] += 1
        clock = shared.Clock()
        the_time_is(clock)
        numbered_ids()
        web.parse_offline = shared.offline_reader
        s = site_settings(tmp / f"ask-{made[0]}", limits)
        state = new_state(s.data_dir / "state.db")
        pipeline = shared.ScriptedPipeline(clock, s.answer["model"], has_model=has_model)
        app = web.create_app(s, pipeline=pipeline, state=state)

        def rows() -> dict:
            with state.connect() as con:
                return {
                    "spending": [list(r) for r in con.execute(
                        "SELECT at, kind, model, visitor, input_tokens, output_tokens, cache_read_tokens, "
                        "cache_write_tokens, cost_usd FROM usage ORDER BY rowid")],
                    "cache": [list(r) for r in con.execute("SELECT key, at, events FROM answer_cache ORDER BY key")],
                    "briefings": [list(r) for r in con.execute(
                        "SELECT id, at, question, options, events, withdrawn_at, withdrawn_reason FROM briefings "
                        "ORDER BY id")],
                    "questions": [list(r) for r in con.execute("SELECT day, visitor, n FROM questions")],
                }

        def stream(question: str, **body):
            route = next(r.endpoint for r in app.routes if getattr(r, "path", "") == "/api/ask")
            response, web.StreamingResponse = web.StreamingResponse, lambda content, **kwargs: content
            try:
                return route(web.AskBody(question=question, **body), REQUEST)
            finally:
                web.StreamingResponse = response

        return shared.Side(app, TestClient(app), pipeline, clock, rows=rows, stream=stream,
                           briefings_today=lambda visitor: usage.questions_today(state, visitor))

    try:
        return shared.play_asks(build)
    finally:
        web.parse_offline = REAL_OFFLINE
        StateDB.new_briefing_id = REAL_ID


# ---- the made-up record: the real pipeline, the pages, the other endpoints ----------------------------------------


def a_site(folder: Path, limits: dict | None = None):
    """The site on the made-up record: its settings, its state database, the model's stand-in and the app."""
    s = site_settings(folder, limits, pages=True)
    shared.store_record(lambda table, gss, rows: store.parquet.write(s.parquet_dir, table, gss, rows))
    index = Indexer(s)
    index.index_all()
    embed_pending(s, index.index, index.state, HashingEmbedder(64))
    fake = shared.FakeClient()
    state = new_state(s.data_dir / "state.db")
    pipeline = Pipeline(s, Engine(s, HashingEmbedder(64), shared.TODAY), client=fake, today=shared.TODAY)
    return s, state, fake, web.create_app(s, pipeline=pipeline, state=state)


def real_pipeline(tmp: Path) -> list[dict]:
    clock = shared.Clock()
    the_time_is(clock)
    numbered_ids()
    s, state, fake, app = a_site(tmp / "real")
    client = TestClient(app)
    out = []
    try:
        for ask in shared.REAL_ASKS:
            fake.refuse = bool(ask.get("refuse"))
            s.raw["usage"]["daily_spend_cap_usd"] = ask.get("cap", 3.0)
            clock.advance(61)
            r = client.post("/api/ask", json=ask["json"])
            out.append({"case": ask["case"], "status": r.status_code,
                        "events": shared.without_scores(shared.events_of(r.text)),
                        "model_calls": len(fake.calls)})
    finally:
        StateDB.new_briefing_id = REAL_ID
    with state.connect() as con:
        written = {
            "spending": [list(r) for r in con.execute(
                "SELECT at, kind, model, visitor, input_tokens, output_tokens, cache_read_tokens, "
                "cache_write_tokens, cost_usd FROM usage ORDER BY rowid")],
            "briefings": [[r["id"], r["at"], r["question"], json.loads(r["options"]),
                           shared.without_scores(json.loads(r["events"]))]
                          for r in con.execute("SELECT * FROM briefings ORDER BY id")],
            "cached": [shared.without_scores(json.loads(r["events"]))
                       for r in con.execute("SELECT events FROM answer_cache ORDER BY at")],
        }
    return [*out, {"case": "what was written", **written}]


def model_requests(tmp: Path) -> dict:
    """What the model is sent: every request the real pipeline made of the stand-in for its SDK."""
    clock = shared.Clock()
    the_time_is(clock)
    s, state, fake, app = a_site(tmp / "requests")
    client = TestClient(app)
    for ask in shared.MODEL_ASKS:
        fake.parsed = shared.PARSED if ask.get("parsed") else None
        clock.advance(61)
        assert client.post("/api/ask", json=ask["json"]).status_code == 200, ask
    return shared.requests_made(fake)


def old_index(tmp: Path, fixture: Path) -> dict:
    """A search index built by this code from the made-up record, kept whole as a fixture (``fixture``), and what
    this code's searches gave on it."""
    from councils.engine import Filters
    from councils.index.lance import SearchIndex

    clock = shared.Clock()
    the_time_is(clock)
    s, _, _, _ = a_site(tmp / "index")
    if fixture.exists():
        shutil.rmtree(fixture)
    shutil.copytree(s.index_dir, fixture)
    index, embedder = SearchIndex(s.index_dir, 64), HashingEmbedder(64)
    engine = Engine(s, embedder, shared.TODAY)
    return {
        "stats": index.stats(), "has_word_index": index.has_keyword_index(),
        "files_beside_the_tables": sorted(p.name for p in s.index_dir.iterdir() if p.is_file()),
        "searches": shared.index_answers(index.bm25, index.vector, embedder.embed_query),
        "rows": sorted(json.loads(json.dumps(index.rows_for_keys([f"{shared.BARNSLEY}:2025",
                                                                  f"{shared.GUILDFORD}:2025"]), default=str)),
                       key=lambda r: r["passage_id"]),
        "engine": {
            "everything": shared.search_given(engine.search("bin collections", Filters(), limit=5)),
            "one party's councils": shared.search_given(engine.search("bin collections", Filters(control=["LD"]),
                                                                      limit=5)),
            "by region": shared.search_given(engine.search("waste strategy", Filters(), limit=5, group_by="region")),
        },
    }


def ranking() -> dict:
    """The ranking of a set of made-up candidates, and the balanced choice of evidence from them."""
    from datetime import date

    from councils.rank.composite import Candidate, RankParams, rank
    from councils.rank.evidence import select_evidence

    settings = load_settings()

    def ranked(overrides: dict) -> list:
        params = RankParams.from_settings(settings.ranking, today=shared.RANKING_TODAY, **overrides)
        return rank([Candidate(record_id=c["record_id"], date=date.fromisoformat(c["date"]), bm25=c["bm25"],
                               cosine=c["cosine"], data=dict(c["data"])) for c in shared.candidates()], params)

    return shared.ranked_and_chosen(ranked, lambda scored, k, **more: select_evidence(scored, k, **more))


def seed_briefings(state: StateDB, clock: shared.Clock) -> None:
    """Three saved briefings: one shown, one withdrawn, and one saved when follow-up questions were kept with it."""
    answer = shared.an_answer()
    events = [{"type": "plan", "plan": {"question": "Bins?"}}, {"type": "text", "text": answer["markdown"]},
              {"type": "final", "answer": answer, "briefing_id": "abc123"}]
    state.save_briefing("abc123", "What has Barnsley decided about public toilets?", {"mode": "summary", "plan": None,
                                                                                    "sources_only": False}, events)
    clock.advance(60)
    state.save_briefing("gone456", "Which council closed its toilets?", {"mode": "summary"},
                        [{"type": "final", "answer": None}])
    state.save_briefing("old789", "And libraries?", {"mode": "summary", "plan": None, "history": shared.EARLIER,
                                                     "sources_only": False}, [{"type": "final", "answer": None}])
    clock.advance(60)
    state.withdraw_briefing("gone456", "It misattributed a decision to the wrong council.")


def kept(state: StateDB) -> dict:
    """What is kept, as the owner sees it: every statement and report, with what the log says was done."""
    with state.connect() as con:
        statements = [dict(r) for r in con.execute("SELECT * FROM statements ORDER BY id")]
        reports = [dict(r) for r in con.execute("SELECT * FROM reports ORDER BY id")]
    return {
        "statements": [{"id": s["id"], "page": s["page"], "council": s["council"], "name": s["name"],
                        "role": s["role"], "text": s["text"], "link": s["link"], "email": s["email"],
                        "status": s["status"], "shown_on": s["shown_on"], "reason": s["reason"],
                        "log": [[e["action"], e.get("note")] for e in json.loads(s["log"])]} for s in statements],
        "reports": [{"id": r["id"], "kind": r["kind"], "page": r["page"], "message": r["message"],
                     "contact": r["contact"], "closed": r["closed_at"] is not None} for r in reports],
    }


def through_the_api(tmp: Path) -> dict:
    clock = shared.Clock()
    the_time_is(clock)
    s, state, _, app = a_site(tmp / "api")
    seed_briefings(state, clock)
    client = TestClient(app)
    answers = []
    for step in shared.API_STEPS:
        clock.advance(61)
        answers.append(shared.send(client, step))
    return {"answers": answers, "kept": kept(state)}


def what_the_owner_types(tmp: Path) -> dict:
    clock = shared.Clock()
    the_time_is(clock)
    s, state, _, app = a_site(tmp / "owner")
    environment(s.data_dir)
    seed_briefings(state, clock)
    client = TestClient(app)
    for step in shared.OWNER_SENT:
        clock.advance(61)
        assert shared.send(client, step)["status"] == 200, step
    for name, text in shared.OWNER_FILES.items():
        (tmp / name).write_text(text)
    runs = []
    for args in shared.OWNER_COMMANDS:
        clock.advance(61)
        result = CliRunner().invoke(cli.app, [a.replace("<tmp>", str(tmp)) for a in args])
        runs.append({"args": args, **shared.command_run(result, tmp)})
    clock.advance(61)
    return {"runs": runs, "kept": kept(state), "reads": [shared.send(client, {"get": path})
                                                         for path in shared.OWNER_READS]}


def pages(tmp: Path) -> list[dict]:
    """What the pages and the other endpoints give on the made-up record, with two statements shown."""
    clock = shared.Clock()
    the_time_is(clock)
    s, state, _, app = a_site(tmp / "pages")
    seed_briefings(state, clock)
    client = TestClient(app)
    for step in (shared.OWNER_SENT[0], shared.OWNER_SENT[3]):
        clock.advance(61)
        assert shared.send(client, step)["status"] == 200, step
    clock.set("2026-11-14T09:00:00+00:00")
    state.publish_statement(1, checked=shared.CHECKED)
    state.publish_statement(2, checked=shared.CHECKED)
    out = []
    for path in shared.PAGES_READ:
        clock.advance(61)
        out.append(shared.page_read(client, path))
    for limits in ({}, {"daily_spend_cap_usd": 0.0}, {"monthly_spend_cap_usd": 0.0}):
        s.raw["usage"].update({"daily_spend_cap_usd": 3.0, "monthly_spend_cap_usd": 50.0, **limits})
        out.append({**shared.send(client, {"get": "/api/status"}), "case": f"/api/status {limits}"})
    return out


# ---- the checks on briefings --------------------------------------------------------------------------------------


def checked(blocks: list[dict], sources: list[Source]) -> dict:
    """Every check, in the order the site's pipeline runs them (rag/pipeline.py), and the answer as it is sent."""
    report = verify.verify(blocks, sources)
    verify.drop_preambles(report.segments)
    british.britishise_segments(report.segments)
    loaded = neutral.flag_loaded(report.segments)
    verify.check_quotes(report, sources)
    return {**report.to_dict(), "loaded_words": loaded}


def shown_again(answer: dict | None) -> dict | None:
    """A saved or cached answer as the site shows it again (api/app.py, ``rechecked``)."""
    return web.rechecked([{"type": "plan"}, {"type": "final", "answer": answer}])[-1]["answer"]


def checks() -> dict:
    named = {}
    for name, briefing in shared.BRIEFINGS.items():
        answer = checked(briefing["blocks"], shared.sources_of(briefing["sources"], Source))
        older = shared.as_older_checks_left_it(answer)
        named[name] = {"answer": answer, "shown_again": shown_again(answer), "older": shown_again(older)}
    generated = []
    for blocks in shared.generated_briefings():
        answer = checked(blocks, shared.sources_of("all", Source))
        generated.append({"answer": answer, "shown_again": shown_again(answer),
                          "older": shown_again(shared.as_older_checks_left_it(answer))})
    return {"named": named, "generated": generated,
            "saved": {name: shown_again(answer) for name, answer in shared.SAVED_ANSWERS.items()},
            "british": {text: british.to_british(text) for text in shared.BRITISH_TEXTS}}


def write_checks(out: Path) -> None:
    """The named briefings in a file that reads well; the generated ones one to a line, in a file beside it."""
    recorded = checks()
    lines = [json.dumps(entry, ensure_ascii=False, sort_keys=True) for entry in recorded.pop("generated")]
    (out / "checks-generated.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    shared.write(out, "checks.json", recorded)


# ---- backups -------------------------------------------------------------------------------------------------------


def backups(tmp: Path) -> dict:
    clock = shared.Clock()
    the_time_is(clock)

    def run(args: list[str]) -> dict:
        result = CliRunner().invoke(cli.app, args)
        return shared.command_run(result, tmp)

    return shared.backups_scenario(
        tmp, run=run, environment=environment, clock=clock,
        make_backup=lambda db, to, keep, day: backup.make_backup(db, to, keep=keep, day=day))


def offsite_copies(tmp: Path) -> list[dict]:
    clock = shared.Clock("2026-10-12T04:10:00+00:00")
    the_time_is(clock)
    return shared.offsite_scenario(
        tmp, error=offsite.OffsiteError,
        send=lambda archive, keep, env, client: offsite.send(archive, keep=keep, env=env, client=client),
        check=lambda env, client: offsite.check(env=env, client=client))


# ---- a state database made by the old code, for the import ---------------------------------------------------------

OTHER = shared.visitor_of("203.0.113.7")
MINE = shared.visitor_of(shared.ADDRESS)
STATEMENT = ("/votes/" + shared.VOTE, shared.BARNSLEY, "Steve Houghton", "Councillor, Barnsley Metropolitan Borough "
             "Council", shared.WORDS)


def old_state(tmp: Path) -> tuple[str, dict]:
    clock = shared.Clock("2026-07-01T09:00:00+00:00")
    the_time_is(clock)
    s, state, _, app = a_site(tmp / "old")
    environment(s.data_dir)
    cfg = s.usage
    U = shared.USAGES

    def spend(kind: str, model: str | None, n: int, visitor: str | None) -> None:
        usage.record_usage(state, visitor, kind, model, U[n], cfg)
        if kind == "answer" and visitor:
            usage.count_question(state, visitor)

    # the summer: spending by a visitor whose code is long out of date; a statement declined then, whose address
    # has since been deleted, and one withdrawn after being shown
    spend("parse", "claude-haiku-5-5", 3, "0123456789abcdef01234567")
    spend("answer", "claude-sonnet-5-5", 4, "0123456789abcdef01234567")
    declined = state.add_statement(f"/councils/{shared.BARNSLEY}", shared.BARNSLEY, "X  Y", "Z W", "Vote for me.", "",
                                   "x@y.org")
    shown_then = state.add_statement(*STATEMENT, "https://example.org/r?a=1&b=2", "old@barnsley.gov.uk")
    clock.advance(86400)
    state.decline_statement(declined, "It appeals for votes.")
    state.publish_statement(shown_then, checked="Phoned the members' room, 2 July.")
    clock.advance(86400)
    state.withdraw_statement(shown_then, "Withdrawn by its author.")
    with state.connect() as con:       # rows the old tables allow: no counts, no visitor, no model; no page
        con.execute("INSERT INTO usage (at, day, visitor, kind, model, cost_usd) VALUES "
                    "('2026-07-03T10:00:00+00:00', '2026-07-03', NULL, 'parse', NULL, 0.0004)")
        con.execute("INSERT INTO reports (at, kind, page, message, contact) VALUES "
                    "('2026-07-03T10:05:00+00:00', 'error', NULL, 'From a row with nothing else in it', NULL)")
    # a statement withdrawn just over three months before the import: its address is due to go at the next tidy
    clock.set("2026-08-12T09:00:00+00:00")
    due = state.add_statement(f"/councils/{shared.GUILDFORD}", shared.GUILDFORD, "Tim Anderson", "Councillor",
                              "Withdrawn in August.", "", "tim@guildford.gov.uk")
    state.publish_statement(due, checked="Reply from tim@guildford.gov.uk, 12 August.")
    clock.set("2026-08-13T11:00:00+00:00")
    state.withdraw_statement(due, "Withdrawn by its author.")
    # last month, and earlier this month
    clock.set("2026-10-31T23:30:00+00:00")
    spend("answer", "claude-sonnet-5-5", 5, "89abcdef0123456789abcdef")
    clock.set("2026-11-01T00:00:10+00:00")
    spend("answer", "claude-sonnet-5-5", 4, "fedcba9876543210fedcba98")
    clock.set("2026-11-05T08:00:00+00:00")
    state.store_cached("a-week-old", [{"type": "final", "answer": shared.an_answer(), "cached": True}], 168)
    seed_briefings(state, clock)
    clock.set("2026-11-07T08:00:00+00:00")
    state.store_cached("six-days-old", [{"type": "final", "answer": shared.no_records_answer(), "cached": True}], 168)
    with state.connect() as con:
        con.execute("INSERT INTO briefings (id, at, question, options, events, withdrawn_at, withdrawn_reason) VALUES "
                    "('bare000', '2026-11-05T08:30:00+00:00', 'Withdrawn with nothing said?', '{}', '[]', "
                    "'2026-11-06T09:00:00+00:00', '')")
    rid = state.add_report("error", "/votes/" + shared.VOTE, "The vote is shown on the wrong side.", "a@b.org")
    state.add_report("takedown", "/councils/" + shared.BARNSLEY, "Please remove my name.", "")
    state.add_report("other", "", "Something else entirely", "c@d.org")
    blank = state.add_report("unfair", "", "A loaded word.", "")
    clock.advance(3600)
    state.close_report(rid)
    state.close_report(blank)
    shown = state.add_statement(*STATEMENT, "https://barnsley.moderngov.co.uk/ieListDocuments.aspx?MId=1",
                                "cllr@barnsley.gov.uk")
    beside_a_briefing = state.add_statement("/b/abc123", None, "Barnsley Council", "Democratic services",
                                            "Our view.", "", "dem@barnsley.gov.uk")
    waiting = state.add_statement(f"/councils/{shared.GUILDFORD}", shared.GUILDFORD, "Julia McShane", "Leader",
                                  "First para.\n\nSecond.", "", "leader@guildford.gov.uk")
    recent = state.add_statement(f"/councils/{shared.BARNSLEY}", shared.BARNSLEY, "Recent Author", "Councillor",
                                 "Shown for a day only.", "", "recent@barnsley.gov.uk")
    clock.set("2026-11-10T10:00:00+00:00")
    state.publish_statement(shown, checked=shared.CHECKED)
    state.publish_statement(beside_a_briefing, shared.BARNSLEY, checked="Reply from democratic services.")
    state.publish_statement(recent, checked="Letter.")
    state.update_statement(waiting, role="Leader, Guildford Borough Council")
    clock.set("2026-11-11T15:00:00+00:00")
    state.update_statement(shown, text="My newer words, as I sent them.")
    state.withdraw_statement(recent, "Withdrawn by its author.")
    # today: two visitors, and what each has had
    clock.set("2026-11-13T07:00:00+00:00")
    with state.connect() as con:
        con.execute("DELETE FROM kv")
        con.execute("INSERT INTO kv (key, value) VALUES (?, ?)", ("visitor_salt:2026-11-13", shared.SALT))
    spend("parse", "claude-haiku-5-5", 3, MINE)
    spend("answer", "claude-sonnet-5-5", 4, MINE)
    clock.advance(600)
    spend("parse", "claude-haiku-5-5", 3, MINE)
    spend("answer", "claude-sonnet-5-5", 13, MINE)
    spend("parse", "claude-haiku-5-5", 3, OTHER)
    spend("answer", "claude-sonnet-5-5", 5, OTHER)
    spend("parse", "claude-haiku-5-5", 3, OTHER)                  # sources only: the question read, nothing written
    clock.set("2026-11-13T11:00:00+00:00")
    state.store_cached("an-hour-old", [{"type": "plan", "plan": {"question": "Bins?"}},
                                       {"type": "final", "answer": shared.an_answer(), "cached": True}], 168)
    with state.connect() as con:       # an answer kept past its week: nothing has been stored since to delete it
        con.execute("INSERT INTO answer_cache (key, at, events) VALUES ('long-expired', "
                    "'2026-10-01T00:00:00+00:00', '[]')")
    clock.set(shared.START)
    con = sqlite3.connect(s.data_dir / "state.db")
    dump = "\n".join(con.iterdump()) + "\n"
    con.close()

    client = TestClient(app)
    tight = {**cfg, "per_visitor_daily_questions": 2, "daily_spend_cap_usd": 0.2}
    figures = {
        "spent_today": usage.spent(state, state_module.today()),
        "spent_this_month": usage.spent(state, state_module.today()[:8] + "01"),
        "briefings_today": {"mine": usage.questions_today(state, MINE), "other": usage.questions_today(state, OTHER),
                            "nobody": usage.questions_today(state, "nobody")},
        "refused": {"mine": usage.blocked(state, MINE, cfg), "paused": usage.site_paused(state, cfg),
                    "mine, with a limit of two a day": usage.blocked(state, MINE, tight),
                    "other, with a limit of two a day": usage.blocked(state, OTHER, tight),
                    "paused, with a cap of 20 cents and 10 pending": usage.site_paused(state, tight, 0.1),
                    "paused, with a cap of 20 cents and 13 pending": usage.site_paused(state, tight, 0.13)},
        "cached": {key: state.cached(key, 168) for key in ("an-hour-old", "six-days-old", "a-week-old", "long-expired", "never")},
        "reads": [shared.send(client, {"get": path}) for path in (
            "/api/briefings/abc123", "/api/briefings/gone456", "/api/briefings/old789", "/api/briefings/bare000",
            f"/api/statements?page=/votes/{shared.VOTE}", f"/api/statements?council={shared.BARNSLEY}",
            "/api/statements?page=/b/abc123", f"/api/statements?council={shared.GUILDFORD}",
            f"/councils/{shared.BARNSLEY}", f"/votes/{shared.VOTE}", "/api/status")],
        "visitor": usage.visitor_key(state, shared.ADDRESS),
        "kept": kept(state),
    }
    runs = []
    for args in (["list-statements", "--all"], ["list-reports", "--all"], ["list-statements"], ["list-reports"]):
        result = CliRunner().invoke(cli.app, args)
        runs.append({"args": args, **shared.command_run(result, tmp)})
    figures["listed"] = runs
    # three months on from the statement withdrawn in August, its address goes; nothing else does
    figures["addresses_deleted_at_the_next_tidy"] = state.forget_statement_emails()
    figures["kept_after_the_tidy"] = kept(state)
    return dump, figures


def main(out: Path) -> None:
    logging.disable(logging.CRITICAL)    # the command line sets logging up afresh on a stream each run closes
    with tempfile.TemporaryDirectory() as folder:
        tmp = Path(folder).resolve()
        for name, record in (("settings", settings), ("limits", limits), ("caps", caps), ("asks", asks),
                             ("real", real_pipeline), ("api", through_the_api), ("owner", what_the_owner_types),
                             ("pages", pages), ("backups", backups), ("offsite", offsite_copies)):
            (tmp / name).mkdir()
            shared.write(out, f"{name}.json", stored(record(tmp / name), tmp / name))
            shutil.rmtree(tmp / name)
        write_checks(out)
        shared.write(out, "ranking.json", ranking())
        (tmp / "requests").mkdir()
        shared.write(out, "requests.json", stored(model_requests(tmp / "requests"), tmp / "requests"))
        (tmp / "index").mkdir()
        fixture = out.parent / "fixtures" / "old-index"
        shared.write(out, "index.json", stored(old_index(tmp / "index", fixture), tmp / "index"))
        (tmp / "old").mkdir()
        dump, figures = old_state(tmp / "old")
        (out / "old-state.sql").write_text(dump)
        shared.write(out, "old-state.json", stored(figures, tmp / "old"))


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else shared.GOLDEN)
