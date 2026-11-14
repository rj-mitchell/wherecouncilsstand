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
    assert stored(shared.settings_given(s), tmp) == case["gives"]


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
