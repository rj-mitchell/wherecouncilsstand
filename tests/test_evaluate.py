"""The briefing test set (eval/questions.toml) and `councils evaluate`, on the synthetic store (no model)."""

from dataclasses import replace
from datetime import date

import pytest
from test_pipeline import BARNSLEY, settings  # noqa: F401 - the fixture

from councils import evaluate as ev
from councils.rag.query_parse import parse_offline
from councils.registry import councils

KNOWN = {*ev.FIELDS, *(f"{k}_any" for k in ev.FIELDS)}


def test_the_test_set_is_well_formed():
    today, qs = ev.load_questions()
    assert today == date(2026, 11, 6) and 20 <= len(qs) <= 40
    assert len({q["id"] for q in qs}) == len(qs)
    for q in qs:
        assert set(q.get("expect", {})) <= KNOWN, q["id"]
        for gss in q.get("expect", {}).get("councils", []) + q.get("include", []):
            assert gss in councils(), (q["id"], gss)
    assert {q["category"] for q in qs} >= {"topic", "dates", "nation", "party", "council", "type"}
    assert any(q.get("no_records") for q in qs) and any(q.get("include") for q in qs)


def test_compare_reads_defaults_years_and_alternatives():
    today = date(2026, 11, 6)
    plan = parse_offline("What have Labour-run councils decided about council housing?", today)
    ok, got = ev.compare(plan, {"date_from": "default", "control": ["LAB"]}, today, 4, date(2018, 5, 1))
    assert all(ok.values()) and got["date_from"] == 2022
    ok, _ = ev.compare(plan, {"date_from": "default"}, today, 4, date(2018, 5, 1))
    assert not ok["control"]
    ok, _ = ev.compare(plan, {"date_from": "default", "control_any": [[], ["LAB"]]}, today, 4, date(2018, 5, 1))
    assert ok["control"]


def test_evaluate_scores_questions_and_evidence(settings, tmp_path):  # noqa: F811
    path = tmp_path / "q.toml"
    path.write_text('today = "2026-11-06"\n'
                    '[[q]]\nid = "barnsley-bins"\nquestion = "What has Barnsley decided about bin collections?"\n'
                    f'category = "council"\nexpect = {{ date_from = "default", councils = ["{BARNSLEY}"] }}\n'
                    f'include = ["{BARNSLEY}"]\n'
                    '[[q]]\nid = "old"\nquestion = "What did councils decide about bin collections in 2012?"\n'
                    'category = "dates"\nexpect = { date_from = "2012", date_to = "2012" }\nno_records = true\n')
    results = ev.run(settings, path=path)
    assert [(r.id, r.plan_ok, r.evidence_ok) for r in results] == [("barnsley-bins", True, True), ("old", True, True)]
    s = ev.summary(results)
    assert s["plans_right"] == 2 and s["evidence_right"] == 2
    saved = ev.save(results, False, tmp_path / "runs")
    assert saved.exists() and '"plans_right": 2' in saved.read_text()


# ---- with each briefing written: the shared package's harness (`councils eval`) -------------------------------------

QUESTIONS = '''today = "2026-10-24"

[[q]]
id = "bins"
question = "What have councils decided about bin collections?"
category = "topic"
expect = { date_from = "default" }
include = ["E08000038"]

[[q]]
id = "moon"
question = "What have councils decided about zebra crossings on the moon in 1999?"
category = "dates"
no_records = true
expect = { date_from = "1999", date_to = "1999" }
'''


def harness(settings, tmp_path, fake=None):  # noqa: F811
    """The site as the harness sees it, on the made-up record with a stand-in for the model, and two questions."""
    from test_pipeline import TODAY, FakeClient, as_model
    from wts_core.adapters.hashing import HashingEmbedder

    from councils.engine import Engine
    from councils.rag.pipeline import Pipeline

    path = tmp_path / "questions.toml"
    path.write_text(QUESTIONS)
    fake = fake or FakeClient()
    pipeline = Pipeline(settings, Engine(settings, HashingEmbedder(64), TODAY), model=as_model(fake), today=TODAY)
    return ev.CouncilsEval(settings, pipeline, path), fake


def test_a_run_writes_each_briefing_scores_it_and_its_fixtures_replay_the_same(settings, tmp_path):  # noqa: F811
    from wts_core import eval as harnessed
    from wts_core.usage import PriceTable

    from councils.rag.checks import LOADED_WORDS, VERIFIER
    from councils.rag.pipeline import configuration

    site, fake = harness(settings, tmp_path)
    config = configuration(settings)
    prices = PriceTable.from_settings(settings.usage, file=settings.config_path)
    made = harnessed.run(site, config.settings, config_id=config.config_id, pricing=prices,
                         record_fixtures=tmp_path / "fixtures", max_cost_usd=1.0)
    bins, moon = made.results
    assert (bins.outcome, moon.outcome) == ("completed", "no_records") and len(fake.calls) == 1
    # what the checks found, as a reader's briefing would be checked: the stand-in cites once, then adds a
    # sentence with a loaded word and no citation
    assert (bins.citations_total, bins.citations_invalid, bins.unsupported, bins.loaded_words) == (1, 0, 1, 1)
    assert bins.cost_usd == 0.004 and moon.cost_usd == 0            # priced as the site prices a briefing
    assert bins.spread == {"Councils controlled by Labour": 1, "Councils controlled by the Liberal Democrats": 1}
    # the site's own two scores beside them: every filter the question was read into, and the evidence
    assert set(bins.expect_met) == {*ev.FIELDS, "include"} and all(bins.expect_met.values())
    assert moon.expect_met["no_records"] is True and moon.expect_met["date_from"] is True
    # held to the thresholds in the settings: the stand-in's briefing breaks none of them
    thresholds = settings.section("eval")["thresholds"]
    assert harnessed.check_thresholds(made, thresholds) == []
    assert harnessed.check_thresholds(made, {**thresholds, "max_loaded_words": 0}) != []

    # the briefing was kept as a fixture: what the model was given and what it wrote, with the checks' report.
    # Run over it again, the checks say exactly what they said (and CI's guard, never weaker, holds)
    fixture = harnessed.load_fixture(tmp_path / "fixtures" / "bins.jsonl")
    assert bins.fixture and len(fixture.documents) == 2 and fixture.report["citations_total"] == 1
    assert fixture.headings == tuple(card["heading"] for card in
                                     [e for e in site.pipeline.run(ev.AskRequest(question=bins.question))
                                      if e["type"] == "sources"][0]["sources"])
    differences = harnessed.replay([fixture], VERIFIER, LOADED_WORDS)
    assert differences == []
    harnessed.assert_never_weaker(differences)
    # and a check that has weakened is caught: with no words on the list, the loaded word is no longer flagged
    import re

    from wts_core.checks import LoadedWords

    weaker = harnessed.replay([fixture], VERIFIER, LoadedWords(re.compile(r"\bno such word\b")))
    assert any(d.kind == "weaker" for d in weaker)
    with pytest.raises(AssertionError):
        harnessed.assert_never_weaker(weaker)


def test_the_evaluation_and_the_record_of_briefings_give_a_configuration_the_same_id(settings):  # noqa: F811
    from councils.api.app import create_app
    from councils.rag.pipeline import configuration

    app = create_app(settings)
    with app.state.councils.db.connect() as con:
        (kept,) = [r[0] for r in con.execute("SELECT config_id FROM wts_configs")]
    assert configuration(settings).config_id == kept
    other = replace(settings, raw={**settings.raw, "ranking": {**settings.raw["ranking"], "max_per_council": 3}})
    assert configuration(other).config_id != kept                   # any setting that could change a briefing


def test_the_eval_commands_keep_to_the_limit_and_replay_for_free(settings, tmp_path, monkeypatch):  # noqa: F811
    from typer.testing import CliRunner

    from councils import cli

    site, fake = harness(settings, tmp_path)
    monkeypatch.setattr(cli, "_eval_site", lambda: site)
    monkeypatch.setenv("COUNCILS_DATA_DIR", str(settings.data_dir))
    run = CliRunner().invoke
    # a limit of nothing: no question is asked, nothing is spent, and the run does not pass
    none = run(cli.app, ["eval", "run", "--max-cost", "0", "--out", str(tmp_path / "runs")])
    assert none.exit_code == 1 and "2 questions not asked" in none.output and fake.calls == []
    # the settings' own limit: both asked, the run saved, held to [eval.thresholds] and noted as a pass
    whole = run(cli.app, ["eval", "run", "--out", str(tmp_path / "runs"),
                          "--record-fixtures", str(tmp_path / "fixtures")])
    assert whole.exit_code == 0, whole.output
    assert "Passed: every threshold met" in whole.output and len(fake.calls) == 1
    assert (tmp_path / "runs" / "passed.jsonl").exists()
    again = run(cli.app, ["eval", "replay", str(tmp_path / "fixtures")])
    assert again.exit_code == 0 and "exactly what they said when each was recorded" in again.output
    assert len(fake.calls) == 1                                     # the replay asked no model


def test_the_note_of_a_passing_run_is_the_one_file_under_eval_runs_that_git_keeps():
    import subprocess

    root = ev.REPO_ROOT

    def ignored(path: str) -> bool:
        return subprocess.run(["git", "check-ignore", "-q", path], cwd=root, check=False).returncode == 0

    assert ignored("eval/runs/20261106T120000.json") and not ignored("eval/runs/passed.jsonl")
