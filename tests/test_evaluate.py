"""The briefing test set (eval/questions.toml) and `councils evaluate`, on the synthetic store (no model)."""

from datetime import date

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
