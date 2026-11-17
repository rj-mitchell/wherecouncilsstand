# Contributing

Thank you for your interest in Where Councils Stand. Bug reports, corrections to council data and pull requests are
welcome. For a correction to something shown on the live site, the site's
[corrections page](https://wherecouncilsstand.com/corrections) is usually the quickest route.

## Setting up

You need Python 3.12 with [uv](https://docs.astral.sh/uv/), and Node 22.

```bash
uv sync
cd web && npm ci && npm run build && cd ..
uv run python scripts/fixture_site.py /tmp/councils-fixture
COUNCILS_DATA_DIR=/tmp/councils-fixture uv run councils serve
```

This serves the site at http://127.0.0.1:8000 on a small made-up record. The README explains how to load real
data.

## Tests and checks

Run these before opening a pull request; CI runs the same:

```bash
uv run ruff check
uv run pytest
cd web && npm run typecheck && npm test && npm run build
```

Add or update tests with any change in behaviour. The tests in `tests/test_parity.py` compare the site with
recorded output in `tests/golden/`; a deliberate change to that output should be asserted in the test, with the
reason.

## Style

- Python is checked with ruff, configured in `pyproject.toml`; TypeScript with `tsc` in strict mode.
- Write in plain British English, in sentence case. Wording seen by readers follows the Where They Stand family
  glossary (`family/GLOSSARY.md` in the charity's repository) and is kept the same across the sister sites.
- Product decisions are recorded in `docs/DECISIONS.md`. A change that goes against one needs the decision updated
  first.
- Don't edit the family kit in `web/public/family`; update it with the kit's sync script (see the README).

## Commits and pull requests

Write commit messages as plain sentences that say what changed, with a short body explaining why when it isn't
obvious. Keep each pull request to one change.

## Licence

By contributing you agree that your contribution is licensed under the GNU Affero General Public License v3.0
([LICENSE](LICENSE)).
