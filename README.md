# Where Councils Stand

[![CI](https://github.com/rj-mitchell/wherecouncilsstand/actions/workflows/ci.yml/badge.svg)](https://github.com/rj-mitchell/wherecouncilsstand/actions/workflows/ci.yml)

Where Councils Stand publishes sourced briefings on what councils across the UK have discussed, decided and voted
on, drawn from the minutes they publish for full council and cabinet. Readers can ask a question and get a short,
balanced briefing in which every point cites the council's own record, or look up a council and see its named votes
with each councillor's party on the date. It is a project of Where They Stand, which is applying to register as a
charity in England and Wales ([wheretheystand.uk](https://wheretheystand.uk)).

Live site: [wherecouncilsstand.com](https://wherecouncilsstand.com). It is a public alpha: still being built and
tested, and it says so on every page. The main piece of work before the beta is a test set of checked votes
([decision 15](docs/DECISIONS.md#15-vote-accuracy-in-the-alpha)).

Where Councils Stand is independent. It is not affiliated with or endorsed by any council, the Local Government
Association, Civica or Northgate.

## Features

- Lists every principal council in the UK and England's 20 strategic authorities, and reads the meetings of those
  whose minutes are published through Modern.gov, CMIS or CoINS, or (for four strategic authorities) on their own
  websites. Coverage starts in May 2018, and the data is brought up to date every night.
- Reads attendance with each member's party on the date, named votes and declarations of interest from the minutes.
  Names of people who aren't councillors are removed before anything is indexed or shown.
- Answers questions with streamed briefings written by an AI model from the minutes found, with every citation and
  quotation checked against the source. Evidence is drawn in turn from councils under each party's control.
- Gives every council, strategic authority and named vote its own page, readable without JavaScript.
- Offers a corrections route, a right of reply for councillors and councils, and a public corrections log.

Known limitations are listed on the site's [methodology page](https://wherecouncilsstand.com/methodology). The main
ones are that minutes are summaries written by council officers, and that about 1 named vote in 100 has a
councillor on the wrong side ([`docs/PILOT.md`](docs/PILOT.md)).

## How it works

The council registry (`data_static/councils.csv`) is built from MHCLG's local-authority register, MapIt and Local
Democracy UK. Readers for each kind of meetings site (`src/councils/sources/`) fetch each council's meetings
politely, one request at a time and at least a second apart, and cache every response. The minutes are parsed into
meetings, attendance, named votes and declarations (`src/councils/parse/`), stored as Parquet and queried with
DuckDB, then split into passages for a LanceDB index with keyword and vector search.

A question is read into filters (by built-in rules or the model), the evidence is retrieved and balanced across
councils and party control (`src/councils/rank/`), and the model writes a briefing from that evidence only
(`src/councils/rag/`). `councils serve` runs the web service (FastAPI) and serves the front end (React and Vite, in
`web/`). Much of the shared machinery (the state database, limits, the answer cache, the checks on briefings, the
model client and the index store) comes from [wts-core](https://github.com/rj-mitchell/wts-core), the package the
Where They Stand sites share.

## Quick start

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), and Node 22 for the front end.

To run the website on a small made-up record of three councils and a strategic authority:

```bash
uv sync
cd web && npm ci && npm run build && cd ..
uv run python scripts/fixture_site.py /tmp/councils-fixture
COUNCILS_DATA_DIR=/tmp/councils-fixture uv run councils serve    # http://127.0.0.1:8000
```

To load real data (written to `data/`):

```bash
uv run councils list --status ok          # councils whose meetings site answers
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

## Documentation

[`docs/README.md`](docs/README.md) lists every document and who it is for. The main ones:

- [`docs/DECISIONS.md`](docs/DECISIONS.md): the product decisions, which take precedence over everything else.
- [`docs/DATA.md`](docs/DATA.md): data sources, and how each kind of meetings site is read.
- [`docs/DEPLOY.md`](docs/DEPLOY.md) and [`docs/OPERATIONS.md`](docs/OPERATIONS.md): installing and running the site
  on the charity's server.
- [`CONTRIBUTING.md`](CONTRIBUTING.md): tests, checks and style for contributors.

## The Where They Stand family

Where Councils Stand shares its design, footer shelf and favicon with its sister sites through the family kit,
copied into `web/public/family` from the charity's repository and not edited here; `tests/test_family.py` checks
the copy against the hash in its `VERSION` file. To update it, from a checkout of the charity's repository beside
this one:

```bash
node family/kit/sync.mjs --site councils --out ../wherecouncilsstand/web/public/family
node family/kit/sync.mjs --site councils --out ../wherecouncilsstand/web/public/family --check
```

Council pages link to Where Landlords Stand (`data_static/landlords_links.csv`, built by
`scripts/landlords_links.py`) and to the MPs whose seats overlap them on Where MPs Stand
(`data_static/council_constituencies.csv` and `data_static/mps.json`, built by `scripts/mp_links.py`, with the list
of MPs refreshed by the nightly update; decision 31), and each written briefing offers the same question on Where MPs
Stand.

## Data sources and licences

- Council registry: MHCLG's local-authority register (Open Government Licence), mySociety's MapIt, and Local
  Democracy UK (CC BY 4.0).
- Meetings, minutes, attendance and votes: each council's own meetings site. Minutes remain each council's
  copyright and are shown only as cited extracts linking to the council's record
  ([decision 10](docs/DECISIONS.md#10-reuse)).
- Party labels: Open Council Data's lists of councillors (public domain), used to interpret councils' own codes.
- Westminster constituencies overlapping each council: the ONS's "Ward to Westminster Parliamentary Constituency to
  Local Authority District to Upper Tier Local Authority (July 2024) Lookup in the UK". Source: Office for National
  Statistics licensed under the Open Government Licence v.3.0. The ONS asks lookups to carry that statement only (no
  Ordnance Survey notice).
- Each constituency's MP: Where MPs Stand's public list of current members.

Text written by the site, including briefings, and the data it publishes are licensed under CC BY 4.0 (see the
site's terms page). The name and mark are not covered by these licences.

## Licence

The code is licensed under the GNU Affero General Public License v3.0 only ([LICENSE](LICENSE)).
