"""The record of each briefing, the structured log, and the commands that read them (`councils stats`,
`councils weekly-report`, `councils tidy`): docs/OPERATIONS.md, "How briefings went"."""

import json
import logging
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_api import events, rows, site_with
from test_pipeline import TODAY, FakeClient, as_model, settings  # noqa: F401 - the fixture
from typer.testing import CliRunner
from wts_core.adapters.hashing import HashingEmbedder
from wts_core.observe import LOGGER
from wts_core.testing import FixedClock

from councils import cli
from councils.api.app import create_app, start_logging
from councils.engine import Engine
from councils.rag.pipeline import Pipeline
from councils.state import forget_old_secret, open_state

ROOT = Path(__file__).resolve().parent.parent
BINS = "What have councils decided about bin collections?"
RECYCLING = "What have councils said about the recycling strategy?"
LOCAL = '[embedding]\nbackend = "hashing"\ndim = 64\n'      # the made-up record's embedder, for the commands


def record(site) -> list[dict]:
    with site.db.connect() as con:
        return [dict(r) for r in con.execute("SELECT * FROM wts_briefing_log ORDER BY rowid")]


@pytest.fixture
def asked(settings, monkeypatch):  # noqa: F811
    """The site after four questions (a briefing, the same again, a refusal, and a report of the first), with the
    structured log on: the site's parts, its settings and the first briefing's id. The owner's commands read the
    same data folder."""
    monkeypatch.setenv("COUNCILS_DATA_DIR", str(settings.data_dir))
    (settings.data_dir / "settings.local.toml").write_text(LOCAL)
    handler = start_logging(settings)
    try:
        c, _, site, cfg = site_with(settings)
        bid = events(c.post("/api/ask", json={"question": BINS}))[-1]["briefing_id"]
        c.post("/api/ask", json={"question": BINS})
        refusing, *_ = site_with(settings, FakeClient(refuse=True))
        refusing.post("/api/ask", json={"question": RECYCLING})
        c.post("/api/report", json={"kind": "error", "message": "The date in this briefing is wrong.",
                                    "page": f"https://wherecouncilsstand.com/b/{bid}"})
    finally:
        logging.getLogger(LOGGER).removeHandler(handler)
        handler.close()
    return site, cfg, bid


def test_each_briefing_leaves_one_record_and_none_holds_a_visitors_code(asked):
    site, cfg, bid = asked
    first, again, refused = record(site)
    assert [r["outcome"] for r in (first, again, refused)] == ["completed", "cached", "error"]
    assert first["question"] == again["question"] == BINS and refused["question"] == RECYCLING
    assert first["briefing_id"] == again["briefing_id"] == bid and refused["briefing_id"] is None
    assert refused["error_type"] == "ModelDeclined"
    assert (first["model"], first["parse_model"], first["instructions"]) == ("claude-sonnet-5-5",
                                                                             "claude-haiku-5-5", "2")
    assert (first["input_tokens"], first["output_tokens"], first["cost_usd"]) == (1000, 200, 0.004)
    assert (again["input_tokens"], again["cost_usd"]) == (0, 0.0)             # a replay costs nothing
    assert (first["citations_total"], first["unsupported"], first["loaded_words"]) == (1, 1, 1)
    assert json.loads(first["spread"]) == {"Councils controlled by Labour": 1,
                                           "Councils controlled by the Liberal Democrats": 1}
    # what the reader did next: the report of the briefing is marked on the record of the request that wrote it
    assert (first["reported"], again["reported"], first["corrected"]) == (1, 0, 0)
    # the settings each was written under, kept once
    (config,) = rows(site, "SELECT config_id, settings FROM wts_configs")
    assert {r["config_id"] for r in (first, again, refused)} == {config[0]}
    kept = json.loads(config[1])
    assert kept["model"] == "claude-sonnet-5-5" and kept["ranking"] == dict(cfg.ranking)
    assert set(kept) == {"answer", "embedding", "ranking", "instructions", "model", "parse_model",
                         "package_version", "site_version"}
    # no column for who asked, and the day's codes (kept with the spending, to count a visitor's briefings) are
    # in no row of the record
    codes = {v for (v,) in rows(site, "SELECT visitor FROM wts_spending WHERE visitor != ''")}
    assert codes and not any(code in json.dumps(r) for code in codes for r in record(site))
    assert not {"visitor", "address", "ip"} & set(first)


def test_the_structured_log_names_stages_and_never_the_question(asked):
    site, cfg, _ = asked
    files = sorted(cfg.logs_dir.glob("*"))
    assert [f.name for f in files] == ["briefings.jsonl"]
    lines = [json.loads(line) for line in files[0].read_text().splitlines()]
    ids = [r["id"] for r in record(site)]
    assert {line["briefing"] for line in lines} == set(ids)
    assert all(set(line) == {"at", "level", "site", "event", "briefing", "stage", "ms", "error_type"}
               and line["site"] == "councils" for line in lines)
    by_id = {i: [(e["event"], e["stage"]) for e in lines if e["briefing"] == i] for i in ids}
    assert by_id[ids[0]] == [("briefing.stage", s) for s in ("parsed", "searched", "ranked", "sources_sent",
                                                             "first_token", "written", "checked")] \
        + [("briefing.completed", None)]
    assert by_id[ids[1]][-1] == ("briefing.cached", None)
    assert lines[-1]["event"] == "briefing.error" and lines[-1]["error_type"] == "ModelDeclined"
    text = files[0].read_text().lower()
    assert "bin collections" not in text and "recycling" not in text and "testclient" not in text


def test_a_briefing_withdrawn_or_corrected_by_the_owner_is_marked_on_its_record(asked):
    site, _, bid = asked
    run = CliRunner().invoke
    (report,) = [r["id"] for r in site.replies.reports()]
    out = run(cli.app, ["reports", "close", str(report), "--public-note", "The date was wrong: it is put right."])
    assert out.exit_code == 0, out.output
    assert [r["corrected"] for r in record(site)] == [1, 0, 0]      # on the request that wrote that briefing


def test_stats_gives_the_figures_as_a_page_and_as_json(asked, monkeypatch):
    monkeypatch.setattr(cli, "CLOCK", FixedClock(datetime.now(UTC) + timedelta(minutes=1)))   # a minute later
    run = CliRunner().invoke
    page = run(cli.app, ["stats", "--since", "24h"])
    assert page.exit_code == 0, page.output
    assert page.output.startswith("# Where Councils Stand: how the briefings went")
    assert "No alert thresholds are set yet" in page.output
    found = json.loads(run(cli.app, ["stats", "--since", "24h", "--json"]).output)
    assert set(found) == {"stats", "tripped", "counts"} and found["tripped"] == []
    assert found["stats"]["period"]["questions"] == 3
    assert {k: v for k, v in found["stats"]["period"]["by_outcome"].items() if v} == {"completed": 1, "cached": 1,
                                                                                      "error": 1}
    # nothing is over a threshold while none is set: --check prints nothing and ends well
    check = run(cli.app, ["stats", "--check"])
    assert (check.exit_code, check.output) == (0, "")


def test_the_weekly_report_is_saved_proposes_thresholds_and_fails_once_one_is_crossed(asked, monkeypatch):
    _, cfg, _ = asked
    monkeypatch.setattr(cli, "CLOCK", FixedClock(datetime.now(UTC) + timedelta(days=7)))   # the week just gone
    run = CliRunner().invoke
    first = run(cli.app, ["weekly-report"])
    assert first.exit_code == 0, first.output
    page, data = (Path(line) for line in first.output.splitlines()[:2])
    assert page.parent == data.parent == cfg.reports_dir and page.suffix == ".md" and data.suffix == ".json"
    assert "No alert thresholds are set yet." in first.output and "error_rate" in first.output
    # the owner sets one, lower than the week's figure: the report is still saved, and the command fails, which
    # is what makes the timer's unit send the alert email
    (cfg.data_dir / "settings.local.toml").write_text(LOCAL + "[alerts]\nerror_rate = 0.01\n")
    second = run(cli.app, ["weekly-report"])
    assert second.exit_code == 1 and "error" in second.output.lower()
    assert page.exists() and data.exists()
    # a name the package does not know stops the report before anything is written, rather than being ignored
    (cfg.data_dir / "settings.local.toml").write_text(LOCAL + "[alerts]\nerorr_rate = 0.01\n")
    assert run(cli.app, ["weekly-report"]).exit_code == 1


def test_tidy_deletes_what_the_privacy_page_says_is_deleted(asked, monkeypatch):
    site, cfg, _ = asked
    run = CliRunner().invoke
    with site.db.connect() as con:      # as a database imported from the old code has it: yesterday's secret
        con.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        con.execute("INSERT INTO kv VALUES ('visitor_salt:2020-01-01', 'old'), (?, 'today')",
                    (f"visitor_salt:{datetime.now(UTC):%Y-%m-%d}",))
    old_copy = cfg.data_dir / "state.pre-wts-core.2020-01-01.db"
    old_copy.write_bytes(b"x")
    quiet = run(cli.app, ["tidy"])
    assert quiet.exit_code == 0, quiet.output
    assert "Deleted an earlier day's secret" in quiet.output
    assert rows(site, "SELECT key FROM kv") == [(f"visitor_salt:{datetime.now(UTC):%Y-%m-%d}",)]
    assert rows(site, "SELECT count(*) FROM wts_spending WHERE visitor != ''") != [(0,)]   # today's stay
    assert len(record(site)) == 3

    # fourteen months on: the day's visitors' codes are forgotten, the record is past its thirteen months, and
    # the copy of the database made before the one-off import is older than any backup
    later = FixedClock(datetime.now(UTC) + timedelta(days=430))
    monkeypatch.setattr(cli, "CLOCK", later)
    out = run(cli.app, ["tidy"])
    assert out.exit_code == 0, out.output
    assert rows(site, "SELECT count(*) FROM wts_spending WHERE visitor != ''") == [(0,)]
    assert rows(site, "SELECT count(*) FROM wts_spending") != [(0,)]          # the spending itself is kept
    assert record(site) == []
    assert rows(site, "SELECT key FROM kv") == [] and forget_old_secret(open_state(cfg), later) == []
    assert not old_copy.exists()


def test_every_command_the_timers_run_is_one_the_site_has():
    """deploy/*.service run `councils <command>` in the container: each must exist, with the options given."""
    run = CliRunner().invoke
    seen = set()
    for unit in sorted((ROOT / "deploy").glob("*.service")):
        for command in re.findall(r" app councils (.+)$", unit.read_text(), re.M):
            name, *rest = command.split()
            seen.add(name)
            help_text = run(cli.app, [name, "--help"])
            assert help_text.exit_code == 0, f"{unit.name}: no command `councils {name}`"
            for option in [word for word in rest if word.startswith("--")]:
                assert option in help_text.output, f"{unit.name}: `councils {name}` has no {option}"
    assert seen == {"update", "backup", "backup-check", "weekly-report", "tidy"}
    installed = (ROOT / "deploy" / "update.sh").read_text()
    for unit in sorted((ROOT / "deploy").glob("councils-*.*")):
        assert unit.name in installed, f"deploy/update.sh does not install {unit.name}"


def test_the_familys_check_gets_counts_and_ages_and_nothing_a_reader_wrote(settings, monkeypatch):  # noqa: F811
    """GET /api/check (wts-core docs/adr/0010): not there until the site has the family's token; then only for
    whoever presents it. A question asked with the token is written afresh, and kept apart from readers'."""
    c, _, site, _ = site_with(settings)
    assert c.get("/api/check").status_code == 404 and c.get("/api/check").json() == {"detail": "Not Found"}
    assert c.get("/api/check", headers={"Authorization": "Bearer anything"}).status_code == 404

    monkeypatch.setenv("COUNCILS_CHECK_TOKEN", "the-family-token")
    clock = FixedClock(datetime.now(UTC))
    fake = FakeClient()
    app = create_app(settings, pipeline=Pipeline(settings, Engine(settings, HashingEmbedder(64), TODAY),
                                                 model=as_model(fake), today=TODAY), clock=clock)
    c, site = TestClient(app), app.state.councils
    assert c.get("/api/check").status_code == 401
    assert c.get("/api/check", headers={"Authorization": "Bearer wrong"}).json() == {}
    with_token = {"Authorization": "Bearer the-family-token"}
    c.post("/api/ask", json={"question": BINS})
    c.post("/api/report", json={"kind": "error", "message": "The date in this briefing is wrong.", "page": "",
                                "contact": "reader@example.org"})
    # the check's own question: never from the cache (it would prove nothing on six nights in seven)
    for _ in range(2):
        final = events(c.post("/api/ask", json={"question": BINS}, headers=with_token))[-1]
        assert final["type"] == "final" and not final.get("cached")
    assert len(fake.calls) == 3
    assert [r["kind"] for r in record(site)] == ["reader", "check", "check"]

    clock.advance(minutes=5)
    answer = c.get("/api/check", headers=with_token)
    assert answer.status_code == 200
    body = answer.json()
    assert set(body) == {"site", "at", "versions", "waiting", "backups", "figures"} and body["site"] == "councils"
    assert body["waiting"] == {"reports": 1, "statements": 0, "hidden": 0, "oldest_working_days": 0}
    assert set(body["backups"]) == {"newest_hours", "offsite_hours", "offsite_ok"}
    assert body["figures"]["briefings"] == 1 and body["figures"]["checks"] == 2 and body["figures"]["errors"] == 0
    assert "bin collections" not in answer.text and "reader@example.org" not in answer.text
    assert "the-family-token" not in answer.text
