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
