# Where Councils Stand

**Sourced briefings on what councils in England and Wales have discussed, decided and voted on.**

Where Councils Stand applies the approach of [Where They Stand](https://wheretheystand.uk) to local government. It
reads the minutes councils already publish for full council and cabinet meetings, and will offer short, balanced
briefings in which every point cites the council's own record, with each councillor's party on the date. If the
record holds nothing relevant, it will say "No records found."

It is a project of the Where They Stand Foundation, a charitable incorporated organisation being registered in England
and Wales. The code is adapted from Where Countries Stand and Where They Stand (same licence, same author).

> Where Councils Stand is independent. It is not affiliated with or endorsed by any council, the Local Government
> Association or Civica.

## Status

Pilot stage. The data layer works on the real record:

- the registry of all 340 principal councils in England and Wales, and which publish through Modern.gov;
- loading full council and cabinet meetings from May 2018: minutes, attendance and party on the date;
- reading named votes and declarations of interest from the minutes.

It has been run on 20 councils chosen by a fixed rule. The results are in [`docs/PILOT.md`](docs/PILOT.md). There's no
search index, briefing engine or website yet: those come next, adapted from Where Countries Stand.

| File | What it is |
|---|---|
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Product decisions made so far. They override everything else. |
| [`docs/DATA.md`](docs/DATA.md) | Data sources, what the Modern.gov web service returns, and what was found in it |
| [`docs/PILOT.md`](docs/PILOT.md) | The 20-council pilot: how the councils were chosen, and what was measured |

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
uv run councils report                    # the pilot's measurements
uv run pytest
```

Data is written to `data/` (raw responses and Parquet). `scripts/build_councils.py` rebuilds the council registry.

## Licence

Code: AGPL-3.0, as Where They Stand. Council minutes remain the councils' copyright. See docs/DECISIONS.md, 10.
