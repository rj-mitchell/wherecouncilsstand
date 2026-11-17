# Where Councils Stand

[![CI](https://github.com/rj-mitchell/wherecouncilsstand/actions/workflows/ci.yml/badge.svg)](https://github.com/rj-mitchell/wherecouncilsstand/actions/workflows/ci.yml)

Where Councils Stand publishes sourced briefings on what councils across the UK have discussed, decided and voted
on, drawn from the minutes they publish for full council and cabinet. Readers can ask a question and get a short,
balanced briefing in which every point cites the council's own record, or look up a council and see its named votes
with each councillor's party on the date. It is a Where They Stand project; Where They Stand is applying to register
as a charity in England and Wales ([wheretheystand.uk](https://wheretheystand.uk)).

Live site: [wherecouncilsstand.com](https://wherecouncilsstand.com)

Where Councils Stand is independent. It is not affiliated with or endorsed by any council, the Local Government
Association, Civica or Northgate.

## Status

Public alpha. The site is still being built and tested, and says so on every page. A test set of checked votes is
the main piece of work before the beta (decision 15 in [`docs/DECISIONS.md`](docs/DECISIONS.md)).

## Features

- Lists every principal council in the UK and England's 20 strategic authorities, and loads the meetings of those
  whose minutes are published through Modern.gov, CMIS or CoINS, or (for four strategic authorities) on their own
  websites. Coverage starts in May 2018.
- Reads attendance with each member's party on the date, named votes and declarations of interest from the minutes.
  Names of people who aren't councillors are removed before anything is indexed or shown.
- Answers questions with streamed briefings written by an AI model from the minutes found, with every citation and
  quotation checked against the source. Evidence is drawn in turn from councils under each party's control.
- Gives every council, strategic authority and named vote its own page, readable without JavaScript.
- Offers a corrections route, a right of reply for councillors and councils, and a public corrections log.

The data is brought up to date every night. Known limitations are listed on the site's
[methodology page](https://wherecouncilsstand.com/methodology); the main ones are that about 1 named vote in 100 has
a councillor on the wrong side ([`docs/PILOT.md`](docs/PILOT.md)), and that minutes are summaries written by
council officers.

## Architecture

The council registry (`data_static/councils.csv`) is built from MHCLG's local-authority register, MapIt and Local
Democracy UK. Readers for Modern.gov, CMIS, CoINS and the authorities' own sites (`src/councils/sources/`) fetch
each council's meetings politely, one request at a time and at least a second apart, and cache every response. The
minutes are parsed into meetings, attendance, named votes and declarations (`src/councils/parse/`), stored as
Parquet and queried with DuckDB, then split into passages for a LanceDB index with keyword and vector search.

A question is read into filters (by built-in rules or the model), the evidence is retrieved and balanced across
councils and party control (`src/councils/rank/`), and the model writes a briefing from that evidence only
(`src/councils/rag/`). The web service (FastAPI) and the front end (React and Vite, in `web/`) are served by
`councils serve`. Much of the shared machinery (state database, limits, answer cache, checks on briefings, model
client, index store) comes from [wts-core](https://github.com/rj-mitchell/wts-core), the Where They Stand sites'
shared package.

More detail:

| Document | Contents |
|---|---|
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Product decisions; these take precedence over the other documents |
| [`docs/DATA.md`](docs/DATA.md) | Data sources, the councils' meetings systems and the links to Where Landlords Stand |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | The nightly update, running the website, reports and statements, the state database |
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | Deployment on the charity's shared server |
| [`docs/DESIGN.md`](docs/DESIGN.md) | The site's design, based on the Where They Stand family kit |
| [`docs/EVALUATION.md`](docs/EVALUATION.md) | The briefing test set and how to score changes against it |
| [`docs/PILOT.md`](docs/PILOT.md) | The 20-council pilot, the full load and hand checks of the votes |
| [`docs/research/strategic-authorities.md`](docs/research/strategic-authorities.md) | Research note on England's strategic authorities |
| [`outreach/`](outreach/) | Letters asking councils for permission to read their meetings sites |

## Running it locally

You need Python 3.12 with [uv](https://docs.astral.sh/uv/), and Node 22 for the front end.

To run the website on a small made-up record of three councils:

```bash
uv sync
cd web && npm ci && npm run build && cd ..
uv run python scripts/fixture_site.py /tmp/councils-fixture
COUNCILS_DATA_DIR=/tmp/councils-fixture uv run councils serve    # http://127.0.0.1:8000
```

To load real data (written to `data/`):

```bash
uv run councils list --status ok          # councils whose Modern.gov web service answers
uv run councils ingest barnsley           # one council's meetings since May 2018
uv run councils parse barnsley            # its named votes and declarations
uv run councils index                     # keyword index of everything loaded
uv run councils embed --max-minutes 30    # vector search (local model; resumable)
uv run councils search "bin collections" --control NOC
uv run councils ask "What have Labour-run councils decided about bin collections since 2023?"
```

`councils --help` lists every command. Written briefings need an Anthropic API key in `COUNCILS_ANTHROPIC_API_KEY`
(or `ANTHROPIC_API_KEY`, or the file `data/anthropic_api_key`); without one, `ask` and the site show the evidence
only. Settings are in `config/settings.toml`.

## Testing

```bash
uv run ruff check
uv run pytest
cd web && npm run typecheck && npm test && npm run build
```

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs these, builds the Docker image, and runs an axe
accessibility check (`scripts/a11y.mjs`) over the built site on the made-up record. `uv run councils evaluate`
scores question reading and evidence against `eval/questions.toml` ([`docs/EVALUATION.md`](docs/EVALUATION.md)).

## Deployment

The site runs in Docker on the charity's shared server, updated with `deploy/update.sh` and kept current by systemd
timers. See [`docs/DEPLOY.md`](docs/DEPLOY.md) and [`docs/OPERATIONS.md`](docs/OPERATIONS.md).

## The Where They Stand family

Where Councils Stand shares its design, footer shelf and favicon with its sister sites through the family kit,
copied into `web/public/family` from the charity's repository and not edited here; `tests/test_family.py` checks
the copy against the hash in its `VERSION` file. To update it, from a checkout of the charity's repository:

```bash
node family/kit/sync.mjs --site councils --out ../wherecouncilsstand/web/public/family
node family/kit/sync.mjs --site councils --out ../wherecouncilsstand/web/public/family --check
```

Council pages link to Where Landlords Stand (`data_static/landlords_links.csv`, built by
`scripts/landlords_links.py`), and each briefing links to the same question on Where MPs Stand.

## Data sources and licences

- Council registry: MHCLG's local-authority register (Open Government Licence), mySociety's MapIt, and Local
  Democracy UK (CC BY 4.0).
- Meetings, minutes, attendance and votes: each council's own meetings site. Minutes remain each council's
  copyright and are shown only as cited extracts linking to the council's record (decision 10).
- Party labels: Open Council Data's lists of councillors (public domain), used to interpret councils' own codes.

Text written by the site, including briefings, and the data it publishes are licensed under CC BY 4.0 (see the
site's terms page). The name and mark are not covered by these licences.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Licence

The code is licensed under the GNU Affero General Public License v3.0 only ([LICENSE](LICENSE)).
