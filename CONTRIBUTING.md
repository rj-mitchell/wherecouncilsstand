# Contributing

How to contribute to Where Councils Stand: setting up, the checks to run, and the project's style. Bug reports,
corrections to council data and pull requests are welcome. For a correction to something shown on the live site,
the site's [corrections page](https://wherecouncilsstand.com/corrections) is usually the quickest route.

## Setting up

Follow the README's [quick start](README.md#quick-start) to install the dependencies and run the site on a small
made-up record.

## Tests and checks

Run these before opening a pull request:

```bash
uv run ruff check
uv run pytest
cd web && npm run typecheck && npm test && npm run build
```

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs the same checks, builds the Docker image, and runs
an axe accessibility check (`scripts/a11y.mjs`) over the built site on the made-up record.

Add or update tests with any change in behaviour. The tests in `tests/test_parity.py` compare the site with
recorded output in `tests/golden/`; a deliberate change to that output should be asserted in the test, with the
reason. A change to how questions are read or evidence is chosen should be scored against the briefing test set
([`docs/EVALUATION.md`](docs/EVALUATION.md)).

## Style

- Python is checked with ruff, configured in `pyproject.toml`; TypeScript with `tsc` in strict mode.
- Write in plain British English, in sentence case. Wording seen by readers follows the Where They Stand family
  glossary (`family/GLOSSARY.md` in the charity's repository) and is kept the same across the sister sites.
- Product decisions are recorded in [`docs/DECISIONS.md`](docs/DECISIONS.md). A change that goes against one needs
  the decision updated first.
- Don't edit the family kit in `web/public/family`; update it with the kit's sync script (README, "The Where They
  Stand family").

## Commits and pull requests

Write commit messages as plain sentences that say what changed, with a short body explaining why when it isn't
obvious. Keep each pull request to one change.

## Licence

By contributing, contributors agree that their contributions are licensed under the GNU Affero General Public
License v3.0 ([LICENSE](LICENSE)).
