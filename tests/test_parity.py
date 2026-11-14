"""The site on the shared package (wts-core) gives what its own code gave before.

tests/golden/ holds what the site's code gave on 14 November 2026, before the switch, recorded by
tests/golden/record.py from the scripts in tests/golden/shared.py. Each test here plays the same script to the site
as it is now and compares. Where the two differ on purpose, the difference is asserted, with the entry of wts-core's
docs/AS-BUILT.md (or docs/MIGRATION.md, or its CHANGELOG.md) that lists it: nothing is skipped.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "golden"))

import pytest  # noqa: E402
import shared  # noqa: E402

from councils.config import REPO_ROOT, load_settings  # noqa: E402


def stored(value, tmp: Path):
    """As the recorder wrote it: the scenario's own folder as "<tmp>", the repository as "<root>"."""
    return shared.plain(value, (tmp, "<tmp>"), (REPO_ROOT, "<root>"))


# ---- settings (wts-core docs/MIGRATION.md, 1.1: no difference) -----------------------------------------------------


@pytest.mark.parametrize("case", shared.read("settings.json"), ids=lambda case: case["name"])
def test_settings_resolve_as_before(case, tmp_path):
    tmp = tmp_path.resolve()
    env = {k: v.replace("<tmp>", str(tmp)) for k, v in case["env"].items()}
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
            env["COUNCILS_CONFIG"] = str(path)
    s = load_settings(argument, env, **case.get("overrides", {}))
    now = stored(shared.settings_given(s), tmp)
    if case["config"] == "real":
        added_to_the_settings_file(now, case["gives"])
    assert now == case["gives"]


# Sections config/settings.toml has gained with the shared package, each for something the site did not do before:
# the structured log's limits, the alert thresholds (empty until the owner sets them), and the evaluation harness's.
NEW_SECTIONS = ("logs", "alerts", "eval")


def added_to_the_settings_file(now: dict, golden: dict) -> None:
    """Take out of what the real settings file gives now what it has gained since the goldens were recorded, each
    addition checked: everything else in the file must resolve as it did."""
    # MIGRATION 1.3, "Unknown model": "Each site's settings get an explicit entry for every model they name." The
    # briefing model had none and took the base prices; its own entry has the same three figures.
    for usage in (now["usage"], now["raw"]["usage"]):
        base = {k: usage[k] for k in ("price_input_per_mtok", "price_output_per_mtok", "price_cache_read_per_mtok")}
        if "claude-sonnet-5-5" in usage["models"] and "claude-sonnet-5-5" not in golden["usage"]["models"]:
            assert usage["models"].pop("claude-sonnet-5-5") == base == {
                "price_input_per_mtok": 2.0, "price_output_per_mtok": 10.0, "price_cache_read_per_mtok": 0.2}
    for section in NEW_SECTIONS:
        assert section not in golden["raw"]
        now["raw"].pop(section, None)
    # MIGRATION 1.5: "prompt caching becomes a setting ([answer] cache_instructions, on as today)"; and how alike two
    # questions must be to be one theme in the weekly report, which is new with the record of briefings
    for section, key, value in (("answer", "cache_instructions", "short"), ("embedding", "theme_similarity", 0.8)):
        for given in (now[section], now["raw"][section]):
            assert key not in golden[section] and given.pop(key) == value


def test_the_settings_are_read_from_the_real_environment_too(monkeypatch, tmp_path):
    monkeypatch.setenv("COUNCILS_DATA_DIR", str(tmp_path / "data"))
    s = load_settings()
    assert s.data_dir == tmp_path / "data" and s.state_db == tmp_path / "data" / "state.db"
    assert (s.site.env_prefix, s.site.package, s.site.name) == ("COUNCILS", "councils", "Where Councils Stand")


# ---- the checks on briefings (MIGRATION 1.4; AS-BUILT, checks) -----------------------------------------------------
# This site passes its longer list of honorifics, the strict form of the "note about the evidence" rule and its own
# loaded words (councils/rag/checks.py). Every recorded report must be given again, exactly.


def checked(blocks: list[dict], which: str) -> dict:
    """Every check, as the site's pipeline now runs them (rag/pipeline.py)."""
    from wts_core.checks import check_briefing

    from councils.rag.checks import LOADED_WORDS, VERIFIER
    from councils.rag.sources import Source

    return check_briefing(blocks, shared.sources_of(which, Source), VERIFIER, LOADED_WORDS)


def shown_again(answer: dict | None) -> dict | None:
    """A saved or cached answer as the site shows it again."""
    from councils.rag.checks import rechecked

    return rechecked([{"type": "plan"}, {"type": "final", "answer": answer}])[-1]["answer"]


def as_before(answer: dict) -> dict:
    """AS-BUILT, checks: "to_dict() writes today's keys and then rules": the one key a report has that it had not,
    the number of the checking rules that wrote it (1), written last. With it taken off, the report must be what
    the site's own verifier gave."""
    assert list(answer)[-1] == "rules" and answer["rules"] == 1
    return {k: v for k, v in answer.items() if k != "rules"}


def the_same_checks(blocks: list[dict], which: str, golden: dict, name: str) -> None:
    now = checked(blocks, which)
    assert as_before(now) == golden["answer"], name
    # AS-BUILT, checks: "Answers from before adoption carry no stamp, so recheck judges them again each time ...
    # For those answers it gives what the site's own recheck_flags gives": the recorded answer, shown again as it
    # was written and as older checks might have left it
    assert shown_again(golden["answer"]) == golden["shown_again"], name
    assert shown_again(shared.as_older_checks_left_it(golden["answer"])) == golden["older"], name
    # AS-BUILT, checks: "Answers written after adoption are stamped and left alone": its marks on unsupported text
    # are as they were written, where the site's own code judged a just-written answer again when it was shown
    assert shown_again(now) == now, name


@pytest.mark.parametrize("name", list(shared.BRIEFINGS))
def test_the_checks_report_each_named_briefing_as_before(name):
    briefing = shared.BRIEFINGS[name]
    the_same_checks(briefing["blocks"], briefing["sources"], shared.read("checks.json")["named"][name], name)


def test_the_checks_report_150_generated_briefings_as_before():
    import json

    lines = (shared.GOLDEN / "checks-generated.jsonl").read_text(encoding="utf-8").splitlines()
    briefings = shared.generated_briefings()
    assert len(lines) == len(briefings) == 150
    for n, (blocks, line) in enumerate(zip(briefings, lines, strict=True)):
        the_same_checks(blocks, "all", json.loads(line), f"generated briefing {n}")


def test_saved_answers_are_judged_again_as_before():
    golden = shared.read("checks.json")["saved"]
    assert list(golden) == sorted(shared.SAVED_ANSWERS)
    for name, answer in shared.SAVED_ANSWERS.items():
        assert shown_again(answer) == golden[name], name
    # one of the recorded briefings was changed by being shown again straight after it was written: the old
    # judging again could never repeat exactly what the first judging did, which is why answers are now stamped
    named = shared.read("checks.json")["named"]
    assert [name for name, g in named.items() if g["shown_again"] != g["answer"]] == [
        "headings, labels, bullets, dates and joins"]


def test_the_models_own_words_are_made_british_as_before():
    from wts_core.checks import to_british

    assert {text: to_british(text) for text in shared.BRITISH_TEXTS} == shared.read("checks.json")["british"]


# ---- backups and their off-site copies (MIGRATION 1.11: the name, what it holds and what is kept, unchanged) -------


def environment(monkeypatch, data_dir: Path, **more: str) -> None:
    import os

    for key in [k for k in os.environ if k.startswith("COUNCILS_")]:
        monkeypatch.delenv(key)
    monkeypatch.setenv("COUNCILS_DATA_DIR", str(data_dir))
    for key, value in more.items():
        monkeypatch.setenv(key, value)


def command(args: list[str], tmp: Path) -> dict:
    """One of the owner's commands: what it printed, where, and how it ended (as the recorder kept it)."""
    from typer.testing import CliRunner

    from councils.cli import app

    return shared.command_run(CliRunner().invoke(app, args), tmp)


def test_backups_are_named_hold_and_keep_what_they_did_and_the_commands_print_the_same_lines(tmp_path, monkeypatch):
    import sqlite3

    from wts_core import ops

    from councils.state import BACKUPS

    tmp, clock = tmp_path.resolve(), shared.Clock()
    monkeypatch.setattr("councils.cli.CLOCK", clock)

    def make_backup(db: Path, to: Path, keep: int, day: str) -> Path | None:
        return ops.make_backup(db, to, BACKUPS, keep=keep, clock=shared.Clock(f"{day}T04:10:00+00:00"))

    golden = shared.read("backups.json")
    now = stored(shared.backups_scenario(
        tmp, make_backup=make_backup, run=lambda args: command(args, tmp), clock=clock,
        environment=lambda data_dir, **more: environment(monkeypatch, data_dir, **more)), tmp)
    if golden["sqlite"] != sqlite3.sqlite_version:
        # the database inside a backup is SQLite's own copy, which carries the library's version, and the words of
        # its integrity check are the library's: both are compared only where the library is the one the goldens
        # were recorded with
        for made in (*golden["made"], *now["made"]):
            del made["inside"]["sha256"]
        for recorded in (golden, now):
            recorded["damaged"]["error"] = recorded["damaged"]["error"].split(":")[0]
            for run in recorded["commands"]:
                if run["case"] == "a copy that fails its check":
                    run["error"] = run["error"].split(": ***")[0]
        golden["sqlite"] = now["sqlite"]
    assert now == golden


def test_off_site_copies_are_sent_pruned_and_recorded_as_before(tmp_path):
    import json

    from wts_core import ops
    from wts_core.adapters import b2

    from councils.config import SITE
    from councils.state import BACKUPS

    clock = shared.Clock("2026-10-12T04:10:00+00:00")
    now = shared.offsite_scenario(
        tmp_path, error=ops.OffsiteError,
        send=lambda archive, keep, env, client: ops.send_offsite(archive, b2.configured(SITE, env, client=client),
                                                                 BACKUPS, keep=keep, clock=clock),
        check=lambda env, client: ops.check_offsite(b2.configured(SITE, env, client=client), BACKUPS,
                                                    how_to_set_up=b2.how_to_set_up(SITE)))
    assert json.loads(json.dumps(now)) == shared.read("offsite.json")
    assert BACKUPS.keep_offsite == 60          # how many stay off site when a backup is made by the command


# ---- /api/ask over a scripted pipeline (MIGRATION 1.8; wts-core docs/adr/0009, "Parity") ----------------------------

REQUEST = __import__("types").SimpleNamespace(client=__import__("types").SimpleNamespace(host=shared.ADDRESS),
                                              headers={}, cookies={})


def site_settings(folder: Path, limits: dict | None = None, pages: bool = False):
    """The site's real settings, with its data in a folder of the scenario's and the scenario's limits."""
    from dataclasses import replace

    s = load_settings(**{"embedding.backend": "hashing", "embedding.dim": 64})
    raw = {**s.raw, "usage": {**s.raw["usage"], **(limits or {})}}
    if pages:
        raw["paths"] = {**raw.get("paths", {}), "web_dist": str(shared.web_pages(folder / "dist"))}
    folder.mkdir(parents=True, exist_ok=True)
    return replace(s, raw=raw, data_dir=folder)


def new_state(settings, clock):
    """An empty state database with the day's visitor secret fixed, as the recorder's had."""
    from councils.state import open_state

    db = open_state(settings, clock)
    db.set(f"visitor_salt:{clock.now():%Y-%m-%d}", shared.SALT)
    return db


def numbered_ids(monkeypatch) -> None:
    ids = (f"briefing{n:03d}" for n in range(1, 100))
    monkeypatch.setattr("councils.api.app.new_briefing_id", lambda chance: next(ids))


def rows_written(db) -> dict:
    """What the site has written, under the names of the tables it kept before the shared package and with their
    columns, so that it can be compared row for row with what the recorder read from them."""
    with db.connect() as con:
        spending = [list(r) for r in con.execute(
            "SELECT at, kind, model, visitor, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, "
            "cost_usd FROM wts_spending ORDER BY id")]
        return {
            "spending": spending,
            "cache": [list(r) for r in con.execute("SELECT key, created_at, events FROM wts_answer_cache ORDER BY key")],
            "briefings": [list(r) for r in con.execute(
                "SELECT id, created_at, question, options, events, withdrawn_at, withdrawn_reason FROM wts_briefings "
                "ORDER BY id")],
        }


def as_the_questions_table(spending: list[list]) -> list[list]:
    """Each visitor's briefings for the day as the site's own ``questions`` table held them: a row for each visitor
    with any, counting their rows of kind "answer" (AS-BUILT, usage: "Where Councils Stand keeps that count in its
    questions table today; the package ... counts the imported usage rows of kind answer")."""
    counts: dict[tuple[str, str], int] = {}
    for at, kind, _, visitor, *_ in spending:
        if kind == "answer" and visitor:
            counts[(at[:10], visitor)] = counts.get((at[:10], visitor), 0) + 1
    return [[day, visitor, n] for (day, visitor), n in counts.items()]


@pytest.fixture
def asked(tmp_path, monkeypatch):
    """Builds the site's real app over a scripted pipeline, as the recorder did on the old code."""
    from fastapi.testclient import TestClient

    from councils.api import app as web

    made = [0]

    def build(limits: dict, has_model: bool) -> shared.Side:
        made[0] += 1
        clock = shared.Clock()
        numbered_ids(monkeypatch)
        monkeypatch.setattr(web, "parse_offline", shared.offline_reader)
        s = site_settings(tmp_path / f"ask-{made[0]}", limits)
        db = new_state(s, clock)
        pipeline = shared.ScriptedPipeline(clock, s.answer["model"], has_model=has_model)
        app = web.create_app(s, pipeline=pipeline, state=db, clock=clock)
        spending = app.state.councils.parts.spending

        def stream(question: str, **body):
            route = next(r.endpoint for r in app.routes if getattr(r, "path", "") == "/api/ask")
            with monkeypatch.context() as patch:
                patch.setattr(web, "StreamingResponse", lambda content, **kwargs: content)
                return route(web.AskBody(question=question, **body), REQUEST)

        def rows() -> dict:
            written = rows_written(db)
            return {**written, "questions": as_the_questions_table(written["spending"])}

        side = shared.Side(app, TestClient(app), pipeline, clock, rows=rows, stream=stream,
                           briefings_today=lambda visitor: spending.briefings_today(visitor=visitor))
        side.db = db
        return side

    return build


def test_every_case_of_the_briefing_flow_sends_the_same_text_and_writes_the_same_rows(asked):
    """The cases of wts-core's docs/adr/0009: a fresh question, the same again, a follow-up, sources only, each
    limit and cap reached, a place too many, the second check of the caps, the pipeline raising, the model
    declining, no records, no API key, the reader leaving. Byte for byte and row for row."""
    golden = {case["name"]: case for case in shared.read("asks.json")}
    now = {case["name"]: case for case in stored(shared.play_asks(asked), Path("/nowhere"))}
    assert list(now) == list(golden)

    # AS-BUILT, briefing, "At adoption": "Where Councils Stand with answer_cache_hours = 0 stored a cache row that
    # could never be read; the desk stores none. The bytes are the same."
    name = "with no hours to keep an answer, every question is written afresh"
    assert len(golden[name]["rows"]["cache"]) == 1 and now[name]["rows"]["cache"] == []
    golden[name]["rows"]["cache"] = []
    for name, was in golden.items():
        got = now[name]
        assert got["sent"] == was["sent"], name                       # every byte of every answer
        assert got["calls"] == was["calls"], name                     # the model was asked as often, and no more
        assert got["rows"] == was["rows"], name                       # spending, the cache, saved briefings, counts
        assert got["briefings_today"] == was["briefings_today"], name


# ---- the per-minute limit, a visitor's code, cost and the cache's key (MIGRATION 1.3: no difference) ---------------


@pytest.fixture
def parts_of(tmp_path):
    """The parts the site's briefing desk is made of (the limiter, the spending record, the caps, the cache), as the
    site itself builds them, on the scenario's clock and limits."""
    from councils.api.app import build

    def make(clock: shared.Clock, limits: dict | None = None, name: str = "parts"):
        s = site_settings(tmp_path / name, limits)
        return build(s, new_state(s, clock), clock=clock)

    return make


def test_the_per_minute_limit_lets_in_and_refuses_as_before(parts_of):
    golden = shared.read("limits.json")["limiter"]
    clock = shared.Clock()
    limiter = parts_of(clock).parts.limiter
    assert limiter.per_minute == golden["per_minute"] == 20
    allowed, at = [], 0.0
    for t, who in golden["script"]:
        clock.advance(t - at)
        at = t
        allowed.append(limiter.allow(who))
    assert allowed == golden["allowed"]


def test_a_visitors_code_is_made_as_before_and_yesterdays_secret_is_deleted(parts_of):
    from wts_core.usage import network_of, visitor_code

    golden = shared.read("limits.json")["visitors"]
    clock = shared.Clock()
    db = parts_of(clock).db
    assert {repr(a): visitor_code(db, a, clock=clock) for a in shared.ADDRESSES} == golden["codes"]
    assert {repr(a): network_of(a) for a in shared.ADDRESSES} == golden["networks"]
    assert golden["codes"][repr(shared.ADDRESS)] == shared.visitor_of(shared.ADDRESS)
    clock.set("2026-11-14T00:00:01+00:00")
    tomorrow = visitor_code(db, shared.ADDRESS, clock=clock)
    with db.connect() as con:
        kept = [r["key"] for r in con.execute("SELECT key FROM wts_kv WHERE key LIKE 'visitor_salt:%' ORDER BY key")]
    assert {"code_differs": tomorrow != golden["codes"][repr(shared.ADDRESS)], "secrets_kept": kept} == \
        golden["the_next_day"]


def test_cost_and_stored_token_counts_are_the_same_for_every_usage_and_model(parts_of):
    from wts_core.ports import Usage
    from wts_core.settings import SettingsError
    from wts_core.usage import PriceTable

    golden = shared.read("limits.json")
    prices = parts_of(shared.Clock()).parts.prices
    now = [{"usage": n, "model": m, "cost_usd": prices.cost(Usage.from_mapping(u), m) if u else 0.0}
           for n, u in enumerate(shared.USAGES) for m in shared.MODELS]
    assert now == golden["cost"] and len(now) == 84
    assert [Usage.from_mapping(u).as_stored() for u in shared.USAGES] == golden["token_counts"]
    # AS-BUILT, usage: "The four prices are required in [usage], with no fallback in code." The site's own code
    # fell back to $2 a million tokens in and $10 out where a price was missing; the real settings file has all
    # four, and a file without them now stops the site, naming them.
    assert golden["cost_with_no_prices_set"] == 12.4
    with pytest.raises(SettingsError, match="price_input_per_mtok, price_output_per_mtok, price_cache_read_per_mtok, "
                                            "cache_write_multiplier"):
        PriceTable.from_settings({})


def test_the_answer_caches_key_is_the_same_for_every_question_and_choice():
    """So nothing cached is lost at the move: a key the old code made is the key the new code looks for."""
    from councils.api.app import AskBody, answer_key
    from councils.config import INSTRUCTIONS_VERSION

    golden = shared.read("limits.json")["cache_keys"]
    assert golden["instructions_version"] == INSTRUCTIONS_VERSION
    now = [{"body": body, "stamp": stamp, "key": answer_key(AskBody(**body), stamp, golden["model"])}
           for body in shared.KEY_BODIES for stamp in shared.KEY_STAMPS]
    assert now == golden["keys"]
    assert all(len(k["key"]) == 32 for k in now) and len({k["key"] for k in now}) == 16
    # the first two questions differ only in case and spacing, and share a key
    assert now[0]["key"] == now[2]["key"] and now[1]["key"] == now[3]["key"]


def test_the_answer_caches_key_changes_with_the_model_the_instructions_and_the_record(monkeypatch):
    """wts-core's docs/adr/0009, as amended: the site makes the key, so these three are the site's to keep in it.
    Change any one and an answer written before is not served again."""
    from councils.api import app as web

    body = web.AskBody(question="What have councils decided about bin collections?")
    key = web.answer_key(body, 1731500000.25, "claude-sonnet-5-5")
    assert web.answer_key(body, 1731500000.25, "claude-sonnet-5-5") == key
    assert web.answer_key(body, 1731500000.25, "claude-opus-5-5") != key          # another model
    assert web.answer_key(body, 1731586400.0, "claude-sonnet-5-5") != key         # the record has changed
    monkeypatch.setattr(web, "INSTRUCTIONS_VERSION", "3")
    assert web.answer_key(body, 1731500000.25, "claude-sonnet-5-5") != key        # new instructions


# ---- the daily limit, the spending caps, the briefings in progress, the answer cache (MIGRATION 1.3) ---------------


def test_the_limit_and_the_caps_decide_the_same_over_scripted_spending(parts_of):
    golden = shared.read("caps.json")
    clock = shared.Clock(golden["start"])
    site = parts_of(clock, golden["limits"])
    spending, caps = site.parts.spending, site.parts.caps
    steps = []
    for step in shared.CAPS_SCRIPT:
        what = step[0]
        if what == "spend":
            _, kind, model, n, visitor = step
            gives = spending.add(kind, model, shared.USAGES[n] if n is not None else None, visitor=visitor)
        elif what in ("check", "paused"):
            refusal = caps.refusal(visitor=step[1], pending_usd=step[2]) if what == "check" else \
                caps.site_paused(step[1])
            gives = refusal.message if refusal else None
        elif what == "count":
            gives = spending.briefings_today(visitor=step[1])
        elif what == "spent":
            gives = [spending.spent_since(f"{clock.now():%Y-%m-%d}"), spending.spent_since(f"{clock.now():%Y-%m}")]
        else:
            clock.set(step[1])
            gives = None
        steps.append({"step": step, "gives": gives})
    assert steps == golden["steps"]


def test_briefings_in_progress_are_counted_and_refused_as_before():
    from wts_core.usage import BriefingsInProgress, busy_refusal

    from councils.api.app import MESSAGES

    golden = shared.read("caps.json")["in_progress"]
    places = BriefingsInProgress(shared.IN_PROGRESS["per_key"], shared.IN_PROGRESS["total"],
                                 shared.IN_PROGRESS["estimate_usd"])
    now = []
    for what, arg in shared.IN_PROGRESS_SCRIPT:
        if what == "start":
            busy = places.start(arg)
            gives = busy_refusal(busy, MESSAGES).message if busy else None
        else:
            gives = places.finish(arg) if what == "finish" else places.pending_usd(arg)
        now.append({"step": [what, arg], "gives": gives})
    assert now == golden


def test_a_cached_answer_is_given_and_dropped_as_before(parts_of):
    import json

    golden = shared.read("caps.json")["cache"]
    clock = shared.Clock()
    site = parts_of(clock)
    cache, now = site.parts.cache, []
    for step in shared.CACHE_SCRIPT:
        if step[0] == "put":
            gives = cache.put(step[1], shared.CACHE_EVENTS, step[2])
        elif step[0] == "get":
            gives = cache.get(step[1], step[2])
        elif step[0] == "advance":
            gives = clock.advance(step[1])
        else:
            with site.db.connect() as con:
                gives = [r["key"] for r in con.execute("SELECT key FROM wts_answer_cache ORDER BY key")]
        now.append({"step": step, "gives": gives})
    now = json.loads(json.dumps(now, default=str))
    # AS-BUILT, usage, "At adoption": "Where Councils Stand's cache gave an answer up a second sooner at the end
    # of its life": an answer exactly as old as it may be kept (an hour to the second, with an hour to keep it; 168
    # hours to the second, with a week) is still given, where the old code had just stopped giving it
    at_the_last_second = [n for n, (was, got) in enumerate(zip(golden, now, strict=True)) if was != got]
    assert [golden[n]["step"] for n in at_the_last_second] == [["get", "k1", 1], ["get", "k1", 168]]
    for n in at_the_last_second:
        assert golden[n]["gives"] is None and now[n]["gives"] == golden[2]["gives"]
        now[n]["gives"] = None
    assert now == golden


# ---- the made-up record: reports and statements, the owner's commands, the pages, the real pipeline ---------------


def a_site(folder: Path, clock: shared.Clock, limits: dict | None = None, state=None, model=None):
    """The site on the made-up record: its settings, the model's stand-in and the app, on the scenario's clock."""
    from wts_core.adapters.anthropic import BASE_URL, AnthropicClient
    from wts_core.adapters.hashing import HashingEmbedder

    from councils import store
    from councils.api.app import create_app
    from councils.engine import Engine
    from councils.index.build import Indexer, embed_pending
    from councils.rag.pipeline import Pipeline

    s = site_settings(folder, limits, pages=True)
    if not (s.parquet_dir / "meetings").exists():
        shared.store_record(lambda table, gss, rows: store.parquet.write(s.parquet_dir, table, gss, rows))
        index = Indexer(s)
        index.index_all()
        embed_pending(s, index.index, index.state, HashingEmbedder(64))
    fake = model or shared.FakeClient()
    pipeline = Pipeline(s, Engine(s, HashingEmbedder(64), shared.TODAY), today=shared.TODAY,
                        model=AnthropicClient(None, base_url=BASE_URL, client=fake))
    app = create_app(s, pipeline=pipeline, state=state or new_state(s, clock), clock=clock)
    return s, fake, app


def seed_briefings(app, clock: shared.Clock) -> None:
    """Three saved briefings, as the recorder's: one shown, one withdrawn, one saved with its follow-up questions."""
    archive = app.state.councils.parts.archive
    answer = shared.an_answer()
    events = [{"type": "plan", "plan": {"question": "Bins?"}}, {"type": "text", "text": answer["markdown"]},
              {"type": "final", "answer": answer, "briefing_id": "abc123"}]
    archive.save("What has Barnsley decided about public toilets?", {"mode": "summary", "plan": None,
                                                                    "sources_only": False}, events, id="abc123")
    clock.advance(60)
    archive.save("Which council closed its toilets?", {"mode": "summary"}, [{"type": "final", "answer": None}],
                 id="gone456")
    archive.save("And libraries?", {"mode": "summary", "plan": None, "history": shared.EARLIER,
                                    "sources_only": False}, [{"type": "final", "answer": None}], id="old789")
    clock.advance(60)
    archive.withdraw("gone456", "It misattributed a decision to the wrong council.")


def kept(replies) -> dict:
    """What is kept, as the owner sees it, under the names the site's own tables had (as the recorder wrote it)."""
    def shown_on(s: dict) -> str | None:
        return max(s["published_at"] or "", s["updated_at"] or "")[:10] if s["published_at"] else None

    statements = [{"id": s["id"], "page": s["item"], "council": s["about"], "name": s["name"], "role": s["role"],
                   "text": s["text"], "link": s["link"], "email": s["email"], "status": s["status"],
                   "shown_on": shown_on(s), "reason": s["reason"],
                   "log": [[e["action"], e["note"]] for e in replies.log(s["id"])]}
                  for s in sorted(replies.statements(), key=lambda s: s["id"])]
    reports = [{"id": r["id"], "kind": r["kind"], "page": r["page"], "message": r["message"],
                "contact": r["contact"], "closed": r["closed_at"] is not None}
               for r in sorted(replies.reports(open_only=False), key=lambda r: r["id"])]
    return {"statements": statements, "reports": reports}


def as_the_old_tables_kept_it(now: dict) -> dict:
    """AS-BUILT, replies, "At adoption": "No link is stored as NULL (Where Countries Stand and Where Councils Stand
    had "")". The same is true of a statement's address once it is deleted, and of a report's page and contact:
    what was an empty text in the site's own tables is nothing at all in the package's. Each is shown, where it is
    shown, as it was."""
    for s in now["statements"]:
        assert s["link"] != "" and s["email"] != ""
        s["link"], s["email"] = s["link"] or "", s["email"] or ""
    for r in now["reports"]:
        assert r["page"] != "" and r["contact"] != ""
        r["page"], r["contact"] = r["page"] or "", r["contact"] or ""
    return now


def test_every_answer_to_a_report_or_a_statement_is_as_before(tmp_path):
    from fastapi.testclient import TestClient

    golden = shared.read("api.json")
    clock = shared.Clock()
    s, _, app = a_site(tmp_path / "api", clock)
    seed_briefings(app, clock)
    client = TestClient(app)
    answers = {}
    for step in shared.API_STEPS:
        clock.advance(61)
        answer = shared.send(client, step)
        answers[answer["case"]] = answer
    before = {answer["case"]: answer for answer in golden["answers"]}
    assert list(answers) == list(before)

    def said(answer: dict) -> tuple:
        return answer["status"], answer["json"]["detail"]

    # 1. AS-BUILT, replies, "At adoption": "Order of checks when two things are wrong: the package's order is ...
    #    words, name, role, link, email, address, item shown. ... the other two checked the address first (kept if
    #    the site passes an Item). A sender with two faults may be told about a different one first." Here the
    #    address is still read first (the route passes the item it found); the words now come before the name and
    #    the role. Each fault alone gets the same words as before.
    told_first = {
        "two faults: a name of spaces and no words": ("Give your name, as it should be shown.",
                                                      "Write the statement."),
        "two faults: a role of spaces and 151 words": (
            "Give your role, such as Councillor, Barnsley Metropolitan Borough Council.",
            "A statement can be up to 150 words; this one is 151."),
    }
    for case, (was, now) in told_first.items():
        assert said(before.pop(case)) == (422, was) and said(answers.pop(case)) == (422, now)
    # 2. A report of nothing but spaces was kept (the form's own check counts characters, and seven spaces are
    #    seven); the package reads a report with the spaces around it taken off, finds nothing, and refuses it, in
    #    words that are new (AS-BUILT, replies: "Wording the sites have no words for today ... the report
    #    refusals"). One report fewer is kept, so each later one's number is one lower.
    case = "a message of spaces"
    assert (before[case]["status"], before.pop(case)["json"]) == (200, {"ok": True, "id": 6})
    assert said(answers.pop(case)) == (422, "Say what is wrong, in a few words.")
    for case, number in (("a message at its longest", 7), ("a contact at its longest", 8)):
        assert before.pop(case)["json"] == {"ok": True, "id": number}
        assert answers.pop(case)["json"] == {"ok": True, "id": number - 1}
    # Every other answer, word for word: each statement and report taken, each refusal in the site's own words,
    # what the form's own limits turn away, and nothing shown until it is published.
    assert answers == before and len(answers) == 63

    now, then = as_the_old_tables_kept_it(kept(app.state.councils.replies)), golden["kept"]
    # 2, again: the report of spaces is not kept, and the two after it are numbered one lower
    assert [r["message"] for r in then["reports"]][5] == "       "
    del then["reports"][5]
    for r in then["reports"][5:]:
        r["id"] -= 1
    # 3. A report's contact is kept without the spaces typed around it (the package's; nobody is shown it but the
    #    owner, who replies to it)
    assert then["reports"][2]["contact"] == "  c@d.org  " and now["reports"][2]["contact"] == "c@d.org"
    then["reports"][2]["contact"] = "c@d.org"
    assert now["reports"] == then["reports"]
    # 4. AS-BUILT, replies, "At adoption": "Text cleaning now closes runs of blank lines on Where Countries Stand
    #    and Where Councils Stand": line endings are made plain and three or more in a row become one blank line.
    #    The words themselves are never changed.
    typed = "Line one <b>bold</b>\r\nline two\r\n\r\n\r\n\r\npara two & more"
    assert then["statements"][5]["text"] == typed
    assert now["statements"][5]["text"] == "Line one <b>bold</b>\nline two\n\npara two & more"
    then["statements"][5]["text"] = now["statements"][5]["text"]
    assert now["statements"] == then["statements"]


@pytest.fixture
def owner(tmp_path, monkeypatch):
    """A site with five statements and four reports sent, the clock in hand, and the owner's command line."""
    from fastapi.testclient import TestClient

    tmp, clock = tmp_path.resolve(), shared.Clock()
    monkeypatch.setattr("councils.cli.CLOCK", clock)
    s, _, app = a_site(tmp / "owner", clock)
    environment(monkeypatch, s.data_dir)
    seed_briefings(app, clock)
    client = TestClient(app)
    for step in shared.OWNER_SENT:
        clock.advance(61)
        assert shared.send(client, step)["status"] == 200, step
    for name, text in shared.OWNER_FILES.items():
        (tmp / name).write_text(text)
    return tmp, clock, app, client


# What can't be done is now said in the shared package's words, after "error: " and on standard error, where the
# site printed one fixed line on standard output. AS-BUILT, cli, "At adoption": "Where each site printed one fixed
# line when something could not be done ("no waiting statement with that number"), the owner now sees the exact
# reason. The exit code is 1 as before."
NO_WAITING, NOT_SHOWN = "no waiting statement with that number\n", "no waiting or published statement with that number\n"
NOTHING = "nothing changed: no waiting or published statement with that number, or no change\n"
NO_REPORT = "no open report with that number\n"
CHECKED_WORDS = f"publish-statement 1 --checked {shared.CHECKED}"
NOT_DONE_NOW = {
    "publish-statement 1 --checked    ": ("stderr", "error: Say how you confirmed who sent it (--checked), for the "
                                          "log.\n", "say how you confirmed who sent it (checked), for the log"),
    CHECKED_WORDS: ("stdout", NO_WAITING, "statement 1 is published, not pending"),       # its second run
    f"publish-statement 9 --checked {shared.CHECKED}": ("stdout", NO_WAITING, "no statement 9"),
    "update-statement 1": ("stdout", NOTHING, "nothing to change: give new words, a name, a role, a link or whom it "
                                              "speaks for"),
    "update-statement 9 --role Mayor": ("stdout", NOTHING, "no statement 9"),
    "decline-statement 3 --reason again": ("stdout", NO_WAITING, "statement 3 is declined, not pending"),
    "decline-statement 1 --reason it is published": ("stdout", NO_WAITING, "statement 1 is published, not pending"),
    "decline-statement 999 --reason x": ("stdout", NO_WAITING, "no statement 999"),
    "withdraw-statement 4": ("stdout", NOT_SHOWN, "statement 4 is withdrawn, not pending or published"),  # its second
    "withdraw-statement 9": ("stdout", NOT_SHOWN, "no statement 9"),
    "update-statement 1 --role Mayor": ("stdout", NOTHING, "statement 1 is withdrawn, not pending or published"),
    "close-report 1": ("stdout", NO_REPORT, "no open report 1"),                           # its second run
    "close-report 999": ("stdout", NO_REPORT, "no open report 999"),
}


def listed(output: str) -> list[str]:
    """A listing cut into its reports or statements: each begins "#<number>" at the start of a line."""
    import re

    return [block for block in re.split(r"(?m)^(?=#\d)", output) if block]


def test_the_owners_commands_print_what_they_did(owner):
    """Under the names the commands had before the shared package, which still work."""
    tmp, clock, app, client = owner
    golden = shared.read("owner.json")
    seen: dict[str, int] = {}
    for was in golden["runs"]:
        typed = " ".join(was["args"])
        seen[typed] = seen.get(typed, 0) + 1
        clock.advance(61)
        now = {"args": was["args"], **command([a.replace("<tmp>", str(tmp)) for a in was["args"]], tmp)}
        if typed in NOT_DONE_NOW and not (typed in (CHECKED_WORDS, "withdraw-statement 4", "close-report 1")
                                          and seen[typed] == 1):
            where, line, reason = NOT_DONE_NOW[typed]
            assert (was["exit_code"], was[where]) == (1, line), typed
            assert now == {"args": was["args"], "exit_code": 1, "stdout": "", "stderr": f"error: {reason}\n",
                           "error": None}, typed
        elif typed.startswith("list-reports"):
            # MIGRATION 1.9: "Takedown requests listed first: gains (O)". They were listed newest first, with a
            # request to take a person's name down among the rest; an open one now comes before everything else.
            # Each report's own lines are the same.
            assert now["exit_code"] == was["exit_code"] == 0
            first = [b for b in listed(was["stdout"]) if "  takedown  " in b and "(closed)" not in b]
            assert listed(now["stdout"]) == first + [b for b in listed(was["stdout"]) if b not in first], typed
            assert first and listed(was["stdout"])[0] not in first
        elif "no such council anywhere" in typed:
            # New here: a council the owner's words match none of (or more than one of) was an error nobody caught,
            # shown as a traceback. It is now said in a line, and nothing is published either way.
            assert (was["exit_code"], was["error"]) == (1, "KeyError: \"'no such council anywhere' matches 0 "
                                                           "councils\"")
            assert (now["exit_code"], now["stdout"], now["error"]) == (1, "", None)
            assert now["stderr"] == ("error: no one council is called no such council anywhere: give its GSS code, "
                                     "or more of its name\n")
        else:       # every other command: the same lines, in the same place, with the same exit status
            assert now == was, typed
    clock.advance(61)
    now_kept, then = as_the_old_tables_kept_it(kept(app.state.councils.replies)), golden["kept"]
    # The log's note of an update names what was changed. The site's own code named the date among them when the
    # statement was published ("shown_on, text"), since it wrote the new date into the same row; the package keeps
    # the time of the update in a column of its own and names the author's changes only ("text"). The date a
    # statement is shown with is the same (compared above, and in what the pages are given below).
    for statement in then["statements"]:
        for entry in statement["log"]:
            if entry[0] == "updated":
                entry[1] = ", ".join(part for part in entry[1].split(", ") if part != "shown_on")
    assert now_kept == then
    assert [shared.send(client, {"get": path}) for path in shared.OWNER_READS] == golden["reads"]


def test_the_owners_commands_under_their_new_names_do_the_same(owner):
    """MIGRATION 1.9: the commands take the family's shape (`councils statements publish 3`); the old names keep
    working. Each pair prints the same line."""
    tmp, clock, app, _ = owner
    said = [command(args, tmp) for args in (
        ["statements", "publish", "1", "--checked", shared.CHECKED],
        ["statements", "publish", "2", "--checked", shared.CHECKED, "--council", "barnsley"],
        ["statements", "update", "1", "--text", "New words.", "--role", "Leader"],
        ["statements", "decline", "3", "--reason", "It appeals for votes."],
        ["statements", "withdraw", "4"],
        ["reports", "close", "1"],
    )]
    assert [(run["exit_code"], run["stdout"], run["stderr"]) for run in said] == [
        (0, f"{word}\n", "") for word in ("published", "published", "updated", "declined", "withdrawn", "closed")]
    assert command(["statements", "list", "--all"], tmp)["stdout"] == command(["list-statements", "--all"], tmp)[
        "stdout"]
    assert listed(command(["reports", "list"], tmp)["stdout"]) == listed(command(["list-reports"], tmp)["stdout"])
    replies = app.state.councils.replies
    assert [s["status"] for s in sorted(replies.statements(), key=lambda s: s["id"])] == [
        "published", "published", "declined", "withdrawn", "pending"]
    assert replies.statement(2)["about"] == shared.BARNSLEY and replies.statement(4)["reason"] == "Withdrawn by its author."


def test_the_pages_and_the_other_endpoints_give_what_they_gave(tmp_path):
    """With nothing hidden and two statements shown: the council's and the vote's pages as they are sent to readers
    without scripts, the directory, the sitemap, saved briefings, the status page's figures."""
    from fastapi.testclient import TestClient

    golden = {answer["case"]: answer for answer in shared.read("pages.json")}
    clock = shared.Clock()
    s, _, app = a_site(tmp_path / "pages", clock)
    seed_briefings(app, clock)
    client = TestClient(app)
    for step in (shared.OWNER_SENT[0], shared.OWNER_SENT[3]):
        clock.advance(61)
        assert shared.send(client, step)["status"] == 200, step
    clock.set("2026-11-14T09:00:00+00:00")
    replies = app.state.councils.replies
    replies.publish(1, checked=shared.CHECKED)
    replies.publish(2, checked=shared.CHECKED)
    now = {}
    for path in shared.PAGES_READ:
        clock.advance(61)
        now[path] = shared.page_read(client, path)
    for limits in ({}, {"daily_spend_cap_usd": 0.0}, {"monthly_spend_cap_usd": 0.0}):
        # the limits are read when the site starts: the same data folder, started again with the scenario's
        _, _, again = a_site(tmp_path / "pages", clock, limits, state=app.state.councils.db)
        now[f"/api/status {limits}"] = {**shared.send(TestClient(again), {"get": "/api/status"}),
                                        "case": f"/api/status {limits}"}
    assert list(now) == list(golden)
    for case, was in golden.items():
        if now[case] != was:
            print("PAGE", case, "\n   was", str(was)[:3000], "\n   now", str(now[case])[:3000])
    assert now == golden


def test_the_real_pipeline_sends_and_writes_what_it_did(tmp_path, monkeypatch):
    """The same route over the site's real pipeline on the made-up record, with the model's SDK stood in for: the
    search, the ranking, the sources' cards, the checks and what is saved and cached."""
    import json

    from fastapi.testclient import TestClient

    golden = shared.read("real.json")
    clock = shared.Clock()
    numbered_ids(monkeypatch)
    s, fake, app = a_site(tmp_path / "real", clock)
    db = app.state.councils.db
    _, _, capped = a_site(tmp_path / "real", clock, {"daily_spend_cap_usd": 0.0}, state=db, model=fake)
    now = []
    for ask in shared.REAL_ASKS:
        fake.refuse = bool(ask.get("refuse"))
        clock.advance(61)
        r = TestClient(capped if "cap" in ask else app).post("/api/ask", json=ask["json"])
        now.append({"case": ask["case"], "status": r.status_code,
                    "events": shared.without_scores(shared.events_of(r.text)), "model_calls": len(fake.calls)})
    written = rows_written(db)
    now.append({"case": "what was written", "spending": written["spending"],
                "briefings": [[b[0], b[1], b[2], json.loads(b[3]), shared.without_scores(json.loads(b[4]))]
                              for b in written["briefings"]],
                "cached": [shared.without_scores(json.loads(c[2])) for c in sorted(written["cache"],
                                                                                 key=lambda c: c[1])]})
    now = json.loads(json.dumps(now, default=str))

    # AS-BUILT, checks: "to_dict() writes today's keys and then rules". The answer the real pipeline's checks give
    # carries the number of the checking rules that wrote it, in every copy: sent, saved and cached. Nothing else
    # of any event is different. (The "no records" answer is the pipeline's own words, with no checks to stamp it.)
    def unstamped(events: list) -> list:
        return [{**e, "answer": as_before(e["answer"])} if e.get("type") == "final" and e.get("answer")
                and not e["answer"].get("no_records") else e for e in events]

    for answer in now[:-1]:
        answer["events"] = unstamped(answer["events"])
    now[-1]["briefings"] = [[*b[:4], unstamped(b[4])] for b in now[-1]["briefings"]]
    now[-1]["cached"] = [unstamped(events) for events in now[-1]["cached"]]
    for got, was in zip(now, golden, strict=True):
        assert got == was, was["case"]


# ---- what the model is sent, and an index the old code built (MIGRATION 1.5 and 1.6) -------------------------------


def test_the_model_is_sent_what_it_was_sent(tmp_path):
    """Every request the real pipeline makes of the model's SDK, argument for argument, through the shared
    package's model client: the instructions (as one cacheable block), the sources as documents, the question as
    this site words it, the model, the effort, the fallback; and each question the model is asked to read."""
    from fastapi.testclient import TestClient

    clock = shared.Clock()
    s, fake, app = a_site(tmp_path / "requests", clock)
    client = TestClient(app)
    for ask in shared.MODEL_ASKS:
        fake.parsed = shared.PARSED if ask.get("parsed") else None
        clock.advance(61)
        assert client.post("/api/ask", json=ask["json"]).status_code == 200, ask
    golden, now = shared.read("requests.json"), shared.requests_made(fake)
    assert len(now["briefings"]) == len(golden["briefings"]) == 5
    for got, was in zip(now["briefings"], golden["briefings"], strict=True):
        assert got == was
    assert now["questions_read"] == golden["questions_read"] and len(now["questions_read"]) == 2


def old_index(tmp: Path):
    """The made-up record with the search index the old code built from it, as the old code left it."""
    import shutil

    from councils import store

    s = site_settings(tmp)
    shared.store_record(lambda table, gss, rows: store.parquet.write(s.parquet_dir, table, gss, rows))
    shutil.copytree(Path(__file__).parent / "fixtures" / "old-index", s.index_dir)
    return s


def test_an_index_the_old_code_built_opens_and_searches_the_same(tmp_path):
    """tests/fixtures/old-index: an index made before the shared package, with no note of what it was built with.
    It opens as it is, takes the note the first time it is opened with its embedder, and every search by words and
    by meaning, and the engine's choice of evidence, gives what the old code gave on it."""
    import json

    from wts_core.adapters.hashing import HashingEmbedder
    from wts_core.adapters.lancedb import stored_meta

    from councils.engine import Engine, Filters
    from councils.index.lance import open_index

    golden = shared.read("index.json")
    s = old_index(tmp_path / "old")
    assert golden["files_beside_the_tables"] == ["state.json"] and stored_meta(s.index_dir) is None
    index, embedder = open_index(s), HashingEmbedder(64)
    assert index.stats() == golden["stats"] and index.has_word_index() is golden["has_word_index"]
    assert stored_meta(s.index_dir) is None          # opened as it stands, nothing is written
    index = open_index(s, embedder)                  # AS-BUILT, adapters: "The first opening ... writes wts_index.json"
    assert stored_meta(s.index_dir).embedder_id == "hashing-64" and stored_meta(s.index_dir).dimension == 64
    assert shared.index_answers(index.search_words, index.search_meaning, embedder.embed_query) == golden["searches"]
    rows = index.rows_for_keys([f"{shared.BARNSLEY}:2025", f"{shared.GUILDFORD}:2025"])
    assert sorted(json.loads(json.dumps(rows, default=str)), key=lambda r: r["passage_id"]) == golden["rows"]
    engine = Engine(s, embedder, shared.TODAY)
    assert {
        "everything": shared.search_given(engine.search("bin collections", Filters(), limit=5)),
        "one party's councils": shared.search_given(engine.search("bin collections", Filters(control=["LD"]),
                                                                  limit=5)),
        "by region": shared.search_given(engine.search("waste strategy", Filters(), limit=5, group_by="region")),
    } == golden["engine"]


def test_an_index_the_old_code_built_is_updated_and_keeps_its_vectors(tmp_path):
    """The nightly update on an index the old code built: a council indexed again keeps the vectors of its
    unchanged passages (none is embedded twice), the indexes are merged, and the searches still give the same."""
    from wts_core.adapters.hashing import HashingEmbedder

    from councils.index.build import Indexer, update_index
    from councils.index.lance import open_index

    golden = shared.read("index.json")
    s = old_index(tmp_path / "old")
    embedder = HashingEmbedder(64)
    out = update_index(s, [shared.GUILDFORD], embedder)
    assert out == {"passages_embedded": 0, "still_to_embed": 0, "index": "merged"}
    index = open_index(s, embedder)
    assert index.stats() == golden["stats"] and not index.unmerged()
    assert shared.index_answers(index.search_words, index.search_meaning, embedder.embed_query) == golden["searches"]
    # and the whole index built again from the store, with no embedder loaded: its vectors are still kept
    indexer = Indexer(s)
    assert indexer.index_all() == 2 and all(v["embedded"] for v in indexer.state.data.values())
    assert open_index(s, embedder).stats() == golden["stats"]
    # the same on an index nobody has opened with its embedder yet (`councils index` straight after the move): the
    # embedder the settings name is loaded once, the index takes its note, and the vectors are kept
    fresh = old_index(tmp_path / "fresh")
    indexer = Indexer(fresh)
    assert indexer.index_all() == 2 and all(v["embedded"] for v in indexer.state.data.values())
    index = open_index(fresh, embedder)
    assert index.stats() == golden["stats"]
    assert shared.index_answers(index.search_words, index.search_meaning, embedder.embed_query) == golden["searches"]


# ---- ranking, and the balanced choice of evidence (MIGRATION 1.7: no difference) ---------------------------------


def test_candidates_are_ranked_and_the_evidence_chosen_as_before():
    """The blend of the two relevance scores, the recency factor and the round robin across groups are the shared
    package's now; the weights, the relevance floor, the grouping and the caps are this site's. Two hundred and
    forty made-up candidates rank the same, score for score, and every selection takes the same records."""
    import json
    from datetime import date

    from councils.rank.composite import Candidate, RankParams, rank
    from councils.rank.evidence import select_evidence

    settings = load_settings()

    def ranked(overrides: dict) -> list:
        params = RankParams.from_settings(settings.ranking, today=shared.RANKING_TODAY, **overrides)
        return rank([Candidate(record_id=c["record_id"], date=date.fromisoformat(c["date"]), bm25=c["bm25"],
                               cosine=c["cosine"], data=dict(c["data"])) for c in shared.candidates()], params)

    now = shared.ranked_and_chosen(ranked, lambda scored, k, **more: select_evidence(scored, k, **more))
    golden = shared.read("ranking.json")
    assert json.loads(json.dumps(now)) == golden
    assert [len(s["chosen"]) for s in golden["selections"]] == [24, 40, 12, 12, 12, 20, 5, 60]
