# Where Councils Stand

**Sourced briefings on what councils across the UK have discussed, decided and voted on.**

Where Councils Stand applies the approach of [Where MPs Stand](https://wherempsstand.com) to local government. It
reads the minutes councils already publish for full council and cabinet meetings, and will offer short, balanced
briefings in which every point cites the council's own record, with each councillor's party on the date. If the
record holds nothing relevant, it will say "No records found."

It is a project of Where They Stand, which is applying to register as a charity in England and Wales. The code is adapted from Where Countries Stand and Where They Stand (same licence, same author).

> Where Councils Stand is independent. It is not affiliated with or endorsed by any council, the Local Government
> Association or Civica.

## Status

Pilot stage. The data layer works on the real record:

- the registry of every principal council in the UK (England, Wales, Scotland and Northern Ireland), and which publish through Modern.gov;
- loading full council and cabinet meetings from May 2018: minutes, attendance and party on the date;
- minutes published only as a document, where the council serves documents;
- reading named votes and declarations of interest from the minutes;
- removing the names of people who aren't councillors before anything is indexed or shown.

It was first run on 20 councils chosen by a fixed rule. It has since loaded 213 of the 215 councils whose
web service answers. They hold about 30,800 meetings and 7,300 named votes, with each councillor's party on the
date. The results, and a hand check of the votes, are in [`docs/PILOT.md`](docs/PILOT.md).

The search index and briefing engine, adapted from Where Countries Stand, give keyword and meaning search over the
minutes, evidence balanced across councils and party control, and Claude briefings with re-checked citations. The
data is brought up to date every night (`councils update`, [`docs/OPERATIONS.md`](docs/OPERATIONS.md)).

The website (`web/`, served by `councils serve`) has:
- questions answered as streamed, sourced briefings, each saved at its own address;
- a page for every council: the party in control over time, members by party, named votes and meetings;
- a page for every named vote, with each councillor's party on the date;
- pages on how it works, corrections and takedown requests, and privacy.

It isn't deployed yet: [`docs/DEPLOY.md`](docs/DEPLOY.md) puts it on the charity's shared server. Its look is described
in [`docs/DESIGN.md`](docs/DESIGN.md).

| File | What it is |
|---|---|
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Product decisions made so far. They override everything else. |
| [`docs/DATA.md`](docs/DATA.md) | Data sources, what the Modern.gov web service returns, and what was found in it |
| [`docs/OPERATIONS.md`](docs/OPERATIONS.md) | The daily update, and running the website: limits, costs, reports |
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | Putting the site on the charity's shared server: Docker, Cloudflare, the first load |
| [`docs/DESIGN.md`](docs/DESIGN.md) | The website's look: the minute book |
| [`docs/PILOT.md`](docs/PILOT.md) | The 20-council pilot, the full load, and hand checks of the votes |

## How it works

```
 MHCLG local-authority register ─┐
 MapIt (Wales) ──────────────────┼─► data_static/councils.csv (scripts/build_councils.py)
 Local Democracy UK + probing ───┘                 │
                                                   ▼
 each council's Modern.gov web service ─► committees in scope (committees.py: council, cabinet, policy)
 (GetCommittees, GetMeetings, GetMeeting)          │
          │ cached raw XML (data/raw/modgov/)      ▼
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
uv run pytest
cd web && npm ci && npm run build && npm test && cd ..
uv run councils serve                     # the website, at http://127.0.0.1:8000
```

Data is written to `data/` (raw responses and Parquet). `scripts/build_councils.py` rebuilds the council registry.

## Licence

Code: AGPL-3.0, as Where They Stand. Council minutes remain the councils' copyright. See docs/DECISIONS.md, 10.
