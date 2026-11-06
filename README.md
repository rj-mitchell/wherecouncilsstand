# Where Councils Stand

**Sourced briefings on what councils across the UK have discussed, decided and voted on, from their own minutes.**

[wherecouncilsstand.com](https://wherecouncilsstand.com) · Status: Alpha

For journalists and anyone who wants to know what their council has done. Ask a question and get a short, balanced
briefing from the minutes councils publish for full council and cabinet, or look up a council and see its named
votes, with each councillor's party on the date. Every point cites the council's own record; if the record holds
nothing relevant, the site says "No records found."

A Where They Stand project. Where They Stand is applying to register as a charity in England and Wales
([wheretheystand.uk](https://wheretheystand.uk)).

> Where Councils Stand is independent. It is not affiliated with or endorsed by any council, the Local Government
> Association, Civica or Northgate.

## Status

6 November 2026. A public alpha, live at [wherecouncilsstand.com](https://wherecouncilsstand.com) on the charity's
shared server. It is still being built and tested, and says so on every page.

- **The record.** Every principal council in the UK (England, Wales, Scotland and Northern Ireland) is listed, with
  which of them publish through Modern.gov, CMIS or CoINS. Full council and cabinet meetings are loaded from May 2018:
  minutes (including those published only as a document), attendance with each member's party on the date, named
  votes and declarations of interest. Names of people who aren't councillors are removed before anything is indexed
  or shown. On 6 November 2026 the live site held 295 of the 383 councils, with about 43,300 meetings and 8,900 named
  votes. The data is brought up to date every night (`councils update`, [`docs/OPERATIONS.md`](docs/OPERATIONS.md)).
- **The website** (`web/`, served by `councils serve`): questions answered as streamed, sourced briefings, each saved
  at its own address; a page for every council (the party in control over time, members by party, named votes and
  meetings, and links to Where Landlords Stand); a page for every named vote; pages on how it works, corrections and
  takedown requests, accessibility, privacy, terms, press and the site's status.
- **Next:** a test set of checked votes, before the beta (decision 15).

It was first run on 20 councils chosen by a fixed rule; the pilot's results, and the hand checks of the votes, are in
[`docs/PILOT.md`](docs/PILOT.md).

## In the family

Where Councils Stand is one of the Where They Stand projects, with Where MPs Stand, Where Landlords Stand, Where
Countries Stand and Where Lives Stand. The family as a whole (the projects, the shelves, names and wording) is
described in the charity's family overview.

- **Code.** Adapted from Where Countries Stand's and Where MPs Stand's code (same licence). The search index and
  briefing engine came from Where Countries Stand; the web service, limits and visitor privacy from Where MPs Stand.
- **Where it runs.** The charity's shared server in London, beside Where MPs Stand, Where Landlords Stand and Where
  Countries Stand, behind the front door in Where MPs Stand's checkout. Where MPs Stand's `docs/HOSTING.md` is the
  manual for the server; [`docs/DEPLOY.md`](docs/DEPLOY.md) has only this site's own steps.
- **The family binding.** Every page carries "A Where They Stand project" under the site's name, the family shelf in
  the footer, the town-hall mark as the favicon and on the link card, the theme colour in the site's cloth (Buckram
  brown), and Source Serif 4 for headings. They come from the charity's family kit, copied into `web/public/family`
  and committed; don't edit the copies. To update them, and before merging a change to them, run from a checkout of
  the charity's repository:

  ```bash
  node family/kit/sync.mjs --site councils --out ../wherecouncilsstand/web/public/family          # copy the kit in
  node family/kit/sync.mjs --site councils --out ../wherecouncilsstand/web/public/family --check  # is it the latest?
  ```

  CI can't run `--check` (the charity's repository is private), so `tests/test_family.py` checks the copy against
  the hash in its own `VERSION` file instead: an edited or missing file fails the tests.
- **Links to sister sites.**
  - *To Where Landlords Stand:* each council's page links to the council as a landlord (where it owns homes) and to
    the social landlords with homes in its area. Both sites key councils by ONS GSS code. The pages are listed in
    `data_static/landlords_links.csv`, rebuilt by `scripts/landlords_links.py` from that site's published data after
    its weekly update ([`docs/DATA.md`](docs/DATA.md)).
  - *To Where MPs Stand:* under each briefing, "Ask Where MPs Stand the same question" hands the question over in
    its `?q=` parameter.
  - *From Where Landlords Stand:* its council landlords link to their page here, `/councils/{gss}`.
  - *Family links:* the endorsement links to wheretheystand.uk, and the footer shelf to every sister site.

## Documents

| File | What it is |
|---|---|
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Product decisions made by the owner. They override everything else |
| [`docs/DATA.md`](docs/DATA.md) | Data sources, what the councils' web services return, and the links to Where Landlords Stand |
| [`docs/DESIGN.md`](docs/DESIGN.md) | The website's look: the minute book, in the family's binding |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | The nightly update, and running the website: limits, costs, reports |
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | This site's steps on the charity's shared server |
| [`docs/PILOT.md`](docs/PILOT.md) | The 20-council pilot, the full load, and hand checks of the votes |
| [`docs/EVALUATION.md`](docs/EVALUATION.md) | The briefing test set (`eval/questions.toml`) and its results |
| [`outreach/`](outreach/) | Letters asking councils for permission to read their meetings sites |

How the site works, for readers, is on its [How it works](https://wherecouncilsstand.com/methodology) page.

## How it works

```
 MHCLG local-authority register ─┐
 MapIt (Wales) ──────────────────┼─► data_static/councils.csv (scripts/build_councils.py)
 Local Democracy UK + probing ───┘                 │
                                                   ▼
 each council's Modern.gov web service ─► committees in scope (committees.py: council, cabinet, policy)
 (GetCommittees, GetMeetings, GetMeeting)          │
          │ cached, gzipped (data/raw/modgov/)     ▼
          └──────────────────────────────► meetings, agenda items with minutes text, attendance with party
                                                   │  (sources/meeting.py, parse/minutes.py, parse/parties.py)
                                                   ▼
                                           named votes and declarations of interest (parse/votes.py,
                                           parse/declarations.py), matched to members
                                                   │
                                                   ▼
                                           Parquet (zstd, one file per table and council) ─► DuckDB
                                                   │
                                                   ▼
                          names of non-councillors removed (parse/redact.py), passages of ~250 words, each tagged
                          with council, region, kind of meeting, party in control on the date (reference/people.py)
                          and the parties of the councillors it names ─► LanceDB: BM25 + vectors (local model)
                                                   │
 question ─► filter plan (offline rules, or Claude) ─► deterministic retrieval, ranking, balance across councils
                                                   │                  and party control (rank/evidence.py)
                                                   ▼
                     Claude answers ONLY from the minutes, with search-result citations
                                                   ▼
                     verification: citations re-checked, quotations checked, loaded words flagged
```

* **Committees.** Only full council and the cabinet are loaded, or for councils run by committees, their main
  policy committees (docs/DECISIONS.md, 3).
* **Party on the date.** Each meeting's attendance records the party each member had at the time. Councils' labels
  ("LAB", "Labour", "Labour & Co-operative") are mapped to one code per party. Named local groups count as local
  parties, not "Independent".
* **Named votes.** Minutes give a recorded vote as a heading for each side ("In favour of the Motion:", "Against:",
  "Abstentions:") and a list of names. Each name is matched to the members at the meeting, by surname, and by
  initial and surname where two share a surname. "The Mayor" or "The Chair" is the member in that role. A name that
  can't be matched is kept as written.
* **Briefings.** Minutes are officers' summaries, so briefings say what the minutes record and quote only their
  words. Evidence is drawn from councils under each party's control, and under no overall control, in turn; the
  same rules apply to every party (docs/DECISIONS.md, 7 and 12). `ask` needs an Anthropic API key
  (`COUNCILS_ANTHROPIC_API_KEY`, `ANTHROPIC_API_KEY`, or `data/anthropic_api_key`); without one it shows the
  evidence it would use.
* **Politeness.** One request at a time to each council, at least a second apart, with a user agent that names the
  project. Every response is cached.

## Try it

You need [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run councils list --status ok          # councils whose Modern.gov web service answers
uv run councils ingest barnsley           # load one council since May 2018 (about 40 minutes: servers are slow)
uv run councils parse barnsley            # named votes and declarations from its minutes
uv run councils pilot                     # load and parse the 20 pilot councils
uv run councils load --workers 20         # every council whose web service answers (hours; --resume continues)
uv run councils parties                   # map stored party labels again after data_static/parties.csv changes
uv run councils update                    # the daily update: new and changed meetings, votes, index (docs/OPERATIONS.md)
uv run councils report                    # the pilot's measurements
uv run councils index                     # keyword index of everything loaded
uv sync --extra embed && uv run councils embed --max-minutes 30   # meaning search (local model; resumable)
uv run councils search "bin collections" --control NOC
uv run councils ask "What have Labour-run councils decided about bin collections since 2023?"
uv run councils evaluate                  # score question reading and evidence against eval/questions.toml (free)
uv run pytest
cd web && npm ci && npm test && npm run build && cd ..
uv run councils serve                     # the website, at http://127.0.0.1:8000
```

To run the website without the real data, on a small made-up record of three councils:

```bash
uv run python scripts/fixture_site.py /tmp/councils-fixture
COUNCILS_DATA_DIR=/tmp/councils-fixture uv run councils serve
```

CI runs ruff, the Python tests, the web tests and build, and an accessibility check (`scripts/a11y.mjs`: axe in
Chromium over the built site on that made-up record, failing on any serious or critical problem).

Data is written to `data/` (raw responses and Parquet). `scripts/build_councils.py` rebuilds the council registry.

## Known limitations

- **Vote accuracy.** About 1 named vote in 100 has a councillor on the wrong side (three hand-checked samples of 100,
  [`docs/PILOT.md`](docs/PILOT.md)). This is accepted for the alpha (decision 15) and said on the How it works page.
- **Coverage.** Councils whose minutes aren't published through Modern.gov, CMIS or CoINS, and those whose sites
  refuse the crawler or forbid it in robots.txt, are left out, with the reason shown. Councils were asked for
  permission ([`outreach/`](outreach/)).
- **Minutes are summaries** written by council officers, not word-for-word records, and briefings are written by AI:
  they are checked automatically against the minutes, and can still be wrong.
- **JavaScript.** Asking a question needs it. The home page, the list of councils, council pages and vote pages
  are sent with a readable copy of their content (`api/plaintext.py`), with their own title, canonical link and
  structured data, for readers with scripts off and search engines; `/sitemap.xml` lists every council and vote.
  Saved briefings (`/b/…`) still need JavaScript.
- **Accessibility** is checked with axe-core in CI, and has been checked with the keyboard and a reflow check, but
  not yet by people who use assistive technology (the site's Accessibility page).

## Licence

Code: AGPL-3.0 ([LICENSE](LICENSE)). Text written by the site, including briefings, and the data it publishes: CC BY
4.0 (the site's Terms page). Data: each publisher's terms; councils' minutes remain each council's copyright and are
shown only as cited extracts (decision 10). The name and mark are not covered.
